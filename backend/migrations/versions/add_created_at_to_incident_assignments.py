"""Add created_at column to incident_assignments table

Revision ID: add_created_at_assignments
Revises: add_performance_indexes
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_created_at_assignments'
down_revision = 'update_incident_status_check'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('incident_assignments', sa.Column(
        'created_at',
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=True
    ))


def downgrade():
    op.drop_column('incident_assignments', 'created_at')
