"""IR-aligned playbook models.

A Playbook is a reusable, phase-gated runbook template (org-scoped). Its
`definition` JSONB holds the phase structure:

    {"phases": [
        {"phase": 2, "name": "Containment",
         "tasks":   [{"title": "Isolate host", "owner_role": "forensics"}],
         "actions": [{"key": "a1", "type": "enrich_iocs",
                      "name": "Enrich network IOCs", "config": {}, "auto_run": false}]}
    ]}

An IncidentPlaybook is a template activated on a specific incident, tracking
phase progress, task completion, and action-run history in `state`.

Actions are strictly IR-augmenting (enrich/summarize/suggest/create-task) — this
is NOT a SOC alert-triage engine.
"""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Playbook(BaseModel):
    """Reusable phase-gated IR runbook template (org-scoped)."""
    __tablename__ = 'playbooks'

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    incident_type = Column(String(100))
    definition = Column(JSONB, default=dict)
    is_template = Column(Boolean, default=True)
    cloned_from = Column(String(120))   # 'builtin:<key>' when cloned from a built-in playbook
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    organization = relationship('Organization')
    creator = relationship('User')

    # Strictly investigation-augmenting actions (no SOC alert triage).
    ACTION_TYPES = ['enrich_iocs', 'generate_summary', 'suggest_mitre', 'create_task']

    def __repr__(self):
        return f'<Playbook {self.name}>'

    def to_dict(self):
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        return data


class IncidentPlaybook(BaseModel):
    """A playbook activated on a specific incident, tracking its progress."""
    __tablename__ = 'incident_playbooks'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    playbook_id = Column(UUID(as_uuid=True), ForeignKey('playbooks.id', ondelete='SET NULL'), nullable=True)
    builtin_key = Column(String(64))           # set when a built-in playbook was activated (playbook_id is NULL)
    name = Column(String(255))
    definition = Column(JSONB, default=dict)   # snapshot of the template at activation
    current_phase = Column(Integer, default=1)
    state = Column(JSONB, default=dict)        # {tasks: {<key>: bool}, action_runs: [...]}
    activated_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    # Optimistic concurrency: bumped by SQLAlchemy on every UPDATE
    # (see app/utils/concurrency.py).
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident')
    playbook = relationship('Playbook')
    creator = relationship('User')

    def __repr__(self):
        return f'<IncidentPlaybook {self.name} phase={self.current_phase}>'

    def to_dict(self):
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        return data
