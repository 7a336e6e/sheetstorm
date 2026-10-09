"""audit governance: append-only, hash-chained audit log

* Drops the audit_logs foreign keys, so deleting a user / incident / org never
  rewrites an audit row (and the original ids survive).
* Adds the keyed hash-chain columns (chain_seq, prev_hash, row_hash,
  chain_key_id). Existing rows stay NULL ("legacy, unchained"); there is no
  backfill because the chain key must never be needed inside a migration.
* Adds composite indexes for the org-scoped audit queries.
* Adds ``ledger_heads`` (chain heads; services/ledger.py).
* Adds ``integrations.last_tested_at`` / ``last_test_ok``.
* Creates ``audit_logs_append_only()`` and its triggers LAST: UPDATE, DELETE
  and TRUNCATE on audit_logs raise (SQLSTATE 42501) unless the retention purge
  set ``sheetstorm.audit_purge = 'on'`` (DELETE only).

No permission grants here (``audit_logs:export`` is granted by
admin_guardrails_rbac). Downgrade drops the triggers FIRST and re-adds the
foreign keys as NOT VALID (ids may now dangle).

Revision ID: audit_governance
Revises: realtime_versions
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'audit_governance'
down_revision = 'realtime_versions'
branch_labels = None
depends_on = None

_FKS = (
    ('audit_logs_organization_id_fkey', 'organization_id', 'organizations'),
    ('audit_logs_user_id_fkey', 'user_id', 'users'),
    ('audit_logs_incident_id_fkey', 'incident_id', 'incidents'),
)

_CHAIN_COLUMNS = (
    ('chain_seq', sa.BigInteger()),
    ('prev_hash', sa.String(64)),
    ('row_hash', sa.String(64)),
    ('chain_key_id', sa.String(16)),
)

_INDEXES = (
    # Unique per chain; NULL org rows form the 'audit:global' chain.
    ("uq_audit_org_seq",
     "CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_org_seq ON audit_logs "
     "((COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid)), chain_seq) "
     "WHERE chain_seq IS NOT NULL"),
    ("idx_audit_org_created_id",
     "CREATE INDEX IF NOT EXISTS idx_audit_org_created_id ON audit_logs "
     "(organization_id, created_at DESC, id)"),
    ("idx_audit_org_user_created",
     "CREATE INDEX IF NOT EXISTS idx_audit_org_user_created ON audit_logs "
     "(organization_id, user_id, created_at DESC)"),
    ("idx_audit_org_event_created",
     "CREATE INDEX IF NOT EXISTS idx_audit_org_event_created ON audit_logs "
     "(organization_id, event_type, created_at DESC)"),
)

_INTEGRATION_COLUMNS = (
    ('last_tested_at', sa.DateTime(timezone=True)),
    ('last_test_ok', sa.Boolean()),
)

_APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('sheetstorm.audit_purge', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'audit_logs is append-only (% blocked)', TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$ LANGUAGE plpgsql;
"""


def _bind():
    return op.get_bind()


def _table_exists(table):
    return sa.inspect(_bind()).has_table(table)


def _column_exists(table, column):
    return column in {c['name'] for c in sa.inspect(_bind()).get_columns(table)}


def _audit_fk_names():
    return set(_bind().execute(sa.text(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'audit_logs'::regclass AND contype = 'f'")).scalars())


def upgrade():
    # 1. No foreign keys on the append-only table (any ON DELETE SET NULL
    #    would turn a user / incident delete into a blocked UPDATE).
    for name in sorted(_audit_fk_names()):
        op.execute(sa.text(f'ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS "{name}"'))

    # 2. Chain columns (legacy rows stay NULL).
    for name, type_ in _CHAIN_COLUMNS:
        if not _column_exists('audit_logs', name):
            op.add_column('audit_logs', sa.Column(name, type_, nullable=True))

    # 3-4. Chain uniqueness + composite indexes.
    for _, ddl in _INDEXES:
        op.execute(sa.text(ddl))

    # 5. Chain heads.
    if not _table_exists('ledger_heads'):
        op.create_table(
            'ledger_heads',
            sa.Column('chain_key', sa.String(100), primary_key=True),
            sa.Column('last_seq', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('last_hash', sa.String(64)),
            sa.Column('purged_through_seq', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('anchor_hash', sa.String(64)),
            sa.Column('last_verified_at', sa.DateTime(timezone=True)),
            sa.Column('last_verify_ok', sa.Boolean()),
            sa.Column('last_verify_summary', sa.dialects.postgresql.JSONB()),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
        )

    # 6. Integration connection-test result.
    for name, type_ in _INTEGRATION_COLUMNS:
        if _table_exists('integrations') and not _column_exists('integrations', name):
            op.add_column('integrations', sa.Column(name, type_, nullable=True))

    # 7. Append-only triggers, created last.
    op.execute(sa.text(_APPEND_ONLY_FN))
    op.execute(sa.text('DROP TRIGGER IF EXISTS audit_logs_append_only_row ON audit_logs'))
    op.execute(sa.text(
        'CREATE TRIGGER audit_logs_append_only_row BEFORE UPDATE OR DELETE ON audit_logs '
        'FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()'))
    op.execute(sa.text('DROP TRIGGER IF EXISTS audit_logs_append_only_truncate ON audit_logs'))
    op.execute(sa.text(
        'CREATE TRIGGER audit_logs_append_only_truncate BEFORE TRUNCATE ON audit_logs '
        'FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_append_only()'))


def downgrade():
    # Triggers first, so the rest of the downgrade may touch the table.
    op.execute(sa.text('DROP TRIGGER IF EXISTS audit_logs_append_only_truncate ON audit_logs'))
    op.execute(sa.text('DROP TRIGGER IF EXISTS audit_logs_append_only_row ON audit_logs'))
    op.execute(sa.text('DROP FUNCTION IF EXISTS audit_logs_append_only()'))

    for name, _ in reversed(_INTEGRATION_COLUMNS):
        if _table_exists('integrations') and _column_exists('integrations', name):
            op.drop_column('integrations', name)

    if _table_exists('ledger_heads'):
        op.drop_table('ledger_heads')

    for name, _ in reversed(_INDEXES):
        op.execute(sa.text(f'DROP INDEX IF EXISTS {name}'))

    for name, _ in reversed(_CHAIN_COLUMNS):
        if _column_exists('audit_logs', name):
            op.drop_column('audit_logs', name)

    # Restore the original ON DELETE SET NULL foreign keys. NOT VALID: rows
    # written while they were absent may reference deleted users/incidents.
    existing = _audit_fk_names()
    for name, column, target in _FKS:
        if name not in existing:
            op.execute(sa.text(
                f'ALTER TABLE audit_logs ADD CONSTRAINT "{name}" FOREIGN KEY ({column}) '
                f'REFERENCES {target}(id) ON DELETE SET NULL NOT VALID'))
