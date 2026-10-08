"""add DFIR investigation depth fields (leads, triage, dual-time, confidence)

Revision ID: add_dfir_fields
Revises: add_openai_compatible
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'add_dfir_fields'
down_revision = 'add_openai_compatible'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('task_type', sa.String(length=50), nullable=False, server_default='action_item'))
    op.add_column('tasks', sa.Column('lead_outcome', sa.String(length=50), nullable=True))
    op.add_column('tasks', sa.Column('investigation_direction', sa.Text(), nullable=True))
    op.add_column('tasks', sa.Column('evidence_refs', JSONB(), nullable=True, server_default='[]'))
    op.add_column('compromised_hosts', sa.Column('triage_status', sa.String(length=50), nullable=False, server_default='under_analysis'))
    op.add_column('compromised_hosts', sa.Column('acquisition_status', JSONB(), nullable=True, server_default='{}'))
    op.add_column('timeline_events', sa.Column('detection_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('timeline_events', sa.Column('confidence_level', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('timeline_events', 'confidence_level')
    op.drop_column('timeline_events', 'detection_time')
    op.drop_column('compromised_hosts', 'acquisition_status')
    op.drop_column('compromised_hosts', 'triage_status')
    op.drop_column('tasks', 'evidence_refs')
    op.drop_column('tasks', 'investigation_direction')
    op.drop_column('tasks', 'lead_outcome')
    op.drop_column('tasks', 'task_type')
