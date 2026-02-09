"""Artifact and chain of custody models"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, BigInteger, Index
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Artifact(BaseModel):
    """Artifact model for evidence files."""
    __tablename__ = 'artifacts'
    __table_args__ = (
        Index('idx_artifact_incident_type', 'incident_id', 'mime_type'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    storage_path = Column(Text, nullable=False)
    storage_type = Column(String(50), default='local')
    mime_type = Column(String(255))
    file_size = Column(BigInteger, nullable=False)
    md5 = Column(String(32), nullable=False)
    sha256 = Column(String(64), nullable=False)
    sha512 = Column(String(128), nullable=False)
    description = Column(Text)
    source = Column(String(255))
    collected_at = Column(DateTime(timezone=True))
    is_verified = Column(Boolean, default=True)
    verification_status = Column(String(50), default='verified')
    last_verified_at = Column(DateTime(timezone=True))
    extra_data = Column(JSONB, default=dict)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Relationships
    incident = relationship('Incident', back_populates='artifacts')
    uploader = relationship('User')
    chain_of_custody = relationship('ChainOfCustody', back_populates='artifact', lazy='dynamic', cascade='all, delete-orphan')

    STORAGE_TYPES = ['local', 's3']
    VERIFICATION_STATUSES = ['verified', 'mismatch', 'pending']

    def __repr__(self):
        return f'<Artifact {self.original_filename}>'

    def to_dict(self, include_custody=False):
        """Convert to dictionary."""
        data = super().to_dict()
        data['uploader'] = {'id': str(self.uploader.id), 'name': self.uploader.name} if self.uploader else None

        if include_custody:
            data['chain_of_custody'] = [coc.to_dict() for coc in self.chain_of_custody.order_by(ChainOfCustody.created_at.desc()).limit(10)]

        return data


class ChainOfCustody(BaseModel):
    """Chain of custody log for artifacts."""
    __tablename__ = 'chain_of_custody'

    artifact_id = Column(UUID(as_uuid=True), ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False)
    action = Column(String(50), nullable=False)
    performed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    ip_address = Column(INET)
    user_agent = Column(Text)
    purpose = Column(Text)
    recipient_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    verification_result = Column(String(50))
    extra_data = Column(JSONB, default=dict)

    # Relationships
    artifact = relationship('Artifact', back_populates='chain_of_custody')
    performer = relationship('User', foreign_keys=[performed_by])
    recipient = relationship('User', foreign_keys=[recipient_id])

    ACTIONS = ['upload', 'view', 'download', 'transfer', 'verify', 'export']

    def __repr__(self):
        return f'<ChainOfCustody {self.action} by {self.performed_by}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['ip_address'] = str(self.ip_address) if self.ip_address else None
        data['performer'] = {'id': str(self.performer.id), 'name': self.performer.name} if self.performer else None
        data['recipient'] = {'id': str(self.recipient.id), 'name': self.recipient.name} if self.recipient else None
        return data
