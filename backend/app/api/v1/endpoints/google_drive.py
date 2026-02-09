"""Google Drive integration endpoints for artifact upload and case management."""
import json
import secrets
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
    """Get a valid access token, refreshing if necessary."""
    if not creds or 'refresh_token' not in creds:
        return None

    access_token = creds.get('access_token')
    if not access_token:
        # Need to refresh
        try:
            new_tokens = google_drive_service.refresh_access_token(creds['refresh_token'])
            creds['access_token'] = new_tokens['access_token']
            # Save updated tokens
            creds_json = json.dumps(creds)
            integration.credentials_encrypted = encryption_service.encrypt(creds_json)
            db.session.commit()
            return new_tokens['access_token']
        except Exception as e:
            current_app.logger.error(f"Failed to refresh Google Drive token: {e}")
            return None

    return access_token


@api_bp.route('/google-drive/status', methods=['GET'])
@jwt_required()
@require_permission('integrations:read')
def google_drive_status():
    """Check Google Drive integration status."""
    user = get_current_user()

    if not google_drive_service.is_configured():
        return jsonify({
            'configured': False,
            'connected': False,
            'message': 'Google Drive OAuth not configured. Set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET.',
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
            'email': user_info.get('email', ''),
            'display_name': user_info.get('display_name', ''),
            'root_folder_id': creds.get('root_folder_id', ''),
            'root_folder_name': creds.get('root_folder_name', ''),
        }), 200
    except Exception:
        return jsonify({
            'configured': True,
            'connected': False,
            'message': 'Google Drive connection expired. Please reconnect.',
        }), 200


@api_bp.route('/google-drive/auth', methods=['POST'])
@jwt_required()
@require_permission('integrations:create')
def google_drive_auth():
    """Initiate Google Drive OAuth flow. Returns the auth URL."""
    if not google_drive_service.is_configured():
        return jsonify({'error': 'not_configured', 'message': 'Google Drive OAuth not configured'}), 400

    user = get_current_user()
    state = secrets.token_urlsafe(32)

    # Store state in the integration config for CSRF verification
    auth_url = google_drive_service.get_auth_url(state=state)

    return jsonify({
        'auth_url': auth_url,
        'state': state,
    }), 200


@api_bp.route('/google-drive/oauth/callback', methods=['GET'])
def google_drive_callback():
    """Handle Google OAuth callback (browser redirect)."""
    code = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('state')

    frontend_url = current_app.config.get('FRONTEND_URL', 'http://127.0.0.1:3000')

    if error:
        return redirect(f'{frontend_url}/dashboard/admin?drive_error={error}')

    if not code:
        return redirect(f'{frontend_url}/dashboard/admin?drive_error=no_code')

    try:
        tokens = google_drive_service.exchange_code(code)
        # Store tokens temporarily — they'll be saved by the complete endpoint
        return redirect(
            f'{frontend_url}/dashboard/admin?drive_connected=true'
            f'&drive_token={tokens.get("access_token", "")}'
            f'&drive_refresh={tokens.get("refresh_token", "")}'
        )
    except Exception as e:
        current_app.logger.error(f"Google Drive OAuth callback error: {e}")
        return redirect(f'{frontend_url}/dashboard/admin?drive_error=token_exchange_failed')


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

    creds = {
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
@require_incident_access('artifacts:write')
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
@require_incident_access('artifacts:write')
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
