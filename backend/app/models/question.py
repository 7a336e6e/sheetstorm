"""Investigative questions: the answerable questions of an investigation.

An ``InvestigativeQuestion`` belongs to one incident (org scope comes through
the incident, like ``Task``). Its answer cites evidence through the shared
``evidence_refs`` shape and may be linked to the leads (tasks) that produced
it (``QuestionLead``, many-to-many).
"""
from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class InvestigativeQuestion(BaseModel):
    __tablename__ = 'investigative_questions'
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'answered', 'unanswerable')",
                        name='ck_investigative_question_status'),
        CheckConstraint("confidence IS NULL OR confidence IN ('low', 'medium', 'high', 'confirmed')",
                        name='ck_investigative_question_confidence'),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')",
                        name='ck_investigative_question_priority'),
        CheckConstraint('phase IS NULL OR (phase >= 1 AND phase <= 6)', name='ck_investigative_question_phase'),
        CheckConstraint("source IN ('manual', 'dfiq', 'core', 'template')",
                        name='ck_investigative_question_source'),
        Index('idx_investigative_questions_incident_status', 'incident_id', 'status'),
        Index('idx_investigative_questions_owner', 'owner_id'),
        Index('uq_investigative_questions_dedupe', 'incident_id', 'dedupe_key', unique=True,
              postgresql_where=text('dedupe_key IS NOT NULL')),
    )

    STATUSES = ['open', 'in_progress', 'answered', 'unanswerable']
    CONFIDENCES = ['low', 'medium', 'high', 'confirmed']
    PRIORITIES = ['low', 'medium', 'high', 'critical']
    SOURCES = ['manual', 'dfiq', 'core', 'template']

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    question = Column(String(1000), nullable=False)
    description = Column(Text)
    facet = Column(String(255))
    status = Column(String(20), nullable=False, default='open', server_default='open')
    answer = Column(Text)                      # markdown source, rendered as plain text by the UI
    confidence = Column(String(20))
    priority = Column(String(20), nullable=False, default='medium', server_default='medium')
    phase = Column(Integer)
    owner_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    evidence_refs = Column(JSONB, nullable=False, default=list, server_default='[]')  # [{evidence_type, evidence_id}]
    source = Column(String(20), nullable=False, default='manual', server_default='manual')
    source_ref = Column(String(160))           # 'dfiq:Q1058', 'ss:SSQ-006', 'tpl:<template>:<key>'
    dedupe_key = Column(String(160))           # = source_ref for library / template questions
    guidance = Column(JSONB, nullable=False, default=list, server_default='[]')
    order_index = Column(Integer, nullable=False, default=0, server_default='0')
    answered_at = Column(DateTime(timezone=True))
    answered_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    is_archived = Column(Boolean, nullable=False, default=False, server_default='false')
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))
    # Optimistic concurrency (see app/utils/concurrency.py).
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident')
    owner = relationship('User', foreign_keys=[owner_id])
    answerer = relationship('User', foreign_keys=[answered_by])
    lead_links = relationship('QuestionLead', back_populates='question', cascade='all, delete-orphan',
                              lazy='select')

    def __repr__(self):
        return f'<InvestigativeQuestion {self.question[:40]!r} {self.status}>'

    def to_dict(self, lead_ids=None):
        data = super().to_dict()
        data['owner'] = self.owner.to_summary() if self.owner else None
        data['answered_by_user'] = ({'id': str(self.answerer.id), 'name': self.answerer.name}
                                    if self.answerer else None)
        data['lead_ids'] = list(lead_ids) if lead_ids is not None else sorted(
            str(link.task_id) for link in self.lead_links)
        return data


class QuestionLead(BaseModel):
    """Link between a question and a lead (task) that informs it."""
    __tablename__ = 'investigative_question_leads'
    __table_args__ = (
        UniqueConstraint('question_id', 'task_id', name='uq_investigative_question_lead'),
        Index('idx_investigative_question_leads_task', 'task_id'),
    )

    question_id = Column(UUID(as_uuid=True), ForeignKey('investigative_questions.id', ondelete='CASCADE'),
                         nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))

    question = relationship('InvestigativeQuestion', back_populates='lead_links')
    task = relationship('Task')
