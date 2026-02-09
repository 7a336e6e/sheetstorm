"""Team management endpoints"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Team, TeamMember, User
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/teams', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def list_teams():
    """List all teams in the organization."""
    user = get_current_user()

    teams = Team.query.filter_by(organization_id=user.organization_id)\
        .order_by(Team.name.asc()).all()

    return jsonify({
        'items': [t.to_dict() for t in teams]
    }), 200


@api_bp.route('/teams', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'create_team', 'team')
def create_team():
    """Create a new team."""
    user = get_current_user()
    data = request.get_json()

    if not data or not data.get('name'):
        return jsonify({'error': 'bad_request', 'message': 'Team name is required'}), 400

    existing = Team.query.filter_by(
        organization_id=user.organization_id, name=data['name'].strip()
    ).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'A team with this name already exists'}), 409

    team = Team(
        organization_id=user.organization_id,
        name=data['name'].strip(),
        description=data.get('description', '').strip() or None,
    )
    db.session.add(team)
    db.session.commit()

    return jsonify(team.to_dict()), 201


@api_bp.route('/teams/<uuid:team_id>', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def get_team(team_id):
    """Get a team with members."""
    user = get_current_user()
    team = Team.query.filter_by(id=team_id, organization_id=user.organization_id).first()

    if not team:
        return jsonify({'error': 'not_found', 'message': 'Team not found'}), 404

    return jsonify(team.to_dict(include_members=True)), 200


@api_bp.route('/teams/<uuid:team_id>', methods=['PUT'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'update_team', 'team')
def update_team(team_id):
    """Update a team."""
    user = get_current_user()
    team = Team.query.filter_by(id=team_id, organization_id=user.organization_id).first()

    if not team:
        return jsonify({'error': 'not_found', 'message': 'Team not found'}), 404

    data = request.get_json()

    if 'name' in data:
        name = data['name'].strip()
        if name != team.name:
            existing = Team.query.filter_by(
                organization_id=user.organization_id, name=name
            ).first()
            if existing:
                return jsonify({'error': 'conflict', 'message': 'A team with this name already exists'}), 409
            team.name = name

    if 'description' in data:
        team.description = data['description'].strip() or None

    db.session.commit()

    return jsonify(team.to_dict()), 200


@api_bp.route('/teams/<uuid:team_id>', methods=['DELETE'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'delete_team', 'team')
def delete_team(team_id):
    """Delete a team."""
    user = get_current_user()
    team = Team.query.filter_by(id=team_id, organization_id=user.organization_id).first()

    if not team:
        return jsonify({'error': 'not_found', 'message': 'Team not found'}), 404

    db.session.delete(team)
    db.session.commit()

    return jsonify({'message': 'Team deleted successfully'}), 200


@api_bp.route('/teams/<uuid:team_id>/members', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'add_team_member', 'team')
def add_team_member(team_id):
    """Add a user to a team."""
    current = get_current_user()
    team = Team.query.filter_by(id=team_id, organization_id=current.organization_id).first()

    if not team:
        return jsonify({'error': 'not_found', 'message': 'Team not found'}), 404

    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'bad_request', 'message': 'user_id is required'}), 400

    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    existing = TeamMember.query.filter_by(team_id=team.id, user_id=user.id).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'User is already a member of this team'}), 409

    member = TeamMember(team_id=team.id, user_id=user.id)
    db.session.add(member)
    db.session.commit()

    return jsonify({'message': 'User added to team'}), 201


@api_bp.route('/teams/<uuid:team_id>/members/<uuid:user_id>', methods=['DELETE'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'remove_team_member', 'team')
def remove_team_member(team_id, user_id):
    """Remove a user from a team."""
    current = get_current_user()
    team = Team.query.filter_by(id=team_id, organization_id=current.organization_id).first()

    if not team:
        return jsonify({'error': 'not_found', 'message': 'Team not found'}), 404

    member = TeamMember.query.filter_by(team_id=team.id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'not_found', 'message': 'Team membership not found'}), 404

    db.session.delete(member)
    db.session.commit()

    return jsonify({'message': 'User removed from team'}), 200
