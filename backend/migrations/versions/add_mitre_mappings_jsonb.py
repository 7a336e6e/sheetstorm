"""Add mitre_mappings JSONB column for multi-TTP support

Revision ID: add_mitre_mappings_jsonb
Revises: restrict_viewer_perms
Create Date: 2026-02-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_mitre_mappings_jsonb'
down_revision = 'restrict_viewer_perms'
branch_labels = None
depends_on = None


def upgrade():
    """Add mitre_mappings JSONB column and migrate existing data."""

    # --- timeline_events ---
    op.add_column('timeline_events', sa.Column(
        'mitre_mappings', postgresql.JSONB(), nullable=True, server_default='[]'
    ))

    # Migrate existing single-value rows into the new JSONB array
    op.execute("""
        UPDATE timeline_events
        SET mitre_mappings = json_build_array(
            json_build_object(
                'tactic', mitre_tactic,
                'technique', mitre_technique,
                'name', ''
            )
        )
        WHERE mitre_tactic IS NOT NULL
          AND mitre_tactic != ''
          AND (mitre_mappings IS NULL OR mitre_mappings = '[]'::jsonb)
    """)

    # GIN index for JSONB containment queries
    op.create_index(
        'idx_timeline_mitre_mappings',
        'timeline_events',
        ['mitre_mappings'],
        postgresql_using='gin'
    )


def downgrade():
    op.drop_index('idx_timeline_mitre_mappings', table_name='timeline_events')
    op.drop_column('timeline_events', 'mitre_mappings')
