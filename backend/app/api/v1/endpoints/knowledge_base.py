"""Knowledge base reference data — LOLBAS, Windows Event IDs, MITRE ATT&CK, D3FEND.

All data is served from embedded static datasets so no external
API key is required.  The frontend can search/filter client-side.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app.middleware.rbac import require_permission

from app.api.v1.endpoints.kb_data_lolbas import LOLBAS_DATA, LOLBAS_CATEGORIES
from app.api.v1.endpoints.kb_data_events import WINDOWS_EVENT_IDS, EVENT_CATEGORIES, EVENT_SEVERITIES
from app.api.v1.endpoints.kb_data_mitre_attack import (
    MITRE_ATTACK_TACTICS, MITRE_ATTACK_TECHNIQUES,
    MITRE_ATTACK_TACTIC_IDS, MITRE_ATTACK_TECHNIQUE_IDS, MITRE_ATTACK_TACTIC_NAMES,
)
from app.api.v1.endpoints.kb_data_d3fend import D3FEND_TECHNIQUES, D3FEND_TACTICS, D3FEND_TECHNIQUE_IDS


@api_bp.route('/knowledge-base/lolbas', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def kb_lolbas():
    """Return LOLBAS reference data with optional search/filter."""
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')

    items = LOLBAS_DATA
    if search:
        items = [b for b in items if search in b['name'].lower() or search in b['description'].lower() or search in b.get('mitre_id', '').lower()]
    if category:
        items = [b for b in items if b['category'] == category]

    return jsonify({'items': items, 'total': len(items), 'categories': LOLBAS_CATEGORIES}), 200


# ---------------------------------------------------------------------------
# Windows Event ID Knowledge Base
# ---------------------------------------------------------------------------


@api_bp.route('/knowledge-base/event-ids', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def kb_event_ids():
    """Return Windows Event ID reference data with optional search/filter."""
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    severity = request.args.get('severity', '')

    items = WINDOWS_EVENT_IDS
    if search:
        items = [e for e in items if search in str(e['event_id']) or search in e['description'].lower() or search in e.get('provider', '').lower()]
    if category:
        items = [e for e in items if e['category'] == category]
    if severity:
        items = [e for e in items if e['severity'] == severity]

    return jsonify({'items': items, 'total': len(items), 'categories': EVENT_CATEGORIES, 'severities': EVENT_SEVERITIES}), 200


# ---------------------------------------------------------------------------
# MITRE ATT&CK — Enterprise Techniques & Tactics
# ---------------------------------------------------------------------------


@api_bp.route('/knowledge-base/mitre-attack', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def kb_mitre_attack():
    """Return MITRE ATT&CK enterprise techniques with optional search/filter.

    Query params:
      search   — free-text search across id, name, description
      tactic   — filter by tactic name (e.g., "Initial Access")
      platform — filter by platform (e.g., "Windows")
    """
    search = request.args.get('search', '').lower()
    tactic = request.args.get('tactic', '')
    platform = request.args.get('platform', '')

    items = MITRE_ATTACK_TECHNIQUES
    if search:
        items = [t for t in items if search in t['id'].lower()
                 or search in t['name'].lower()
                 or search in t['description'].lower()]
    if tactic:
        items = [t for t in items if t['tactic'].lower() == tactic.lower()]
    if platform:
        items = [t for t in items if platform in t.get('platforms', [])]

    return jsonify({
        'items': items,
        'total': len(items),
        'tactics': [t['name'] for t in MITRE_ATTACK_TACTICS],
    }), 200


@api_bp.route('/knowledge-base/mitre-attack/tactics', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def kb_mitre_attack_tactics():
    """Return all 14 MITRE ATT&CK Enterprise tactics."""
    return jsonify({'items': MITRE_ATTACK_TACTICS, 'total': len(MITRE_ATTACK_TACTICS)}), 200


@api_bp.route('/knowledge-base/mitre-attack/form-data', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def kb_mitre_attack_form_data():
    """Return tactic→techniques mapping for Add Event form dropdowns.

    Returns:
      tactics: list of {id, name, slug}
      technique_by_tactic: {slug: [{id, name}]}
      technique_to_tactic: {technique_id: slug}
    """
    # Build tactic list with slugs (kebab-case)
    tactics_list = []
    for t in MITRE_ATTACK_TACTICS:
        slug = t["name"].lower().replace(" ", "-")
        tactics_list.append({"id": t["id"], "name": t["name"], "slug": slug})

    # Group techniques by tactic slug
    technique_by_tactic: dict = {}
    technique_to_tactic: dict = {}
    for tech in MITRE_ATTACK_TECHNIQUES:
        slug = tech["tactic"].lower().replace(" ", "-")
        entry = {"id": tech["id"], "name": tech["name"]}
        technique_by_tactic.setdefault(slug, []).append(entry)
        # Map technique ID → tactic slug (first tactic wins for multi-tactic techniques)
        if tech["id"] not in technique_to_tactic:
            technique_to_tactic[tech["id"]] = slug

    return jsonify({
        "tactics": tactics_list,
        "technique_by_tactic": technique_by_tactic,
        "technique_to_tactic": technique_to_tactic,
    }), 200


# ---------------------------------------------------------------------------
# MITRE D3FEND  — Defensive Countermeasures
# ---------------------------------------------------------------------------


@api_bp.route('/knowledge-base/d3fend', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def kb_d3fend():
    """Return MITRE D3FEND technique reference data."""
    search = request.args.get('search', '').lower()
    tactic = request.args.get('tactic', '')
    attack_id = request.args.get('attack_id', '')

    items = D3FEND_TECHNIQUES
    if search:
        items = [t for t in items if search in t['name'].lower() or search in t['description'].lower() or search in t['id'].lower()]
    if tactic:
        items = [t for t in items if t['tactic'] == tactic]
    if attack_id:
        items = [t for t in items if attack_id in t.get('mitre_attack_mappings', [])]

    return jsonify({'items': items, 'total': len(items), 'tactics': D3FEND_TACTICS}), 200


@api_bp.route('/knowledge-base/d3fend/suggest', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def kb_d3fend_suggest():
    """Given a list of MITRE ATT&CK technique IDs, suggest D3FEND countermeasures.

    Body: { "attack_techniques": ["T1059", "T1078", ...] }
    """
    data = request.get_json() or {}
    techniques = data.get('attack_techniques', [])
    if not techniques:
        return jsonify({'error': 'bad_request', 'message': 'attack_techniques list required'}), 400

    # Build an expanded lookup set: include both exact IDs and parent technique IDs
    # so that sub-techniques like T1059.001 also match D3FEND entries for T1059
    lookup_ids = set(techniques)
    for tid in techniques:
        if '.' in tid:
            lookup_ids.add(tid.split('.')[0])

    suggestions: dict = {}
    for d3 in D3FEND_TECHNIQUES:
        mappings = d3.get('mitre_attack_mappings', [])
        matched = [t for t in lookup_ids if t in mappings]
        if matched:
            suggestions[d3['id']] = {
                **d3,
                'matched_techniques': matched,
            }

    return jsonify({
        'items': list(suggestions.values()),
        'total': len(suggestions),
        'input_techniques': techniques,
    }), 200


# ---------------------------------------------------------------------------
# MITRE ATT&CK Auto-Suggest — keyword/regex pattern matching
# ---------------------------------------------------------------------------

from app.services.mitre_suggest_service import suggest as mitre_suggest, get_all_patterns, save_patterns, reload_patterns


@api_bp.route('/mitre/suggest', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def mitre_auto_suggest():
    """Suggest MITRE techniques for a timeline-event activity description.

    Body: { "activity": "...", "limit": 5 }
    Returns: { "suggestions": [{ "technique", "tactic", "name", "score" }] }
    """
    data = request.get_json() or {}
    activity = data.get('activity', '')
    limit = min(int(data.get('limit', 5)), 20)

    suggestions = mitre_suggest(activity, limit=limit)
    return jsonify({'suggestions': suggestions}), 200


# ---------------------------------------------------------------------------
# MITRE Pattern Management (CRUD)
# ---------------------------------------------------------------------------

@api_bp.route('/mitre/patterns', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_mitre_patterns():
    """Return all MITRE detection patterns."""
    return jsonify({'patterns': get_all_patterns()}), 200


@api_bp.route('/mitre/patterns', methods=['PUT'])
@jwt_required()
@require_permission('admin:manage')
def update_mitre_patterns():
    """Replace the full pattern list.

    Body: { "patterns": [ ... ] }
    Each pattern: { technique, tactic, name, keywords[], regex[]?, weight? }
    """
    data = request.get_json() or {}
    patterns_list = data.get('patterns')
    if patterns_list is None:
        return jsonify({'error': 'bad_request', 'message': 'patterns list required'}), 400

    for p in patterns_list:
        if not p.get('technique') or not p.get('tactic') or not p.get('name'):
            return jsonify({'error': 'bad_request', 'message': 'Each pattern needs technique, tactic, name'}), 400
        if not isinstance(p.get('keywords', []), list):
            return jsonify({'error': 'bad_request', 'message': 'keywords must be a list'}), 400

    save_patterns(patterns_list)
    return jsonify({'message': 'Patterns updated', 'count': len(patterns_list)}), 200


@api_bp.route('/mitre/patterns', methods=['POST'])
@jwt_required()
def add_mitre_pattern():
    """Add a single pattern to the list.

    Body: { technique, tactic, name, keywords[], regex[]?, weight? }
    """
    data = request.get_json() or {}
    if not data.get('technique') or not data.get('tactic') or not data.get('name'):
        return jsonify({'error': 'bad_request', 'message': 'technique, tactic, name required'}), 400

    current = get_all_patterns()
    current.append({
        'technique': data['technique'],
        'tactic': data['tactic'],
        'name': data['name'],
        'keywords': data.get('keywords', []),
        'regex': data.get('regex', []),
        'weight': float(data.get('weight', 0.8)),
    })
    save_patterns(current)
    return jsonify({'message': 'Pattern added', 'count': len(current)}), 201


@api_bp.route('/mitre/patterns/<technique_id>', methods=['DELETE'])
@jwt_required()
def delete_mitre_pattern(technique_id):
    """Remove pattern(s) matching the given technique ID."""
    current = get_all_patterns()
    filtered = [p for p in current if p['technique'] != technique_id]

    if len(filtered) == len(current):
        return jsonify({'error': 'not_found', 'message': f'No pattern for {technique_id}'}), 404

    save_patterns(filtered)
    return jsonify({'message': f'Pattern {technique_id} removed', 'count': len(filtered)}), 200
