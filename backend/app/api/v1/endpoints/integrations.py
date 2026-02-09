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
    """List available integration types."""
    return jsonify({
        'types': [
            {'id': 's3', 'name': 'S3 Storage', 'description': 'Amazon S3 or compatible storage'},
            {'id': 'slack', 'name': 'Slack', 'description': 'Slack notifications via webhook'},
            {'id': 'openai', 'name': 'OpenAI', 'description': 'OpenAI GPT for AI summaries'},
            {'id': 'google_ai', 'name': 'Google AI', 'description': 'Google Gemini for AI summaries'},
            {'id': 'oauth_google', 'name': 'Google OAuth', 'description': 'Google sign-in'},
            {'id': 'oauth_github', 'name': 'GitHub OAuth', 'description': 'GitHub sign-in'},
            {'id': 'oauth_azure', 'name': 'Azure AD', 'description': 'Microsoft Entra ID sign-in'},
            {'id': 'webhook', 'name': 'Webhook', 'description': 'Custom webhook notifications'},
            {'id': 'siem', 'name': 'SIEM', 'description': 'SIEM integration'},
        ]
    }), 200
