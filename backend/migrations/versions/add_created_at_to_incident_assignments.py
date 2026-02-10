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


def _column_exists(table, column):
    """Check if a column already exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def upgrade():
    if not _column_exists('incident_assignments', 'created_at'):
        op.add_column('incident_assignments', sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True
        ))


def downgrade():
    if _column_exists('incident_assignments', 'created_at'):
        op.drop_column('incident_assignments', 'created_at')
