"""add team based incident access

Revision ID: add_incident_team_access
Revises: add_performance_indexes
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = 'add_incident_team_access'
down_revision = 'add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade():
    """Add team_id to incidents and incident_teams junction table."""
    # Create junction table for many-to-many incident-team relationships
    op.create_table(
        'incident_teams',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('incident_id', UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_id', UUID(as_uuid=True), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('incident_id', 'team_id', name='uq_incident_teams'),
    )

    # Add index for faster lookups
    op.create_index('idx_incident_teams_incident', 'incident_teams', ['incident_id'])
    op.create_index('idx_incident_teams_team', 'incident_teams', ['team_id'])

    # Add teams:create, teams:read, teams:update, teams:delete permissions to Administrator role
    op.execute("""
        UPDATE roles SET permissions = permissions || '["teams:create", "teams:read", "teams:update", "teams:delete"]'::jsonb
        WHERE name = 'Administrator'
        AND NOT permissions @> '["teams:create"]'::jsonb;
    """)

    # Add teams:read to all roles that have incidents:read
    op.execute("""
        UPDATE roles SET permissions = permissions || '["teams:read"]'::jsonb
        WHERE permissions @> '["incidents:read"]'::jsonb
        AND NOT permissions @> '["teams:read"]'::jsonb;
    """)


def downgrade():
    """Remove team-based incident access."""
    op.drop_index('idx_incident_teams_team')
    op.drop_index('idx_incident_teams_incident')
    op.drop_table('incident_teams')
