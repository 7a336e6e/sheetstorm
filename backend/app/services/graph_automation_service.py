"""Graph Automation Service — handles attack graph auto-generation and event processing."""
import math
from app import db
from app.models import TimelineEvent, AttackGraphNode, AttackGraphEdge, CompromisedHost, CompromisedAccount
from app.models.attack_graph import AttackGraphNode, AttackGraphEdge
from app.models.ioc import NetworkIndicator, HostBasedIndicator, MalwareTool


ORIGIN_AUTO = 'auto'
HOST_GRID_COLUMNS = 4
NETWORK_GRID_COLUMNS = 8   # x = 100 .. 1150 in steps of 150


def host_key(host_id):
    return f'host:{host_id}'


def edge_key(edge_type, source_key, target_key):
    return f'{edge_type}:{source_key}->{target_key}'


class GraphAutomationService:
    """Service that encapsulates all attack-graph auto-generation logic."""

    # --- Full auto-generation entry point ---

    @staticmethod
    def auto_generate(incident, user_id, mode='merge'):
        """
        Auto-generate an attack graph from incident data.

        ``mode='merge'`` (default) only ADDS what is missing: existing nodes
        are matched by ``extra_data.auto_key`` (``host:<id>``, ``account:<id>``,
        ``malware:<id>``, ``hioc:<id>``, ``nioc:<value>``), falling back to the
        host / account foreign keys and to type + label for graphs built before
        keys existed. Nodes are never moved or deleted, nodes without
        ``origin='auto'`` are never modified, and only auto nodes get their
        ``label`` / ``extra_data`` refreshed. New nodes are laid out relative to
        their host node's current position.

        ``mode='replace'`` deletes every node and edge first (the endpoint
        demands an explicit confirmation).

        Every node and edge created here carries ``extra_data.origin='auto'``
        and an ``auto_key``.

        Returns:
            tuple: (nodes_created, edges_created) lists
        """
        if mode not in ('merge', 'replace'):
            raise ValueError("mode must be 'merge' or 'replace'")

        if mode == 'replace':
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

        state = _GraphState.load(incident)
        nodes_created = state.nodes_created
        edges_created = state.edges_created
        node_map = {}  # host_id -> node

        # Step 1: host nodes (existing ones are matched, never moved)
        host_slot = state.count_nodes_with_prefix('host:')
        had_hosts = host_slot > 0
        for i, host in enumerate(hosts):
            key = host_key(host.id)
            node = state.find(key)
            fields = GraphAutomationService._host_fields(host)
            if node is None:
                node = AttackGraphNode(
                    incident_id=incident.id, created_by=user_id, compromised_host_id=host.id,
                    position_x=300 + (host_slot % HOST_GRID_COLUMNS) * 600,
                    position_y=400 + (host_slot // HOST_GRID_COLUMNS) * 500,
                    is_initial_access=(i == 0 and not had_hosts),
                    **GraphAutomationService._node_kwargs(key, fields),
                )
                state.add_node(node, key)
                host_slot += 1
            else:
                state.refresh(node, key, fields)
            node_map[str(host.id)] = node

            # Step 2: sub-nodes (accounts, malware, host indicators)
            GraphAutomationService._merge_sub_nodes(
                incident, host, node, state, host_accounts, host_malware, host_indicators, user_id)

        # Step 3: network IOC nodes
        GraphAutomationService._merge_network_ioc_nodes(
            incident, node_map, hostname_to_id, ip_to_host_id, state, user_id)

        # Step 4: lateral movement edges
        GraphAutomationService._merge_lateral_movement_edges(incident, node_map, state, user_id)

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

        # Collect all tactics from mitre_mappings (multi-TTP) or fall back to legacy field
        mappings = event.mitre_mappings or []
        tactics = {m.get('tactic', '') for m in mappings} if mappings else {event.mitre_tactic or ''}
        first_technique = (mappings[0].get('technique', '') if mappings else event.mitre_technique) or ''

        if 'initial-access' in tactics:
            target_node.is_initial_access = True

        if 'impact' in tactics:
            target_node.is_objective = True

        if 'lateral-movement' in tactics and event.source:
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
                        label=first_technique or 'Lateral Movement',
                        mitre_tactic='lateral-movement',
                        mitre_technique=first_technique,
                        timestamp=event.timestamp,
                        description=event.activity,
                        extra_data={'origin': ORIGIN_AUTO, 'auto_key': edge_key(
                            'lateral_movement', host_key(source_host.id), host_key(event.host_id))},
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
    def _host_fields(host):
        return {
            'node_type': GraphAutomationService._infer_node_type(host),
            'label': host.hostname,
            'extra': {
                'containment_status': host.containment_status,
                'ip_address': str(host.ip_address) if host.ip_address else None,
            },
        }

    @staticmethod
    def _node_kwargs(key, fields):
        """Constructor kwargs shared by every auto node (origin + auto_key)."""
        return {
            'node_type': fields['node_type'],
            'label': (fields['label'] or '')[:255],
            'extra_data': {**fields['extra'], 'origin': ORIGIN_AUTO, 'auto_key': key},
        }

    @staticmethod
    def _merge_sub_nodes(incident, host, host_node, state, host_accounts, host_malware,
                         host_indicators, user_id):
        """Accounts, malware and host indicators around ``host_node``: existing
        ones are matched (and linked if the edge is missing), new ones are laid
        out on a circle around the host node's CURRENT position."""
        elements = []  # (key, fields, extra node kwargs, legacy signature)

        for acc in host_accounts.get(str(host.id), []):
            label = f"{acc.domain}\\{acc.account_name}" if acc.domain else acc.account_name
            elements.append((f'account:{acc.id}', {
                'node_type': 'user', 'label': label,
                'extra': {
                    'account_type': acc.account_type, 'is_privileged': acc.is_privileged,
                    'domain': acc.domain, 'status': acc.status, 'sid': acc.sid,
                    'host_system': host.hostname,
                }}, {'compromised_account_id': acc.id}, None))

        for mal in host_malware.get(str(host.id), []):
            elements.append((f'malware:{mal.id}', {
                'node_type': 'malware', 'label': mal.file_name,
                'extra': {
                    'malware_family': mal.malware_family, 'sha256': mal.sha256,
                    'md5': mal.md5, 'is_tool': mal.is_tool, 'file_path': mal.file_path,
                    'threat_actor': mal.threat_actor, 'host_system': host.hostname,
                }}, {}, ('malware', mal.file_name, host.hostname)))

        for ind in host_indicators.get(str(host.id), []):
            label = f"{ind.artifact_type}: {ind.artifact_value[:60]}"
            elements.append((f'hioc:{ind.id}', {
                'node_type': 'host_indicator', 'label': label,
                'extra': {
                    'artifact_type': ind.artifact_type, 'artifact_value': ind.artifact_value,
                    'is_malicious': ind.is_malicious, 'remediated': ind.remediated,
                    'notes': ind.notes, 'host_system': host.hostname,
                }}, {}, ('host_indicator', label, host.hostname)))

        parent_key = host_key(host.id)
        new_items = []
        for key, fields, extra_kwargs, legacy in elements:
            node = state.find(key, legacy)
            if node is None:
                new_items.append((key, fields, extra_kwargs))
                continue
            state.refresh(node, key, fields)
            state.add_edge(host_node, node, 'associated_with', 'Associated',
                           edge_key('associated_with', parent_key, key), user_id)

        existing_children = state.children_of(host_node)
        total = existing_children + len(new_items)
        host_x, host_y = host_node.position_x or 0, host_node.position_y or 0
        for idx, (key, fields, extra_kwargs) in enumerate(new_items):
            angle = ((existing_children + idx) / max(total, 1)) * 2 * math.pi - (math.pi / 2)
            node = AttackGraphNode(
                incident_id=incident.id, created_by=user_id,
                position_x=host_x + 180 * math.cos(angle), position_y=host_y + 180 * math.sin(angle),
                **extra_kwargs, **GraphAutomationService._node_kwargs(key, fields))
            state.add_node(node, key)
            state.add_edge(host_node, node, 'associated_with', 'Associated',
                           edge_key('associated_with', parent_key, key), user_id)

    @staticmethod
    def _merge_network_ioc_nodes(incident, node_map, hostname_to_id, ip_to_host_id, state, user_id):
        """One node per unique IP / domain, edges from every host it touched."""
        refreshed = set()
        for ioc in NetworkIndicator.query.filter_by(incident_id=incident.id).all():
            target_hid = GraphAutomationService._resolve_host_id(
                ioc.host_id, ioc.source_host, hostname_to_id, ip_to_host_id
            )
            if not target_hid or target_hid not in node_map:
                continue

            value = ioc.dns_ip
            key = f"nioc:{(value or '').strip().lower()}"
            fields = {
                'node_type': 'ip_address', 'label': value,
                'extra': {
                    'direction': ioc.direction, 'is_malicious': ioc.is_malicious,
                    'protocol': ioc.protocol, 'port': ioc.port,
                    'description': ioc.description, 'destination_host': ioc.destination_host,
                    'threat_intel_source': ioc.threat_intel_source,
                },
            }
            node = state.find(key, ('ip_address', value, None))
            if node is None:
                slot = state.ip_slot
                node = AttackGraphNode(
                    incident_id=incident.id, created_by=user_id,
                    position_x=100 + (slot % NETWORK_GRID_COLUMNS) * 150,
                    position_y=100 + (slot // NETWORK_GRID_COLUMNS) * 120,
                    **GraphAutomationService._node_kwargs(key, fields))
                state.add_node(node, key)
                state.ip_slot += 1
                refreshed.add(key)
            elif key not in refreshed:
                refreshed.add(key)
                state.refresh(node, key, fields)

            host_node = node_map[target_hid]
            state.add_edge(host_node, node, 'associated_with', ioc.direction or 'Network IOC',
                           edge_key('associated_with', host_key(target_hid), key), user_id)

    @staticmethod
    def _merge_lateral_movement_edges(incident, node_map, state, user_id):
        """Lateral movement edges from consecutive timeline events on different hosts."""
        events = TimelineEvent.query.filter_by(incident_id=incident.id) \
            .filter(TimelineEvent.host_id.isnot(None)) \
            .order_by(TimelineEvent.timestamp.asc()).all()

        prev_host_id = None
        for event in events:
            cur_host_id = str(event.host_id)
            if prev_host_id and cur_host_id != prev_host_id:
                src = node_map.get(prev_host_id)
                tgt = node_map.get(cur_host_id)
                if src and tgt:
                    state.add_edge(src, tgt, 'lateral_movement', event.activity[:50],
                                   edge_key('lateral_movement', host_key(prev_host_id), host_key(cur_host_id)),
                                   user_id, mitre_tactic=event.mitre_tactic, timestamp=event.timestamp)
            prev_host_id = cur_host_id

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
                extra_data={'origin': ORIGIN_AUTO, 'auto_key': host_key(host_id)},
                created_by=created_by,
                position_x=0,
                position_y=0
            )
            db.session.add(node)
            db.session.flush()

        return node


class _GraphState:
    """The incident's current graph, indexed for merge-mode generation."""

    def __init__(self, incident):
        self.incident = incident
        self.by_key = {}          # auto_key -> node
        self.legacy = {}          # (node_type, label, host_system) -> node, for nodes without a key
        self.edge_set = set()     # (source_id, target_id, edge_type)
        self.assoc_out = {}       # node id -> outgoing associated_with edges
        self.ip_slot = 0          # next free cell of the network IOC grid
        self.nodes_created = []
        self.edges_created = []

    @classmethod
    def load(cls, incident):
        state = cls(incident)
        for node in AttackGraphNode.query.filter_by(incident_id=incident.id).all():
            extra = node.extra_data or {}
            key = extra.get('auto_key')
            if key:
                state.by_key.setdefault(key, node)
            elif node.compromised_host_id:
                state.by_key.setdefault(host_key(node.compromised_host_id), node)
            elif node.compromised_account_id:
                state.by_key.setdefault(f'account:{node.compromised_account_id}', node)
            else:
                state.legacy.setdefault((node.node_type, node.label, extra.get('host_system')), node)
            if node.node_type == 'ip_address':
                state.ip_slot += 1
        for edge in AttackGraphEdge.query.filter_by(incident_id=incident.id).all():
            state.edge_set.add((edge.source_node_id, edge.target_node_id, edge.edge_type))
            if edge.edge_type == 'associated_with':
                state.assoc_out[edge.source_node_id] = state.assoc_out.get(edge.source_node_id, 0) + 1
        return state

    def count_nodes_with_prefix(self, prefix):
        return sum(1 for key in self.by_key if key.startswith(prefix))

    def find(self, key, legacy=None):
        node = self.by_key.get(key)
        if node is None and legacy is not None:
            node = self.legacy.get(legacy)
        return node

    def children_of(self, node):
        return self.assoc_out.get(node.id, 0)

    def add_node(self, node, key):
        db.session.add(node)
        db.session.flush()
        self.by_key[key] = node
        self.nodes_created.append(node)

    @staticmethod
    def refresh(node, key, fields):
        """Update an AUTO node's label and data (never its position); nodes
        that are not auto-origin are left exactly as the analyst made them."""
        extra = node.extra_data or {}
        if extra.get('origin') != ORIGIN_AUTO:
            return
        node.label = (fields['label'] or '')[:255]
        node.extra_data = {**extra, **fields['extra'], 'origin': ORIGIN_AUTO, 'auto_key': key}

    def add_edge(self, source, target, edge_type, label, key, user_id, **fields):
        signature = (source.id, target.id, edge_type)
        if signature in self.edge_set:
            return None
        edge = AttackGraphEdge(
            incident_id=self.incident.id, source_node_id=source.id, target_node_id=target.id,
            edge_type=edge_type, label=label, created_by=user_id,
            extra_data={'origin': ORIGIN_AUTO, 'auto_key': key}, **fields)
        db.session.add(edge)
        self.edge_set.add(signature)
        if edge_type == 'associated_with':
            self.assoc_out[source.id] = self.assoc_out.get(source.id, 0) + 1
        self.edges_created.append(edge)
        return edge
