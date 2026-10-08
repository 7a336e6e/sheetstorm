"""users.preferences + report snapshot columns (schema only)

- users.preferences JSONB NOT NULL DEFAULT '{}': per-user UI preferences.
  The API allowlists keys (today only `display_timezone`: 'utc'|'local').
- reports.sha256 / size_bytes / storage_type: columns for immutable report
  snapshots. Populated later by the report-snapshot work (W3-DFIR-C); no data
  is written here, and the linked_entities -> evidence_refs copy lives in
  `task_evidence_refs_backfill`, not here.

Revision ID: surface_dfir_prefs_reports
Revises: custody_key_id_admin_perm
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'surface_dfir_prefs_reports'
# Planned predecessor is `admin_guardrails_rbac` (_integration.md §4); the
# integrator re-chains this to the integration head at merge time.
down_revision = 'custody_key_id_admin_perm'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    insp = sa.inspect(op.get_bind())
    return column in {c['name'] for c in insp.get_columns(table)}


def upgrade():
    if not _column_exists('users', 'preferences'):
        op.add_column('users', sa.Column(
            'preferences', postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ))
    if not _column_exists('reports', 'sha256'):
        op.add_column('reports', sa.Column('sha256', sa.String(length=64), nullable=True))
    if not _column_exists('reports', 'size_bytes'):
        op.add_column('reports', sa.Column('size_bytes', sa.BigInteger(), nullable=True))
    if not _column_exists('reports', 'storage_type'):
        op.add_column('reports', sa.Column('storage_type', sa.String(length=20), nullable=True))


def downgrade():
    for table, column in (('reports', 'storage_type'), ('reports', 'size_bytes'),
                          ('reports', 'sha256'), ('users', 'preferences')):
        if _column_exists(table, column):
            op.drop_column(table, column)
