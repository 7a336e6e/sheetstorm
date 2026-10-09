"""Post-incident models: structured after-action review (AAR), improvement
actions and the reminder dedupe log (W3-RT-POST, realtime-collab-metrics §3.5).

* ``incident_reviews``  one review per incident (cascades with the incident).
* ``improvement_actions``  org-level follow-ups; **survive** a permanent
  incident delete (``incident_id`` goes NULL, ``incident_ref`` keeps the label).
* ``reminder_log``  one row per (entity, stage, due-date snapshot) already
  reminded; its unique constraint makes concurrent job runs idempotent.
"""
from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel

CONTRIBUTING_CATEGORIES = ('people', 'process', 'technology', 'detection', 'communication', 'third_party', 'other')
DETECTION_SOURCES = ('internal_alert', 'threat_hunt', 'user_report', 'third_party', 'law_enforcement', 'other')
REVIEW_STATUSES = ('draft', 'final')
ACTION_STATUSES = ('open', 'in_progress', 'blocked', 'done', 'wont_fix')
ACTION_OPEN_STATUSES = ('open', 'in_progress', 'blocked')
ACTION_PRIORITIES = ('low', 'medium', 'high', 'critical')
CONTROL_FRAMEWORKS = ('nist_csf', 'd3fend', 'cis', 'iso27001', 'other')
REMINDER_ENTITY_TYPES = ('task', 'improvement_action')
REMINDER_STAGES = ('due_soon', 'overdue')


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class IncidentReview(BaseModel):
    """Structured after-action review of one incident."""
    __tablename__ = 'incident_reviews'
    __table_args__ = (
        UniqueConstraint('incident_id', name='uq_incident_reviews_incident'),
        CheckConstraint(_in('status', REVIEW_STATUSES), name='ck_incident_reviews_status'),
        CheckConstraint(f"detection_source IS NULL OR {_in('detection_source', DETECTION_SOURCES)}",
                        name='ck_incident_reviews_detection_source'),
        Index('idx_incident_reviews_org', 'organization_id'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    what_went_well = Column(Text)
    what_went_wrong = Column(Text)
    root_cause = Column(Text)
    contributing_factors = Column(JSONB, nullable=False, default=list, server_default='[]')  # [{category, description}]
    detection_source = Column(String(50))
    review_date = Column(Date)
    participants = Column(JSONB, nullable=False, default=list, server_default='[]')  # [user_id]
    status = Column(String(20), nullable=False, default='draft', server_default='draft')
    finalized_at = Column(DateTime(timezone=True))
    finalized_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))
    # Optimistic concurrency (see app/utils/concurrency.py).
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident', foreign_keys=[incident_id])
    finalizer = relationship('User', foreign_keys=[finalized_by])
    creator = relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        data = super().to_dict()
        data['review_date'] = self.review_date.isoformat() if self.review_date else None
        data['contributing_factors'] = self.contributing_factors or []
        data['participants'] = self.participants or []
        data['finalized_by_user'] = ({'id': str(self.finalizer.id), 'name': self.finalizer.name}
                                     if self.finalizer else None)
        return data


class ImprovementAction(BaseModel):
    """A tracked follow-up from a post-incident review."""
    __tablename__ = 'improvement_actions'
    __table_args__ = (
        CheckConstraint(_in('status', ACTION_STATUSES), name='ck_improvement_actions_status'),
        CheckConstraint(_in('priority', ACTION_PRIORITIES), name='ck_improvement_actions_priority'),
        CheckConstraint(f"category IS NULL OR {_in('category', CONTRIBUTING_CATEGORIES)}",
                        name='ck_improvement_actions_category'),
        CheckConstraint(f"control_framework IS NULL OR {_in('control_framework', CONTROL_FRAMEWORKS)}",
                        name='ck_improvement_actions_framework'),
        Index('idx_improvement_actions_org_status_due', 'organization_id', 'status', 'due_date'),
        Index('idx_improvement_actions_incident', 'incident_id'),
        Index('idx_improvement_actions_owner_status', 'owner_id', 'status'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    # SET NULL: the action outlives a permanent incident delete.
    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='SET NULL'))
    incident_ref = Column(String(600))  # snapshot "#<n> <title>"
    review_id = Column(UUID(as_uuid=True), ForeignKey('incident_reviews.id', ondelete='SET NULL'))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    owner_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    team_id = Column(UUID(as_uuid=True), ForeignKey('teams.id', ondelete='SET NULL'))
    due_date = Column(DateTime(timezone=True))
    status = Column(String(20), nullable=False, default='open', server_default='open')
    priority = Column(String(20), nullable=False, default='medium', server_default='medium')
    category = Column(String(30))
    control_framework = Column(String(20))
    control_ref = Column(String(100))
    completed_at = Column(DateTime(timezone=True))
    completed_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident', foreign_keys=[incident_id])
    owner = relationship('User', foreign_keys=[owner_id])
    team = relationship('Team', foreign_keys=[team_id])

    def to_dict(self, include_incident=True):
        data = super().to_dict()
        data['owner'] = self.owner.to_summary() if self.owner else None
        data['team'] = {'id': str(self.team.id), 'name': self.team.name} if self.team else None
        if include_incident and self.incident:
            data['incident'] = {'id': str(self.incident.id), 'title': self.incident.title,
                                'incident_number': self.incident.incident_number}
        else:
            data['incident'] = None
        return data


class ReminderLog(BaseModel):
    """A reminder already sent for (entity, stage, due-date snapshot)."""
    __tablename__ = 'reminder_log'
    __table_args__ = (
        UniqueConstraint('entity_type', 'entity_id', 'stage', 'due_date_snapshot', name='uq_reminder_log_entity_stage'),
        CheckConstraint(_in('entity_type', REMINDER_ENTITY_TYPES), name='ck_reminder_log_entity_type'),
        CheckConstraint(_in('stage', REMINDER_STAGES), name='ck_reminder_log_stage'),
    )

    entity_type = Column(String(30), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    stage = Column(String(20), nullable=False)
    due_date_snapshot = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True))
