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


# ---------------------------------------------------------------------------
# CVE Lookup  (CISA KEV + NVD — no API key required)
# ---------------------------------------------------------------------------

@api_bp.route('/threat-intel/cve/lookup', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def cve_lookup():
    """Look up a CVE by ID using public APIs (NVD + CISA KEV).

    Body: { "cve_id": "CVE-2024-1234" }
    No API key required — uses free public endpoints.
    """
    import requests as req

    data = request.get_json() or {}
    cve_id = data.get('cve_id', '').strip().upper()

    if not cve_id or not cve_id.startswith('CVE-'):
        return jsonify({'error': 'bad_request', 'message': 'Valid CVE ID required (e.g., CVE-2024-1234)'}), 400

    result = {
        'cve_id': cve_id,
        'found': False,
        'nvd': None,
        'kev': None,
    }

    # --- NVD lookup (public, no key needed but rate-limited) ---
    try:
        nvd_resp = req.get(
            f'https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}',
            timeout=15,
            headers={'User-Agent': 'SheetStorm-IR-Platform'}
        )
        if nvd_resp.status_code == 200:
            nvd_data = nvd_resp.json()
            vulns = nvd_data.get('vulnerabilities', [])
            if vulns:
                cve_item = vulns[0].get('cve', {})
                descriptions = cve_item.get('descriptions', [])
                en_desc = next((d['value'] for d in descriptions if d.get('lang') == 'en'), descriptions[0]['value'] if descriptions else '')

                # CVSS extraction — prefer v3.1, fallback to v3.0, then v2.0
                cvss_score = None
                cvss_severity = None
                cvss_vector = None
                metrics = cve_item.get('metrics', {})
                for version_key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
                    metric_list = metrics.get(version_key, [])
                    if metric_list:
                        cvss_data = metric_list[0].get('cvssData', {})
                        cvss_score = cvss_data.get('baseScore')
                        cvss_severity = cvss_data.get('baseSeverity') or metric_list[0].get('baseSeverity')
                        cvss_vector = cvss_data.get('vectorString')
                        break

                # CWE / weakness
                weaknesses = cve_item.get('weaknesses', [])
                cwes = []
                for w in weaknesses:
                    for desc in w.get('description', []):
                        if desc.get('value', '').startswith('CWE-'):
                            cwes.append(desc['value'])

                # References
                refs = [r.get('url') for r in cve_item.get('references', [])[:10]]

                result['found'] = True
                result['nvd'] = {
                    'description': en_desc,
                    'published': cve_item.get('published'),
                    'last_modified': cve_item.get('lastModified'),
                    'cvss_score': cvss_score,
                    'cvss_severity': cvss_severity,
                    'cvss_vector': cvss_vector,
                    'cwes': cwes,
                    'references': refs,
                }
    except req.exceptions.Timeout:
        result['nvd_error'] = 'NVD request timed out'
    except Exception as e:
        result['nvd_error'] = str(e)

    # --- CISA KEV lookup ---
    try:
        kev_resp = req.get(
            'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json',
            timeout=15,
            headers={'User-Agent': 'SheetStorm-IR-Platform'}
        )
        if kev_resp.status_code == 200:
            kev_data = kev_resp.json()
            for vuln in kev_data.get('vulnerabilities', []):
                if vuln.get('cveID') == cve_id:
                    result['found'] = True
                    result['kev'] = {
                        'vendor': vuln.get('vendorProject'),
                        'product': vuln.get('product'),
                        'vulnerability_name': vuln.get('vulnerabilityName'),
                        'date_added': vuln.get('dateAdded'),
                        'due_date': vuln.get('dueDate'),
                        'short_description': vuln.get('shortDescription'),
                        'required_action': vuln.get('requiredAction'),
                        'known_ransomware_use': vuln.get('knownRansomwareCampaignUse', 'Unknown'),
                    }
                    break
    except req.exceptions.Timeout:
        result['kev_error'] = 'CISA KEV request timed out'
    except Exception as e:
        result['kev_error'] = str(e)

    status = 200 if result['found'] else 200  # always 200, found flag tells the story
    return jsonify(result), status


# ---------------------------------------------------------------------------
# IP Reputation Lookup  (AbuseIPDB — requires API key, VT fallback)
# ---------------------------------------------------------------------------

@api_bp.route('/threat-intel/ip/lookup', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def ip_reputation_lookup():
    """Look up IP reputation.  Tries AbuseIPDB first (if configured),
    then VirusTotal, then free ip-api.com for geo only.

    Body: { "ip": "1.2.3.4" }
    """
    import requests as req

    user = get_current_user()
    data = request.get_json() or {}
    ip = data.get('ip', '').strip()

    if not ip:
        return jsonify({'error': 'bad_request', 'message': 'IP address required'}), 400

    result = {'ip': ip, 'sources': {}}

    # --- AbuseIPDB (optional) ---
    abuse_integration = Integration.query.filter_by(
        organization_id=user.organization_id, type='abuseipdb', is_enabled=True
    ).first()
    if abuse_integration and abuse_integration.credentials_encrypted:
        try:
            creds = EncryptionService.decrypt_json(abuse_integration.credentials_encrypted)
            api_key = creds.get('api_key')
            if api_key:
                resp = req.get(
                    'https://api.abuseipdb.com/api/v2/check',
                    params={'ipAddress': ip, 'maxAgeInDays': 90, 'verbose': ''},
                    headers={'Key': api_key, 'Accept': 'application/json'},
                    timeout=10,
                )
                if resp.status_code == 200:
                    d = resp.json().get('data', {})
                    result['sources']['abuseipdb'] = {
                        'abuse_confidence_score': d.get('abuseConfidenceScore'),
                        'total_reports': d.get('totalReports'),
                        'country_code': d.get('countryCode'),
                        'isp': d.get('isp'),
                        'domain': d.get('domain'),
                        'is_tor': d.get('isTor'),
                        'is_whitelisted': d.get('isWhitelisted'),
                        'usage_type': d.get('usageType'),
                        'last_reported_at': d.get('lastReportedAt'),
                    }
        except Exception:
            pass

    # --- VirusTotal (optional) ---
    vt_integration = Integration.query.filter_by(
        organization_id=user.organization_id, type='virustotal', is_enabled=True
    ).first()
    if vt_integration and vt_integration.credentials_encrypted:
        try:
            creds = EncryptionService.decrypt_json(vt_integration.credentials_encrypted)
            api_key = creds.get('api_key')
            if api_key:
                resp = req.get(
                    f'https://www.virustotal.com/api/v3/ip_addresses/{ip}',
                    headers={'x-apikey': api_key},
                    timeout=10,
                )
                if resp.status_code == 200:
                    attrs = resp.json().get('data', {}).get('attributes', {})
                    stats = attrs.get('last_analysis_stats', {})
                    result['sources']['virustotal'] = {
                        'malicious': stats.get('malicious', 0),
                        'suspicious': stats.get('suspicious', 0),
                        'harmless': stats.get('harmless', 0),
                        'undetected': stats.get('undetected', 0),
                        'reputation': attrs.get('reputation', 0),
                        'as_owner': attrs.get('as_owner'),
                        'country': attrs.get('country'),
                    }
        except Exception:
            pass

    # --- Free geo lookup (always available) ---
    try:
        geo_resp = req.get(f'http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,as,query', timeout=5)
        if geo_resp.status_code == 200:
            geo = geo_resp.json()
            if geo.get('status') == 'success':
                result['sources']['geo'] = {
                    'country': geo.get('country'),
                    'region': geo.get('regionName'),
                    'city': geo.get('city'),
                    'isp': geo.get('isp'),
                    'org': geo.get('org'),
                    'as': geo.get('as'),
                }
    except Exception:
        pass

    result['enriched'] = len(result['sources']) > 0
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Domain Reputation Lookup
# ---------------------------------------------------------------------------

@api_bp.route('/threat-intel/domain/lookup', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def domain_reputation_lookup():
    """Look up domain reputation via VirusTotal (if configured).

    Body: { "domain": "evil.com" }
    """
    import requests as req

    user = get_current_user()
    data = request.get_json() or {}
    domain = data.get('domain', '').strip().lower()

    if not domain:
        return jsonify({'error': 'bad_request', 'message': 'Domain required'}), 400

    result = {'domain': domain, 'sources': {}}

    # --- VirusTotal (optional) ---
    vt_integration = Integration.query.filter_by(
        organization_id=user.organization_id, type='virustotal', is_enabled=True
    ).first()
    if vt_integration and vt_integration.credentials_encrypted:
        try:
            creds = EncryptionService.decrypt_json(vt_integration.credentials_encrypted)
            api_key = creds.get('api_key')
            if api_key:
                resp = req.get(
                    f'https://www.virustotal.com/api/v3/domains/{domain}',
                    headers={'x-apikey': api_key},
                    timeout=10,
                )
                if resp.status_code == 200:
                    attrs = resp.json().get('data', {}).get('attributes', {})
                    stats = attrs.get('last_analysis_stats', {})
                    result['sources']['virustotal'] = {
                        'malicious': stats.get('malicious', 0),
                        'suspicious': stats.get('suspicious', 0),
                        'harmless': stats.get('harmless', 0),
                        'undetected': stats.get('undetected', 0),
                        'reputation': attrs.get('reputation', 0),
                        'registrar': attrs.get('registrar'),
                        'creation_date': attrs.get('creation_date'),
                        'last_analysis_date': attrs.get('last_analysis_date'),
                        'categories': attrs.get('categories', {}),
                    }
        except Exception:
            pass

    result['enriched'] = len(result['sources']) > 0
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Email Reputation Lookup
# ---------------------------------------------------------------------------

@api_bp.route('/threat-intel/email/lookup', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def email_reputation_lookup():
    """Look up email address in breach databases.
    Uses Have I Been Pwned API if configured, otherwise returns
    a stub indicating the integration is not set up.

    Body: { "email": "user@example.com" }
    """
    import requests as req

    user = get_current_user()
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    if not email or '@' not in email:
        return jsonify({'error': 'bad_request', 'message': 'Valid email required'}), 400

    result = {'email': email, 'sources': {}}

    # --- Have I Been Pwned (optional — requires paid API key) ---
    hibp_integration = Integration.query.filter_by(
        organization_id=user.organization_id, type='hibp', is_enabled=True
    ).first()
    if hibp_integration and hibp_integration.credentials_encrypted:
        try:
            creds = EncryptionService.decrypt_json(hibp_integration.credentials_encrypted)
            api_key = creds.get('api_key')
            if api_key:
                resp = req.get(
                    f'https://haveibeenpwned.com/api/v3/breachedaccount/{email}',
                    headers={
                        'hibp-api-key': api_key,
                        'User-Agent': 'SheetStorm-IR-Platform',
                    },
                    params={'truncateResponse': 'false'},
                    timeout=10,
                )
                if resp.status_code == 200:
                    breaches = resp.json()
                    result['sources']['hibp'] = {
                        'breach_count': len(breaches),
                        'breaches': [
                            {
                                'name': b.get('Name'),
                                'domain': b.get('Domain'),
                                'breach_date': b.get('BreachDate'),
                                'added_date': b.get('AddedDate'),
                                'pwn_count': b.get('PwnCount'),
                                'data_classes': b.get('DataClasses', []),
                                'is_verified': b.get('IsVerified'),
                            }
                            for b in breaches[:20]
                        ],
                    }
                elif resp.status_code == 404:
                    result['sources']['hibp'] = {'breach_count': 0, 'breaches': []}
        except Exception:
            pass

    result['enriched'] = len(result['sources']) > 0
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Ransomware Victim Lookup  (ransomware.live — free, no key)
# ---------------------------------------------------------------------------

@api_bp.route('/threat-intel/ransomware/lookup', methods=['POST'])
@jwt_required()
@require_permission('incidents:read')
def ransomware_victim_lookup():
    """Search ransomware.live for victim postings.

    Body: { "query": "company name" }
    No API key required — public API.
    """
    import requests as req

    data = request.get_json() or {}
    query = data.get('query', '').strip()

    if not query or len(query) < 3:
        return jsonify({'error': 'bad_request', 'message': 'Search query must be at least 3 characters'}), 400

    try:
        resp = req.get(
            f'https://api.ransomware.live/v2/victims/{query}',
            timeout=15,
            headers={'User-Agent': 'SheetStorm-IR-Platform'},
        )

        if resp.status_code == 200:
            victims = resp.json()
            if not isinstance(victims, list):
                victims = []

            results = [
                {
                    'victim': v.get('victim', v.get('post_title', 'Unknown')),
                    'group': v.get('group_name', v.get('group', 'Unknown')),
                    'discovered': v.get('discovered', v.get('post_date')),
                    'country': v.get('country'),
                    'domain': v.get('website', v.get('domain')),
                    'description': v.get('description'),
                    'activity': v.get('activity'),
                }
                for v in victims[:50]
            ]

            return jsonify({
                'query': query,
                'found': len(results) > 0,
                'items': results,
                'total': len(results),
            }), 200
        elif resp.status_code == 404:
            return jsonify({'query': query, 'found': False, 'items': [], 'total': 0}), 200
        else:
            return jsonify({'error': 'upstream_error', 'message': f'ransomware.live returned {resp.status_code}'}), 502

    except req.exceptions.Timeout:
        return jsonify({'error': 'timeout', 'message': 'ransomware.live request timed out'}), 504
    except Exception as e:
        return jsonify({'error': 'server_error', 'message': str(e)}), 500
