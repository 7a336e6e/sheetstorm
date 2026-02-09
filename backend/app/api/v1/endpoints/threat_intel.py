"""Threat intelligence endpoints for IOC enrichment and sharing."""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Integration
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log
from app.services.encryption_service import EncryptionService


@api_bp.route('/threat-intel/virustotal/lookup', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def virustotal_lookup():
    """Look up a hash, URL, domain, or IP on VirusTotal.
    
    Body: { "type": "hash|url|domain|ip", "value": "..." }
    """
    import requests as req

    user = get_current_user()
    data = request.get_json()

    lookup_type = data.get('type', 'hash')
    value = data.get('value', '').strip()

    if not value:
        return jsonify({'error': 'bad_request', 'message': 'Value is required'}), 400

    # Get VirusTotal API key from integration config
    integration = Integration.query.filter_by(
        organization_id=user.organization_id,
        type='virustotal',
        is_enabled=True
    ).first()

    api_key = None
    if integration and integration.credentials_encrypted:
        try:
            creds = EncryptionService.decrypt_json(integration.credentials_encrypted)
            api_key = creds.get('api_key')
        except Exception:
            pass

    if not api_key:
        return jsonify({'error': 'not_configured', 'message': 'VirusTotal integration not configured'}), 400

    headers = {'x-apikey': api_key}
    base_url = 'https://www.virustotal.com/api/v3'

    try:
        if lookup_type == 'hash':
            resp = req.get(f'{base_url}/files/{value}', headers=headers, timeout=15)
        elif lookup_type == 'url':
            # URL needs to be base64-encoded for VT API
            import base64
            url_id = base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')
            resp = req.get(f'{base_url}/urls/{url_id}', headers=headers, timeout=15)
        elif lookup_type == 'domain':
            resp = req.get(f'{base_url}/domains/{value}', headers=headers, timeout=15)
        elif lookup_type == 'ip':
            resp = req.get(f'{base_url}/ip_addresses/{value}', headers=headers, timeout=15)
        else:
            return jsonify({'error': 'bad_request', 'message': f'Invalid lookup type: {lookup_type}'}), 400

        if resp.status_code == 404:
            return jsonify({
                'found': False,
                'type': lookup_type,
                'value': value,
                'message': 'Not found in VirusTotal'
            }), 200

        if resp.status_code != 200:
            return jsonify({'error': 'vt_error', 'message': f'VirusTotal returned status {resp.status_code}'}), 502

        vt_data = resp.json().get('data', {})
        attrs = vt_data.get('attributes', {})

        # Extract relevant summary
        result = {
            'found': True,
            'type': lookup_type,
            'value': value,
            'id': vt_data.get('id'),
        }

        if lookup_type == 'hash':
            stats = attrs.get('last_analysis_stats', {})
            result.update({
                'malicious': stats.get('malicious', 0),
                'suspicious': stats.get('suspicious', 0),
                'undetected': stats.get('undetected', 0),
                'harmless': stats.get('harmless', 0),
                'total_engines': sum(stats.values()),
                'detection_ratio': f"{stats.get('malicious', 0)}/{sum(stats.values())}",
                'file_name': attrs.get('meaningful_name') or attrs.get('names', [None])[0] if attrs.get('names') else None,
                'file_type': attrs.get('type_description'),
                'file_size': attrs.get('size'),
                'sha256': attrs.get('sha256'),
                'md5': attrs.get('md5'),
                'sha1': attrs.get('sha1'),
                'first_seen': attrs.get('first_submission_date'),
                'last_seen': attrs.get('last_analysis_date'),
                'tags': attrs.get('tags', []),
                'popular_threat_names': [
                    r.get('value') for r in attrs.get('popular_threat_classification', {}).get('suggested_threat_label', [])
                ] if attrs.get('popular_threat_classification') else [],
            })
        elif lookup_type in ('domain', 'ip'):
            stats = attrs.get('last_analysis_stats', {})
            result.update({
                'malicious': stats.get('malicious', 0),
                'suspicious': stats.get('suspicious', 0),
                'harmless': stats.get('harmless', 0),
                'undetected': stats.get('undetected', 0),
                'total_engines': sum(stats.values()),
                'reputation': attrs.get('reputation', 0),
                'registrar': attrs.get('registrar') if lookup_type == 'domain' else None,
                'country': attrs.get('country') if lookup_type == 'ip' else None,
                'as_owner': attrs.get('as_owner') if lookup_type == 'ip' else None,
                'last_analysis_date': attrs.get('last_analysis_date'),
            })
        elif lookup_type == 'url':
            stats = attrs.get('last_analysis_stats', {})
            result.update({
                'malicious': stats.get('malicious', 0),
                'suspicious': stats.get('suspicious', 0),
                'harmless': stats.get('harmless', 0),
                'undetected': stats.get('undetected', 0),
                'total_engines': sum(stats.values()),
                'final_url': attrs.get('last_final_url'),
                'title': attrs.get('title'),
            })

        return jsonify(result), 200

    except req.exceptions.Timeout:
        return jsonify({'error': 'timeout', 'message': 'VirusTotal request timed out'}), 504
    except Exception as e:
        return jsonify({'error': 'server_error', 'message': str(e)}), 500


@api_bp.route('/threat-intel/misp/push', methods=['POST'])
@jwt_required()
@require_permission('incidents:update')
@audit_log('data_modification', 'push_ioc', 'misp')
def misp_push_ioc():
    """Push IOCs to MISP as events/attributes.
    
    Body: {
        "incident_id": "uuid",
        "iocs": [
            { "type": "ip-dst", "value": "1.2.3.4", "comment": "C2 server" },
            { "type": "md5", "value": "abc123...", "comment": "Malware hash" }
        ],
        "event_info": "Optional MISP event title"
    }
    """
    import requests as req

    user = get_current_user()
    data = request.get_json()

    iocs = data.get('iocs', [])
    if not iocs:
        return jsonify({'error': 'bad_request', 'message': 'No IOCs provided'}), 400

    # Get MISP integration
    integration = Integration.query.filter_by(
        organization_id=user.organization_id,
        type='misp',
        is_enabled=True
    ).first()

    if not integration:
        return jsonify({'error': 'not_configured', 'message': 'MISP integration not configured'}), 400

    api_url = integration.config.get('api_url', integration.config.get('url', '')).rstrip('/')
    verify_ssl = integration.config.get('verify_ssl', True)
    api_key = None

    if integration.credentials_encrypted:
        try:
            creds = EncryptionService.decrypt_json(integration.credentials_encrypted)
            api_key = creds.get('api_key')
        except Exception:
            pass

    if not api_key or not api_url:
        return jsonify({'error': 'not_configured', 'message': 'MISP API URL or key missing'}), 400

    headers = {
        'Authorization': api_key,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }

    try:
        # Create MISP event
        event_info = data.get('event_info', f'IOCs from SheetStorm incident')
        event_payload = {
            'Event': {
                'info': event_info,
                'distribution': 0,  # Organization only
                'threat_level_id': 2,  # Medium
                'analysis': 1,  # Ongoing
                'Attribute': [
                    {
                        'type': ioc.get('type', 'text'),
                        'value': ioc.get('value'),
                        'comment': ioc.get('comment', ''),
                        'to_ids': True,
                        'category': _misp_type_to_category(ioc.get('type', 'text')),
                    }
                    for ioc in iocs if ioc.get('value')
                ]
            }
        }

        resp = req.post(
            f'{api_url}/events',
            json=event_payload,
            headers=headers,
            verify=verify_ssl,
            timeout=30
        )

        if resp.status_code in (200, 201):
            misp_event = resp.json().get('Event', {})
            return jsonify({
                'success': True,
                'misp_event_id': misp_event.get('id'),
                'misp_event_uuid': misp_event.get('uuid'),
                'attributes_pushed': len(iocs),
                'message': f'Successfully pushed {len(iocs)} IOC(s) to MISP'
            }), 201
        else:
            return jsonify({
                'error': 'misp_error',
                'message': f'MISP returned status {resp.status_code}: {resp.text[:200]}'
            }), 502

    except req.exceptions.Timeout:
        return jsonify({'error': 'timeout', 'message': 'MISP request timed out'}), 504
    except Exception as e:
        return jsonify({'error': 'server_error', 'message': str(e)}), 500


def _misp_type_to_category(ioc_type: str) -> str:
    """Map MISP attribute type to category."""
    mapping = {
        'ip-src': 'Network activity',
        'ip-dst': 'Network activity',
        'domain': 'Network activity',
        'hostname': 'Network activity',
        'url': 'Network activity',
        'email-src': 'Network activity',
        'email-dst': 'Network activity',
        'md5': 'Payload delivery',
        'sha1': 'Payload delivery',
        'sha256': 'Payload delivery',
        'filename': 'Payload delivery',
        'filename|md5': 'Payload delivery',
        'filename|sha256': 'Payload delivery',
        'mutex': 'Artifacts dropped',
        'regkey': 'Persistence mechanism',
    }
    return mapping.get(ioc_type, 'External analysis')
