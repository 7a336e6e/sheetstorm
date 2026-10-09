"""api keys: api_keys table, users.is_service_account

- users.is_service_account BOOLEAN NOT NULL DEFAULT false.
- api_keys: scoped API keys (only the peppered HMAC of the secret is
  stored), CHECK expires_at > created_at, indexes (organization_id,
  revoked_at) and (owner_user_id), and a partial unique index on
  (owner_user_id, lower(name)) WHERE revoked_at IS NULL.

No role updates: api_keys:own / api_keys:manage were granted by
admin_guardrails_rbac (_integration.md C13). Every step is idempotent.
Downgrade drops the table and the column (keys are lost).

Revision ID: add_api_keys
Revises: evidence_register_ledger
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_api_keys'
down_revision = 'evidence_register_ledger'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table, column):
    return column in {c['name'] for c in _insp().get_columns(table)}


def _table_exists(table):
    return _insp().has_table(table)


def upgrade():
    if not _column_exists('users', 'is_service_account'):
        op.add_column('users', sa.Column('is_service_account', sa.Boolean(), nullable=False,
                                         server_default=sa.false()))

    if not _table_exists('api_keys'):
        op.create_table(
            'api_keys',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('owner_user_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.String(500), nullable=True),
            sa.Column('prefix', sa.String(32), nullable=False, unique=True),
            sa.Column('key_hash', sa.String(64), nullable=False),
            sa.Column('hash_alg', sa.String(32), nullable=False, server_default='hmac-sha256-v1'),
            sa.Column('scopes', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_used_ip', postgresql.INET(), nullable=True),
            sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('rotated_from_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('api_keys.id', ondelete='SET NULL'), nullable=True),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('revoked_reason', sa.String(200), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint('expires_at > created_at', name='ck_api_keys_expiry_after_creation'),
        )
    op.execute('CREATE INDEX IF NOT EXISTS ix_api_keys_org_revoked ON api_keys (organization_id, revoked_at)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_api_keys_owner ON api_keys (owner_user_id)')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_owner_name_active ON api_keys '
               '(owner_user_id, lower(name)) WHERE revoked_at IS NULL')


def downgrade():
    if _table_exists('api_keys'):
        op.drop_table('api_keys')
    if _column_exists('users', 'is_service_account'):
        op.drop_column('users', 'is_service_account')
