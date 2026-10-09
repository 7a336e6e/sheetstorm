"""investigative questions, case templates, custom fields

Creates ``investigative_questions``, ``investigative_question_leads``,
``case_templates`` and ``incident_case_templates``; adds
``incidents.custom_fields`` (JSONB, default ``{}``), ``playbooks.cloned_from``
and ``incident_playbooks.builtin_key``.

No data is seeded (built-in questions, templates and playbooks are shipped
with the application) and no role is updated: ``templates:manage`` and every
other permission grant live in ``admin_guardrails_rbac``.

Idempotent: every table / column is created only when missing, so a re-run is
a no-op. Downgrade drops the three columns and the four tables (child tables
first); the question and template data they hold is lost.

Revision ID: questions_case_templates
Revises: add_record_provenance
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'questions_case_templates'
down_revision = 'add_record_provenance'
branch_labels = None
depends_on = None


def _table_exists(table):
    return sa.inspect(op.get_bind()).has_table(table)


def _column_exists(table, column):
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and column in {c['name'] for c in insp.get_columns(table)}


def _uuid_pk():
    return sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True)


def _created_at():
    return sa.Column('created_at', sa.DateTime(timezone=True))


def upgrade():
    if not _table_exists('investigative_questions'):
        op.create_table(
            'investigative_questions',
            _uuid_pk(), _created_at(),
            sa.Column('incident_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('question', sa.String(1000), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('facet', sa.String(255)),
            sa.Column('status', sa.String(20), nullable=False, server_default='open'),
            sa.Column('answer', sa.Text()),
            sa.Column('confidence', sa.String(20)),
            sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
            sa.Column('phase', sa.Integer()),
            sa.Column('owner_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('evidence_refs', postgresql.JSONB(), nullable=False, server_default='[]'),
            sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
            sa.Column('source_ref', sa.String(160)),
            sa.Column('dedupe_key', sa.String(160)),
            sa.Column('guidance', postgresql.JSONB(), nullable=False, server_default='[]'),
            sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('answered_at', sa.DateTime(timezone=True)),
            sa.Column('answered_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.CheckConstraint("status IN ('open', 'in_progress', 'answered', 'unanswerable')",
                               name='ck_investigative_question_status'),
            sa.CheckConstraint("confidence IS NULL OR confidence IN ('low', 'medium', 'high', 'confirmed')",
                               name='ck_investigative_question_confidence'),
            sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')",
                               name='ck_investigative_question_priority'),
            sa.CheckConstraint('phase IS NULL OR (phase >= 1 AND phase <= 6)',
                               name='ck_investigative_question_phase'),
            sa.CheckConstraint("source IN ('manual', 'dfiq', 'core', 'template')",
                               name='ck_investigative_question_source'),
        )
        op.create_index('idx_investigative_questions_incident_status', 'investigative_questions',
                        ['incident_id', 'status'])
        op.create_index('idx_investigative_questions_owner', 'investigative_questions', ['owner_id'])
        op.create_index('uq_investigative_questions_dedupe', 'investigative_questions',
                        ['incident_id', 'dedupe_key'], unique=True,
                        postgresql_where=sa.text('dedupe_key IS NOT NULL'))

    if not _table_exists('investigative_question_leads'):
        op.create_table(
            'investigative_question_leads',
            _uuid_pk(), _created_at(),
            sa.Column('question_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('investigative_questions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('task_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.UniqueConstraint('question_id', 'task_id', name='uq_investigative_question_lead'),
        )
        op.create_index('idx_investigative_question_leads_task', 'investigative_question_leads', ['task_id'])

    if not _table_exists('case_templates'):
        op.create_table(
            'case_templates',
            _uuid_pk(), _created_at(),
            sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('key', sa.String(64), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('incident_type', sa.String(100)),
            sa.Column('definition', postgresql.JSONB(), nullable=False, server_default='{}'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('cloned_from', sa.String(120)),
            sa.Column('created_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('updated_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.UniqueConstraint('organization_id', 'key', name='uq_case_templates_org_key'),
        )

    if not _table_exists('incident_case_templates'):
        op.create_table(
            'incident_case_templates',
            _uuid_pk(), _created_at(),
            sa.Column('incident_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('case_template_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('case_templates.id', ondelete='SET NULL')),
            sa.Column('builtin_key', sa.String(64)),
            sa.Column('template_key', sa.String(64), nullable=False),
            sa.Column('template_name', sa.String(255), nullable=False),
            sa.Column('template_version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('custom_field_defs', postgresql.JSONB(), nullable=False, server_default='[]'),
            sa.Column('result', postgresql.JSONB(), nullable=False, server_default='{}'),
            sa.Column('applied_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('applied_at', sa.DateTime(timezone=True)),
        )
        op.create_index('idx_incident_case_templates_incident', 'incident_case_templates', ['incident_id'])

    if not _column_exists('incidents', 'custom_fields'):
        op.add_column('incidents', sa.Column('custom_fields', postgresql.JSONB(), nullable=False,
                                             server_default='{}'))
    if not _column_exists('playbooks', 'cloned_from'):
        op.add_column('playbooks', sa.Column('cloned_from', sa.String(120)))
    if not _column_exists('incident_playbooks', 'builtin_key'):
        op.add_column('incident_playbooks', sa.Column('builtin_key', sa.String(64)))


def downgrade():
    if _column_exists('incident_playbooks', 'builtin_key'):
        op.drop_column('incident_playbooks', 'builtin_key')
    if _column_exists('playbooks', 'cloned_from'):
        op.drop_column('playbooks', 'cloned_from')
    if _column_exists('incidents', 'custom_fields'):
        op.drop_column('incidents', 'custom_fields')
    # Children before parents.
    for table in ('incident_case_templates', 'case_templates', 'investigative_question_leads',
                  'investigative_questions'):
        if _table_exists(table):
            op.drop_table(table)
