"""Google Drive integration endpoints for artifact upload and case management."""
import json
import re
import secrets
from urllib.parse import quote
from flask import jsonify, request, g, redirect, current_app
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Integration, Artifact, Incident
from app.middleware.rbac import require_permission, require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.google_drive_service import google_drive_service
from app.services.encryption_service import encryption_service
from app.services.storage_service import storage_service


def _get_drive_integration(user):
    """Get the user's org Google Drive integration with decrypted credentials."""
    integration = Integration.query.filter_by(
        organization_id=user.organization_id,
        type='google_drive',
        is_enabled=True,
    ).first()

    if not integration:
        return None, None

    if not integration.credentials_encrypted:
        return integration, None

    try:
        creds_json = encryption_service.decrypt(integration.credentials_encrypted)
        creds = json.loads(creds_json)
        return integration, creds
    except Exception:
        return integration, None


def _get_valid_access_token(integration, creds):
    """Get a valid access token, always refreshing to avoid expired tokens."""
    if not creds or 'refresh_token' not in creds:
        return None

    try:
        new_tokens = google_drive_service.refresh_access_token(
            creds['refresh_token'], org_id=str(integration.organization_id))
        creds['access_token'] = new_tokens['access_token']
        # Save updated tokens
        creds_json = json.dumps(creds)
        integration.credentials_encrypted = encryption_service.encrypt(creds_json)
        db.session.commit()
        return new_tokens['access_token']
    except Exception as e:
        current_app.logger.error(f"Failed to refresh Google Drive token: {e}")
        return None


@api_bp.route('/google-drive/status', methods=['GET'])
@jwt_required()
@require_permission('integrations:read')
def google_drive_status():
    """Check Google Drive integration status."""
    user = get_current_user()

    if not google_drive_service.is_configured(str(user.organization_id)):
        return jsonify({
            'configured': False,
            'connected': False,
            'message': 'Google Drive OAuth not configured. Add your Client ID and Client Secret on the Settings → Integrations page.',
        }), 200

    integration, creds = _get_drive_integration(user)

    if not integration or not creds:
        return jsonify({
            'configured': True,
            'connected': False,
            'message': 'Google Drive not connected. Click Connect to link your account.',
        }), 200

    # Try to get user info to verify connection
    access_token = _get_valid_access_token(integration, creds)
    if not access_token:
        return jsonify({
            'configured': True,
            'connected': False,
            'message': 'Google Drive connection expired. Please reconnect.',
        }), 200

    try:
        user_info = google_drive_service.get_user_info(access_token)
        return jsonify({
            'configured': True,
            'connected': True,
            'root_folder_id': creds.get('root_folder_id', ''),
            'root_folder_name': creds.get('root_folder_name', ''),
        }), 200
    except Exception:
        return jsonify({
            'configured': True,
            'connected': False,
            'message': 'Google Drive connection expired. Please reconnect.',
        }), 200


_DRIVE_STATE_TTL = 600  # seconds an OAuth `state` stays valid


def _drive_state_key(state):
    return f'gdrive_oauth_state:{state}'


@api_bp.route('/google-drive/auth', methods=['POST'])
@jwt_required()
@require_permission('integrations:create')
def google_drive_auth():
    """Initiate Google Drive OAuth flow. Returns the auth URL.

    The OAuth `state` is bound server-side (Redis, TTL) to the initiating
    user + organization; the callback only accepts a state it issued.
    """
    from app import redis_client
    user = get_current_user()
    org_id = str(user.organization_id)
    if not google_drive_service.is_configured(org_id):
        return jsonify({'error': 'not_configured', 'message': 'Google Drive OAuth not configured'}), 400
    if redis_client is None:
        return jsonify({'error': 'unavailable', 'message': 'OAuth state store unavailable'}), 503

    state = secrets.token_urlsafe(32)
    redis_client.setex(
        _drive_state_key(state), _DRIVE_STATE_TTL,
        json.dumps({'user_id': str(user.id), 'org_id': org_id}),
    )
    auth_url = google_drive_service.get_auth_url(state=state, org_id=org_id)

    return jsonify({
        'auth_url': auth_url,
        'state': state,
    }), 200


def _settings_redirect(suffix):
    """Redirect back to the storage settings tab.

    The host comes from FRONTEND_URL config only (never the request Host
    header, which is attacker-influenced); without it a same-host relative
    redirect is used. Tokens are never placed in the URL.
    """
    frontend_url = (current_app.config.get('FRONTEND_URL') or '').rstrip('/')
    return redirect(f'{frontend_url}/dashboard/admin/settings?tab=storage&{suffix}')


def _drive_error(code):
    code = re.sub(r'[^a-z0-9_]', '', str(code or '').lower())[:64] or 'oauth_error'
    return _settings_redirect(f'drive_error={quote(code)}')


@api_bp.route('/google-drive/oauth/callback', methods=['GET'])
def google_drive_callback():
    """Handle Google OAuth callback (browser redirect).

    Validates the single-use `state`, exchanges the code server-side and
    stores the tokens encrypted on the organization's google_drive
    integration. The browser only ever sees `drive=connected` or
    `drive_error=<code>`.
    """
    from app import redis_client
    from app.models import User
    from app.middleware.audit import log_audit_event

    code = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('state')

    if not state or redis_client is None:
        return _drive_error('invalid_state')
    try:
        pipe = redis_client.pipeline()
        pipe.get(_drive_state_key(state))
        pipe.delete(_drive_state_key(state))
        raw, _ = pipe.execute()
        ctx = json.loads(raw) if raw else None
    except Exception:
        current_app.logger.exception('Google Drive OAuth state lookup failed')
        ctx = None
    if not ctx:
        return _drive_error('invalid_state')

    user = db.session.get(User, ctx.get('user_id'))
    if (not user or not user.is_active or str(user.organization_id) != ctx.get('org_id')
            or not user.has_permission('integrations:create')):
        return _drive_error('invalid_state')
    org_id = ctx['org_id']

    if error:
        return _drive_error(error)
    if not code:
        return _drive_error('no_code')

    try:
        tokens = google_drive_service.exchange_code(code, org_id=org_id)
    except Exception as e:
        current_app.logger.error(f"Google Drive OAuth callback error: {e}")
        return _drive_error('token_exchange_failed')

    integration = Integration.query.filter_by(organization_id=org_id, type='google_drive').first()
    existing = {}
    if integration and integration.credentials_encrypted:
        try:
            existing = json.loads(encryption_service.decrypt(integration.credentials_encrypted) or '{}')
        except Exception:
            existing = {}

    refresh_token = tokens.get('refresh_token') or existing.get('refresh_token')
    if not tokens.get('access_token') or not refresh_token:
        return _drive_error('no_refresh_token')

    oauth_config = google_drive_service.get_oauth_config(org_id)
    creds = {
        **existing,
        'client_id': oauth_config.get('client_id', ''),
        'client_secret': oauth_config.get('client_secret', ''),
        'access_token': tokens['access_token'],
        'refresh_token': refresh_token,
        'root_folder_id': existing.get('root_folder_id', 'root'),
        'root_folder_name': existing.get('root_folder_name', 'My Drive'),
    }
    creds_encrypted = encryption_service.encrypt(json.dumps(creds))
    config = dict((integration.config if integration else None) or {})
    config.update({'root_folder_id': creds['root_folder_id'], 'root_folder_name': creds['root_folder_name']})

    if integration:
        integration.credentials_encrypted = creds_encrypted
        integration.is_enabled = True
        integration.config = config
    else:
        integration = Integration(
            organization_id=org_id,
            type='google_drive',
            name='Google Drive',
            is_enabled=True,
            config=config,
            credentials_encrypted=creds_encrypted,
            created_by=user.id,
        )
        db.session.add(integration)
    db.session.commit()

    log_audit_event('admin_action', 'connect', resource_type='google_drive',
                    resource_id=integration.id, user=user)
    return _settings_redirect('drive=connected')


@api_bp.route('/google-drive/connect', methods=['POST'])
@jwt_required()
@require_permission('integrations:create')
@audit_log('admin_action', 'connect', 'google_drive')
def google_drive_connect():
    """Complete Google Drive connection by saving tokens and root folder.

    Expected body: { access_token, refresh_token, root_folder_id?, root_folder_name? }
    """
    user = get_current_user()
    data = request.get_json()

    if not data or not data.get('access_token') or not data.get('refresh_token'):
        return jsonify({'error': 'bad_request', 'message': 'Tokens required'}), 400

    # Store OAuth app credentials alongside tokens so the record is self-contained
    oauth_config = google_drive_service.get_oauth_config(str(user.organization_id))
    creds = {
        'client_id': oauth_config.get('client_id', ''),
        'client_secret': oauth_config.get('client_secret', ''),
        'access_token': data['access_token'],
        'refresh_token': data['refresh_token'],
        'root_folder_id': data.get('root_folder_id', 'root'),
        'root_folder_name': data.get('root_folder_name', 'My Drive'),
    }

    creds_json = json.dumps(creds)
    creds_encrypted = encryption_service.encrypt(creds_json)

    # Find or create integration
    integration = Integration.query.filter_by(
        organization_id=user.organization_id,
        type='google_drive',
    ).first()

    if integration:
        integration.credentials_encrypted = creds_encrypted
        integration.is_enabled = True
        integration.config = {
            'root_folder_id': creds['root_folder_id'],
            'root_folder_name': creds['root_folder_name'],
        }
    else:
        integration = Integration(
            organization_id=user.organization_id,
            type='google_drive',
            name='Google Drive',
            is_enabled=True,
            config={
                'root_folder_id': creds['root_folder_id'],
                'root_folder_name': creds['root_folder_name'],
            },
            credentials_encrypted=creds_encrypted,
            created_by=user.id,
        )
        db.session.add(integration)

    db.session.commit()

    return jsonify({'message': 'Google Drive connected successfully'}), 200


@api_bp.route('/google-drive/disconnect', methods=['POST'])
@jwt_required()
@require_permission('integrations:update')
@audit_log('admin_action', 'disconnect', 'google_drive')
def google_drive_disconnect():
    """Disconnect Google Drive integration."""
    user = get_current_user()

    integration = Integration.query.filter_by(
        organization_id=user.organization_id,
        type='google_drive',
    ).first()

    if integration:
        integration.is_enabled = False
        integration.credentials_encrypted = None
        db.session.commit()

    return jsonify({'message': 'Google Drive disconnected'}), 200


@api_bp.route('/google-drive/folders', methods=['GET'])
@jwt_required()
@require_permission('integrations:read')
def google_drive_list_folders():
    """List folders in Google Drive for folder selection."""
    user = get_current_user()
    parent_id = request.args.get('parent_id', 'root')

    integration, creds = _get_drive_integration(user)
    if not integration or not creds:
        return jsonify({'error': 'not_connected', 'message': 'Google Drive not connected'}), 400

    access_token = _get_valid_access_token(integration, creds)
    if not access_token:
        return jsonify({'error': 'auth_expired', 'message': 'Google Drive auth expired'}), 401

    try:
        folders = google_drive_service.list_folders(access_token, parent_id)
        return jsonify({'folders': folders, 'parent_id': parent_id}), 200
    except Exception as e:
        current_app.logger.error(f"Google Drive list folders error: {e}")
        return jsonify({'error': 'drive_error', 'message': str(e)}), 500


@api_bp.route('/google-drive/set-root', methods=['POST'])
@jwt_required()
@require_permission('integrations:update')
def google_drive_set_root():
    """Set the root folder for case directories."""
    user = get_current_user()
    data = request.get_json() or {}

    folder_id = data.get('folder_id', 'root')
    folder_name = data.get('folder_name', 'My Drive')

    integration, creds = _get_drive_integration(user)
    if not integration or not creds:
        return jsonify({'error': 'not_connected', 'message': 'Google Drive not connected'}), 400

    # Update credentials with new root folder
    creds['root_folder_id'] = folder_id
    creds['root_folder_name'] = folder_name

    creds_json = json.dumps(creds)
    integration.credentials_encrypted = encryption_service.encrypt(creds_json)
    integration.config = {
        'root_folder_id': folder_id,
        'root_folder_name': folder_name,
    }
    db.session.commit()

    return jsonify({'message': 'Root folder updated', 'root_folder_id': folder_id}), 200


@api_bp.route('/incidents/<uuid:incident_id>/google-drive/setup', methods=['POST'])
@jwt_required()
@require_incident_access('artifacts:upload')
@audit_log('data_modification', 'create', 'google_drive_case_folder')
def google_drive_setup_case(incident_id):
    """Create the CASE-xxxx folder structure in Google Drive for this incident."""
    user = get_current_user()
    incident = g.incident

    integration, creds = _get_drive_integration(user)
    if not integration or not creds:
        return jsonify({'error': 'not_connected', 'message': 'Google Drive not connected'}), 400

    access_token = _get_valid_access_token(integration, creds)
    if not access_token:
        return jsonify({'error': 'auth_expired', 'message': 'Google Drive auth expired'}), 401

    root_folder_id = creds.get('root_folder_id', 'root')

    try:
        folder_ids = google_drive_service.ensure_case_structure(
            access_token=access_token,
            root_folder_id=root_folder_id,
            incident_number=incident.incident_number,
        )
        return jsonify({
            'message': f'Case folder CASE-{incident.incident_number:04d} created',
            'folders': folder_ids,
        }), 200
    except Exception as e:
        current_app.logger.error(f"Google Drive case setup error: {e}")
        return jsonify({'error': 'drive_error', 'message': str(e)}), 500


@api_bp.route('/incidents/<uuid:incident_id>/google-drive/upload', methods=['POST'])
@jwt_required()
@require_incident_access('artifacts:upload')
@audit_log('data_modification', 'upload', 'google_drive_file')
def google_drive_upload_artifact(incident_id):
    """Upload an artifact to the incident's Google Drive case folder.

    Expected body: { artifact_id, subfolder? }
    subfolder defaults to 'Artifacts'
    """
    user = get_current_user()
    incident = g.incident
    data = request.get_json() or {}

    artifact_id = data.get('artifact_id')
    subfolder = data.get('subfolder', 'Artifacts')

    if not artifact_id:
        return jsonify({'error': 'bad_request', 'message': 'artifact_id required'}), 400

    if subfolder not in google_drive_service.CASE_SUBFOLDERS:
        subfolder = 'Artifacts'

    # Get the artifact
    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    # Get Drive credentials
    integration, creds = _get_drive_integration(user)
    if not integration or not creds:
        return jsonify({'error': 'not_connected', 'message': 'Google Drive not connected'}), 400

    access_token = _get_valid_access_token(integration, creds)
    if not access_token:
        return jsonify({'error': 'auth_expired', 'message': 'Google Drive auth expired'}), 401

    # Ensure case folder structure exists
    root_folder_id = creds.get('root_folder_id', 'root')
    try:
        folder_ids = google_drive_service.ensure_case_structure(
            access_token=access_token,
            root_folder_id=root_folder_id,
            incident_number=incident.incident_number,
        )
    except Exception as e:
        return jsonify({'error': 'drive_error', 'message': f'Failed to create case folders: {e}'}), 500

    target_folder_id = folder_ids.get(subfolder, folder_ids.get('Artifacts'))

    # Download the artifact file
    try:
        file_obj = storage_service.retrieve_file(artifact.storage_path, artifact.storage_type or 'local')
        if not file_obj:
            return jsonify({'error': 'storage_error', 'message': 'Artifact file not found in storage'}), 404
        file_content = file_obj.read()
    except Exception as e:
        return jsonify({'error': 'storage_error', 'message': f'Failed to read artifact: {e}'}), 500

    # Upload to Google Drive
    try:
        result = google_drive_service.upload_file(
            access_token=access_token,
            folder_id=target_folder_id,
            filename=artifact.original_filename,
            content=file_content,
            mime_type=artifact.mime_type or 'application/octet-stream',
        )
        return jsonify({
            'message': 'File uploaded to Google Drive',
            'file_id': result.get('id'),
            'file_name': result.get('name'),
            'web_link': result.get('webViewLink'),
        }), 200
    except Exception as e:
        current_app.logger.error(f"Google Drive upload error: {e}")
        return jsonify({'error': 'drive_error', 'message': str(e)}), 500


@api_bp.route('/incidents/<uuid:incident_id>/google-drive/files', methods=['GET'])
@jwt_required()
@require_incident_access('artifacts:read')
def google_drive_list_case_files(incident_id):
    """List files in the incident's Google Drive case folder."""
    user = get_current_user()
    incident = g.incident
    subfolder = request.args.get('subfolder', '')

    integration, creds = _get_drive_integration(user)
    if not integration or not creds:
        return jsonify({'error': 'not_connected', 'message': 'Google Drive not connected'}), 400

    access_token = _get_valid_access_token(integration, creds)
    if not access_token:
        return jsonify({'error': 'auth_expired', 'message': 'Google Drive auth expired'}), 401

    root_folder_id = creds.get('root_folder_id', 'root')

    try:
        # Find the case folder
        case_name = f"CASE-{incident.incident_number:04d}"
        case_folder = google_drive_service.find_folder(access_token, case_name, root_folder_id)

        if not case_folder:
            return jsonify({'files': [], 'case_exists': False}), 200

        # If subfolder specified, find it
        if subfolder and subfolder in google_drive_service.CASE_SUBFOLDERS:
            target = google_drive_service.find_folder(access_token, subfolder, case_folder['id'])
            if not target:
                return jsonify({'files': [], 'case_exists': True}), 200
            folder_id = target['id']
        else:
            folder_id = case_folder['id']

        files = google_drive_service.list_files(access_token, folder_id)

        return jsonify({
            'files': files,
            'case_exists': True,
            'case_folder_id': case_folder['id'],
        }), 200
    except Exception as e:
        current_app.logger.error(f"Google Drive list files error: {e}")
        return jsonify({'error': 'drive_error', 'message': str(e)}), 500
