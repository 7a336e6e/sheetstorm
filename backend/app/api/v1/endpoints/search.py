"""Cross-incident search and IOC correlation endpoints.

Provides full-text search across all incident data (timeline events,
IOCs, hosts, accounts, notes) and cross-incident IOC correlation.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_, func, text, cast, String
from app.api.v1 import api_bp
from app.middleware.rbac import require_permission
from app import db
from app.models.incident import Incident
from app.models.timeline import TimelineEvent
from app.models.compromised import CompromisedHost, CompromisedAccount
from app.models.ioc import NetworkIndicator, HostBasedIndicator, MalwareTool
from app.models.case_note import CaseNote
from app.models.user import User


def _user_incident_ids(user_id):
    """Return incident IDs accessible by the user (org-scoped)."""
    user = db.session.get(User, user_id)
    if not user:
        return []
    return [
        r[0] for r in db.session.query(Incident.id)
        .filter(
            Incident.organization_id == user.organization_id,
            Incident.is_deleted.is_(False),
        ).all()
    ]


# ---------------------------------------------------------------------------
# Full-text search across incidents
# ---------------------------------------------------------------------------

@api_bp.route('/search', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def search_across_incidents():
    """Full-text search across all incident data.

    Query params:
        q (str):        Search term (required, min 2 chars)
        types (str):    Comma-separated entity types to search
                        (incidents,timeline,hosts,accounts,network_iocs,
                         host_iocs,malware,notes). Default: all.
        page (int):     Page number (default 1)
        per_page (int): Results per page (default 50, max 200)
    """
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'error': 'Search term must be at least 2 characters'}), 400

    types_param = request.args.get('types', '')
    allowed_types = {'incidents', 'timeline', 'hosts', 'accounts',
                     'network_iocs', 'host_iocs', 'malware', 'notes'}
    if types_param:
        search_types = set(types_param.split(',')) & allowed_types
    else:
        search_types = allowed_types

    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(200, max(1, request.args.get('per_page', 50, type=int)))

    user_id = get_jwt_identity()
    accessible_ids = _user_incident_ids(user_id)
    if not accessible_ids:
        return jsonify({'results': [], 'total': 0, 'page': page, 'per_page': per_page}), 200

    search_term = f'%{q}%'
    results = []

    if 'incidents' in search_types:
        rows = db.session.query(Incident).filter(
            Incident.id.in_(accessible_ids),
            or_(
                Incident.title.ilike(search_term),
                Incident.description.ilike(search_term),
                Incident.executive_summary.ilike(search_term),
                Incident.classification.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'incident',
                'incident_id': str(r.id),
                'incident_title': r.title,
                'title': r.title,
                'snippet': (r.description or '')[:200],
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    if 'timeline' in search_types:
        rows = db.session.query(TimelineEvent).filter(
            TimelineEvent.incident_id.in_(accessible_ids),
            or_(
                TimelineEvent.activity.ilike(search_term),
                TimelineEvent.hostname.ilike(search_term),
                TimelineEvent.mitre_tactic.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'timeline_event',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': r.activity[:100] if r.activity else '',
                'snippet': r.activity[:200] if r.activity else '',
                'hostname': r.hostname,
                'timestamp': r.timestamp.isoformat() if r.timestamp else None,
            })

    if 'hosts' in search_types:
        rows = db.session.query(CompromisedHost).filter(
            CompromisedHost.incident_id.in_(accessible_ids),
            or_(
                CompromisedHost.hostname.ilike(search_term),
                cast(CompromisedHost.ip_address, String).ilike(search_term),
                CompromisedHost.system_type.ilike(search_term),
                CompromisedHost.notes.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'host',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': f"{r.hostname} ({str(r.ip_address)})" if r.ip_address else r.hostname,
                'snippet': (r.notes or '')[:200],
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    if 'accounts' in search_types:
        rows = db.session.query(CompromisedAccount).filter(
            CompromisedAccount.incident_id.in_(accessible_ids),
            or_(
                CompromisedAccount.account_name.ilike(search_term),
                CompromisedAccount.domain.ilike(search_term),
                CompromisedAccount.notes.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'account',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': f"{r.domain}\\{r.account_name}" if r.domain else r.account_name,
                'snippet': (r.notes or '')[:200],
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    if 'network_iocs' in search_types:
        rows = db.session.query(NetworkIndicator).filter(
            NetworkIndicator.incident_id.in_(accessible_ids),
            or_(
                NetworkIndicator.dns_ip.ilike(search_term),
                NetworkIndicator.source_host.ilike(search_term),
                NetworkIndicator.destination_host.ilike(search_term),
                NetworkIndicator.description.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'network_ioc',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': r.dns_ip,
                'snippet': (r.description or '')[:200],
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    if 'host_iocs' in search_types:
        rows = db.session.query(HostBasedIndicator).filter(
            HostBasedIndicator.incident_id.in_(accessible_ids),
            or_(
                HostBasedIndicator.artifact_value.ilike(search_term),
                HostBasedIndicator.notes.ilike(search_term),
                HostBasedIndicator.host.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'host_ioc',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': f"[{r.artifact_type}] {r.artifact_value[:80]}",
                'snippet': (r.notes or '')[:200],
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    if 'malware' in search_types:
        rows = db.session.query(MalwareTool).filter(
            MalwareTool.incident_id.in_(accessible_ids),
            or_(
                MalwareTool.file_name.ilike(search_term),
                MalwareTool.file_path.ilike(search_term),
                MalwareTool.md5.ilike(search_term),
                MalwareTool.sha256.ilike(search_term),
                MalwareTool.malware_family.ilike(search_term),
                MalwareTool.description.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'malware',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': r.file_name,
                'snippet': f"MD5: {r.md5 or 'N/A'} | SHA256: {r.sha256 or 'N/A'}",
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    if 'notes' in search_types:
        rows = db.session.query(CaseNote).filter(
            CaseNote.incident_id.in_(accessible_ids),
            or_(
                CaseNote.title.ilike(search_term),
                CaseNote.content.ilike(search_term),
            )
        ).all()
        for r in rows:
            results.append({
                'type': 'case_note',
                'incident_id': str(r.incident_id),
                'incident_title': r.incident.title if r.incident else None,
                'title': r.title,
                'snippet': (r.content or '')[:200],
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

    # Sort by timestamp descending
    results.sort(key=lambda x: x.get('timestamp') or '', reverse=True)
    total = len(results)

    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    paginated = results[start:end]

    return jsonify({
        'results': paginated,
        'total': total,
        'page': page,
        'per_page': per_page,
    }), 200


# ---------------------------------------------------------------------------
# Cross-incident IOC Correlation
# ---------------------------------------------------------------------------

@api_bp.route('/correlate-iocs', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def correlate_iocs():
    """Find IOCs that appear across multiple incidents.

    Body:
        ioc_values (list[str]):  Optional list of specific IOC values to check.
                                 If empty, finds all IOCs shared across 2+ incidents.
        ioc_types (list[str]):   Optional filter by IOC type:
                                 [ip, domain, hash, hostname, file, all]. Default: all.
    Returns:
        Grouped IOC matches with incident references.
    """
    user_id = get_jwt_identity()
    accessible_ids = _user_incident_ids(user_id)
    if not accessible_ids:
        return jsonify({'correlations': [], 'total': 0}), 200

    data = request.get_json(silent=True) or {}
    ioc_values = data.get('ioc_values', [])
    ioc_types = data.get('ioc_types', ['all'])
    if 'all' in ioc_types:
        ioc_types = ['ip', 'domain', 'hash', 'hostname', 'file']

    correlations = []

    # --- Network IOCs (IPs, domains) ---
    if any(t in ioc_types for t in ['ip', 'domain']):
        q = db.session.query(
            NetworkIndicator.dns_ip,
            func.count(func.distinct(NetworkIndicator.incident_id)).label('incident_count'),
            func.array_agg(func.distinct(cast(NetworkIndicator.incident_id, String))).label('incident_ids'),
        ).filter(
            NetworkIndicator.incident_id.in_(accessible_ids),
        ).group_by(NetworkIndicator.dns_ip).having(
            func.count(func.distinct(NetworkIndicator.incident_id)) > 1
        )
        if ioc_values:
            q = q.filter(NetworkIndicator.dns_ip.in_(ioc_values))

        for row in q.all():
            # Fetch incident titles
            incidents = db.session.query(Incident.id, Incident.title).filter(
                Incident.id.in_(row.incident_ids)
            ).all()
            correlations.append({
                'ioc_value': row.dns_ip,
                'ioc_type': 'network_ioc',
                'incident_count': row.incident_count,
                'incidents': [{'id': str(i.id), 'title': i.title} for i in incidents],
            })

    # --- Hash correlations (MD5/SHA256 from malware) ---
    if 'hash' in ioc_types:
        for hash_col, hash_name in [(MalwareTool.md5, 'md5'), (MalwareTool.sha256, 'sha256')]:
            q = db.session.query(
                hash_col,
                func.count(func.distinct(MalwareTool.incident_id)).label('incident_count'),
                func.array_agg(func.distinct(cast(MalwareTool.incident_id, String))).label('incident_ids'),
            ).filter(
                MalwareTool.incident_id.in_(accessible_ids),
                hash_col.isnot(None),
                hash_col != '',
            ).group_by(hash_col).having(
                func.count(func.distinct(MalwareTool.incident_id)) > 1
            )
            if ioc_values:
                q = q.filter(hash_col.in_(ioc_values))

            for row in q.all():
                incidents = db.session.query(Incident.id, Incident.title).filter(
                    Incident.id.in_(row.incident_ids)
                ).all()
                correlations.append({
                    'ioc_value': getattr(row, hash_name if hash_name == 'md5' else hash_name, row[0]),
                    'ioc_type': hash_name,
                    'incident_count': row.incident_count,
                    'incidents': [{'id': str(i.id), 'title': i.title} for i in incidents],
                })

    # --- Host IOC artifact values ---
    if 'file' in ioc_types:
        q = db.session.query(
            HostBasedIndicator.artifact_value,
            HostBasedIndicator.artifact_type,
            func.count(func.distinct(HostBasedIndicator.incident_id)).label('incident_count'),
            func.array_agg(func.distinct(cast(HostBasedIndicator.incident_id, String))).label('incident_ids'),
        ).filter(
            HostBasedIndicator.incident_id.in_(accessible_ids),
        ).group_by(
            HostBasedIndicator.artifact_value,
            HostBasedIndicator.artifact_type,
        ).having(
            func.count(func.distinct(HostBasedIndicator.incident_id)) > 1
        )
        if ioc_values:
            q = q.filter(HostBasedIndicator.artifact_value.in_(ioc_values))

        for row in q.all():
            incidents = db.session.query(Incident.id, Incident.title).filter(
                Incident.id.in_(row.incident_ids)
            ).all()
            correlations.append({
                'ioc_value': row.artifact_value,
                'ioc_type': f'host_ioc:{row.artifact_type}',
                'incident_count': row.incident_count,
                'incidents': [{'id': str(i.id), 'title': i.title} for i in incidents],
            })

    # --- Hostname correlations ---
    if 'hostname' in ioc_types:
        q = db.session.query(
            CompromisedHost.hostname,
            func.count(func.distinct(CompromisedHost.incident_id)).label('incident_count'),
            func.array_agg(func.distinct(cast(CompromisedHost.incident_id, String))).label('incident_ids'),
        ).filter(
            CompromisedHost.incident_id.in_(accessible_ids),
        ).group_by(CompromisedHost.hostname).having(
            func.count(func.distinct(CompromisedHost.incident_id)) > 1
        )
        if ioc_values:
            q = q.filter(CompromisedHost.hostname.in_(ioc_values))

        for row in q.all():
            incidents = db.session.query(Incident.id, Incident.title).filter(
                Incident.id.in_(row.incident_ids)
            ).all()
            correlations.append({
                'ioc_value': row.hostname,
                'ioc_type': 'hostname',
                'incident_count': row.incident_count,
                'incidents': [{'id': str(i.id), 'title': i.title} for i in incidents],
            })

    # Sort by incident_count descending
    correlations.sort(key=lambda x: x['incident_count'], reverse=True)

    return jsonify({
        'correlations': correlations,
        'total': len(correlations),
    }), 200


# ---------------------------------------------------------------------------
# Bulk Enrichment
# ---------------------------------------------------------------------------

@api_bp.route('/bulk-enrich', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def bulk_enrich():
    """Batch IOC enrichment across multiple sources.

    Body:
        ioc_values (list[dict]):  List of IOCs to enrich.
            Each dict: { "value": "...", "type": "ip|domain|hash|email" }
    Returns:
        Enrichment results per IOC.
    """
    from app.services.enrichment_service import EnrichmentService

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    ioc_list = data.get('ioc_values', [])
    if not ioc_list:
        return jsonify({'error': 'ioc_values list required'}), 400
    if len(ioc_list) > 100:
        return jsonify({'error': 'Maximum 100 IOCs per batch'}), 400

    enrichment = EnrichmentService
    results = []

    for ioc in ioc_list:
        value = ioc.get('value', '')
        ioc_type = ioc.get('type', 'ip')
        if not value:
            continue

        # Map user-friendly types to enrichment service types
        type_map = {
            'ip': 'ip-src',
            'domain': 'domain',
            'hash': 'sha256',
            'md5': 'md5',
            'sha1': 'sha1',
            'sha256': 'sha256',
            'email': 'email',
            'hostname': 'hostname',
        }
        svc_type = type_map.get(ioc_type, ioc_type)

        try:
            enrichment_result = enrichment.auto_enrich_ioc(svc_type, value, str(user.organization_id))
            results.append({
                'value': value,
                'type': ioc_type,
                'status': 'success',
                'enrichment': enrichment_result or {},
            })
        except Exception as e:
            results.append({
                'value': value,
                'type': ioc_type,
                'status': 'error',
                'error': str(e),
            })

    return jsonify({
        'results': results,
        'total': len(results),
        'enriched': sum(1 for r in results if r['status'] == 'success'),
        'failed': sum(1 for r in results if r['status'] == 'error'),
    }), 200


# ---------------------------------------------------------------------------
# STIX 2.1 Export
# ---------------------------------------------------------------------------

@api_bp.route('/incidents/<incident_id>/export/stix', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def export_incident_stix(incident_id):
    """Export incident data as a STIX 2.1 Bundle.

    Returns a STIX 2.1 JSON bundle containing:
        - Report (incident)
        - Indicators (IOCs)
        - Infrastructure (hosts)
        - Malware (malware samples)
        - Attack Patterns (MITRE techniques)
        - Relationships linking them all
    """
    import uuid as uuid_mod
    from datetime import datetime, timezone

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    incident = db.session.query(Incident).filter(
        Incident.id == incident_id,
        Incident.organization_id == user.organization_id,
        Incident.is_deleted.is_(False),
    ).first()

    if not incident:
        return jsonify({'error': 'Incident not found'}), 404

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    stix_objects = []
    relationships = []

    # --- Identity (organization) ---
    identity_id = f"identity--{uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, f'sheetstorm:{user.organization_id}')}"
    stix_objects.append({
        'type': 'identity',
        'spec_version': '2.1',
        'id': identity_id,
        'created': now,
        'modified': now,
        'name': 'SheetStorm Organization',
        'identity_class': 'organization',
    })

    # --- Report (incident) ---
    report_id = f"report--{incident.id}"
    stix_objects.append({
        'type': 'report',
        'spec_version': '2.1',
        'id': report_id,
        'created': now,
        'modified': now,
        'name': incident.title,
        'description': incident.description or '',
        'report_types': ['incident'],
        'published': incident.created_at.strftime('%Y-%m-%dT%H:%M:%S.000Z') if incident.created_at else now,
        'created_by_ref': identity_id,
        'labels': [incident.severity or 'medium', incident.status or 'open'],
        'object_refs': [],  # Will be populated
        'extensions': {
            'x-sheetstorm-incident': {
                'phase': incident.phase,
                'phase_name': incident.phase_name,
                'classification': incident.classification,
                'severity': incident.severity,
                'status': incident.status,
            }
        }
    })

    ref_ids = []

    # --- Indicators (Network IOCs) ---
    for ioc in incident.network_indicators.all():
        indicator_id = f"indicator--{ioc.id}"
        pattern_type = 'ipv4-addr' if _is_ip(ioc.dns_ip) else 'domain-name'
        pattern_value = f"[{pattern_type}:value = '{ioc.dns_ip}']"
        stix_objects.append({
            'type': 'indicator',
            'spec_version': '2.1',
            'id': indicator_id,
            'created': now,
            'modified': now,
            'name': ioc.dns_ip,
            'description': ioc.description or f"Network IOC: {ioc.dns_ip}",
            'pattern': pattern_value,
            'pattern_type': 'stix',
            'valid_from': ioc.timestamp.strftime('%Y-%m-%dT%H:%M:%S.000Z') if ioc.timestamp else now,
            'indicator_types': ['malicious-activity'] if ioc.is_malicious else ['anomalous-activity'],
            'labels': [ioc.protocol or 'unknown', ioc.direction or 'unknown'],
        })
        ref_ids.append(indicator_id)

    # --- Indicators (Host IOCs) ---
    for ioc in incident.host_indicators.all():
        indicator_id = f"indicator--{ioc.id}"
        pattern_value = f"[file:name = '{ioc.artifact_value}']" if ioc.artifact_type == 'file' else \
                        f"[process:name = '{ioc.artifact_value}']" if ioc.artifact_type == 'process' else \
                        f"[windows-registry-key:key = '{ioc.artifact_value}']" if ioc.artifact_type in ('registry', 'asep') else \
                        f"[artifact:payload_bin = '{ioc.artifact_value}']"
        stix_objects.append({
            'type': 'indicator',
            'spec_version': '2.1',
            'id': indicator_id,
            'created': now,
            'modified': now,
            'name': f"{ioc.artifact_type}: {ioc.artifact_value[:80]}",
            'description': ioc.notes or f"Host IOC ({ioc.artifact_type})",
            'pattern': pattern_value,
            'pattern_type': 'stix',
            'valid_from': ioc.datetime.strftime('%Y-%m-%dT%H:%M:%S.000Z') if ioc.datetime else now,
            'indicator_types': ['malicious-activity'] if ioc.is_malicious else ['anomalous-activity'],
            'labels': [ioc.artifact_type],
        })
        ref_ids.append(indicator_id)

    # --- Malware ---
    for m in incident.malware_tools.all():
        malware_id = f"malware--{m.id}"
        stix_objects.append({
            'type': 'malware',
            'spec_version': '2.1',
            'id': malware_id,
            'created': now,
            'modified': now,
            'name': m.file_name,
            'description': m.description or f"Malware: {m.file_name}",
            'malware_types': ['tool'] if m.is_tool else ['trojan'],
            'is_family': bool(m.malware_family),
            'hashes': {k: v for k, v in {
                'MD5': m.md5, 'SHA-256': m.sha256, 'SHA-512': m.sha512
            }.items() if v},
        })
        ref_ids.append(malware_id)

    # --- Infrastructure (Hosts) ---
    for host in incident.compromised_hosts.all():
        infra_id = f"infrastructure--{host.id}"
        stix_objects.append({
            'type': 'infrastructure',
            'spec_version': '2.1',
            'id': infra_id,
            'created': now,
            'modified': now,
            'name': host.hostname,
            'description': f"IP: {host.ip_address or 'N/A'} | OS: {host.os or 'N/A'}",
            'infrastructure_types': ['workstation'] if host.system_type == 'workstation' else ['server'],
        })
        ref_ids.append(infra_id)

    # --- Attack Patterns (MITRE techniques from timeline) ---
    seen_techniques = set()
    for event in incident.timeline_events.all():
        if event.mitre_technique and event.mitre_technique not in seen_techniques:
            seen_techniques.add(event.mitre_technique)
            ap_id = f"attack-pattern--{uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, event.mitre_technique)}"
            stix_objects.append({
                'type': 'attack-pattern',
                'spec_version': '2.1',
                'id': ap_id,
                'created': now,
                'modified': now,
                'name': f"{event.mitre_tactic}: {event.mitre_technique}" if event.mitre_tactic else event.mitre_technique,
                'external_references': [{
                    'source_name': 'mitre-attack',
                    'external_id': event.mitre_technique,
                    'url': f"https://attack.mitre.org/techniques/{event.mitre_technique.replace('.', '/')}",
                }],
            })
            ref_ids.append(ap_id)

    # Update report object_refs
    for obj in stix_objects:
        if obj['id'] == report_id:
            obj['object_refs'] = ref_ids
            break

    # Build bundle
    bundle = {
        'type': 'bundle',
        'id': f"bundle--{uuid_mod.uuid4()}",
        'objects': stix_objects,
    }

    return jsonify(bundle), 200


def _is_ip(value: str) -> bool:
    """Quick check if a string looks like an IP address."""
    import re
    return bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', value or ''))
