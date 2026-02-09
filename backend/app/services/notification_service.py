"""Notification service for alerts and messaging"""
from typing import Optional, List
import json
import requests
from flask import current_app
from app import db, socketio
from app.models import Notification, User


class NotificationService:
    """Service for sending notifications via multiple channels."""

    @staticmethod
    def create_notification(
        user_id: str,
        notification_type: str,
        title: str,
        message: Optional[str] = None,
        incident_id: Optional[str] = None,
        action_url: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Notification:
        """Create an in-app notification.

        Args:
            user_id: ID of the recipient user
            notification_type: Type of notification
            title: Notification title
            message: Optional message body
            incident_id: Optional related incident ID
            action_url: Optional URL for the notification action
            metadata: Optional additional data

        Returns:
            Created Notification object
        """
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            incident_id=incident_id,
            action_url=action_url,
            metadata=metadata or {}
        )
        db.session.add(notification)
        db.session.commit()

        # Send real-time notification via WebSocket
        NotificationService._emit_notification(user_id, notification)

        return notification

    @staticmethod
    def create_bulk_notifications(
        user_ids: List[str],
        notification_type: str,
        title: str,
        message: Optional[str] = None,
        incident_id: Optional[str] = None,
        action_url: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> List[Notification]:
        """Create notifications for multiple users.

        Args:
            user_ids: List of recipient user IDs
            notification_type: Type of notification
            title: Notification title
            message: Optional message body
            incident_id: Optional related incident ID
            action_url: Optional URL for the notification action
            metadata: Optional additional data

        Returns:
            List of created Notification objects
        """
        notifications = []
        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                message=message,
                incident_id=incident_id,
                action_url=action_url,
                metadata=metadata or {}
            )
            db.session.add(notification)
            notifications.append(notification)

        db.session.commit()

        # Send real-time notifications
        for notification in notifications:
            NotificationService._emit_notification(str(notification.user_id), notification)

        return notifications

    @staticmethod
    def _emit_notification(user_id: str, notification: Notification):
        """Emit notification via WebSocket."""
        try:
            socketio.emit(
                'notification',
                notification.to_dict(),
                room=f'user_{user_id}'
            )
        except Exception as e:
            current_app.logger.error(f"WebSocket notification error: {e}")

    @staticmethod
    def mark_as_read(notification_id: str, user_id: str) -> bool:
        """Mark a notification as read.

        Args:
            notification_id: ID of the notification
            user_id: ID of the user (for verification)

        Returns:
            Success boolean
        """
        notification = Notification.query.filter_by(
            id=notification_id,
            user_id=user_id
        ).first()

        if notification:
            notification.is_read = True
            db.session.commit()
            return True
        return False

    @staticmethod
    def mark_all_as_read(user_id: str) -> int:
        """Mark all notifications as read for a user.

        Args:
            user_id: ID of the user

        Returns:
            Number of notifications marked as read
        """
        count = Notification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
        return count

    @staticmethod
    def get_unread_count(user_id: str) -> int:
        """Get count of unread notifications for a user.

        Args:
            user_id: ID of the user

        Returns:
            Count of unread notifications
        """
        return Notification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).count()

    @staticmethod
    def send_slack_notification(
        message: str,
        channel: Optional[str] = None,
        blocks: Optional[list] = None,
        webhook_url: Optional[str] = None
    ) -> bool:
        """Send a notification to Slack.

        Args:
            message: Message text
            channel: Optional channel override
            blocks: Optional Slack blocks for rich formatting
            webhook_url: Optional webhook URL override

        Returns:
            Success boolean
        """
        url = webhook_url or current_app.config.get('SLACK_WEBHOOK_URL')
        if not url:
            current_app.logger.warning("Slack webhook not configured")
            return False

        try:
            payload = {'text': message}
            if channel:
                payload['channel'] = channel
            if blocks:
                payload['blocks'] = blocks

            response = requests.post(
                url,
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            current_app.logger.error(f"Slack notification error: {e}")
            return False

    @staticmethod
    def send_incident_slack_notification(incident, event_type: str):
        """Send a formatted incident notification to Slack.

        Args:
            incident: Incident object
            event_type: Type of event (created, updated, closed, etc.)
        """
        severity_emoji = {
            'low': ':white_circle:',
            'medium': ':large_yellow_circle:',
            'high': ':large_orange_circle:',
            'critical': ':red_circle:'
        }

        emoji = severity_emoji.get(incident.severity, ':question:')
        status_text = f"*Incident {event_type.capitalize()}*"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {status_text}: #{incident.incident_number}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Title:*\n{incident.title}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{incident.severity.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{incident.status}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Phase:*\n{incident.phase_name}"
                    }
                ]
            }
        ]

        if incident.description:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{incident.description[:500]}"
                }
            })

        NotificationService.send_slack_notification(
            message=f"Incident {event_type}: #{incident.incident_number} - {incident.title}",
            blocks=blocks
        )


# Convenience functions
def notify_incident_created(incident):
    """Notify about new incident creation."""
    NotificationService.send_incident_slack_notification(incident, 'created')


def notify_incident_updated(incident):
    """Notify about incident update."""
    NotificationService.send_incident_slack_notification(incident, 'updated')


def notify_user_assigned(user_id: str, incident):
    """Notify user about incident assignment."""
    NotificationService.create_notification(
        user_id=user_id,
        notification_type='incident_assigned',
        title=f'Assigned to Incident #{incident.incident_number}',
        message=incident.title,
        incident_id=str(incident.id),
        action_url=f'/incidents/{incident.id}'
    )


def notify_task_assigned(user_id: str, task):
    """Notify user about task assignment."""
    NotificationService.create_notification(
        user_id=user_id,
        notification_type='task_assigned',
        title='New Task Assigned',
        message=task.title,
        incident_id=str(task.incident_id),
        action_url=f'/incidents/{task.incident_id}/tasks/{task.id}'
    )
