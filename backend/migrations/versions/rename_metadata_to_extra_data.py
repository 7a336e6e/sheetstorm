"""Rename metadata column to extra_data across all tables

Revision ID: rename_metadata_to_extra_data
Revises: add_created_at_assignments
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rename_metadata_to_extra_data'
down_revision = 'add_created_at_assignments'
branch_labels = None
depends_on = None

TABLES = [
    'artifacts',
    'attack_graph_edges',
    'attack_graph_nodes',
    'chain_of_custody',
    'compromised_accounts',
    'compromised_hosts',
    'host_based_indicators',
    'malware_tools',
    'network_indicators',
    'notifications',
    'tasks',
    'timeline_events',
]


def _column_exists(table, column):
    """Check if a column already exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def upgrade():
    for table in TABLES:
        # Only rename if old 'metadata' column exists (skip if init schema already uses 'extra_data')
        if _column_exists(table, 'metadata'):
            op.alter_column(table, 'metadata', new_column_name='extra_data')


def downgrade():
    for table in TABLES:
        if _column_exists(table, 'extra_data'):
            op.alter_column(table, 'extra_data', new_column_name='metadata')
