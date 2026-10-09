"""Notification endpoints"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Notification
from app.middleware.rbac import get_current_user
from app.utils.pagination import list_response


@api_bp.route('/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    """List the current user's notifications (utils/pagination.py contract;
    filters unread_only, type). Also returns `unread_count`."""
    user = get_current_user()
    query = Notification.query.filter_by(user_id=user.id)
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify(list_response(
        query, sortable={'created_at': Notification.created_at}, default_sort='-created_at',
        id_col=Notification.id, serialize=lambda n: n.to_dict(),
        filters={
            'unread_only': (Notification.is_read == False, 'flag'),  # noqa: E712
            'type': (Notification.type, 'eq'),
        },
        extra={'unread_count': unread_count},
    )), 200


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
