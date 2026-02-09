"""Add teams table, team_members table, and organizational_role column

Revision ID: add_teams_and_org_roles
Revises: add_performance_indexes
Create Date: 2026-02-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_teams_and_org_roles'
down_revision = 'add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade():
    """Add teams, team_members tables and organizational_role to users."""

    # Add organizational_role to users
    op.add_column('users', sa.Column(
        'organizational_role', sa.String(150), nullable=True
    ))

    # Teams table
    op.create_table(
        'teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('organization_id', 'name', name='uq_teams_org_name'),
    )
    op.create_index('idx_teams_org', 'teams', ['organization_id'])

    # Team members junction table
    op.create_table(
        'team_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('team_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_members_team_user'),
    )
    op.create_index('idx_team_members_user', 'team_members', ['user_id'])
    op.create_index('idx_team_members_team', 'team_members', ['team_id'])


def downgrade():
    """Remove teams, team_members tables and organizational_role from users."""
    op.drop_table('team_members')
    op.drop_table('teams')
    op.drop_column('users', 'organizational_role')
