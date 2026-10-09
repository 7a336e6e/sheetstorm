"""DFIQ question library: status, one-click import, removal.

    GET    /questions/library/dfiq          templates:manage or platform admin
    POST   /questions/library/dfiq/import   platform admin (download, or multipart `archive` upload)
    DELETE /questions/library/dfiq          platform admin

The question library is shared by every organization, so only platform
administrators change it. See services/dfiq_import.py for the integrity rules.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import get_current_user, is_platform_admin, require_platform_admin
from app.models.system_setting import SystemSetting
from app.services import dfiq_import, question_library
from app.services.rate_limit_settings import limited
from app.utils.audit_diff import record_changes


def _row():
    return SystemSetting.query.filter_by(key=question_library.DFIQ_SETTING_KEY).first()


def _payload(user):
    return {**dfiq_import.status(_row()), 'can_import': bool(user and is_platform_admin(user))}


@api_bp.route('/questions/library/dfiq', methods=['GET'])
@jwt_required()
def dfiq_status():
    user = get_current_user()
    if not user or not (user.has_permission('templates:manage') or is_platform_admin(user)):
        return jsonify({'error': 'forbidden', 'message': 'Permission denied. Required: templates:manage'}), 403
    return jsonify(_payload(user)), 200


@api_bp.route('/questions/library/dfiq/import', methods=['POST'])
@jwt_required()
@require_platform_admin
@limited('library_import')
@audit_log('admin_action', 'dfiq_import', 'system_setting')
def dfiq_import_route():
    """Download (default) or accept an uploaded archive of the pinned DFIQ
    commit, verify its SHA-256, and store the questions. 400/502 with a code:
    integrity_mismatch, invalid_archive, download_failed, archive_too_large."""
    user = get_current_user()
    upload = request.files.get('archive')
    try:
        if upload is not None:
            data = upload.read(dfiq_import.MAX_ARCHIVE_BYTES + 1)
            method = 'upload'
        else:
            data = dfiq_import.download_archive()
            method = 'download'
        digest = dfiq_import.verify_archive(data)
        document = dfiq_import.build_document(data, digest, user, method)
    except dfiq_import.DfiqImportError as e:
        return jsonify({'error': e.code, 'message': e.message}), e.status

    row = _row()
    before = {'commit': row.value.get('commit'), 'questions': (row.value.get('counts') or {}).get('questions')} \
        if row is not None and row.value else {}
    if row is None:
        row = SystemSetting(key=question_library.DFIQ_SETTING_KEY, value=document, updated_by=user.id,
                            updated_at=db.func.now())
        db.session.add(row)
    else:
        row.value, row.updated_by, row.updated_at = document, user.id, db.func.now()
    try:
        db.session.commit()
    except IntegrityError:  # concurrent first import
        db.session.rollback()
        return jsonify({'error': 'conflict', 'message': 'Another import finished first; reload.'}), 409
    question_library.invalidate_db_cache()
    record_changes(before, {'commit': document['commit'], 'questions': document['counts']['questions']},
                   method=method, sha256=digest)
    return jsonify(_payload(user)), 200


@api_bp.route('/questions/library/dfiq', methods=['DELETE'])
@jwt_required()
@require_platform_admin
@audit_log('admin_action', 'dfiq_remove', 'system_setting')
def dfiq_remove():
    """Remove the imported library. Questions already added to incidents keep
    their text; templates that reference dfiq: refs stop resolving them."""
    user = get_current_user()
    row = _row()
    if row is not None:
        record_changes({'commit': (row.value or {}).get('commit')}, {'commit': None})
        db.session.delete(row)
        db.session.commit()
        question_library.invalidate_db_cache()
    return jsonify(_payload(user)), 200
