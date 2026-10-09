"""optimistic-concurrency version column on user-editable incident tables

Adds ``version INTEGER NOT NULL DEFAULT 1`` to the 12 tables whose models use
``__mapper_args__ = {'version_id_col': version}`` (realtime-collab §3.4).
Existing rows get version 1 through the server default (no backfill).

Revision ID: realtime_versions
Revises: surface_dfir_prefs_reports
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'realtime_versions'
down_revision = 'surface_dfir_prefs_reports'
branch_labels = None
depends_on = None

VERSIONED_TABLES = (
    'incidents',
    'timeline_events',
    'tasks',
    'case_notes',
    'compromised_hosts',
    'compromised_accounts',
    'network_indicators',
    'host_based_indicators',
    'malware_tools',
    'attack_graph_nodes',
    'attack_graph_edges',
    'incident_playbooks',
)


def _column_exists(table, column):
    insp = sa.inspect(op.get_bind())
    return column in {c['name'] for c in insp.get_columns(table)}


def _table_exists(table):
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade():
    for table in VERSIONED_TABLES:
        if _table_exists(table) and not _column_exists(table, 'version'):
            op.add_column(table, sa.Column('version', sa.Integer(), nullable=False,
                                           server_default='1'))


def downgrade():
    for table in reversed(VERSIONED_TABLES):
        if _table_exists(table) and _column_exists(table, 'version'):
            op.drop_column(table, 'version')
