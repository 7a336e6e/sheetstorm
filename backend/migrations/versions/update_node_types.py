"""Update attack graph node types check constraint

Revision ID: update_node_types
Revises: add_host_correlations
Create Date: 2026-02-06 17:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'update_node_types'
down_revision = 'add_teams_and_org_roles'
branch_labels = None
depends_on = None


def upgrade():
    """Update check constraint for attack graph node types."""
    # Drop existing constraint
    op.execute("ALTER TABLE attack_graph_nodes DROP CONSTRAINT IF EXISTS attack_graph_nodes_node_type_check")
    
    # Create new constraint with expanded list
    node_types = [
        'workstation', 'server', 'domain_controller', 'attacker', 'c2_server',
        'cloud_resource', 'user', 'service_account', 'external', 'unknown',
        'ip_address', 'malware', 'host_indicator', 'database', 'web_server', 'file_server'
    ]
    types_str = "', '".join(node_types)
    op.execute(f"ALTER TABLE attack_graph_nodes ADD CONSTRAINT attack_graph_nodes_node_type_check CHECK (node_type IN ('{types_str}'))")


def downgrade():
    """Revert check constraint to original list (approximate)."""
    op.execute("ALTER TABLE attack_graph_nodes DROP CONSTRAINT IF EXISTS attack_graph_nodes_node_type_check")
    
    # Original list (inferred from previous state)
    node_types = [
        'workstation', 'server', 'domain_controller', 'attacker', 'c2_server',
        'cloud_resource', 'user', 'service_account', 'external', 'unknown',
        'ip_address', 'database'
    ]
    types_str = "', '".join(node_types)
    op.execute(f"ALTER TABLE attack_graph_nodes ADD CONSTRAINT attack_graph_nodes_node_type_check CHECK (node_type IN ('{types_str}'))")
