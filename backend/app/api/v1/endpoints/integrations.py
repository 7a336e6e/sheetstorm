"""Integration configuration endpoints"""
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Integration
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log
from app.services.encryption_service import encryption_service


@api_bp.route('/integrations', methods=['GET'])
@jwt_required()
@require_permission('integrations:read')
def list_integrations():
    """List all integrations for the organization."""
    user = get_current_user()

    integrations = Integration.query.filter_by(organization_id=user.organization_id).all()

    return jsonify({
        'items': [i.to_dict() for i in integrations]
    }), 200


@api_bp.route('/integrations/<uuid:integration_id>', methods=['GET'])
@jwt_required()
@require_permission('integrations:read')
def get_integration(integration_id):
    """Get integration details."""
    user = get_current_user()

    integration = Integration.query.filter_by(
        id=integration_id,
        organization_id=user.organization_id
    ).first()

    if not integration:
        return jsonify({'error': 'not_found', 'message': 'Integration not found'}), 404

    return jsonify(integration.to_dict()), 200


@api_bp.route('/integrations', methods=['POST'])
@jwt_required()
@require_permission('integrations:create')
@audit_log('admin_action', 'create', 'integration')
def create_integration():
    """Create a new integration."""
    user = get_current_user()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    integration_type = data.get('type', '').strip()
    if integration_type not in Integration.INTEGRATION_TYPES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid integration type'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'bad_request', 'message': 'name is required'}), 400

    # Check for duplicate
    existing = Integration.query.filter_by(
        organization_id=user.organization_id,
        type=integration_type,
        name=name
    ).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'Integration with this name already exists'}), 409

    # Encrypt credentials if provided
    credentials_encrypted = None
    if data.get('credentials'):
        import json
        credentials_json = json.dumps(data['credentials'])
        credentials_encrypted = encryption_service.encrypt(credentials_json)

    integration = Integration(
        organization_id=user.organization_id,
        type=integration_type,
        name=name,
        is_enabled=data.get('is_enabled', True),
        config=data.get('config', {}),
        credentials_encrypted=credentials_encrypted,
        created_by=user.id
    )

    db.session.add(integration)
    db.session.commit()

    return jsonify(integration.to_dict()), 201


@api_bp.route('/integrations/<uuid:integration_id>', methods=['PUT'])
@jwt_required()
@require_permission('integrations:update')
@audit_log('admin_action', 'update', 'integration')
def update_integration(integration_id):
    """Update an integration."""
    user = get_current_user()
    data = request.get_json()

    integration = Integration.query.filter_by(
        id=integration_id,
        organization_id=user.organization_id
    ).first()

    if not integration:
        return jsonify({'error': 'not_found', 'message': 'Integration not found'}), 404

    if 'name' in data:
        integration.name = data['name'].strip()
    if 'is_enabled' in data:
        integration.is_enabled = data['is_enabled']
    if 'config' in data:
        integration.config = data['config']

    # Update credentials if provided
    if 'credentials' in data:
        if data['credentials']:
            import json
            credentials_json = json.dumps(data['credentials'])
            integration.credentials_encrypted = encryption_service.encrypt(credentials_json)
        else:
            integration.credentials_encrypted = None

    db.session.commit()

    return jsonify(integration.to_dict()), 200


@api_bp.route('/integrations/<uuid:integration_id>', methods=['DELETE'])
@jwt_required()
@require_permission('integrations:delete')
@audit_log('admin_action', 'delete', 'integration')
def delete_integration(integration_id):
    """Delete an integration."""
    user = get_current_user()

    integration = Integration.query.filter_by(
        id=integration_id,
        organization_id=user.organization_id
    ).first()

    if not integration:
        return jsonify({'error': 'not_found', 'message': 'Integration not found'}), 404

    db.session.delete(integration)
    db.session.commit()

    return jsonify({'message': 'Integration deleted'}), 200


@api_bp.route('/integrations/<uuid:integration_id>/test', methods=['POST'])
@jwt_required()
@require_permission('integrations:update')
def test_integration(integration_id):
    """Test an integration connection."""
    user = get_current_user()

    integration = Integration.query.filter_by(
        id=integration_id,
        organization_id=user.organization_id
    ).first()

    if not integration:
        return jsonify({'error': 'not_found', 'message': 'Integration not found'}), 404

    # Get decrypted credentials
    credentials = None
    if integration.credentials_encrypted:
        import json
        decrypted = encryption_service.decrypt(integration.credentials_encrypted)
        if decrypted:
            credentials = json.loads(decrypted)

    success = False
    message = 'Unknown integration type'

    try:
        if integration.type == 's3':
            success, message = _test_s3(integration.config, credentials)
        elif integration.type == 'slack':
            success, message = _test_slack(integration.config, credentials)
        elif integration.type == 'openai':
            success, message = _test_openai(credentials)
        elif integration.type == 'google_ai':
            success, message = _test_google_ai(credentials)
        elif integration.type == 'email_smtp':
            success, message = _test_smtp(integration.config, credentials)
        elif integration.type == 'misp':
            success, message = _test_misp(integration.config, credentials)
        elif integration.type == 'virustotal':
            success, message = _test_virustotal(credentials)
        elif integration.type == 'velociraptor':
            success, message = _test_velociraptor(integration.config, credentials)
        elif integration.type == 'thehive':
            success, message = _test_thehive(integration.config, credentials)
        elif integration.type == 'cortex':
            success, message = _test_cortex(integration.config, credentials)
        elif integration.type == 'jira':
            success, message = _test_jira(integration.config, credentials)
        elif integration.type == 'splunk':
            success, message = _test_splunk(integration.config, credentials)
        elif integration.type == 'elastic':
            success, message = _test_elastic(integration.config, credentials)
        elif integration.type == 'webhook':
            success, message = _test_webhook(integration.config, credentials)
        elif integration.type in ('oauth_github', 'oauth_google', 'oauth_azure'):
            success, message = _test_oauth(integration.type, integration.config, credentials)
        else:
            message = f'Testing not implemented for {integration.type}'
    except Exception as e:
        message = str(e)

    # Update last used/error
    from datetime import datetime, timezone
    integration.last_used_at = datetime.now(timezone.utc)
    if not success:
        integration.last_error = message
    else:
        integration.last_error = None
    db.session.commit()

    return jsonify({
        'success': success,
        'message': message
    }), 200 if success else 400


def _test_s3(config, credentials):
    """Test S3 connection."""
    import boto3
    try:
        client = boto3.client(
            's3',
            endpoint_url=config.get('endpoint'),
            aws_access_key_id=credentials.get('access_key'),
            aws_secret_access_key=credentials.get('secret_key'),
            region_name=config.get('region', 'us-east-1')
        )
        client.list_buckets()
        return True, 'S3 connection successful'
    except Exception as e:
        return False, f'S3 connection failed: {str(e)}'


def _test_slack(config, credentials):
    """Test Slack webhook."""
    import requests
    try:
        webhook_url = credentials.get('webhook_url') or config.get('webhook_url')
        response = requests.post(
            webhook_url,
            json={'text': 'SheetStorm integration test'},
            timeout=10
        )
        if response.status_code == 200:
            return True, 'Slack webhook test successful'
        return False, f'Slack returned status {response.status_code}'
    except Exception as e:
        return False, f'Slack test failed: {str(e)}'


def _test_openai(credentials):
    """Test OpenAI API."""
    try:
        import openai
        client = openai.OpenAI(api_key=credentials.get('api_key'))
        client.models.list()
        return True, 'OpenAI connection successful'
    except Exception as e:
        return False, f'OpenAI test failed: {str(e)}'


def _test_google_ai(credentials):
    """Test Google AI API."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=credentials.get('api_key'))
        model = genai.GenerativeModel('gemini-pro')
        model.generate_content('Test')
        return True, 'Google AI connection successful'
    except Exception as e:
        return False, f'Google AI test failed: {str(e)}'


@api_bp.route('/integrations/types', methods=['GET'])
@jwt_required()
def list_integration_types():
    """List available integration types with categories, config and credential fields."""
    return jsonify({
        'types': [
            # Storage
            {'id': 's3', 'name': 'S3 Storage', 'description': 'Amazon S3 or S3-compatible object storage for artifacts', 'category': 'storage',
             'config_fields': ['bucket_name', 'region', 'endpoint_url'], 'credential_fields': ['access_key', 'secret_key']},
            {'id': 'google_drive', 'name': 'Google Drive', 'description': 'Google Drive for case folder management and report storage', 'category': 'storage',
             'config_fields': ['folder_id'], 'credential_fields': ['api_key']},
            # AI Providers
            {'id': 'openai', 'name': 'OpenAI', 'description': 'OpenAI GPT models for AI-powered report generation and analysis', 'category': 'ai',
             'config_fields': ['model'], 'credential_fields': ['api_key']},
            {'id': 'google_ai', 'name': 'Google AI', 'description': 'Google Gemini models for AI-powered analysis', 'category': 'ai',
             'config_fields': ['model'], 'credential_fields': ['api_key']},
            # Notification
            {'id': 'slack', 'name': 'Slack', 'description': 'Send incident notifications and alerts to Slack channels', 'category': 'notification',
             'config_fields': [], 'credential_fields': ['webhook_url']},
            {'id': 'email_smtp', 'name': 'Email (SMTP)', 'description': 'Send email notifications and alerts via SMTP', 'category': 'notification',
             'config_fields': ['smtp_host', 'smtp_port', 'from_address'], 'credential_fields': ['smtp_user', 'smtp_password']},
            {'id': 'webhook', 'name': 'Webhook', 'description': 'Send event notifications to custom webhook endpoints', 'category': 'notification',
             'config_fields': ['url'], 'credential_fields': ['token']},
            # Threat Intelligence
            {'id': 'misp', 'name': 'MISP', 'description': 'Share threat intelligence via MISP platform (IOC push/pull)', 'category': 'threat_intel',
             'config_fields': ['api_url', 'verify_ssl'], 'credential_fields': ['api_key']},
            {'id': 'virustotal', 'name': 'VirusTotal', 'description': 'Automated hash/URL/domain lookups via VirusTotal API', 'category': 'threat_intel',
             'config_fields': [], 'credential_fields': ['api_key']},
            {'id': 'mitre_attack', 'name': 'MITRE ATT&CK', 'description': 'MITRE ATT&CK framework data feed for tactic/technique mapping', 'category': 'threat_intel',
             'config_fields': ['api_url'], 'credential_fields': []},
            # IR Tools
            {'id': 'velociraptor', 'name': 'Velociraptor', 'description': 'Endpoint monitoring and forensic collection via Velociraptor', 'category': 'ir_tools',
             'config_fields': ['api_url', 'verify_ssl'], 'credential_fields': ['api_key']},
            {'id': 'thehive', 'name': 'TheHive', 'description': 'Security incident response platform for case management', 'category': 'ir_tools',
             'config_fields': ['api_url'], 'credential_fields': ['api_key']},
            {'id': 'cortex', 'name': 'Cortex', 'description': 'Observable analysis and active response engine', 'category': 'ir_tools',
             'config_fields': ['api_url'], 'credential_fields': ['api_key']},
            # Ticketing
            {'id': 'jira', 'name': 'Jira', 'description': 'Create and sync Jira tickets from incident tasks', 'category': 'ticketing',
             'config_fields': ['api_url', 'project_key'], 'credential_fields': ['username', 'api_key']},
            # SIEM
            {'id': 'splunk', 'name': 'Splunk', 'description': 'Query Splunk for log data and forward alerts', 'category': 'siem',
             'config_fields': ['api_url', 'index'], 'credential_fields': ['token']},
            {'id': 'elastic', 'name': 'Elastic SIEM', 'description': 'Query Elasticsearch/Kibana for log data and alerts', 'category': 'siem',
             'config_fields': ['api_url', 'index', 'verify_ssl'], 'credential_fields': ['api_key']},
            {'id': 'siem', 'name': 'Generic SIEM', 'description': 'Generic SIEM integration via syslog or API', 'category': 'siem',
             'config_fields': ['api_url'], 'credential_fields': ['api_key']},
            # Authentication
            {'id': 'oauth_google', 'name': 'Google OAuth', 'description': 'Allow users to sign in with Google accounts', 'category': 'auth',
             'config_fields': ['client_id'], 'credential_fields': ['client_secret']},
            {'id': 'oauth_github', 'name': 'GitHub OAuth', 'description': 'Allow users to sign in with GitHub accounts', 'category': 'auth',
             'config_fields': ['client_id'], 'credential_fields': ['client_secret']},
            {'id': 'oauth_azure', 'name': 'Azure AD / Entra ID', 'description': 'Microsoft Entra ID (Azure AD) for enterprise SSO', 'category': 'auth',
             'config_fields': ['client_id', 'tenant_id'], 'credential_fields': ['client_secret']},
        ],
        'categories': [
            {'id': 'storage', 'name': 'Storage', 'description': 'File and artifact storage'},
            {'id': 'ai', 'name': 'AI Providers', 'description': 'AI models for analysis and reporting'},
            {'id': 'notification', 'name': 'Notifications', 'description': 'Alerts and notifications'},
            {'id': 'threat_intel', 'name': 'Threat Intelligence', 'description': 'IOC enrichment and sharing'},
            {'id': 'ir_tools', 'name': 'IR Tools', 'description': 'Forensic tools and IR platforms'},
            {'id': 'ticketing', 'name': 'Ticketing', 'description': 'Issue tracking and task management'},
            {'id': 'siem', 'name': 'SIEM', 'description': 'Security information and event management'},
            {'id': 'auth', 'name': 'Authentication', 'description': 'Single sign-on and OAuth providers'},
        ]
    }), 200


def _test_smtp(config, credentials):
    """Test SMTP connection."""
    import smtplib
    try:
        host = config.get('host', 'localhost')
        port = int(config.get('port', 587))
        use_tls = config.get('use_tls', True)

        if use_tls:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP(host, port, timeout=10)

        username = credentials.get('username') if credentials else None
        password = credentials.get('password') if credentials else None
        if username and password:
            server.login(username, password)

        server.quit()
        return True, 'SMTP connection successful'
    except Exception as e:
        return False, f'SMTP test failed: {str(e)}'


def _test_misp(config, credentials):
    """Test MISP connection."""
    import requests
    try:
        url = config.get('url', '').rstrip('/')
        api_key = credentials.get('api_key') if credentials else ''
        verify_ssl = config.get('verify_ssl', True)

        resp = requests.get(
            f'{url}/servers/getPyMISPVersion.json',
            headers={'Authorization': api_key, 'Accept': 'application/json'},
            verify=verify_ssl,
            timeout=10
        )
        if resp.status_code == 200:
            return True, f'MISP connection successful (version: {resp.json().get("version", "unknown")})'
        return False, f'MISP returned status {resp.status_code}'
    except Exception as e:
        return False, f'MISP test failed: {str(e)}'


def _test_virustotal(credentials):
    """Test VirusTotal API."""
    import requests
    try:
        api_key = credentials.get('api_key') if credentials else ''
        resp = requests.get(
            'https://www.virustotal.com/api/v3/users/me',
            headers={'x-apikey': api_key},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json().get('data', {}).get('attributes', {})
            quotas = data.get('quotas', {})
            return True, f'VirusTotal API connected. User: {data.get("user_id", "unknown")}'
        return False, f'VirusTotal returned status {resp.status_code}'
    except Exception as e:
        return False, f'VirusTotal test failed: {str(e)}'


def _test_velociraptor(config, credentials):
    """Test Velociraptor API connection."""
    import requests
    try:
        url = config.get('url', '').rstrip('/')
        api_key = credentials.get('api_key') if credentials else ''
        verify_ssl = config.get('verify_ssl', False)

        resp = requests.get(
            f'{url}/api/v1/GetServerMonitoringState',
            headers={'Grpc-Metadata-Authorization': f'Bearer {api_key}'},
            verify=verify_ssl,
            timeout=10
        )
        if resp.status_code == 200:
            return True, 'Velociraptor API connection successful'
        return False, f'Velociraptor returned status {resp.status_code}'
    except Exception as e:
        return False, f'Velociraptor test failed: {str(e)}'


def _test_thehive(config, credentials):
    """Test TheHive connection."""
    import requests
    try:
        url = config.get('url', '').rstrip('/')
        api_key = credentials.get('api_key') if credentials else ''

        resp = requests.get(
            f'{url}/api/v1/user/current',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=10
        )
        if resp.status_code == 200:
            user = resp.json().get('login', 'unknown')
            return True, f'TheHive connection successful (user: {user})'
        return False, f'TheHive returned status {resp.status_code}'
    except Exception as e:
        return False, f'TheHive test failed: {str(e)}'


def _test_cortex(config, credentials):
    """Test Cortex connection."""
    import requests
    try:
        url = config.get('url', '').rstrip('/')
        api_key = credentials.get('api_key') if credentials else ''

        resp = requests.get(
            f'{url}/api/analyzer',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=10
        )
        if resp.status_code == 200:
            analyzers = resp.json()
            return True, f'Cortex connection successful ({len(analyzers)} analyzers available)'
        return False, f'Cortex returned status {resp.status_code}'
    except Exception as e:
        return False, f'Cortex test failed: {str(e)}'


def _test_jira(config, credentials):
    """Test Jira connection."""
    import requests
    from requests.auth import HTTPBasicAuth
    try:
        url = config.get('url', '').rstrip('/')
        email = credentials.get('email') if credentials else ''
        api_token = credentials.get('api_token') if credentials else ''

        resp = requests.get(
            f'{url}/rest/api/3/myself',
            auth=HTTPBasicAuth(email, api_token),
            timeout=10
        )
        if resp.status_code == 200:
            user = resp.json().get('displayName', 'unknown')
            return True, f'Jira connection successful (user: {user})'
        return False, f'Jira returned status {resp.status_code}'
    except Exception as e:
        return False, f'Jira test failed: {str(e)}'


def _test_splunk(config, credentials):
    """Test Splunk connection."""
    import requests
    try:
        url = config.get('url', '').rstrip('/')
        token = credentials.get('token') if credentials else ''
        verify_ssl = config.get('verify_ssl', False)

        resp = requests.get(
            f'{url}/services/server/info',
            headers={'Authorization': f'Bearer {token}'},
            params={'output_mode': 'json'},
            verify=verify_ssl,
            timeout=10
        )
        if resp.status_code == 200:
            return True, 'Splunk connection successful'
        return False, f'Splunk returned status {resp.status_code}'
    except Exception as e:
        return False, f'Splunk test failed: {str(e)}'


def _test_elastic(config, credentials):
    """Test Elasticsearch connection."""
    import requests
    try:
        url = config.get('url', '').rstrip('/')
        api_key = credentials.get('api_key') if credentials else ''
        username = credentials.get('username') if credentials else ''
        password = credentials.get('password') if credentials else ''

        headers = {}
        auth = None
        if api_key:
            headers['Authorization'] = f'ApiKey {api_key}'
        elif username and password:
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(username, password)

        resp = requests.get(
            f'{url}/_cluster/health',
            headers=headers,
            auth=auth,
            timeout=10
        )
        if resp.status_code == 200:
            health = resp.json()
            return True, f'Elasticsearch connected. Cluster: {health.get("cluster_name")}, Status: {health.get("status")}'
        return False, f'Elasticsearch returned status {resp.status_code}'
    except Exception as e:
        return False, f'Elasticsearch test failed: {str(e)}'


def _test_webhook(config, credentials):
    """Test webhook endpoint."""
    import requests
    try:
        url = config.get('url') or (credentials.get('url') if credentials else '')
        if not url:
            return False, 'No webhook URL configured'

        resp = requests.post(
            url,
            json={'event': 'test', 'source': 'SheetStorm', 'message': 'Integration test'},
            timeout=10
        )
        if resp.status_code < 300:
            return True, f'Webhook test successful (status {resp.status_code})'
        return False, f'Webhook returned status {resp.status_code}'
    except Exception as e:
        return False, f'Webhook test failed: {str(e)}'


def _test_oauth(oauth_type, config, credentials):
    """Test OAuth credentials validity."""
    client_id = config.get('client_id', '')
    has_secret = bool(credentials and credentials.get('client_secret'))

    if not client_id:
        return False, 'Client ID is not configured'
    if not has_secret:
        return False, 'Client Secret is not configured'

    return True, f'OAuth credentials configured (Client ID: {client_id[:8]}...)'
