"""custody signature key id + grant admin:manage to Administrator

- chain_of_custody.signature_key_id: short fingerprint of the HMAC key that
  signed each entry, so a CUSTODY_SIGNING_KEY rotation is detectable instead
  of every older row looking tampered.
- Administrator role gains `admin:manage` (required by the MITRE pattern
  management endpoints, never previously granted).
- artifacts.storage_type CHECK also allows 'google_drive' (Drive-primary
  uploads were rejected by the original local/s3-only constraint).

Revision ID: custody_key_id_admin_perm
Revises: add_playbooks
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'custody_key_id_admin_perm'
down_revision = 'add_playbooks'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    insp = sa.inspect(op.get_bind())
    return column in {c['name'] for c in insp.get_columns(table)}


def upgrade():
    if not _column_exists('chain_of_custody', 'signature_key_id'):
        op.add_column('chain_of_custody', sa.Column('signature_key_id', sa.String(length=16), nullable=True))

    op.execute("""
        UPDATE roles SET permissions = permissions || '["admin:manage"]'::jsonb
        WHERE name = 'Administrator'
          AND NOT permissions @> '["admin:manage"]'::jsonb
    """)

    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_storage_type_check")
    op.execute(
        "ALTER TABLE artifacts ADD CONSTRAINT artifacts_storage_type_check "
        "CHECK (storage_type IN ('local', 's3', 'google_drive'))"
    )


def downgrade():
    # Rows stored on Google Drive cannot satisfy the old constraint; keep the
    # data and only restore the original constraint when it is satisfiable.
    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_storage_type_check")
    op.execute(
        "ALTER TABLE artifacts ADD CONSTRAINT artifacts_storage_type_check "
        "CHECK (storage_type IN ('local', 's3', 'google_drive')) NOT VALID"
    )
    op.execute("""
        UPDATE roles SET permissions = permissions - 'admin:manage'
        WHERE name = 'Administrator'
    """)
    if _column_exists('chain_of_custody', 'signature_key_id'):
        op.drop_column('chain_of_custody', 'signature_key_id')
