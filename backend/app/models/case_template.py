"""Case templates (org-scoped) and the ledger of their applications.

Built-in templates are code-resident (``services/builtin_templates.py``) and
addressed as ``builtin:<key>``; only org templates are rows here. The
template ``version`` is the optimistic-concurrency column: every update bumps
it, and an application records the version it used.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class CaseTemplate(BaseModel):
    __tablename__ = 'case_templates'
    __table_args__ = (
        UniqueConstraint('organization_id', 'key', name='uq_case_templates_org_key'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=False)
    key = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    incident_type = Column(String(100))
    definition = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')
    cloned_from = Column(String(120))          # 'builtin:<key>' or the source template's uuid
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))
    # The template revision *is* the optimistic-concurrency column.
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    creator = relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<CaseTemplate {self.key} v{self.version}>'

    def to_dict(self):
        data = super().to_dict()
        data['id'] = str(self.id)
        data['is_builtin'] = False
        data['builtin_key'] = None
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        return data


class IncidentCaseTemplate(BaseModel):
    """One application of a template to an incident (append-only ledger)."""
    __tablename__ = 'incident_case_templates'
    __table_args__ = (
        Index('idx_incident_case_templates_incident', 'incident_id'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    case_template_id = Column(UUID(as_uuid=True), ForeignKey('case_templates.id', ondelete='SET NULL'))
    builtin_key = Column(String(64))
    template_key = Column(String(64), nullable=False)
    template_name = Column(String(255), nullable=False)
    template_version = Column(Integer, nullable=False, default=1)
    custom_field_defs = Column(JSONB, nullable=False, default=list, server_default='[]')  # snapshot
    result = Column(JSONB, nullable=False, default=dict, server_default='{}')             # counts + skipped
    applied_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    applied_at = Column(DateTime(timezone=True))

    applier = relationship('User', foreign_keys=[applied_by])

    def to_dict(self):
        data = super().to_dict()
        data['applied_by_user'] = {'id': str(self.applier.id), 'name': self.applier.name} if self.applier else None
        return data
