"""Audit log model"""
from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey
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
    request_query_params = Column(JSONB, default=dict)
    request_body_summary = Column(JSONB, default=dict)
    content_type = Column(String(255))
    referrer = Column(Text)
    origin = Column(String(255))
    status_code = Column(Integer)
    duration_ms = Column(Float)
    # Cloudflare geo headers
    geo_country = Column(String(100))
    geo_city = Column(String(255))
    geo_region = Column(String(255))
    cf_ray = Column(String(100))
    # Browser/device parsed from user-agent
    browser = Column(String(100))
    os = Column(String(100))
    device_type = Column(String(50))
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
        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'name': self.user.name,
            'role': ', '.join(self.user.role_names) if self.user.role_names else None,
        } if self.user else None
        data['incident'] = {
            'id': str(self.incident.id),
            'title': self.incident.title,
        } if self.incident else None
        return data
