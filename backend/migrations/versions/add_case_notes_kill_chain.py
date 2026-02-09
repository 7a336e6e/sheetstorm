"""add case notes and kill chain phase

Revision ID: add_case_notes_kill_chain
Revises: add_incident_team_access
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'add_case_notes_kill_chain'
down_revision = 'add_incident_team_access'
branch_labels = None
depends_on = None


def upgrade():
    """Add case_notes table and kill_chain_phase to timeline_events."""
    # Create case_notes table
    op.create_table(
        'case_notes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('incident_id', UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('category', sa.String(50), server_default='general'),
        sa.Column('is_pinned', sa.Boolean, server_default='false'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.Column('is_deleted', sa.Boolean, server_default='false'),
    )
    op.create_index('idx_case_notes_incident', 'case_notes', ['incident_id'])
    op.create_index('idx_case_notes_created', 'case_notes', ['created_at'])

    # Add kill_chain_phase to timeline_events
    op.add_column('timeline_events', sa.Column('kill_chain_phase', sa.String(50), nullable=True))


def downgrade():
    """Remove case_notes and kill_chain_phase."""
    op.drop_column('timeline_events', 'kill_chain_phase')
    op.drop_index('idx_case_notes_created')
    op.drop_index('idx_case_notes_incident')
    op.drop_table('case_notes')
