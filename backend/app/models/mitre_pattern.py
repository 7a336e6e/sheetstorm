"""MITRE pattern model"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class MitrePattern(BaseModel):
    """MITRE ATT&CK auto-suggest pattern scoped to an organization."""
    __tablename__ = 'mitre_patterns'
    __table_args__ = (
        Index('idx_mitre_patterns_org', 'organization_id'),
        Index('uq_mitre_patterns_org_technique', 'organization_id', 'technique', unique=True),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    technique = Column(String(20), nullable=False)
    tactic = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    keywords = Column(JSONB, default=list, server_default='[]', nullable=False)
    regex = Column(JSONB, default=list, server_default='[]', nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    organization = relationship('Organization')

    def __repr__(self):
        return f'<MitrePattern {self.technique}>'

    def to_dict(self):
        """Convert to dictionary."""
        return super().to_dict()
