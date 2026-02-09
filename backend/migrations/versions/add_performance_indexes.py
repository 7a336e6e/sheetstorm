"""Add performance indexes

Revision ID: add_performance_indexes
Revises: add_host_correlations
Create Date: 2026-02-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_performance_indexes'
down_revision = 'add_host_correlations'
branch_labels = None
depends_on = None


def upgrade():
    """Add indexes for performance."""
    
    # Timeline Events - optimize retrieval by incident and time
    op.create_index(
        'ix_timeline_events_incident_timestamp', 
        'timeline_events', 
        ['incident_id', 'timestamp']
    )
    
    # Attack Graph Edges - optimize graph traversal
    op.create_index(
        'ix_attack_graph_edges_source', 
        'attack_graph_edges', 
        ['source_node_id']
    )
    op.create_index(
        'ix_attack_graph_edges_target', 
        'attack_graph_edges', 
        ['target_node_id']
    )
    
    # Compromised Hosts - optimize lookup by incident and hostname (for graph service)
    op.create_index(
        'ix_compromised_hosts_incident_hostname',
        'compromised_hosts',
        ['incident_id', 'hostname']
    )


def downgrade():
    """Remove indexes."""
    op.drop_index('ix_compromised_hosts_incident_hostname', table_name='compromised_hosts')
    op.drop_index('ix_attack_graph_edges_target', table_name='attack_graph_edges')
    op.drop_index('ix_attack_graph_edges_source', table_name='attack_graph_edges')
    op.drop_index('ix_timeline_events_incident_timestamp', table_name='timeline_events')
