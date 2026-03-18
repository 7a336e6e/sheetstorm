"""Artifact upload and management endpoints"""
import io
import json
import os
import mimetypes
from flask import jsonify, request, g, send_file, current_app
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db
from app.models import Artifact, Incident, Integration
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.hash_service import HashService
from app.services.storage_service import storage_service
from app.services.chain_of_custody_service import ChainOfCustodyService


@api_bp.route('/incidents/<uuid:incident_id>/artifacts', methods=['GET'])
@jwt_required()
@require_incident_access('artifacts:read')
def list_artifacts(incident_id):
    """List artifacts for an incident."""
    incident = g.incident
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = Artifact.query.filter_by(incident_id=incident.id)

    # Search by filename or hash
    search = request.args.get('search')
    if search:
        query = query.filter(
            db.or_(
                Artifact.original_filename.ilike(f'%{search}%'),
                Artifact.sha256.ilike(f'%{search}%'),
                Artifact.md5.ilike(f'%{search}%')
            )
        )

    # Filter by verification status
    verified = request.args.get('verified')
    if verified is not None:
        query = query.filter(Artifact.is_verified == (verified.lower() == 'true'))

    pagination = query.order_by(Artifact.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [a.to_dict() for a in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/artifacts', methods=['POST'])
@jwt_required()
@require_incident_access('artifacts:upload')
def upload_artifact(incident_id):
    """Upload an artifact file.

    When Google Drive is connected and a case folder structure exists,
    the file is uploaded directly to Google Drive as primary storage.
    Otherwise it falls back to local storage.
    """
    user = get_current_user()
    incident = g.incident

    if 'file' not in request.files:
        return jsonify({'error': 'bad_request', 'message': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'bad_request', 'message': 'No file selected'}), 400

    # Get file info
    original_filename = file.filename
    file_size = file.seek(0, 2)  # Seek to end to get size
    file.seek(0)  # Reset to beginning

    # Compute hashes before storing
    hashes = HashService.compute_hashes(file)

    # Generate storage path (used for local fallback and as a reference key)
    storage_path, stored_filename = storage_service.generate_storage_path(
        str(incident.id), original_filename
    )

    # Detect MIME type
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

    # Try Google Drive as primary storage
    drive_result = _try_google_drive_primary(file, incident, user, original_filename, mime_type)

    if drive_result:
        # Google Drive is primary storage
        storage_type = 'google_drive'
        extra_data = {
            'google_drive_file_id': drive_result.get('id'),
            'google_drive_web_link': drive_result.get('webViewLink'),
        }
    else:
        # Fall back to local storage
        storage_type = 'local'
        extra_data = {}
        success, storage_type = storage_service.store_file(file, storage_path, mime_type)
        if not success:
            return jsonify({'error': 'server_error', 'message': 'Failed to store file'}), 500

    # Create artifact record
    artifact = Artifact(
        incident_id=incident.id,
        filename=stored_filename,
        original_filename=original_filename,
        storage_path=storage_path,
        storage_type=storage_type,
        mime_type=mime_type,
        file_size=file_size,
        md5=hashes['md5'],
        sha256=hashes['sha256'],
        sha512=hashes['sha512'],
        description=request.form.get('description'),
        source=request.form.get('source'),
        collected_at=parse_date(request.form.get('collected_at')) if request.form.get('collected_at') else None,
        uploaded_by=user.id,
        extra_data=extra_data,
    )

    db.session.add(artifact)
    db.session.commit()

    # Log chain of custody
    ChainOfCustodyService.log_upload(artifact, str(user.id), request.form.get('source'))

    return jsonify(artifact.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/artifacts/<uuid:artifact_id>', methods=['GET'])
@jwt_required()
@require_incident_access('artifacts:read')
def get_artifact(incident_id, artifact_id):
    """Get artifact details."""
    incident = g.incident
    user = get_current_user()

    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    # Log view in chain of custody
    ChainOfCustodyService.log_view(artifact, str(user.id))

    return jsonify(artifact.to_dict(include_custody=True)), 200


@api_bp.route('/incidents/<uuid:incident_id>/artifacts/<uuid:artifact_id>/download', methods=['GET'])
@jwt_required()
@require_incident_access('artifacts:download')
def download_artifact(incident_id, artifact_id):
    """Download an artifact file."""
    incident = g.incident
    user = get_current_user()

    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    # Retrieve file — from Google Drive or local/S3
    file_obj = _retrieve_artifact_file(artifact, user)
    if not file_obj:
        return jsonify({'error': 'not_found', 'message': 'File not found in storage'}), 404

    # Verify integrity
    computed_hashes = HashService.compute_hashes(file_obj)
    verification_result = 'match'

    if computed_hashes['sha256'] != artifact.sha256:
        verification_result = 'mismatch'
        current_app.logger.warning(
            f"Artifact integrity mismatch for {artifact.id}: "
            f"stored={artifact.sha256}, computed={computed_hashes['sha256']}"
        )

    # Log download with verification result
    ChainOfCustodyService.log_download(
        artifact,
        str(user.id),
        purpose=request.args.get('purpose'),
        verification_result=verification_result
    )

    # Reset file position
    file_obj.seek(0)

    return send_file(
        file_obj,
        mimetype=artifact.mime_type,
        as_attachment=True,
        download_name=artifact.original_filename
    )


@api_bp.route('/incidents/<uuid:incident_id>/artifacts/<uuid:artifact_id>/verify', methods=['POST'])
@jwt_required()
@require_incident_access('artifacts:read')
def verify_artifact(incident_id, artifact_id):
    """Verify artifact integrity."""
    incident = g.incident
    user = get_current_user()

    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    # Retrieve file — from Google Drive or local/S3
    file_obj = _retrieve_artifact_file(artifact, user)
    if not file_obj:
        return jsonify({'error': 'not_found', 'message': 'File not found in storage'}), 404

    # Compute hashes
    computed_hashes = HashService.compute_hashes(file_obj)

    # Compare hashes
    all_match, results = HashService.verify_hashes(file_obj, {
        'md5': artifact.md5,
        'sha256': artifact.sha256,
        'sha512': artifact.sha512
    })

    result = 'match' if all_match else 'mismatch'

    # Log verification
    ChainOfCustodyService.log_verification(artifact, str(user.id), result, computed_hashes)

    return jsonify({
        'result': result,
        'stored_hashes': {
            'md5': artifact.md5,
            'sha256': artifact.sha256,
            'sha512': artifact.sha512
        },
        'computed_hashes': computed_hashes,
        'matches': results
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/artifacts/<uuid:artifact_id>/custody', methods=['GET'])
@jwt_required()
@require_incident_access('artifacts:read')
def get_custody_chain(incident_id, artifact_id):
    """Get chain of custody for an artifact."""
    incident = g.incident

    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    custody_chain = ChainOfCustodyService.get_custody_chain(str(artifact.id))

    return jsonify({
        'artifact_id': str(artifact.id),
        'original_filename': artifact.original_filename,
        'chain_of_custody': custody_chain
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/artifacts/<uuid:artifact_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('artifacts:delete')
@audit_log('data_modification', 'delete', 'artifact')
def delete_artifact(incident_id, artifact_id):
    """Delete an artifact."""
    incident = g.incident
    user = get_current_user()

    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    # Delete from Google Drive if stored there
    extra = artifact.extra_data or {}
    drive_file_id = extra.get('google_drive_file_id')
    if drive_file_id:
        try:
            access_token = _get_drive_access_token(user)
            if access_token:
                from app.services.google_drive_service import google_drive_service
                google_drive_service.delete_file(access_token, drive_file_id)
                current_app.logger.info(f"Deleted artifact {artifact.id} from Google Drive (file_id={drive_file_id})")
        except Exception as e:
            current_app.logger.warning(f"Failed to delete artifact from Google Drive: {e}")

    # Delete from local/S3 storage (may not exist if Drive-primary, but safe to call)
    if artifact.storage_type in ('local', 's3'):
        storage_service.delete_file(artifact.storage_path, artifact.storage_type)

    # Delete record
    db.session.delete(artifact)
    db.session.commit()

    return jsonify({'message': 'Artifact deleted'}), 200


def _get_drive_credentials(user):
    """Get Google Drive integration credentials for the user's org.

    Returns:
        Tuple of (integration, decrypted_creds) or (None, None)
    """
    try:
        from app.services.google_drive_service import google_drive_service
        from app.services.encryption_service import encryption_service

        if not google_drive_service.is_configured():
            return None, None

        integration = Integration.query.filter_by(
            organization_id=user.organization_id,
            type='google_drive',
            is_enabled=True,
        ).first()
        if not integration or not integration.credentials_encrypted:
            return None, None

        creds = json.loads(encryption_service.decrypt(integration.credentials_encrypted))
        if 'refresh_token' not in creds:
            return None, None

        return integration, creds
    except Exception:
        return None, None


@api_bp.route('/storage/stats', methods=['GET'])
@jwt_required()
def storage_stats():
    """Return aggregate storage statistics across all artifacts."""
    import shutil
    from sqlalchemy import func

    user = get_current_user()

    # Per-storage-type aggregates
    rows = (
        db.session.query(
            Artifact.storage_type,
            func.count(Artifact.id).label('count'),
            func.coalesce(func.sum(Artifact.file_size), 0).label('size'),
        )
        .join(Incident, Artifact.incident_id == Incident.id)
        .filter(Incident.organization_id == user.organization_id)
        .group_by(Artifact.storage_type)
        .all()
    )

    by_storage_type = {}
    total_size = 0
    total_count = 0
    for storage_type, count, size in rows:
        by_storage_type[storage_type or 'local'] = {'count': count, 'size_bytes': int(size)}
        total_size += int(size)
        total_count += count

    # Per-MIME-type aggregates
    mime_rows = (
        db.session.query(
            Artifact.mime_type,
            func.count(Artifact.id).label('count'),
            func.coalesce(func.sum(Artifact.file_size), 0).label('size'),
        )
        .join(Incident, Artifact.incident_id == Incident.id)
        .filter(Incident.organization_id == user.organization_id)
        .group_by(Artifact.mime_type)
        .all()
    )

    by_mime_type = {}
    for mime, count, size in mime_rows:
        by_mime_type[mime or 'unknown'] = {'count': count, 'size_bytes': int(size)}

    # Disk usage for local artifact storage
    disk_usage = None
    local_path = '/app/artifacts'
    try:
        usage = shutil.disk_usage(local_path)
        disk_usage = {
            'total_bytes': usage.total,
            'used_bytes': usage.used,
            'free_bytes': usage.free,
            'usage_percent': round(usage.used / usage.total * 100, 1) if usage.total else 0,
            'path': local_path,
        }
    except OSError:
        pass

    return jsonify({
        'total_artifacts': total_count,
        'total_size_bytes': total_size,
        'by_storage_type': by_storage_type,
        'by_mime_type': by_mime_type,
        'disk_usage': disk_usage,
    }), 200


def _get_drive_access_token(user):
    """Get a valid Google Drive access token for the user's org.

    Always refreshes the token to avoid using expired ones.

    Returns:
        Access token string or None
    """
    try:
        from app.services.google_drive_service import google_drive_service
        from app.services.encryption_service import encryption_service

        integration, creds = _get_drive_credentials(user)
        if not integration or not creds:
            return None

        # Always refresh to ensure we have a valid token
        new_tokens = google_drive_service.refresh_access_token(creds['refresh_token'])
        access_token = new_tokens['access_token']
        creds['access_token'] = access_token
        integration.credentials_encrypted = encryption_service.encrypt(json.dumps(creds))
        db.session.commit()

        return access_token
    except Exception as e:
        current_app.logger.warning(f"Failed to get Drive access token: {e}")
        return None


def _try_google_drive_primary(file, incident, user, original_filename, mime_type):
    """Attempt to upload a file directly to Google Drive as primary storage.

    Returns:
        Drive upload result dict on success, or None to fall back to local.
    """
    try:
        from app.services.google_drive_service import google_drive_service
        from app.services.encryption_service import encryption_service

        integration, creds = _get_drive_credentials(user)
        if not integration or not creds:
            return None

        # Always refresh to get a valid token
        new_tokens = google_drive_service.refresh_access_token(creds['refresh_token'])
        access_token = new_tokens['access_token']
        creds['access_token'] = access_token
        integration.credentials_encrypted = encryption_service.encrypt(json.dumps(creds))

        root_folder_id = creds.get('root_folder_id', 'root')

        # Ensure CASE-xxxx folder structure exists
        folder_ids = google_drive_service.ensure_case_structure(
            access_token=access_token,
            root_folder_id=root_folder_id,
            incident_number=incident.incident_number,
        )
        target_folder_id = folder_ids.get('Artifacts', folder_ids.get('case'))

        # Read file content
        file.seek(0)
        file_content = file.read()

        # Upload to Google Drive
        result = google_drive_service.upload_file(
            access_token=access_token,
            folder_id=target_folder_id,
            filename=original_filename,
            content=file_content,
            mime_type=mime_type or 'application/octet-stream',
        )

        current_app.logger.info(
            f"Uploaded artifact to Google Drive as primary storage (file_id={result.get('id')})"
        )
        return result
    except Exception as e:
        current_app.logger.warning(f"Google Drive primary upload failed, falling back to local: {e}")
        return None


def _retrieve_artifact_file(artifact, user):
    """Retrieve an artifact file from its storage backend.

    Handles Google Drive, local, and S3 storage types.

    Returns:
        File-like object (BytesIO) or None
    """
    extra = artifact.extra_data or {}
    drive_file_id = extra.get('google_drive_file_id')

    if artifact.storage_type == 'google_drive' and drive_file_id:
        # Download from Google Drive
        try:
            access_token = _get_drive_access_token(user)
            if access_token:
                from app.services.google_drive_service import google_drive_service
                content = google_drive_service.download_file(access_token, drive_file_id)
                if content:
                    return io.BytesIO(content)
        except Exception as e:
            current_app.logger.warning(f"Failed to download from Google Drive: {e}")
        return None
    else:
        # Local or S3
        return storage_service.retrieve_file(artifact.storage_path, artifact.storage_type or 'local')
