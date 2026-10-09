"""user lifecycle: account state columns, invites, granted_by SET NULL

- users: failed_login_count, locked_until, must_change_password,
  deactivated_at / deactivated_by (SET NULL) / deactivation_reason, plus the
  index (organization_id, is_active). Inactive users get deactivated_at
  backfilled from updated_at.
- user_roles.granted_by is recreated ON DELETE SET NULL so a past granter
  never blocks deleting a user.
- user_invites (token stored as SHA-256 only; expiry capped at 7 days by a
  CHECK; at most one pending invite per org + lower(email)).

Every step is idempotent. Downgrade drops the table and columns and restores
the granted_by FK without ON DELETE.

Revision ID: user_lifecycle
Revises: audit_governance
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'user_lifecycle'
down_revision = 'audit_governance'
branch_labels = None
depends_on = None

USER_COLUMNS = (
    ('failed_login_count', lambda: sa.Column('failed_login_count', sa.Integer(), nullable=False,
                                             server_default='0')),
    ('locked_until', lambda: sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True)),
    ('must_change_password', lambda: sa.Column('must_change_password', sa.Boolean(), nullable=False,
                                               server_default=sa.false())),
    ('deactivated_at', lambda: sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True)),
    ('deactivated_by', lambda: sa.Column('deactivated_by', postgresql.UUID(as_uuid=True), nullable=True)),
    ('deactivation_reason', lambda: sa.Column('deactivation_reason', sa.String(500), nullable=True)),
)
DEACTIVATED_BY_FK = 'fk_users_deactivated_by'
GRANTED_BY_FK = 'user_roles_granted_by_fkey'


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table, column):
    return column in {c['name'] for c in _insp().get_columns(table)}


def _table_exists(table):
    return _insp().has_table(table)


def _index_exists(table, name):
    return name in {i['name'] for i in _insp().get_indexes(table)}


def _fk(table, column, referred='users'):
    """The FK on `table`.`column` -> `referred`.id, or None."""
    for fk in _insp().get_foreign_keys(table):
        if fk['constrained_columns'] == [column] and fk['referred_table'] == referred:
            return fk
    return None


def _recreate_granted_by_fk(ondelete):
    fk = _fk('user_roles', 'granted_by')
    current = ((fk or {}).get('options') or {}).get('ondelete')
    if fk and (current or '').upper() == (ondelete or '').upper():
        return
    if fk:
        op.drop_constraint(fk['name'], 'user_roles', type_='foreignkey')
    # Older installs could hold grants by users that were deleted while no FK
    # (or no enforced FK) existed; the new FK would refuse them. SET NULL is
    # exactly what the constraint does on delete, so apply it to the orphans.
    op.execute(sa.text(
        'UPDATE user_roles SET granted_by = NULL WHERE granted_by IS NOT NULL '
        'AND NOT EXISTS (SELECT 1 FROM users WHERE users.id = user_roles.granted_by)'))
    op.create_foreign_key(GRANTED_BY_FK, 'user_roles', 'users', ['granted_by'], ['id'], ondelete=ondelete)


def upgrade():
    for name, make in USER_COLUMNS:
        if not _column_exists('users', name):
            op.add_column('users', make())
    if not _fk('users', 'deactivated_by'):
        op.create_foreign_key(DEACTIVATED_BY_FK, 'users', 'users', ['deactivated_by'], ['id'],
                              ondelete='SET NULL')
    op.execute("UPDATE users SET deactivated_at = COALESCE(updated_at, now()) "
               "WHERE is_active = false AND deactivated_at IS NULL")
    if not _index_exists('users', 'ix_users_org_active'):
        op.create_index('ix_users_org_active', 'users', ['organization_id', 'is_active'])

    _recreate_granted_by_fk('SET NULL')

    if not _table_exists('user_invites'):
        op.create_table(
            'user_invites',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=True),
            sa.Column('organizational_role', sa.String(150), nullable=True),
            sa.Column('role_ids', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column('team_ids', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column('token_hash', sa.CHAR(64), nullable=False, unique=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('accepted_user_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("expires_at <= created_at + interval '7 days 5 minutes'",
                               name='ck_user_invites_max_expiry'),
        )
    if not _index_exists('user_invites', 'uq_user_invites_pending'):
        op.execute("CREATE UNIQUE INDEX uq_user_invites_pending ON user_invites "
                   "(organization_id, lower(email)) WHERE accepted_at IS NULL AND revoked_at IS NULL")
    if not _index_exists('user_invites', 'ix_user_invites_org_created'):
        op.execute("CREATE INDEX ix_user_invites_org_created ON user_invites (organization_id, created_at DESC)")


def downgrade():
    if _table_exists('user_invites'):
        op.drop_table('user_invites')

    _recreate_granted_by_fk(None)

    if _index_exists('users', 'ix_users_org_active'):
        op.drop_index('ix_users_org_active', table_name='users')
    fk = _fk('users', 'deactivated_by')
    if fk:
        op.drop_constraint(fk['name'], 'users', type_='foreignkey')
    for name, _ in reversed(USER_COLUMNS):
        if _column_exists('users', name):
            op.drop_column('users', name)
