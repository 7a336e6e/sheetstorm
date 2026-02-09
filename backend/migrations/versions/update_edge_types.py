"""Update attack graph edge types check constraint

Revision ID: update_edge_types
Revises: update_node_types
Create Date: 2026-02-06 17:15:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'update_edge_types'
down_revision = 'update_node_types'
branch_labels = None
depends_on = None


def upgrade():
    """Update check constraint for attack graph edge types."""
    # Drop existing constraint
    op.execute("ALTER TABLE attack_graph_edges DROP CONSTRAINT IF EXISTS attack_graph_edges_edge_type_check")
    
    # Create new constraint with expanded list
    edge_types = [
        'lateral_movement', 'credential_theft', 'data_exfiltration', 'command_control',
        'initial_access', 'privilege_escalation', 'persistence', 'discovery',
        'execution', 'defense_evasion', 'collection', 'associated_with'
    ]
    types_str = "', '".join(edge_types)
    op.execute(f"ALTER TABLE attack_graph_edges ADD CONSTRAINT attack_graph_edges_edge_type_check CHECK (edge_type IN ('{types_str}'))")


def downgrade():
    """Revert check constraint to original list (approximate)."""
    op.execute("ALTER TABLE attack_graph_edges DROP CONSTRAINT IF EXISTS attack_graph_edges_edge_type_check")
    
    # Original list (inferred from previous state, without 'associated_with')
    edge_types = [
        'lateral_movement', 'credential_theft', 'data_exfiltration', 'command_control',
        'initial_access', 'privilege_escalation', 'persistence', 'discovery',
        'execution', 'defense_evasion', 'collection'
    ]
    types_str = "', '".join(edge_types)
    op.execute(f"ALTER TABLE attack_graph_edges ADD CONSTRAINT attack_graph_edges_edge_type_check CHECK (edge_type IN ('{types_str}'))")
