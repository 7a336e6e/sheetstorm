"""Audit log endpoints"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db
from app.models import AuditLog
from app.middleware.rbac import require_permission, get_current_user


@api_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def list_audit_logs():
    """List audit logs with filtering."""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = AuditLog.query.filter_by(organization_id=user.organization_id)

    # Filters
    user_id = request.args.get('user_id')
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    event_type = request.args.get('event_type')
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)

    action = request.args.get('action')
    if action:
        query = query.filter(AuditLog.action.ilike(f'%{action}%'))

    resource_type = request.args.get('resource_type')
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    incident_id = request.args.get('incident_id')
    if incident_id:
        query = query.filter(AuditLog.incident_id == incident_id)

    start_date = request.args.get('start_date')
    if start_date:
        query = query.filter(AuditLog.created_at >= parse_date(start_date))

    end_date = request.args.get('end_date')
    if end_date:
        query = query.filter(AuditLog.created_at <= parse_date(end_date))

    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@api_bp.route('/audit-logs/<uuid:log_id>', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def get_audit_log(log_id):
    """Get audit log details."""
    user = get_current_user()

    log = AuditLog.query.filter_by(
        id=log_id,
        organization_id=user.organization_id
    ).first()

    if not log:
        return jsonify({'error': 'not_found', 'message': 'Audit log not found'}), 404

    return jsonify(log.to_dict()), 200


@api_bp.route('/audit-logs/event-types', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def list_event_types():
    """List available event types."""
    return jsonify({'event_types': AuditLog.EVENT_TYPES}), 200


@api_bp.route('/audit-logs/stats', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def get_audit_stats():
    """Get audit log statistics."""
    user = get_current_user()

    # Get counts by event type
    from sqlalchemy import func

    event_counts = db.session.query(
        AuditLog.event_type,
        func.count(AuditLog.id)
    ).filter(
        AuditLog.organization_id == user.organization_id
    ).group_by(AuditLog.event_type).all()

    # Get counts by day (last 30 days)
    from datetime import datetime, timedelta, timezone
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    daily_counts = db.session.query(
        func.date(AuditLog.created_at),
        func.count(AuditLog.id)
    ).filter(
        AuditLog.organization_id == user.organization_id,
        AuditLog.created_at >= thirty_days_ago
    ).group_by(func.date(AuditLog.created_at)).all()

    return jsonify({
        'by_event_type': {et: count for et, count in event_counts},
        'by_day': {str(day): count for day, count in daily_counts},
        'total': sum(count for _, count in event_counts)
    }), 200
