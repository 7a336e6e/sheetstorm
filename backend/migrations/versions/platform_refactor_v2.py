"""Platform refactoring v2 — custom field options, TLP, network IOC source/dest, default team

Revision ID: platform_refactor_v2
Revises: update_integration_type_check
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'platform_refactor_v2'
down_revision = 'update_integration_type_check'
branch_labels = None
depends_on = None


def upgrade():
    """Add custom_field_options table, TLP to incidents, source/dest host IDs to network_indicators, default team flag."""
    
    # 1. Create custom_field_options table for storing custom system types, artifact types, etc.
    op.create_table(
        'custom_field_options',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),  # e.g., 'system_type', 'artifact_type', 'protocol'
        sa.Column('field_value', sa.String(255), nullable=False),
        sa.Column('display_label', sa.String(255)),
        sa.Column('is_default', sa.Boolean, server_default='false'),  # built-in vs user-created
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'field_name', 'field_value', name='uq_custom_field_option'),
    )
    op.create_index('idx_custom_field_options_field', 'custom_field_options', ['organization_id', 'field_name'])

    # 2. Add TLP (Traffic Light Protocol) to incidents
    op.add_column('incidents', sa.Column('tlp', sa.String(20), server_default='amber', nullable=True))

    # 3. Add source/destination host ID FKs to network_indicators for graph integration
    op.add_column('network_indicators', sa.Column('source_host_id', UUID(as_uuid=True), nullable=True))
    op.add_column('network_indicators', sa.Column('destination_host_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_network_indicators_source_host', 'network_indicators', 'compromised_hosts',
        ['source_host_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_network_indicators_dest_host', 'network_indicators', 'compromised_hosts',
        ['destination_host_id'], ['id'], ondelete='SET NULL'
    )

    # 4. Add is_default flag to teams table for default team support
    op.add_column('teams', sa.Column('is_default', sa.Boolean, server_default='false', nullable=True))

    # 5. Add team_id FK to incidents for team-based creation
    op.add_column('incidents', sa.Column('team_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_incidents_team', 'incidents', 'teams',
        ['team_id'], ['id'], ondelete='SET NULL'
    )


def downgrade():
    """Remove platform refactor v2 changes."""
    op.drop_constraint('fk_incidents_team', 'incidents', type_='foreignkey')
    op.drop_column('incidents', 'team_id')
    op.drop_column('teams', 'is_default')
    op.drop_constraint('fk_network_indicators_dest_host', 'network_indicators', type_='foreignkey')
    op.drop_constraint('fk_network_indicators_source_host', 'network_indicators', type_='foreignkey')
    op.drop_column('network_indicators', 'destination_host_id')
    op.drop_column('network_indicators', 'source_host_id')
    op.drop_column('incidents', 'tlp')
    op.drop_index('idx_custom_field_options_field')
    op.drop_table('custom_field_options')
