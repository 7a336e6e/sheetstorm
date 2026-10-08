"""rename is_deleted to is_archived and add archived_at/archived_by columns

Revision ID: rename_deleted_to_archived
Revises: add_mitre_mappings_jsonb
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'rename_deleted_to_archived'
down_revision = 'add_mitre_mappings_jsonb'
branch_labels = None
depends_on = None


def _columns(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _fks(table):
    return {fk['name'] for fk in sa.inspect(op.get_bind()).get_foreign_keys(table)}


def _archive_columns(table):
    """Idempotent: tolerate databases where the soft-delete column is missing
    or was already renamed (e.g. schemas created outside this chain)."""
    cols = _columns(table)
    if 'is_deleted' in cols and 'is_archived' not in cols:
        op.alter_column(table, 'is_deleted', new_column_name='is_archived')
    elif 'is_archived' not in cols:
        op.add_column(table, sa.Column('is_archived', sa.Boolean, server_default='false', nullable=False))
    if 'archived_at' not in cols:
        op.add_column(table, sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    if 'archived_by' not in cols:
        op.add_column(table, sa.Column('archived_by', UUID(as_uuid=True), nullable=True))
    fk_name = f'fk_{table}_archived_by'
    if fk_name not in _fks(table):
        op.create_foreign_key(fk_name, table, 'users', ['archived_by'], ['id'])


def upgrade():
    for table in ('incidents', 'reports', 'case_notes'):
        _archive_columns(table)


def downgrade():
    # Case notes
    op.drop_constraint('fk_case_notes_archived_by', 'case_notes', type_='foreignkey')
    op.drop_column('case_notes', 'archived_by')
    op.drop_column('case_notes', 'archived_at')
    op.alter_column('case_notes', 'is_archived', new_column_name='is_deleted')

    # Reports
    op.drop_constraint('fk_reports_archived_by', 'reports', type_='foreignkey')
    op.drop_column('reports', 'archived_by')
    op.drop_column('reports', 'archived_at')
    op.alter_column('reports', 'is_archived', new_column_name='is_deleted')

    # Incidents
    op.drop_constraint('fk_incidents_archived_by', 'incidents', type_='foreignkey')
    op.drop_column('incidents', 'archived_by')
    op.drop_column('incidents', 'archived_at')
    op.alter_column('incidents', 'is_archived', new_column_name='is_deleted')
