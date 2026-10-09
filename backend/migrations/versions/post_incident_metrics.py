"""post-incident metrics, after-action reviews, improvement actions, reminders

* ``incidents.first_malicious_at`` / ``incidents.responded_at`` (nullable
  lifecycle timestamps; ``first_malicious_at`` overrides the value derived
  from the timeline).
* ``incident_reviews``: one structured AAR per incident (cascades with it).
* ``improvement_actions``: org-level follow-ups; ``incident_id`` is
  ON DELETE SET NULL so they survive a permanent incident delete.
* ``reminder_log``: dedupe of due-date reminders (unique per entity, stage and
  due-date snapshot).

Permissions are NOT granted here: every new permission key and role grant
lives in ``admin_guardrails_rbac`` (integration plan C13).

Idempotent (existence guards) and reversible; the downgrade drops the new
tables and columns (the review/action data is lost, documented).

Revision ID: post_incident_metrics
Revises: questions_case_templates
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'post_incident_metrics'
down_revision = 'questions_case_templates'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and column in {c['name'] for c in insp.get_columns(table)}


def _table_exists(table):
    return sa.inspect(op.get_bind()).has_table(table)


def _index_exists(table, name):
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and name in {i['name'] for i in insp.get_indexes(table)}


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade():
    for column in ('first_malicious_at', 'responded_at'):
        if not _column_exists('incidents', column):
            op.add_column('incidents', sa.Column(column, sa.DateTime(timezone=True), nullable=True))

    if not _table_exists('incident_reviews'):
        op.create_table(
            'incident_reviews',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True)),
            sa.Column('incident_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('what_went_well', sa.Text()),
            sa.Column('what_went_wrong', sa.Text()),
            sa.Column('root_cause', sa.Text()),
            sa.Column('contributing_factors', postgresql.JSONB(), nullable=False, server_default='[]'),
            sa.Column('detection_source', sa.String(50)),
            sa.Column('review_date', sa.Date()),
            sa.Column('participants', postgresql.JSONB(), nullable=False, server_default='[]'),
            sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
            sa.Column('finalized_at', sa.DateTime(timezone=True)),
            sa.Column('finalized_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.UniqueConstraint('incident_id', name='uq_incident_reviews_incident'),
            sa.CheckConstraint(_in('status', ('draft', 'final')), name='ck_incident_reviews_status'),
            sa.CheckConstraint(
                "detection_source IS NULL OR " + _in('detection_source', (
                    'internal_alert', 'threat_hunt', 'user_report', 'third_party', 'law_enforcement', 'other')),
                name='ck_incident_reviews_detection_source'),
        )
    if not _index_exists('incident_reviews', 'idx_incident_reviews_org'):
        op.create_index('idx_incident_reviews_org', 'incident_reviews', ['organization_id'])

    if not _table_exists('improvement_actions'):
        categories = ('people', 'process', 'technology', 'detection', 'communication', 'third_party', 'other')
        op.create_table(
            'improvement_actions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True)),
            sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('incident_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='SET NULL')),
            sa.Column('incident_ref', sa.String(600)),
            sa.Column('review_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('incident_reviews.id', ondelete='SET NULL')),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id', ondelete='SET NULL')),
            sa.Column('due_date', sa.DateTime(timezone=True)),
            sa.Column('status', sa.String(20), nullable=False, server_default='open'),
            sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
            sa.Column('category', sa.String(30)),
            sa.Column('control_framework', sa.String(20)),
            sa.Column('control_ref', sa.String(100)),
            sa.Column('completed_at', sa.DateTime(timezone=True)),
            sa.Column('completed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.CheckConstraint(_in('status', ('open', 'in_progress', 'blocked', 'done', 'wont_fix')),
                               name='ck_improvement_actions_status'),
            sa.CheckConstraint(_in('priority', ('low', 'medium', 'high', 'critical')),
                               name='ck_improvement_actions_priority'),
            sa.CheckConstraint("category IS NULL OR " + _in('category', categories),
                               name='ck_improvement_actions_category'),
            sa.CheckConstraint(
                "control_framework IS NULL OR " + _in('control_framework', (
                    'nist_csf', 'd3fend', 'cis', 'iso27001', 'other')),
                name='ck_improvement_actions_framework'),
        )
    for name, cols in (
        ('idx_improvement_actions_org_status_due', ['organization_id', 'status', 'due_date']),
        ('idx_improvement_actions_incident', ['incident_id']),
        ('idx_improvement_actions_owner_status', ['owner_id', 'status']),
    ):
        if not _index_exists('improvement_actions', name):
            op.create_index(name, 'improvement_actions', cols)

    if not _table_exists('reminder_log'):
        op.create_table(
            'reminder_log',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True)),
            sa.Column('entity_type', sa.String(30), nullable=False),
            sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('stage', sa.String(20), nullable=False),
            sa.Column('due_date_snapshot', sa.DateTime(timezone=True), nullable=False),
            sa.Column('sent_at', sa.DateTime(timezone=True)),
            sa.UniqueConstraint('entity_type', 'entity_id', 'stage', 'due_date_snapshot',
                                name='uq_reminder_log_entity_stage'),
            sa.CheckConstraint(_in('entity_type', ('task', 'improvement_action')),
                               name='ck_reminder_log_entity_type'),
            sa.CheckConstraint(_in('stage', ('due_soon', 'overdue')), name='ck_reminder_log_stage'),
        )


def downgrade():
    # Lossy by nature: reviews, improvement actions and the reminder log are
    # dropped with their tables.
    for table in ('reminder_log', 'improvement_actions', 'incident_reviews'):
        if _table_exists(table):
            op.drop_table(table)
    for column in ('responded_at', 'first_malicious_at'):
        if _column_exists('incidents', column):
            op.drop_column('incidents', column)
