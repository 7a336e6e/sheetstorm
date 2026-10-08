"""add acquisition metadata, legal hold, and custody signatures

Revision ID: add_custody_metadata
Revises: a1b2c3d4e5f6
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_custody_metadata'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('artifacts', sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('artifacts', sa.Column('acquisition_method', sa.String(length=100), nullable=True))
    op.add_column('artifacts', sa.Column('acquisition_tool', sa.String(length=150), nullable=True))
    op.add_column('artifacts', sa.Column('source_host', sa.String(length=255), nullable=True))
    op.add_column('artifacts', sa.Column('legal_hold_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('artifacts', sa.Column('is_locked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('chain_of_custody', sa.Column('signature', sa.String(length=64), nullable=True))

    # Allow the new custody actions (delete, legal_hold) at the DB level.
    op.execute("ALTER TABLE chain_of_custody DROP CONSTRAINT IF EXISTS chain_of_custody_action_check")
    op.execute(
        "ALTER TABLE chain_of_custody ADD CONSTRAINT chain_of_custody_action_check "
        "CHECK (action IN ('upload','view','download','transfer','verify','export','delete','legal_hold'))"
    )


def downgrade():
    op.execute("ALTER TABLE chain_of_custody DROP CONSTRAINT IF EXISTS chain_of_custody_action_check")
    op.execute(
        "ALTER TABLE chain_of_custody ADD CONSTRAINT chain_of_custody_action_check "
        "CHECK (action IN ('upload','view','download','transfer','verify','export'))"
    )
    op.drop_column('chain_of_custody', 'signature')
    op.drop_column('artifacts', 'is_locked')
    op.drop_column('artifacts', 'legal_hold_until')
    op.drop_column('artifacts', 'source_host')
    op.drop_column('artifacts', 'acquisition_tool')
    op.drop_column('artifacts', 'acquisition_method')
    op.drop_column('artifacts', 'acquired_at')
