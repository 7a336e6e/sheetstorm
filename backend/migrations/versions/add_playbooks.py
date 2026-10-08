"""add IR-aligned playbooks (templates + incident instances)

Revision ID: add_playbooks
Revises: add_dfir_fields
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = 'add_playbooks'
down_revision = 'add_dfir_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'playbooks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('incident_type', sa.String(length=100)),
        sa.Column('definition', JSONB(), server_default='{}'),
        sa.Column('is_template', sa.Boolean(), server_default=sa.true()),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )
    op.create_index('idx_playbooks_org', 'playbooks', ['organization_id'])

    op.create_table(
        'incident_playbooks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('incident_id', UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('playbook_id', UUID(as_uuid=True), sa.ForeignKey('playbooks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(length=255)),
        sa.Column('definition', JSONB(), server_default='{}'),
        sa.Column('current_phase', sa.Integer(), server_default='1'),
        sa.Column('state', JSONB(), server_default='{}'),
        sa.Column('activated_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )
    op.create_index('idx_incident_playbooks_incident', 'incident_playbooks', ['incident_id'])


def downgrade():
    op.drop_index('idx_incident_playbooks_incident', table_name='incident_playbooks')
    op.drop_table('incident_playbooks')
    op.drop_index('idx_playbooks_org', table_name='playbooks')
    op.drop_table('playbooks')
