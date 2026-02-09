"""Organization model"""
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Organization(BaseModel):
    """Organization model for multi-tenant support."""
    __tablename__ = 'organizations'

    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    settings = Column(JSONB, default=dict)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    users = relationship('User', back_populates='organization', lazy='dynamic')
    incidents = relationship('Incident', back_populates='organization', lazy='dynamic')
    integrations = relationship('Integration', back_populates='organization', lazy='dynamic')
    teams = relationship('Team', back_populates='organization', lazy='dynamic')

    def __repr__(self):
        return f'<Organization {self.name}>'
