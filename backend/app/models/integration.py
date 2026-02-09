"""Integration model"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Integration(BaseModel):
    """Integration configuration model."""
    __tablename__ = 'integrations'

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, default=True)
    config = Column(JSONB, default=dict)
    credentials_encrypted = Column(LargeBinary)
    last_used_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    organization = relationship('Organization', back_populates='integrations')
    creator = relationship('User')

    INTEGRATION_TYPES = [
        's3', 'slack', 'openai', 'google_ai',
        'oauth_google', 'oauth_github', 'oauth_azure',
        'webhook', 'siem', 'google_drive'
    ]

    def __repr__(self):
        return f'<Integration {self.type}: {self.name}>'

    def to_dict(self, include_credentials=False):
        """Convert to dictionary."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None

        # Never include encrypted credentials in default response
        data.pop('credentials_encrypted', None)

        if include_credentials:
            data['has_credentials'] = self.credentials_encrypted is not None
        else:
            data['has_credentials'] = self.credentials_encrypted is not None

        return data
