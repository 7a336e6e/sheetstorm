"""Decision & response-action log (W4-DEC, decision-log plan §3.3).

* ``incident_decisions``  head rows: the current state of each decision
  (``D-007``). Mutable only through ``services/decision_log_service.py``.
* ``response_actions``    head rows of response actions (``A-012``) moving
  through requested -> authorized -> executed -> verified.
* ``decision_log_revisions``  INSERT-only history: one row per change of a
  head row (full snapshot + ``{field: {from, to}}`` diff + reason), hash
  chained per record (``hash_chain`` domain ``decision-v1``) and HMAC-signed
  with the custody signing key. The ``decision_log_revisions_immutable()``
  trigger rejects UPDATE/TRUNCATE, and DELETE outside an audited incident
  purge. ``actor_id`` is NO ACTION (integration plan C3: an append-only table
  never gets an ON DELETE SET NULL FK).

Privileged decisions (``is_privileged``) are readable only with
``decisions:read_privileged``; the service filters them everywhere.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel

DECISION_CATEGORIES = ('containment', 'eradication', 'recovery', 'notification', 'ransom_legal', 'scope',
                       'communication', 'evidence', 'other')
DECISION_STATUSES = ('proposed', 'approved', 'rejected', 'superseded')

ACTION_TYPES = ('isolate_host', 'release_host', 'contain_host', 'reimage_host', 'decommission_host',
                'disable_account', 'reset_credentials', 'revoke_sessions', 'delete_account', 'block_ioc',
                'sinkhole_domain', 'quarantine_file', 'remove_persistence', 'patch', 'notify_party', 'other')
TARGET_TYPES = ('host', 'account', 'network_ioc', 'host_ioc', 'malware', 'external', 'none')
ACTION_STATUSES = ('requested', 'authorized', 'in_progress', 'executed', 'verified', 'failed', 'rolled_back',
                   'cancelled')
VERIFICATION_RESULTS = ('success', 'partial', 'failed')

RECORD_TYPES = ('decision', 'response_action')
REVISION_EVENTS = ('create', 'update', 'approve', 'reject', 'reopen', 'supersede', 'authorize', 'start',
                   'execute', 'fail', 'verify', 'rollback', 'cancel', 'retry')


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _user_fk():
    return ForeignKey('users.id', ondelete='SET NULL')


class IncidentDecision(BaseModel):
    """Head row of one decision (current state)."""
    __tablename__ = 'incident_decisions'
    __table_args__ = (
        UniqueConstraint('incident_id', 'number', name='uq_incident_decisions_number'),
        CheckConstraint(_in('status', DECISION_STATUSES), name='ck_incident_decisions_status'),
        CheckConstraint(_in('category', DECISION_CATEGORIES), name='ck_incident_decisions_category'),
        Index('idx_incident_decisions_incident_status', 'incident_id', 'status'),
        Index('idx_incident_decisions_links', 'links', postgresql_using='gin',
              postgresql_ops={'links': 'jsonb_path_ops'}),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    number = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    decision = Column(Text, nullable=False)
    rationale = Column(Text)
    alternatives = Column(JSONB, nullable=False, default=list, server_default='[]')
    category = Column(String(30), nullable=False, default='other', server_default='other')
    status = Column(String(20), nullable=False, default='proposed', server_default='proposed')
    status_reason = Column(Text)
    is_privileged = Column(Boolean, nullable=False, default=False, server_default='false')
    decided_at = Column(DateTime(timezone=True), nullable=False)
    decided_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    decided_by_name = Column(String(255))
    approved_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    approved_by_name = Column(String(255))
    approved_at = Column(DateTime(timezone=True))
    self_approved = Column(Boolean, nullable=False, default=False, server_default='false')
    superseded_by_id = Column(UUID(as_uuid=True), ForeignKey('incident_decisions.id', ondelete='SET NULL'))
    links = Column(JSONB, nullable=False, default=list, server_default='[]')
    created_by = Column(UUID(as_uuid=True), _user_fk())
    updated_at = Column(DateTime(timezone=True))
    updated_by = Column(UUID(as_uuid=True), _user_fk())
    # Optimistic concurrency (utils/concurrency.py, integration plan C8).
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident', back_populates='decisions')

    @property
    def display_id(self):
        return f'D-{self.number:03d}' if self.number is not None else 'D-?'


class ResponseAction(BaseModel):
    """Head row of one response action (current state)."""
    __tablename__ = 'response_actions'
    __table_args__ = (
        UniqueConstraint('incident_id', 'number', name='uq_response_actions_number'),
        CheckConstraint(_in('status', ACTION_STATUSES), name='ck_response_actions_status'),
        CheckConstraint(_in('action_type', ACTION_TYPES), name='ck_response_actions_type'),
        CheckConstraint(_in('target_type', TARGET_TYPES), name='ck_response_actions_target_type'),
        CheckConstraint(f"verification_result IS NULL OR {_in('verification_result', VERIFICATION_RESULTS)}",
                        name='ck_response_actions_verification_result'),
        Index('idx_response_actions_incident_status', 'incident_id', 'status'),
        Index('idx_response_actions_target', 'incident_id', 'target_type', 'target_id'),
        Index('idx_response_actions_executed', 'incident_id', 'executed_at'),
        Index('idx_response_actions_links', 'links', postgresql_using='gin',
              postgresql_ops={'links': 'jsonb_path_ops'}),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    number = Column(Integer, nullable=False)
    action_type = Column(String(40), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text)
    target_type = Column(String(20), nullable=False, default='none', server_default='none')
    target_id = Column(UUID(as_uuid=True))
    target_label = Column(String(500))
    decision_id = Column(UUID(as_uuid=True), ForeignKey('incident_decisions.id', ondelete='SET NULL'))
    status = Column(String(20), nullable=False, default='requested', server_default='requested')
    status_reason = Column(Text)
    requested_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    requested_at = Column(DateTime(timezone=True), nullable=False)
    authorized_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    authorized_by_name = Column(String(255))
    authorized_at = Column(DateTime(timezone=True))
    self_approved = Column(Boolean, nullable=False, default=False, server_default='false')
    executed_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    executed_by_name = Column(String(255))
    executed_at = Column(DateTime(timezone=True))
    verified_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    verified_by_name = Column(String(255))
    verified_at = Column(DateTime(timezone=True))
    verification_method = Column(String(255))
    verification_result = Column(String(20))
    verification_notes = Column(Text)
    self_verified = Column(Boolean, nullable=False, default=False, server_default='false')
    rollback_plan = Column(Text)
    rolled_back_at = Column(DateTime(timezone=True))
    rolled_back_by_user_id = Column(UUID(as_uuid=True), _user_fk())
    rollback_reason = Column(Text)
    target_state_before = Column(JSONB)
    target_state_after = Column(JSONB)
    links = Column(JSONB, nullable=False, default=list, server_default='[]')
    created_by = Column(UUID(as_uuid=True), _user_fk())
    updated_at = Column(DateTime(timezone=True))
    updated_by = Column(UUID(as_uuid=True), _user_fk())
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident', back_populates='response_actions')

    @property
    def display_id(self):
        return f'A-{self.number:03d}' if self.number is not None else 'A-?'


class DecisionLogRevision(BaseModel):
    """One INSERT-only revision of a decision or response action.

    ``seq`` numbers the revisions of one record from 1. ``entry_hash`` =
    ``link_hash('decision-v1', prev_hash, canonical_json(payload))`` where
    ``prev_hash`` is the previous revision's ``entry_hash`` (or the record's
    genesis hash), and ``signature`` = HMAC(custody key, entry_hash).
    """
    __tablename__ = 'decision_log_revisions'
    __table_args__ = (
        UniqueConstraint('record_type', 'record_id', 'seq', name='uq_decision_log_revisions_seq'),
        CheckConstraint(_in('record_type', RECORD_TYPES), name='ck_decision_log_revisions_record_type'),
        Index('idx_decision_log_revisions_record', 'record_type', 'record_id', 'seq'),
        Index('idx_decision_log_revisions_incident', 'incident_id', 'created_at'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    record_type = Column(String(20), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    seq = Column(Integer, nullable=False)
    event = Column(String(30), nullable=False)
    snapshot = Column(JSONB, nullable=False)
    changes = Column(JSONB, nullable=False, default=dict, server_default='{}')
    reason = Column(Text)
    # NO ACTION (C3): a cascaded SET NULL would UPDATE an append-only row.
    actor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    actor_email = Column(String(255))
    is_privileged = Column(Boolean, nullable=False, default=False, server_default='false')
    self_approved = Column(Boolean, nullable=False, default=False, server_default='false')
    prev_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False)
    signature = Column(String(64))
    signature_key_id = Column(String(16))
