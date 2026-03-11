"""Custom field options CRUD endpoints.

Allows organizations to define custom dropdown values
for system types, artifact types, protocols, etc.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import CustomFieldOption
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/custom-fields', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_custom_field_options():
    """List custom field options for the current organization.

    Query params:
        field_name: filter by field name (e.g. 'system_type', 'artifact_type')
    """
    user = get_current_user()
    field_name = request.args.get('field_name')

    query = CustomFieldOption.query.filter_by(organization_id=user.organization_id)
    if field_name:
        query = query.filter_by(field_name=field_name)

    options = query.order_by(CustomFieldOption.is_default.desc(), CustomFieldOption.display_label.asc()).all()

    return jsonify({
        'items': [o.to_dict() for o in options]
    }), 200


@api_bp.route('/custom-fields', methods=['POST'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('data_modification', 'create', 'custom_field_option')
def create_custom_field_option():
    """Create a new custom field option."""
    user = get_current_user()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    field_name = data.get('field_name', '').strip()
    field_value = data.get('field_value', '').strip()

    if not field_name or not field_value:
        return jsonify({'error': 'bad_request', 'message': 'field_name and field_value are required'}), 400

    if field_name not in CustomFieldOption.FIELD_NAMES:
        return jsonify({'error': 'bad_request', 'message': f'Invalid field_name. Must be one of: {CustomFieldOption.FIELD_NAMES}'}), 400

    # Check for duplicate
    existing = CustomFieldOption.query.filter_by(
        organization_id=user.organization_id,
        field_name=field_name,
        field_value=field_value
    ).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'This option already exists'}), 409

    option = CustomFieldOption(
        organization_id=user.organization_id,
        field_name=field_name,
        field_value=field_value,
        display_label=data.get('display_label', '').strip() or field_value,
        is_default=False,
        created_by=user.id,
    )
    db.session.add(option)
    db.session.commit()

    return jsonify(option.to_dict()), 201


@api_bp.route('/custom-fields/<uuid:option_id>', methods=['PUT'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('data_modification', 'update', 'custom_field_option')
def update_custom_field_option(option_id):
    """Update a custom field option (only non-default ones)."""
    user = get_current_user()
    data = request.get_json()

    option = CustomFieldOption.query.filter_by(
        id=option_id, organization_id=user.organization_id
    ).first()
    if not option:
        return jsonify({'error': 'not_found', 'message': 'Option not found'}), 404

    if option.is_default:
        return jsonify({'error': 'forbidden', 'message': 'Cannot modify default options'}), 403

    if 'display_label' in data:
        option.display_label = data['display_label'].strip()
    if 'field_value' in data:
        option.field_value = data['field_value'].strip()

    db.session.commit()
    return jsonify(option.to_dict()), 200


@api_bp.route('/custom-fields/<uuid:option_id>', methods=['DELETE'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('data_modification', 'delete', 'custom_field_option')
def delete_custom_field_option(option_id):
    """Delete a custom field option (only non-default ones)."""
    user = get_current_user()

    option = CustomFieldOption.query.filter_by(
        id=option_id, organization_id=user.organization_id
    ).first()
    if not option:
        return jsonify({'error': 'not_found', 'message': 'Option not found'}), 404

    if option.is_default:
        return jsonify({'error': 'forbidden', 'message': 'Cannot delete default options'}), 403

    db.session.delete(option)
    db.session.commit()

    return jsonify({'message': 'Deleted'}), 200


@api_bp.route('/custom-fields/seed', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
def seed_custom_field_defaults():
    """Seed default field options for the organization (admin only)."""
    user = get_current_user()
    CustomFieldOption.seed_defaults(user.organization_id, db.session)
    db.session.commit()
    return jsonify({'message': 'Defaults seeded'}), 200
