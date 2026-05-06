"""Add MITRE patterns table

Revision ID: a1b2c3d4e5f6
Revises: update_account_type_check
Create Date: 2026-05-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'update_account_type_check'
branch_labels = None
depends_on = None


def upgrade():
    """Create per-organization MITRE pattern storage."""
    op.create_table(
        'mitre_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('technique', sa.String(20), nullable=False),
        sa.Column('tactic', sa.String(80), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('keywords', postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column('regex', postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_mitre_patterns_org', 'mitre_patterns', ['organization_id'])
    op.create_index(
        'uq_mitre_patterns_org_technique',
        'mitre_patterns',
        ['organization_id', 'technique'],
        unique=True
    )


def downgrade():
    op.drop_table('mitre_patterns')
