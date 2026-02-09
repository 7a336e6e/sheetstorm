"""Audit log model"""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class AuditLog(BaseModel):
    """Audit log model for tracking all system actions."""
    __tablename__ = 'audit_logs'

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='SET NULL'))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    user_email = Column(String(255))
    event_type = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(UUID(as_uuid=True))
    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='SET NULL'))
    ip_address = Column(INET)
    user_agent = Column(Text)
    request_method = Column(String(10))
    request_path = Column(Text)
    status_code = Column(Integer)
    details = Column(JSONB, default=dict)

    # Relationships
    organization = relationship('Organization')
    user = relationship('User')
    incident = relationship('Incident')

    EVENT_TYPES = [
        'authentication', 'authorization', 'data_access', 'data_modification',
        'admin_action', 'security_event', 'system_event'
    ]

    def __repr__(self):
        return f'<AuditLog {self.event_type}: {self.action}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['ip_address'] = str(self.ip_address) if self.ip_address else None
        data['user'] = {'id': str(self.user.id), 'email': self.user.email, 'name': self.user.name} if self.user else None
        return data
