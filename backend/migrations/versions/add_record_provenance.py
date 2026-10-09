"""record provenance on events / IOCs + host clock skew

Adds the provenance columns (decision-log-provenance §3.2) to
``timeline_events``, ``network_indicators``, ``host_based_indicators`` and
``malware_tools``:

* ``source_artifact_id`` (FK artifacts, ON DELETE SET NULL) and
  ``source_evidence_id`` (FK evidence_items, ON DELETE SET NULL; preferred in
  the UI), ``source_record_type``, ``source_record_ref``, ``raw_timestamp``,
  ``source_timezone``, ``timestamp_type``, ``timestamp_derivation``,
  ``clock_skew_applied_seconds``, ``extraction_tool``,
  ``extraction_tool_version``, ``provenance_verified_by`` (FK users, SET NULL),
  ``provenance_verified_at``;
* indexes ``(incident_id, source_artifact_id)`` and
  ``(incident_id, source_evidence_id)`` on each table;

and to ``compromised_hosts`` the clock-skew columns ``clock_skew_seconds``,
``clock_skew_basis``, ``clock_skew_measured_by`` (FK users, SET NULL),
``clock_skew_measured_at`` and ``timezone``.

Existing rows keep every new column NULL (a NULL derivation reads as
``manual``). Idempotent (column / index / table guards); the downgrade drops
exactly what the upgrade adds. No ``UPDATE`` on any versioned row, so no
``version`` bump is needed.

Revision ID: add_record_provenance
Revises: task_evidence_refs_backfill
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'add_record_provenance'
down_revision = 'task_evidence_refs_backfill'
branch_labels = None
depends_on = None

PROVENANCE_TABLES = ('timeline_events', 'network_indicators', 'host_based_indicators', 'malware_tools')
HOST_TABLE = 'compromised_hosts'


def _table_exists(table):
    return sa.inspect(op.get_bind()).has_table(table)


def _columns(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _provenance_columns(table):
    """(name, Column) pairs; FK columns are built inline so the constraint is
    created with the column."""
    return [
        ('source_artifact_id', sa.Column('source_artifact_id', pg.UUID(as_uuid=True),
                                         sa.ForeignKey('artifacts.id', ondelete='SET NULL',
                                                       name=f'fk_{table}_source_artifact'), nullable=True)),
        ('source_evidence_id', sa.Column('source_evidence_id', pg.UUID(as_uuid=True),
                                         sa.ForeignKey('evidence_items.id', ondelete='SET NULL',
                                                       name=f'fk_{table}_source_evidence'), nullable=True)),
        ('source_record_type', sa.Column('source_record_type', sa.String(30))),
        ('source_record_ref', sa.Column('source_record_ref', sa.String(1000))),
        ('raw_timestamp', sa.Column('raw_timestamp', sa.String(100))),
        ('source_timezone', sa.Column('source_timezone', sa.String(64))),
        ('timestamp_type', sa.Column('timestamp_type', sa.String(20))),
        ('timestamp_derivation', sa.Column('timestamp_derivation', sa.String(20))),
        ('clock_skew_applied_seconds', sa.Column('clock_skew_applied_seconds', sa.Integer())),
        ('extraction_tool', sa.Column('extraction_tool', sa.String(150))),
        ('extraction_tool_version', sa.Column('extraction_tool_version', sa.String(50))),
        ('provenance_verified_by', sa.Column('provenance_verified_by', pg.UUID(as_uuid=True),
                                             sa.ForeignKey('users.id', ondelete='SET NULL',
                                                           name=f'fk_{table}_prov_verified_by'),
                                             nullable=True)),
        ('provenance_verified_at', sa.Column('provenance_verified_at', sa.DateTime(timezone=True))),
    ]


def _host_columns():
    return [
        ('clock_skew_seconds', sa.Column('clock_skew_seconds', sa.Integer())),
        ('clock_skew_basis', sa.Column('clock_skew_basis', sa.Text())),
        ('clock_skew_measured_by', sa.Column('clock_skew_measured_by', pg.UUID(as_uuid=True),
                                             sa.ForeignKey('users.id', ondelete='SET NULL',
                                                           name='fk_compromised_hosts_skew_measured_by'),
                                             nullable=True)),
        ('clock_skew_measured_at', sa.Column('clock_skew_measured_at', sa.DateTime(timezone=True))),
        ('timezone', sa.Column('timezone', sa.String(64))),
    ]


def _index_names(table):
    return (f'idx_{table}_incident_source_artifact', f'idx_{table}_incident_source_evidence')


def upgrade():
    for table in PROVENANCE_TABLES:
        if not _table_exists(table):
            continue
        existing = _columns(table)
        for name, column in _provenance_columns(table):
            if name not in existing:
                op.add_column(table, column)
        art_idx, ev_idx = _index_names(table)
        indexes = _indexes(table)
        if art_idx not in indexes:
            op.create_index(art_idx, table, ['incident_id', 'source_artifact_id'])
        if ev_idx not in indexes:
            op.create_index(ev_idx, table, ['incident_id', 'source_evidence_id'])

    if _table_exists(HOST_TABLE):
        existing = _columns(HOST_TABLE)
        for name, column in _host_columns():
            if name not in existing:
                op.add_column(HOST_TABLE, column)


def downgrade():
    if _table_exists(HOST_TABLE):
        existing = _columns(HOST_TABLE)
        for name, _ in reversed(_host_columns()):
            if name in existing:
                op.drop_column(HOST_TABLE, name)

    for table in reversed(PROVENANCE_TABLES):
        if not _table_exists(table):
            continue
        indexes = _indexes(table)
        for idx in _index_names(table):
            if idx in indexes:
                op.drop_index(idx, table_name=table)
        existing = _columns(table)
        for name, _ in reversed(_provenance_columns(table)):
            if name in existing:
                op.drop_column(table, name)
