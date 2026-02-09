"""Add mfa_backup_codes column to users table

Revision ID: add_mfa_backup_codes
Revises: update_edge_types
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_mfa_backup_codes'
down_revision = 'update_edge_types'
branch_labels = None
depends_on = None


def upgrade():
    """Add mfa_backup_codes column to users."""
    op.add_column('users', sa.Column(
        'mfa_backup_codes', sa.Text(), nullable=True
    ))


def downgrade():
    """Remove mfa_backup_codes column from users."""
    op.drop_column('users', 'mfa_backup_codes')
