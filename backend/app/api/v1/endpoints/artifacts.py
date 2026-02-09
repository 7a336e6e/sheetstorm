"""Artifact upload and management endpoints"""
import os
import mimetypes
from flask import jsonify, request, g, send_file, current_app
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db
from app.models import Artifact
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
    """Upload an artifact file."""
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

    # Generate storage path
    storage_path, stored_filename = storage_service.generate_storage_path(
        str(incident.id), original_filename
    )

    # Detect MIME type
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

    # Store file
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
        uploaded_by=user.id
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

    # Retrieve file
    file_obj = storage_service.retrieve_file(artifact.storage_path, artifact.storage_type)
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

    # Retrieve file
    file_obj = storage_service.retrieve_file(artifact.storage_path, artifact.storage_type)
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

    artifact = Artifact.query.filter_by(id=artifact_id, incident_id=incident.id).first()
    if not artifact:
        return jsonify({'error': 'not_found', 'message': 'Artifact not found'}), 404

    # Delete from storage
    storage_service.delete_file(artifact.storage_path, artifact.storage_type)

    # Delete record
    db.session.delete(artifact)
    db.session.commit()

    return jsonify({'message': 'Artifact deleted'}), 200
