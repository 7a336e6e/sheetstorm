"""Report model"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Report(BaseModel):
    """Generated report model."""
    __tablename__ = 'reports'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(500), nullable=False)
    report_type = Column(String(50), default='full')
    format = Column(String(20), default='pdf')
    storage_path = Column(Text)
    ai_summary = Column(Text)
    ai_provider = Column(String(50))
    sections = Column(JSONB, default=list)
    generated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Relationships
    incident = relationship('Incident', back_populates='reports')
    generator = relationship('User')

    REPORT_TYPES = ['full', 'executive', 'technical', 'timeline', 'ioc', 'metrics', 'trends']
    FORMATS = ['pdf', 'html', 'json']

    def __repr__(self):
        return f'<Report {self.report_type}: {self.title}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['generator'] = {'id': str(self.generator.id), 'name': self.generator.name} if self.generator else None
        data['incident'] = {
            'id': str(self.incident.id),
            'title': self.incident.title,
            'incident_number': self.incident.incident_number
        } if self.incident else None
        return data
