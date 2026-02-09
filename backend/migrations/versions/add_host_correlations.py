"""Add host and timeline correlations

Revision ID: add_host_correlations
Revises: 
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_host_correlations'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add FK columns for host and timeline correlations."""
    
    # Timeline Events - add host_id FK and is_ioc flag
    op.add_column('timeline_events', sa.Column(
        'host_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column('timeline_events', sa.Column(
        'is_ioc', sa.Boolean(), nullable=True, server_default='false'
    ))
    op.create_foreign_key(
        'fk_timeline_events_host_id', 'timeline_events', 'compromised_hosts',
        ['host_id'], ['id'], ondelete='SET NULL'
    )
    
    # Compromised Accounts - add host_id and timeline_event_id FKs
    op.add_column('compromised_accounts', sa.Column(
        'host_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column('compromised_accounts', sa.Column(
        'timeline_event_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        'fk_compromised_accounts_host_id', 'compromised_accounts', 'compromised_hosts',
        ['host_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_compromised_accounts_timeline_event_id', 'compromised_accounts', 'timeline_events',
        ['timeline_event_id'], ['id'], ondelete='SET NULL'
    )
    
    # Network Indicators - add host_id and timeline_event_id FKs
    op.add_column('network_indicators', sa.Column(
        'host_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column('network_indicators', sa.Column(
        'timeline_event_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        'fk_network_indicators_host_id', 'network_indicators', 'compromised_hosts',
        ['host_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_network_indicators_timeline_event_id', 'network_indicators', 'timeline_events',
        ['timeline_event_id'], ['id'], ondelete='SET NULL'
    )
    
    # Host Based Indicators - add host_id and timeline_event_id FKs
    op.add_column('host_based_indicators', sa.Column(
        'host_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column('host_based_indicators', sa.Column(
        'timeline_event_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        'fk_host_based_indicators_host_id', 'host_based_indicators', 'compromised_hosts',
        ['host_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_host_based_indicators_timeline_event_id', 'host_based_indicators', 'timeline_events',
        ['timeline_event_id'], ['id'], ondelete='SET NULL'
    )
    
    # Malware Tools - add host_id FK
    op.add_column('malware_tools', sa.Column(
        'host_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        'fk_malware_tools_host_id', 'malware_tools', 'compromised_hosts',
        ['host_id'], ['id'], ondelete='SET NULL'
    )


def downgrade():
    """Remove FK columns for host and timeline correlations."""
    
    # Malware Tools
    op.drop_constraint('fk_malware_tools_host_id', 'malware_tools', type_='foreignkey')
    op.drop_column('malware_tools', 'host_id')
    
    # Host Based Indicators
    op.drop_constraint('fk_host_based_indicators_timeline_event_id', 'host_based_indicators', type_='foreignkey')
    op.drop_constraint('fk_host_based_indicators_host_id', 'host_based_indicators', type_='foreignkey')
    op.drop_column('host_based_indicators', 'timeline_event_id')
    op.drop_column('host_based_indicators', 'host_id')
    
    # Network Indicators
    op.drop_constraint('fk_network_indicators_timeline_event_id', 'network_indicators', type_='foreignkey')
    op.drop_constraint('fk_network_indicators_host_id', 'network_indicators', type_='foreignkey')
    op.drop_column('network_indicators', 'timeline_event_id')
    op.drop_column('network_indicators', 'host_id')
    
    # Compromised Accounts
    op.drop_constraint('fk_compromised_accounts_timeline_event_id', 'compromised_accounts', type_='foreignkey')
    op.drop_constraint('fk_compromised_accounts_host_id', 'compromised_accounts', type_='foreignkey')
    op.drop_column('compromised_accounts', 'timeline_event_id')
    op.drop_column('compromised_accounts', 'host_id')
    
    # Timeline Events
    op.drop_constraint('fk_timeline_events_host_id', 'timeline_events', type_='foreignkey')
    op.drop_column('timeline_events', 'is_ioc')
    op.drop_column('timeline_events', 'host_id')
