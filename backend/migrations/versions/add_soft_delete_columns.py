"""add is_deleted soft delete column to incidents and reports

Revision ID: add_soft_delete_columns
Revises: add_case_notes_kill_chain
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_soft_delete_columns'
down_revision = 'add_case_notes_kill_chain'
branch_labels = None
depends_on = None


def upgrade():
    """Add is_deleted column to incidents and reports tables."""
    op.add_column('incidents', sa.Column('is_deleted', sa.Boolean, server_default='false', nullable=False))
    op.add_column('reports', sa.Column('is_deleted', sa.Boolean, server_default='false', nullable=False))


def downgrade():
    """Remove is_deleted column from incidents and reports tables."""
    op.drop_column('reports', 'is_deleted')
    op.drop_column('incidents', 'is_deleted')
