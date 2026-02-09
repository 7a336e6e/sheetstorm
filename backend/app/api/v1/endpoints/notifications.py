"""Notification endpoints"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Notification
from app.middleware.rbac import get_current_user


@api_bp.route('/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    """List notifications for the current user."""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = Notification.query.filter_by(user_id=user.id)

    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    if unread_only:
        query = query.filter(Notification.is_read == False)

    notification_type = request.args.get('type')
    if notification_type:
        query = query.filter(Notification.type == notification_type)

    pagination = query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [n.to_dict() for n in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages,
        'unread_count': Notification.query.filter_by(user_id=user.id, is_read=False).count()
    }), 200


@api_bp.route('/notifications/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """Get count of unread notifications."""
    user = get_current_user()
    count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify({'unread_count': count}), 200


@api_bp.route('/notifications/<uuid:notification_id>/read', methods=['POST'])
@jwt_required()
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    user = get_current_user()

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id
    ).first()

    if not notification:
        return jsonify({'error': 'not_found', 'message': 'Notification not found'}), 404

    notification.is_read = True
    db.session.commit()

    return jsonify({'message': 'Notification marked as read'}), 200


@api_bp.route('/notifications/read-all', methods=['POST'])
@jwt_required()
def mark_all_read():
    """Mark all notifications as read."""
    user = get_current_user()

    count = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).update({'is_read': True})

    db.session.commit()

    return jsonify({'message': f'{count} notifications marked as read'}), 200


@api_bp.route('/notifications/<uuid:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """Delete a notification."""
    user = get_current_user()

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id
    ).first()

    if not notification:
        return jsonify({'error': 'not_found', 'message': 'Notification not found'}), 404

    db.session.delete(notification)
    db.session.commit()

    return jsonify({'message': 'Notification deleted'}), 200
