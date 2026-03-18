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


def upgrade():
    # Incidents
    op.alter_column('incidents', 'is_deleted', new_column_name='is_archived')
    op.add_column('incidents', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('incidents', sa.Column('archived_by', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_incidents_archived_by', 'incidents', 'users', ['archived_by'], ['id'])

    # Reports
    op.alter_column('reports', 'is_deleted', new_column_name='is_archived')
    op.add_column('reports', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('reports', sa.Column('archived_by', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_reports_archived_by', 'reports', 'users', ['archived_by'], ['id'])

    # Case notes
    op.alter_column('case_notes', 'is_deleted', new_column_name='is_archived')
    op.add_column('case_notes', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('case_notes', sa.Column('archived_by', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_case_notes_archived_by', 'case_notes', 'users', ['archived_by'], ['id'])


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
