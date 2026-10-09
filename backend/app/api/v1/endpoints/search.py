"""Cross-incident search and IOC correlation endpoints.

`/search` is implemented by services/search_service.py (one bounded SQL
statement, per-type read permissions, pg_trgm-indexed ILIKE); this module
also holds cross-incident IOC correlation, bulk enrichment and STIX export.
"""
from flask import Response, g, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, cast, select, String
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import require_permission, get_current_user
from app import db, limiter
from app.models.incident import Incident
from app.models.compromised import CompromisedHost
from app.models.ioc import NetworkIndicator, HostBasedIndicator, MalwareTool
from app.models.user import User
from app.utils.audit_diff import record_changes

MAX_IOC_VALUES = 1000        # correlate-iocs: values per request
MAX_IOC_VALUE_LENGTH = 2048
CORRELATE_TYPES = ('ip', 'domain', 'hash', 'hostname', 'file')
MAX_BULK_ENRICH = 100


def _bad_request(message, code='bad_request', **extra):
    return jsonify({'error': code, 'message': message, **extra}), 400


def _resolve_incident(user, raw):
    """(incident, error_response) for an optional ``incident_id`` body field:
    org-scoped and visible to the caller, else 404 / 403 (never a hint about
    incidents in other organizations)."""
    import uuid
    from app.middleware.rbac import check_incident_access
    try:
        incident_id = uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None, _bad_request('incident_id must be a UUID')
    allowed, incident = check_incident_access(user, incident_id)
    if not incident or incident.is_archived:
        return None, (jsonify({'error': 'not_found', 'message': 'Incident not found'}), 404)
    if not allowed:
        return None, (jsonify({'error': 'forbidden', 'message': 'You do not have access to this incident'}), 403)
    return incident, None


def _user_incident_ids(user_id):
    """Return incident IDs accessible by the user (org + role/team/assignment
    scoped), matching list_incidents so cross-incident search/correlation can
    never leak incidents the user is not entitled to see.
    """
    user = db.session.get(User, user_id)
    if not user:
        return []
    from app.middleware.rbac import accessible_incidents_query
    return [r[0] for r in accessible_incidents_query(user).with_entities(Incident.id).all()]


# ---------------------------------------------------------------------------
# Full-text search across incidents
# ---------------------------------------------------------------------------

@api_bp.route('/search', methods=['GET'])
@limiter.limit("60 per minute")  # rl-group: search
@jwt_required()
@require_permission('incidents:read')
def search_across_incidents():
    """Search across every incident the caller can access.

    Query params:
        q (str):           2..200 characters (required)
        types (str):       comma-separated subset of incidents, timeline,
                           hosts, accounts, network_iocs, host_iocs, malware,
                           notes (result type names are accepted too). Types
                           the caller lacks the read permission for are
                           dropped silently.
        incident_id (uuid): restrict to one accessible incident (else 404)
        since, until:      ISO-8601 bounds on the result timestamp
        sort:              relevance (default) | -timestamp | timestamp
        page, per_page:    per_page 1..50 (default 50)

    Response: {results, total, page, per_page, pages, facets: {type: n},
    sort}; each result has id, type, incident_id, incident_title, title,
    snippet, timestamp and link {incident_id, tab, row}.
    """
    from app.services import search_service
    from app.utils.pagination import ListArgsError, parse_page_args, parse_q, parse_uuid
    from app.utils.validation import parse_datetime
    from app.middleware.rbac import accessible_incidents_query

    user = get_current_user()
    args = request.args
    q = parse_q(args, min_length=2)
    page, per_page = parse_page_args(args, default_per_page=50, max_per_page=50)

    sort = (args.get('sort') or 'relevance').strip()
    if sort not in search_service.SORTS:
        raise ListArgsError(f"invalid sort {sort!r}; allowed: {', '.join(search_service.SORTS)}",
                            'invalid_sort')

    incident_id = None
    accessible = accessible_incidents_query(user)
    if args.get('incident_id'):
        incident_id = parse_uuid('incident_id', args['incident_id'])
        if accessible.filter(Incident.id == incident_id).first() is None:
            return jsonify({'error': 'not_found', 'message': 'Incident not found'}), 404

    requested = [t.strip() for t in (args.get('types') or '').split(',') if t.strip()]
    types = search_service.allowed_types(user, requested)

    params = search_service.SearchParams(
        q=q, page=page, per_page=per_page, sort=sort, incident_id=incident_id,
        since=parse_datetime(args.get('since'), 'since'),
        until=parse_datetime(args.get('until'), 'until'),
    )
    accessible_ids = select(accessible.with_entities(Incident.id).subquery().c.id)
    return jsonify(search_service.run_search(types, accessible_ids, params)), 200


# ---------------------------------------------------------------------------
# Cross-incident IOC Correlation
# ---------------------------------------------------------------------------

@api_bp.route('/correlate-iocs', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
@audit_log('data_access', 'correlate_iocs', 'incident')
def correlate_iocs():
    """Find IOCs that appear across multiple incidents.

    Body:
        incident_id (uuid):      Optional. The caller must be able to access it
                                 (404 / 403 otherwise). When ``ioc_values`` is
                                 empty the values are taken from that incident
                                 (network dns_ip, malware hashes, host IOC
                                 values, hostnames).
        ioc_values (list[str]):  Optional list of specific IOC values to check
                                 (at most 1000, each at most 2048 characters).
                                 If empty (and no incident_id), finds all IOCs
                                 shared across 2+ incidents.
        ioc_types (list[str]):   Optional filter by IOC type:
                                 [ip, domain, hash, hostname, file, all]. Default: all.
    Returns:
        Grouped IOC matches with incident references. Only incidents the
        caller can access are ever listed.
    """
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _bad_request('Request body must be a JSON object')

    ioc_values = data.get('ioc_values') or []
    if not isinstance(ioc_values, list) or len(ioc_values) > MAX_IOC_VALUES:
        return _bad_request(f'ioc_values must be a list of at most {MAX_IOC_VALUES} strings',
                            'invalid_ioc_values')
    if any(not isinstance(v, str) or not v.strip() or len(v) > MAX_IOC_VALUE_LENGTH for v in ioc_values):
        return _bad_request(f'Each ioc_value must be a non-empty string of at most {MAX_IOC_VALUE_LENGTH} characters',
                            'invalid_ioc_values')
    ioc_values = sorted({v.strip() for v in ioc_values})

    ioc_types = data.get('ioc_types') or ['all']
    if not isinstance(ioc_types, list) or any(t not in CORRELATE_TYPES + ('all',) for t in ioc_types):
        return _bad_request(f"ioc_types must be a list of: {', '.join(CORRELATE_TYPES + ('all',))}",
                            'invalid_ioc_types')
    if 'all' in ioc_types:
        ioc_types = list(CORRELATE_TYPES)

    incident = None
    if data.get('incident_id'):
        incident, error = _resolve_incident(user, data['incident_id'])
        if error:
            return error
        g.incident = incident
        if not ioc_values:
            ioc_values = _incident_ioc_values(incident)[:MAX_IOC_VALUES]
            if not ioc_values:
                record_changes({}, {}, correlations=0, values=0)
                return jsonify({'correlations': [], 'total': 0, 'incident_id': str(incident.id)}), 200

    accessible_ids = _user_incident_ids(user_id)
    if not accessible_ids:
        return jsonify({'correlations': [], 'total': 0}), 200

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
    record_changes({}, {}, correlations=len(correlations), values=len(ioc_values),
                   types=ioc_types)

    body = {'correlations': correlations, 'total': len(correlations)}
    if incident is not None:
        body['incident_id'] = str(incident.id)
    return jsonify(body), 200


def _incident_ioc_values(incident) -> list:
    """Distinct correlatable values recorded in ``incident``."""
    values = set()
    for model, columns in ((NetworkIndicator, (NetworkIndicator.dns_ip,)),
                           (MalwareTool, (MalwareTool.md5, MalwareTool.sha256)),
                           (HostBasedIndicator, (HostBasedIndicator.artifact_value,)),
                           (CompromisedHost, (CompromisedHost.hostname,))):
        for column in columns:
            rows = db.session.query(column).filter(model.incident_id == incident.id,
                                                   column.isnot(None), column != '').distinct().limit(MAX_IOC_VALUES)
            values.update(r[0].strip() for r in rows if r[0] and len(r[0]) <= MAX_IOC_VALUE_LENGTH)
    return sorted(v for v in values if v)


# ---------------------------------------------------------------------------
# Bulk Enrichment
# ---------------------------------------------------------------------------

# user-facing IOC type -> EnrichmentService type
_ENRICH_TYPE_MAP = {
    'ip': 'ip-src',
    'domain': 'domain',
    'hash': 'sha256',
    'md5': 'md5',
    'sha1': 'sha1',
    'sha256': 'sha256',
    'email': 'email',
    'hostname': 'hostname',
}
_HEX_LENGTHS = {'md5': 32, 'sha1': 40, 'sha256': 64}


def _valid_enrich_value(ioc_type: str, value: str) -> bool:
    """Shape check per type. The value is interpolated into provider URLs by
    the enrichment service, so only plain indicator characters may pass."""
    import ipaddress
    import re
    if ioc_type == 'ip':
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
    if ioc_type in ('domain', 'hostname'):
        return bool(re.fullmatch(r'[A-Za-z0-9_]([A-Za-z0-9_.-]{0,251}[A-Za-z0-9_])?', value))
    if ioc_type in _HEX_LENGTHS:
        return bool(re.fullmatch(r'[0-9A-Fa-f]{%d}' % _HEX_LENGTHS[ioc_type], value))
    if ioc_type == 'hash':
        return len(value) in _HEX_LENGTHS.values() and bool(re.fullmatch(r'[0-9A-Fa-f]+', value))
    if ioc_type == 'email':
        return bool(re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]{1,253}", value))
    return False


def _enrichment_summary(enrichment: dict) -> str:
    parts = []
    for provider, info in sorted((enrichment or {}).items()):
        if not isinstance(info, dict):
            continue
        facts = []
        for key in ('malicious', 'suspicious', 'abuse_confidence', 'detection_ratio', 'country'):
            if info.get(key) not in (None, ''):
                facts.append(f'{key.replace("_", " ")} {info[key]}')
        parts.append(f"{provider}: {', '.join(facts) if facts else 'no details'}")
    return '; '.join(parts) if parts else 'no provider returned data'


@api_bp.route('/bulk-enrich', methods=['POST'])
@limiter.limit("10 per minute")  # rl-group: bulk_enrich
@jwt_required()
@require_permission('incidents:read')
@audit_log('data_access', 'bulk_enrich', 'incident')
def bulk_enrich():
    """Batch IOC enrichment across multiple sources.

    Body:
        ioc_values (list[dict]):  1..100 IOCs. Each dict:
            { "value": "...", "type": "ip|domain|hash|md5|sha1|sha256|email|hostname" }
            ``value`` is a string of at most 2048 characters that must match
            its type; ``type`` defaults to ``ip``.
        incident_id (uuid):       Optional. The caller must be able to access it
                                  (404 / 403). Enrichment of a TLP-restricted
                                  incident is refused as a whole (403
                                  ``tlp_restricted``): ``red`` always,
                                  ``amber_strict`` unless the org allows it.
    Returns:
        Enrichment results per IOC, the provider names that answered
        (``providers``) and the incident TLP when an incident was given. Values
        that belong to any restricted incident of the org are returned as
        ``blocked`` and never sent out.
    """
    from app.services.egress_policy import EgressBlocked, assert_enrichment_allowed, filter_values_for_enrichment
    from app.services.enrichment_service import EnrichmentService
    from app.middleware.audit import log_security_event

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request('Request body must be a JSON object')
    ioc_list = data.get('ioc_values', [])
    if not isinstance(ioc_list, list) or not ioc_list:
        return _bad_request('ioc_values list required')
    if len(ioc_list) > MAX_BULK_ENRICH:
        return _bad_request(f'Maximum {MAX_BULK_ENRICH} IOCs per batch')

    items = []
    for index, ioc in enumerate(ioc_list):
        if not isinstance(ioc, dict):
            return _bad_request(f'ioc_values[{index}] must be an object', 'invalid_ioc_values')
        value = ioc.get('value')
        ioc_type = ioc.get('type') or 'ip'
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_IOC_VALUE_LENGTH:
            return _bad_request(f'ioc_values[{index}].value must be a non-empty string of at most '
                                f'{MAX_IOC_VALUE_LENGTH} characters', 'invalid_ioc_values')
        if ioc_type not in _ENRICH_TYPE_MAP:
            return _bad_request(f"ioc_values[{index}].type must be one of: {', '.join(_ENRICH_TYPE_MAP)}",
                                'invalid_ioc_values')
        value = value.strip()
        if not _valid_enrich_value(ioc_type, value):
            return _bad_request(f'ioc_values[{index}].value is not a valid {ioc_type}', 'invalid_ioc_values')
        items.append((value, ioc_type))

    incident = None
    if data.get('incident_id'):
        incident, error = _resolve_incident(user, data['incident_id'])
        if error:
            return error
        g.incident = incident
        try:
            assert_enrichment_allowed(incident)
        except EgressBlocked as e:
            log_security_event('enrichment_blocked_by_tlp', resource_type='bulk_enrich',
                               resource_id=incident.id, incident_id=incident.id,
                               details={'tlp': incident.tlp, 'blocked_count': len(items)}, user=user)
            return e.to_response()

    # TLP egress block: values from TLP:RED (and, unless the org allows it,
    # AMBER+STRICT) incidents are never sent to third parties.
    _, blocked_values = filter_values_for_enrichment(user.organization_id, [v for v, _ in items])
    blocked_values = {str(v).strip().lower() for v in blocked_values}
    if blocked_values:
        log_security_event('enrichment_blocked_by_tlp', resource_type='bulk_enrich',
                           details={'blocked_count': len(blocked_values)}, user=user)

    results = []
    providers = set()
    for value, ioc_type in items:
        if value.lower() in blocked_values:
            results.append({'value': value, 'type': ioc_type, 'status': 'blocked',
                            'error': 'tlp_restricted', 'summary': 'blocked: TLP-restricted value'})
            continue
        try:
            enrichment_result = EnrichmentService.auto_enrich_ioc(
                _ENRICH_TYPE_MAP[ioc_type], value, str(user.organization_id)) or {}
            providers.update(k for k in enrichment_result if isinstance(k, str))
            results.append({'value': value, 'type': ioc_type, 'status': 'success',
                            'enrichment': enrichment_result, 'summary': _enrichment_summary(enrichment_result)})
        except Exception:
            current_app.logger.exception('IOC enrichment failed for a bulk item')
            results.append({'value': value, 'type': ioc_type, 'status': 'error',
                            'error': 'enrichment failed', 'summary': 'enrichment failed'})

    summary = {
        'results': results,
        'total': len(results),
        'enriched': sum(1 for r in results if r['status'] == 'success'),
        'failed': sum(1 for r in results if r['status'] == 'error'),
        'blocked': sum(1 for r in results if r['status'] == 'blocked'),
        'providers': sorted(providers),
    }
    if incident is not None:
        summary['incident_id'] = str(incident.id)
        summary['tlp'] = incident.tlp
    record_changes({}, {}, total=summary['total'], enriched=summary['enriched'], blocked=summary['blocked'],
                   providers=summary['providers'], tlp=incident.tlp if incident is not None else None)
    return jsonify(summary), 200


# ---------------------------------------------------------------------------
# STIX 2.1 Export
# ---------------------------------------------------------------------------

@api_bp.route('/incidents/<uuid:incident_id>/export/stix', methods=['GET'])
@jwt_required()
@limiter.limit('30 per minute')  # rl-group: exports
@require_permission('incidents:read')
@audit_log('data_access', 'export_stix', 'incident')
def export_incident_stix(incident_id):
    """Export incident data as a STIX 2.1 Bundle (``application/stix+json``).

    Needs ``incidents:read`` and ``incidents:export`` (C24) plus access to the
    incident itself. The bundle (built by ``services/stix_export.py`` as an
    object model, patterns escaped) contains the Report, Indicators (network
    and host IOCs), Infrastructure (hosts), Malware, Attack Patterns (MITRE
    techniques), a few Relationships, and the incident's TLP marking-definition
    referenced from every object.
    """
    from app.services import stix_export
    from app.api.v1.endpoints.exports import EXPORT_PERMISSION, export_filename, forbidden

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    # Enforce incident-level access (assignment/team/TLP), not just org scope:
    # otherwise a Viewer could STIX-export any incident in the org.
    from app.middleware.rbac import check_incident_access
    allowed, incident = check_incident_access(user, incident_id)
    if not incident or incident.is_archived:
        return jsonify({'error': 'not_found', 'message': 'Incident not found'}), 404
    if not allowed:
        return jsonify({'error': 'forbidden', 'message': 'You do not have access to this incident'}), 403
    if not user.has_permission(EXPORT_PERMISSION):
        return forbidden(EXPORT_PERMISSION)
    g.incident = incident

    bundle = stix_export.build_bundle(incident, user.organization_id)
    record_changes({}, {}, objects=len(bundle['objects']), tlp=incident.tlp)
    response = Response(stix_export.dumps(bundle), content_type='application/stix+json;version=2.1')
    response.headers['Content-Disposition'] = f'attachment; filename="{export_filename(incident, "stix", "json")}"'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
