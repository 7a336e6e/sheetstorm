"""security policy + sessions: organization_security_policies, system_settings,
session inventory columns, registration flag moved into the policy

- organization_security_policies: one row per org (``policy`` JSONB validated
  by services/security_policy.py, optimistic ``version``). No row = code
  defaults, so nothing is backfilled except the registration flag below.
- system_settings: platform-wide JSON settings by key (``version``).
- sessions (unused until now, so no backfill): ``token_hash`` becomes
  nullable; adds ``organization_id`` (FK, CASCADE), ``refresh_jti`` (unique),
  ``last_seen_at``, ``auth_method``, ``revoked_reason`` and the index
  (user_id, revoked_at).
- Data (_integration.md C11): every organization whose ``settings`` holds
  ``registration_enabled`` gets that value copied into
  ``policy.provisioning.registration_enabled`` (a JSON ``true`` stays true,
  anything else becomes false, as the old reader only honoured ``true``),
  then the settings key is removed.

Every step is idempotent. Downgrade writes the policy's registration flag
back into ``organizations.settings``, deletes the session rows created by
the new code (``token_hash`` NULL) so the NOT NULL can be restored, and
drops the new columns and tables.

Revision ID: security_policy_sessions
Revises: task_evidence_refs_backfill
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'security_policy_sessions'
down_revision = 'task_evidence_refs_backfill'
branch_labels = None
depends_on = None

SESSION_COLUMNS = (
    ('organization_id', lambda: sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True)),
    ('refresh_jti', lambda: sa.Column('refresh_jti', sa.String(64), nullable=True)),
    ('last_seen_at', lambda: sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True)),
    ('auth_method', lambda: sa.Column('auth_method', sa.String(32), nullable=True)),
    ('revoked_reason', lambda: sa.Column('revoked_reason', sa.String(32), nullable=True)),
)
SESSIONS_ORG_FK = 'fk_sessions_organization_id'
IDX_REFRESH_JTI = 'uq_sessions_refresh_jti'
IDX_USER_REVOKED = 'idx_sessions_user_revoked'


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table):
    return _insp().has_table(table)


def _column_exists(table, column):
    return column in {c['name'] for c in _insp().get_columns(table)}


def _index_exists(table, name):
    return name in {i['name'] for i in _insp().get_indexes(table)}


def _fk_exists(table, name):
    return name in {fk['name'] for fk in _insp().get_foreign_keys(table)}


def _timestamps():
    return (
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def upgrade():
    if not _table_exists('organization_security_policies'):
        op.create_table(
            'organization_security_policies',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('uuid_generate_v4()')),
            sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('policy', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('updated_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            *_timestamps(),
        )

    if not _table_exists('system_settings'):
        op.create_table(
            'system_settings',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('uuid_generate_v4()')),
            sa.Column('key', sa.String(64), nullable=False, unique=True),
            sa.Column('value', postgresql.JSONB(), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('updated_by', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            *_timestamps(),
        )

    op.alter_column('sessions', 'token_hash', existing_type=sa.String(255), nullable=True)
    for name, make in SESSION_COLUMNS:
        if not _column_exists('sessions', name):
            op.add_column('sessions', make())
    if not _fk_exists('sessions', SESSIONS_ORG_FK):
        op.create_foreign_key(SESSIONS_ORG_FK, 'sessions', 'organizations', ['organization_id'], ['id'],
                              ondelete='CASCADE')
    if not _index_exists('sessions', IDX_REFRESH_JTI):
        op.create_index(IDX_REFRESH_JTI, 'sessions', ['refresh_jti'], unique=True)
    if not _index_exists('sessions', IDX_USER_REVOKED):
        op.create_index(IDX_USER_REVOKED, 'sessions', ['user_id', 'revoked_at'])

    # C11: organizations.settings.registration_enabled -> policy row.
    op.execute("""
        INSERT INTO organization_security_policies (organization_id, policy)
        SELECT o.id, '{}'::jsonb FROM organizations o
        WHERE o.settings IS NOT NULL AND jsonb_typeof(o.settings) = 'object'
          AND o.settings ? 'registration_enabled'
        ON CONFLICT (organization_id) DO NOTHING
    """)
    op.execute("""
        UPDATE organization_security_policies p
        SET policy = jsonb_set(
                p.policy, '{provisioning}',
                COALESCE(CASE WHEN jsonb_typeof(p.policy -> 'provisioning') = 'object'
                              THEN p.policy -> 'provisioning' END, '{}'::jsonb)
                || jsonb_build_object('registration_enabled',
                                      (o.settings -> 'registration_enabled') = 'true'::jsonb)),
            updated_at = CURRENT_TIMESTAMP
        FROM organizations o
        WHERE o.id = p.organization_id
          AND o.settings IS NOT NULL AND jsonb_typeof(o.settings) = 'object'
          AND o.settings ? 'registration_enabled'
    """)
    op.execute("""
        UPDATE organizations SET settings = settings - 'registration_enabled'
        WHERE settings IS NOT NULL AND jsonb_typeof(settings) = 'object' AND settings ? 'registration_enabled'
    """)


def downgrade():
    if _table_exists('organization_security_policies'):
        op.execute("""
            UPDATE organizations o
            SET settings = COALESCE(CASE WHEN jsonb_typeof(o.settings) = 'object' THEN o.settings END,
                                    '{}'::jsonb)
                || jsonb_build_object('registration_enabled',
                                      (p.policy -> 'provisioning' -> 'registration_enabled') = 'true'::jsonb)
            FROM organization_security_policies p
            WHERE p.organization_id = o.id
              AND jsonb_typeof(p.policy -> 'provisioning') = 'object'
              AND (p.policy -> 'provisioning') ? 'registration_enabled'
        """)

    if _index_exists('sessions', IDX_USER_REVOKED):
        op.drop_index(IDX_USER_REVOKED, table_name='sessions')
    if _index_exists('sessions', IDX_REFRESH_JTI):
        op.drop_index(IDX_REFRESH_JTI, table_name='sessions')
    if _fk_exists('sessions', SESSIONS_ORG_FK):
        op.drop_constraint(SESSIONS_ORG_FK, 'sessions', type_='foreignkey')
    for name, _ in reversed(SESSION_COLUMNS):
        if _column_exists('sessions', name):
            op.drop_column('sessions', name)
    # Rows written by the session service have no token_hash; the old schema
    # requires one (and never read the table).
    op.execute('DELETE FROM sessions WHERE token_hash IS NULL')
    op.alter_column('sessions', 'token_hash', existing_type=sa.String(255), nullable=False)

    if _table_exists('system_settings'):
        op.drop_table('system_settings')
    if _table_exists('organization_security_policies'):
        op.drop_table('organization_security_policies')
