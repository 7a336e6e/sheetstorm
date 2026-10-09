"""decision & response-action log (W4-DEC)

* ``incident_decisions`` / ``response_actions``: head rows (current state),
  each with ``version`` (optimistic concurrency, integration plan C8).
* ``decision_log_revisions``: append-only, hash-chained + HMAC-signed history.
  ``actor_id`` is NO ACTION (C3).
* ``decision_log_revisions_immutable()``: rejects UPDATE and TRUNCATE, and a
  DELETE unless the transaction runs the audited incident purge
  (``sheetstorm.custody_purge`` = the row's incident). Created last, dropped
  first.

Permissions are NOT granted here: the ``decisions:*`` / ``response_actions:*``
keys and grants already live in ``admin_guardrails_rbac`` (C13).

Idempotent (existence guards) and reversible; the downgrade drops the tables
(the decision log is lost, documented).

Revision ID: add_decision_log
Revises: post_incident_metrics
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_decision_log'
down_revision = 'post_incident_metrics'
branch_labels = None
depends_on = None

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

TRIGGERS = (
    ('decision_log_revisions_no_update', 'BEFORE UPDATE OR DELETE', 'ROW'),
    ('decision_log_revisions_no_truncate', 'BEFORE TRUNCATE', 'STATEMENT'),
)

IMMUTABLE_FUNCTION = """
CREATE OR REPLACE FUNCTION decision_log_revisions_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_LEVEL = 'ROW' AND TG_OP = 'DELETE' THEN
    IF current_setting('sheetstorm.custody_purge', true) = OLD.incident_id::text THEN
      RETURN OLD;  -- only the audited incident purge path (services/incident_purge.py)
    END IF;
  END IF;
  RAISE EXCEPTION '% on % is forbidden: decision_log_revisions is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;
"""


def _table_exists(table):
    return sa.inspect(op.get_bind()).has_table(table)


def _index_exists(table, name):
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and name in {i['name'] for i in insp.get_indexes(table)}


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name, *args, **kw):
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kw)


def _user(name):
    return _uuid(name, sa.ForeignKey('users.id', ondelete='SET NULL'))


def _ts(name, **kw):
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def _jsonb(name, default):
    return sa.Column(name, postgresql.JSONB(), nullable=False, server_default=default)


def _flag(name):
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text('false'))


def _create_decisions():
    op.create_table(
        'incident_decisions',
        _uuid('id', primary_key=True),
        _ts('created_at'),
        _uuid('incident_id', sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('decision', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text()),
        _jsonb('alternatives', '[]'),
        sa.Column('category', sa.String(30), nullable=False, server_default='other'),
        sa.Column('status', sa.String(20), nullable=False, server_default='proposed'),
        sa.Column('status_reason', sa.Text()),
        _flag('is_privileged'),
        _ts('decided_at', nullable=False),
        _user('decided_by_user_id'),
        sa.Column('decided_by_name', sa.String(255)),
        _user('approved_by_user_id'),
        sa.Column('approved_by_name', sa.String(255)),
        _ts('approved_at'),
        _flag('self_approved'),
        _uuid('superseded_by_id', sa.ForeignKey('incident_decisions.id', ondelete='SET NULL')),
        _jsonb('links', '[]'),
        _user('created_by'),
        _ts('updated_at'),
        _user('updated_by'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('incident_id', 'number', name='uq_incident_decisions_number'),
        sa.CheckConstraint(_in('status', DECISION_STATUSES), name='ck_incident_decisions_status'),
        sa.CheckConstraint(_in('category', DECISION_CATEGORIES), name='ck_incident_decisions_category'),
    )


def _create_actions():
    op.create_table(
        'response_actions',
        _uuid('id', primary_key=True),
        _ts('created_at'),
        _uuid('incident_id', sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(40), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('target_type', sa.String(20), nullable=False, server_default='none'),
        _uuid('target_id'),
        sa.Column('target_label', sa.String(500)),
        _uuid('decision_id', sa.ForeignKey('incident_decisions.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(20), nullable=False, server_default='requested'),
        sa.Column('status_reason', sa.Text()),
        _user('requested_by_user_id'),
        _ts('requested_at', nullable=False),
        _user('authorized_by_user_id'),
        sa.Column('authorized_by_name', sa.String(255)),
        _ts('authorized_at'),
        _flag('self_approved'),
        _user('executed_by_user_id'),
        sa.Column('executed_by_name', sa.String(255)),
        _ts('executed_at'),
        _user('verified_by_user_id'),
        sa.Column('verified_by_name', sa.String(255)),
        _ts('verified_at'),
        sa.Column('verification_method', sa.String(255)),
        sa.Column('verification_result', sa.String(20)),
        sa.Column('verification_notes', sa.Text()),
        _flag('self_verified'),
        sa.Column('rollback_plan', sa.Text()),
        _ts('rolled_back_at'),
        _user('rolled_back_by_user_id'),
        sa.Column('rollback_reason', sa.Text()),
        sa.Column('target_state_before', postgresql.JSONB()),
        sa.Column('target_state_after', postgresql.JSONB()),
        _jsonb('links', '[]'),
        _user('created_by'),
        _ts('updated_at'),
        _user('updated_by'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('incident_id', 'number', name='uq_response_actions_number'),
        sa.CheckConstraint(_in('status', ACTION_STATUSES), name='ck_response_actions_status'),
        sa.CheckConstraint(_in('action_type', ACTION_TYPES), name='ck_response_actions_type'),
        sa.CheckConstraint(_in('target_type', TARGET_TYPES), name='ck_response_actions_target_type'),
        sa.CheckConstraint('verification_result IS NULL OR ' + _in('verification_result', VERIFICATION_RESULTS),
                           name='ck_response_actions_verification_result'),
    )


def _create_revisions():
    op.create_table(
        'decision_log_revisions',
        _uuid('id', primary_key=True),
        _ts('created_at'),
        _uuid('incident_id', sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('record_type', sa.String(20), nullable=False),
        _uuid('record_id', nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(30), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(), nullable=False),
        _jsonb('changes', '{}'),
        sa.Column('reason', sa.Text()),
        # NO ACTION (integration plan C3), never SET NULL.
        _uuid('actor_id', sa.ForeignKey('users.id')),
        sa.Column('actor_email', sa.String(255)),
        _flag('is_privileged'),
        _flag('self_approved'),
        sa.Column('prev_hash', sa.String(64), nullable=False),
        sa.Column('entry_hash', sa.String(64), nullable=False),
        sa.Column('signature', sa.String(64)),
        sa.Column('signature_key_id', sa.String(16)),
        sa.UniqueConstraint('record_type', 'record_id', 'seq', name='uq_decision_log_revisions_seq'),
        sa.CheckConstraint(_in('record_type', ('decision', 'response_action')),
                           name='ck_decision_log_revisions_record_type'),
    )


INDEXES = (
    ('idx_incident_decisions_incident_status', 'incident_decisions', ['incident_id', 'status'], None),
    ('idx_incident_decisions_links', 'incident_decisions', ['links'], 'gin'),
    ('idx_response_actions_incident_status', 'response_actions', ['incident_id', 'status'], None),
    ('idx_response_actions_target', 'response_actions', ['incident_id', 'target_type', 'target_id'], None),
    ('idx_response_actions_executed', 'response_actions', ['incident_id', 'executed_at'], None),
    ('idx_response_actions_links', 'response_actions', ['links'], 'gin'),
    ('idx_decision_log_revisions_record', 'decision_log_revisions', ['record_type', 'record_id', 'seq'], None),
    ('idx_decision_log_revisions_incident', 'decision_log_revisions', ['incident_id', 'created_at'], None),
)


def upgrade():
    if not _table_exists('incident_decisions'):
        _create_decisions()
    if not _table_exists('response_actions'):
        _create_actions()
    if not _table_exists('decision_log_revisions'):
        _create_revisions()
    for name, table, cols, using in INDEXES:
        if _index_exists(table, name):
            continue
        if using == 'gin':
            op.create_index(name, table, cols, postgresql_using='gin',
                            postgresql_ops={cols[0]: 'jsonb_path_ops'})
        else:
            op.create_index(name, table, cols)
    # Append-only trigger last (integration plan §4 rules).
    op.execute(IMMUTABLE_FUNCTION)
    for name, timing, level in TRIGGERS:
        op.execute(f'DROP TRIGGER IF EXISTS {name} ON decision_log_revisions')
        op.execute(f'CREATE TRIGGER {name} {timing} ON decision_log_revisions FOR EACH {level} '
                   'EXECUTE FUNCTION decision_log_revisions_immutable()')


def downgrade():
    # Trigger first, then the tables (lossy: the decision log is dropped).
    if _table_exists('decision_log_revisions'):
        for name, _timing, _level in TRIGGERS:
            op.execute(f'DROP TRIGGER IF EXISTS {name} ON decision_log_revisions')
    op.execute('DROP FUNCTION IF EXISTS decision_log_revisions_immutable()')
    for table in ('decision_log_revisions', 'response_actions', 'incident_decisions'):
        if _table_exists(table):
            op.drop_table(table)
