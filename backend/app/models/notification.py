"""Notification model"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Notification(BaseModel):
    """Notification model."""
    __tablename__ = 'notifications'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'))
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    action_url = Column(Text)
    extra_data = Column(JSONB, default=dict)

    # Relationships
    user = relationship('User')
    incident = relationship('Incident')

    NOTIFICATION_TYPES = [
        'incident_assigned', 'incident_updated', 'task_assigned', 'task_due',
        'comment_added', 'artifact_uploaded', 'mention', 'system'
    ]

    def __repr__(self):
        return f'<Notification {self.type}: {self.title}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        if self.incident:
            data['incident'] = {
                'id': str(self.incident.id),
                'title': self.incident.title,
                'incident_number': self.incident.incident_number
            }
        return data
