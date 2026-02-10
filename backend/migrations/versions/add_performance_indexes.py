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


def _index_exists(index_name):
    """Check if an index already exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def upgrade():
    """Add indexes for performance."""
    
    # Timeline Events - optimize retrieval by incident and time
    if not _index_exists('ix_timeline_events_incident_timestamp'):
        op.create_index(
            'ix_timeline_events_incident_timestamp', 
            'timeline_events', 
            ['incident_id', 'timestamp']
        )
    
    # Attack Graph Edges - optimize graph traversal
    # Skip if equivalent idx_graph_edges_source / idx_graph_edges_target already exist
    if not _index_exists('ix_attack_graph_edges_source') and not _index_exists('idx_graph_edges_source'):
        op.create_index(
            'ix_attack_graph_edges_source', 
            'attack_graph_edges', 
            ['source_node_id']
        )
    if not _index_exists('ix_attack_graph_edges_target') and not _index_exists('idx_graph_edges_target'):
        op.create_index(
            'ix_attack_graph_edges_target', 
            'attack_graph_edges', 
            ['target_node_id']
        )
    
    # Compromised Hosts - optimize lookup by incident and hostname (for graph service)
    if not _index_exists('ix_compromised_hosts_incident_hostname'):
        op.create_index(
            'ix_compromised_hosts_incident_hostname',
            'compromised_hosts',
            ['incident_id', 'hostname']
        )


def downgrade():
    """Remove indexes."""
    if _index_exists('ix_compromised_hosts_incident_hostname'):
        op.drop_index('ix_compromised_hosts_incident_hostname', table_name='compromised_hosts')
    if _index_exists('ix_attack_graph_edges_target'):
        op.drop_index('ix_attack_graph_edges_target', table_name='attack_graph_edges')
    if _index_exists('ix_attack_graph_edges_source'):
        op.drop_index('ix_attack_graph_edges_source', table_name='attack_graph_edges')
    if _index_exists('ix_timeline_events_incident_timestamp'):
        op.drop_index('ix_timeline_events_incident_timestamp', table_name='timeline_events')
