"""Case notes model for incident documentation."""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class CaseNote(BaseModel):
    """Case notes for free-form incident documentation and analyst observations."""
    __tablename__ = 'case_notes'
    __table_args__ = (
        Index('idx_case_notes_incident', 'incident_id'),
        Index('idx_case_notes_created', 'created_at'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default='general')  # general, finding, question, action_item, handoff
    is_pinned = Column(Boolean, default=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', backref='case_notes')
    author = relationship('User', foreign_keys=[created_by])

    # Note categories
    CATEGORIES = [
        'general',
        'finding',
        'question',
        'action_item',
        'handoff',
        'evidence',
        'hypothesis',
    ]

    def __repr__(self):
        return f'<CaseNote {self.title[:40]}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': str(self.id),
            'incident_id': str(self.incident_id),
            'title': self.title,
            'content': self.content,
            'category': self.category,
            'is_pinned': self.is_pinned,
            'author': {
                'id': str(self.author.id),
                'name': self.author.name,
            } if self.author else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
