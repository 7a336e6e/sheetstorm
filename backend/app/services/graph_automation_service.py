"""Graph Automation Service — handles attack graph auto-generation and event processing."""
import math
from app import db
from app.models import TimelineEvent, AttackGraphNode, AttackGraphEdge, CompromisedHost, CompromisedAccount
from app.models.attack_graph import AttackGraphNode, AttackGraphEdge
from app.models.ioc import NetworkIndicator, HostBasedIndicator, MalwareTool


class GraphAutomationService:
    """Service that encapsulates all attack-graph auto-generation logic."""

    # --- Full auto-generation entry point ---

    @staticmethod
    def auto_generate(incident, user_id):
        """
        Auto-generate a complete attack graph from incident data.

        Algorithm:
        1. Clear existing graph
        2. Create host nodes positioned in a grid
        3. Create sub-nodes (accounts, malware, host indicators) around each host
        4. Create network IOC nodes with deduplication
        5. Create lateral movement edges from timeline events

        Returns:
            tuple: (nodes_created, edges_created) lists
        """
        # Clear existing graph
        AttackGraphEdge.query.filter_by(incident_id=incident.id).delete()
        AttackGraphNode.query.filter_by(incident_id=incident.id).delete()
        db.session.commit()

        hosts = CompromisedHost.query.filter_by(incident_id=incident.id) \
            .order_by(CompromisedHost.first_seen.asc().nullslast()).all()

        if not hosts:
            return [], []

        # Prefetch all associated data
        all_accounts = CompromisedAccount.query.filter_by(incident_id=incident.id).all()
        all_malware = MalwareTool.query.filter_by(incident_id=incident.id).all()
        all_host_indicators = HostBasedIndicator.query.filter_by(incident_id=incident.id).all()

        # Build lookup maps
        hostname_to_id = {h.hostname.lower(): str(h.id) for h in hosts if h.hostname}
        ip_to_host_id = {}
        for h in hosts:
            if h.ip_address:
                ip_to_host_id[str(h.ip_address).lower()] = str(h.id)

        # Group data by host
        host_accounts = GraphAutomationService._group_by_host(
            all_accounts, hostname_to_id, ip_to_host_id, host_attr='host_system'
        )
        host_malware = GraphAutomationService._group_by_host(
            all_malware, hostname_to_id, ip_to_host_id, host_attr='host'
        )
        host_indicators = GraphAutomationService._group_by_host(
            all_host_indicators, hostname_to_id, ip_to_host_id, host_attr='host'
        )

        nodes_created = []
        edges_created = []
        node_map = {}  # host_id -> node

        # Step 1: Create host nodes
        for i, host in enumerate(hosts):
            host_node = GraphAutomationService._create_host_node(
                incident, host, i, user_id
            )
            db.session.add(host_node)
            nodes_created.append(host_node)
            node_map[str(host.id)] = host_node
            db.session.flush()

            # Step 2: Create sub-nodes
            sub_nodes, sub_edges = GraphAutomationService._create_sub_nodes(
                incident, host, host_node, host_accounts, host_malware,
                host_indicators, user_id
            )
            nodes_created.extend(sub_nodes)
            edges_created.extend(sub_edges)

        # Step 3: Create network IOC nodes
        net_nodes, net_edges = GraphAutomationService._create_network_ioc_nodes(
            incident, node_map, hostname_to_id, ip_to_host_id, user_id
        )
        nodes_created.extend(net_nodes)
        edges_created.extend(net_edges)

        # Step 4: Create lateral movement edges
        lat_edges = GraphAutomationService._create_lateral_movement_edges(
            incident, node_map, user_id
        )
        edges_created.extend(lat_edges)

        db.session.commit()
        return nodes_created, edges_created

    # --- Per-event processing ---

    @staticmethod
    def process_event_for_graph(event: TimelineEvent):
        """Analyze a timeline event and update the attack graph accordingly."""
        if not event.host_id:
            return

        target_node = GraphAutomationService._get_or_create_node(
            event.incident_id, event.host_id, event.created_by
        )

        if event.mitre_tactic == 'initial-access':
            target_node.is_initial_access = True

        if event.mitre_tactic == 'impact':
            target_node.is_objective = True

        if event.mitre_tactic == 'lateral-movement' and event.source:
            source_host = CompromisedHost.query.filter_by(
                incident_id=event.incident_id, hostname=event.source
            ).first()
            if not source_host and event.source.replace('.', '').isdigit():
                source_host = CompromisedHost.query.filter_by(
                    incident_id=event.incident_id, ip_address=event.source
                ).first()

            if source_host:
                source_node = GraphAutomationService._get_or_create_node(
                    event.incident_id, source_host.id, event.created_by
                )
                existing = AttackGraphEdge.query.filter_by(
                    incident_id=event.incident_id,
                    source_node_id=source_node.id,
                    target_node_id=target_node.id,
                    edge_type='lateral_movement'
                ).first()
                if not existing:
                    edge = AttackGraphEdge(
                        incident_id=event.incident_id,
                        source_node_id=source_node.id,
                        target_node_id=target_node.id,
                        edge_type='lateral_movement',
                        label=event.mitre_technique or 'Lateral Movement',
                        mitre_tactic='lateral-movement',
                        mitre_technique=event.mitre_technique,
                        timestamp=event.timestamp,
                        description=event.activity,
                        created_by=event.created_by
                    )
                    db.session.add(edge)

        db.session.commit()

    # --- Private helpers ---

    @staticmethod
    def _resolve_host_id(obj_host_id, text_hostname, hostname_to_id, ip_to_host_id):
        """Resolve a host_id from FK or fall back to text hostname matching."""
        if obj_host_id:
            return str(obj_host_id)
        if text_hostname:
            key = text_hostname.strip().lower()
            if key in hostname_to_id:
                return hostname_to_id[key]
            if key in ip_to_host_id:
                return ip_to_host_id[key]
        return None

    @staticmethod
    def _group_by_host(items, hostname_to_id, ip_to_host_id, host_attr='host'):
        """Group items by resolved host_id."""
        grouped = {}
        for item in items:
            hid = GraphAutomationService._resolve_host_id(
                item.host_id, getattr(item, host_attr, None),
                hostname_to_id, ip_to_host_id
            )
            if hid:
                grouped.setdefault(hid, []).append(item)
        return grouped

    @staticmethod
    def _infer_node_type(host):
        """Infer node type from host system_type or hostname."""
        if host.system_type:
            st = host.system_type.lower()
            if 'domain_controller' in st or 'dc' in st:
                return 'domain_controller'
            if 'server' in st:
                return 'server'
        return 'workstation'

    @staticmethod
    def _create_host_node(incident, host, index, user_id):
        """Create a graph node for a compromised host."""
        x = 300 + (index % 4) * 600
        y = 400 + (index // 4) * 500
        return AttackGraphNode(
            incident_id=incident.id,
            node_type=GraphAutomationService._infer_node_type(host),
            label=host.hostname,
            compromised_host_id=host.id,
            position_x=x,
            position_y=y,
            is_initial_access=(index == 0),
            extra_data={
                'containment_status': host.containment_status,
                'ip_address': str(host.ip_address) if host.ip_address else None,
            },
            created_by=user_id
        )

    @staticmethod
    def _create_sub_nodes(incident, host, host_node, host_accounts, host_malware,
                          host_indicators, user_id):
        """Create sub-nodes (accounts, malware, host indicators) around a host node."""
        nodes = []
        edges = []
        sub_elements = []

        # Account nodes
        for acc in host_accounts.get(str(host.id), []):
            label = f"{acc.domain}\\{acc.account_name}" if acc.domain else acc.account_name
            sub_elements.append(AttackGraphNode(
                incident_id=incident.id, node_type='user', label=label,
                compromised_account_id=acc.id,
                extra_data={
                    'account_type': acc.account_type, 'is_privileged': acc.is_privileged,
                    'domain': acc.domain, 'status': acc.status, 'sid': acc.sid,
                    'host_system': host.hostname,
                },
                created_by=user_id
            ))

        # Malware nodes
        for mal in host_malware.get(str(host.id), []):
            sub_elements.append(AttackGraphNode(
                incident_id=incident.id, node_type='malware', label=mal.file_name,
                extra_data={
                    'malware_family': mal.malware_family, 'sha256': mal.sha256,
                    'md5': mal.md5, 'is_tool': mal.is_tool, 'file_path': mal.file_path,
                    'threat_actor': mal.threat_actor, 'host_system': host.hostname,
                },
                created_by=user_id
            ))

        # Host indicator nodes
        for ind in host_indicators.get(str(host.id), []):
            sub_elements.append(AttackGraphNode(
                incident_id=incident.id, node_type='host_indicator',
                label=f"{ind.artifact_type}: {ind.artifact_value[:60]}",
                extra_data={
                    'artifact_type': ind.artifact_type, 'artifact_value': ind.artifact_value,
                    'is_malicious': ind.is_malicious, 'remediated': ind.remediated,
                    'notes': ind.notes, 'host_system': host.hostname,
                },
                created_by=user_id
            ))

        # Position in circle and link
        host_x, host_y = host_node.position_x, host_node.position_y
        for idx, sub in enumerate(sub_elements):
            angle = (idx / max(len(sub_elements), 1)) * 2 * math.pi - (math.pi / 2)
            sub.position_x = host_x + 180 * math.cos(angle)
            sub.position_y = host_y + 180 * math.sin(angle)
            db.session.add(sub)
            nodes.append(sub)
            db.session.flush()

            edge = AttackGraphEdge(
                incident_id=incident.id,
                source_node_id=host_node.id, target_node_id=sub.id,
                edge_type='associated_with', label='Associated',
                created_by=user_id
            )
            db.session.add(edge)
            edges.append(edge)

        return nodes, edges

    @staticmethod
    def _create_network_ioc_nodes(incident, node_map, hostname_to_id, ip_to_host_id, user_id):
        """Create network IOC nodes with deduplication — one node per unique IP, edges to all hosts."""
        all_iocs = NetworkIndicator.query.filter_by(incident_id=incident.id).all()
        ip_to_node = {}
        nodes = []
        edges = []
        x, y = 100, 100

        for ioc in all_iocs:
            target_hid = GraphAutomationService._resolve_host_id(
                ioc.host_id, ioc.source_host, hostname_to_id, ip_to_host_id
            )
            if not target_hid or target_hid not in node_map:
                continue

            ip_or_dns = ioc.dns_ip
            if ip_or_dns in ip_to_node:
                existing_node = ip_to_node[ip_or_dns]
                host_node = node_map[target_hid]
                if not AttackGraphEdge.query.filter_by(
                    source_node_id=host_node.id, target_node_id=existing_node.id,
                    edge_type='associated_with'
                ).first():
                    edge = AttackGraphEdge(
                        incident_id=incident.id,
                        source_node_id=host_node.id, target_node_id=existing_node.id,
                        edge_type='associated_with',
                        label=ioc.direction or 'Network IOC',
                        created_by=user_id
                    )
                    db.session.add(edge)
                    edges.append(edge)
                continue

            ioc_node = AttackGraphNode(
                incident_id=incident.id, node_type='ip_address', label=ip_or_dns,
                position_x=x, position_y=y,
                extra_data={
                    'direction': ioc.direction, 'is_malicious': ioc.is_malicious,
                    'protocol': ioc.protocol, 'port': ioc.port,
                    'description': ioc.description, 'destination_host': ioc.destination_host,
                    'threat_intel_source': ioc.threat_intel_source,
                },
                created_by=user_id
            )
            db.session.add(ioc_node)
            nodes.append(ioc_node)
            db.session.flush()
            ip_to_node[ip_or_dns] = ioc_node

            x += 150
            if x > 1200:
                x = 100
                y += 120

            host_node = node_map[target_hid]
            edge = AttackGraphEdge(
                incident_id=incident.id,
                source_node_id=host_node.id, target_node_id=ioc_node.id,
                edge_type='associated_with',
                label=ioc.direction or 'Network IOC',
                created_by=user_id
            )
            db.session.add(edge)
            edges.append(edge)

        return nodes, edges

    @staticmethod
    def _create_lateral_movement_edges(incident, node_map, user_id):
        """Create lateral movement edges from timeline events."""
        events = TimelineEvent.query.filter_by(incident_id=incident.id) \
            .filter(TimelineEvent.host_id.isnot(None)) \
            .order_by(TimelineEvent.timestamp.asc()).all()

        edges = []
        prev_host_id = None
        for event in events:
            cur_host_id = str(event.host_id)
            if prev_host_id and cur_host_id != prev_host_id:
                src = node_map.get(prev_host_id)
                tgt = node_map.get(cur_host_id)
                if src and tgt:
                    if not AttackGraphEdge.query.filter_by(
                        source_node_id=src.id, target_node_id=tgt.id,
                        edge_type='lateral_movement'
                    ).first():
                        edge = AttackGraphEdge(
                            incident_id=incident.id,
                            source_node_id=src.id, target_node_id=tgt.id,
                            edge_type='lateral_movement',
                            label=event.activity[:50],
                            mitre_tactic=event.mitre_tactic,
                            timestamp=event.timestamp,
                            created_by=user_id
                        )
                        db.session.add(edge)
                        edges.append(edge)
            prev_host_id = cur_host_id

        return edges

    @staticmethod
    def _get_or_create_node(incident_id, host_id, created_by):
        """Get existing graph node for a host or create one."""
        node = AttackGraphNode.query.filter_by(
            incident_id=incident_id,
            compromised_host_id=host_id
        ).first()

        if not node:
            host = CompromisedHost.query.get(host_id)
            if not host:
                return None

            node = AttackGraphNode(
                incident_id=incident_id,
                node_type=GraphAutomationService._infer_node_type(host),
                label=host.hostname,
                compromised_host_id=host_id,
                created_by=created_by,
                position_x=0,
                position_y=0
            )
            db.session.add(node)
            db.session.flush()

        return node
