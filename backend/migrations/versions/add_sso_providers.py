"""OpenID Connect single sign-on providers and linked user identities

* ``sso_providers``: one row per identity provider, owned by an organization
  (users it signs in or creates always belong to that organization). The
  ``slug`` is global because it is part of the public sign-in URLs. The
  client secret is stored Fernet-encrypted.
* ``user_identities``: (provider, subject) -> user. Deleting a provider
  deletes its identity links, never the users.

Idempotent (existence guards) and reversible; the downgrade drops both tables
(provider configuration and identity links are lost; users stay).

Revision ID: add_sso_providers
Revises: serialize_incident_numbers
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_sso_providers'
down_revision = 'serialize_incident_numbers'
branch_labels = None
depends_on = None

PRESETS = ('entra', 'okta', 'keycloak', 'google', 'authentik', 'auth0', 'generic')
TOKEN_AUTH_METHODS = ('client_secret_basic', 'client_secret_post', 'none')
ROLE_SYNC_MODES = ('first_login', 'every_login')
MFA_MODES = ('sheetstorm', 'idp', 'idp_amr')


def _table_exists(table):
    return sa.inspect(op.get_bind()).has_table(table)


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name, *args, **kw):
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kw)


def _ts(name, **kw):
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def _flag(name, default):
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text(default))


def upgrade():
    if not _table_exists('sso_providers'):
        op.create_table(
            'sso_providers',
            _uuid('id', primary_key=True),
            _ts('created_at'),
            _uuid('organization_id', sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('slug', sa.String(40), nullable=False),
            sa.Column('display_name', sa.String(80), nullable=False),
            sa.Column('preset', sa.String(20), nullable=False, server_default='generic'),
            sa.Column('issuer', sa.String(500), nullable=False),
            sa.Column('client_id', sa.String(255), nullable=False),
            sa.Column('client_secret_encrypted', sa.LargeBinary()),
            sa.Column('token_auth_method', sa.String(32), nullable=False, server_default='client_secret_basic'),
            sa.Column('scopes', sa.String(500), nullable=False, server_default='openid email profile'),
            sa.Column('email_claims', postgresql.JSONB(), nullable=False),
            sa.Column('name_claim', sa.String(100), nullable=False, server_default='name'),
            sa.Column('groups_claim', sa.String(200)),
            sa.Column('role_mappings', postgresql.JSONB(), nullable=False),
            _uuid('default_role_id', sa.ForeignKey('roles.id', ondelete='SET NULL')),
            sa.Column('allowed_groups', postgresql.JSONB(), nullable=False),
            sa.Column('allowed_domains', postgresql.JSONB(), nullable=False),
            _flag('is_enabled', 'true'),
            _flag('show_on_login', 'true'),
            _flag('auto_provision', 'false'),
            _flag('link_existing', 'false'),
            _flag('require_email_verified', 'true'),
            sa.Column('role_sync', sa.String(20), nullable=False, server_default='first_login'),
            sa.Column('mfa_mode', sa.String(20), nullable=False, server_default='sheetstorm'),
            _uuid('created_by', sa.ForeignKey('users.id', ondelete='SET NULL')),
            _uuid('updated_by', sa.ForeignKey('users.id', ondelete='SET NULL')),
            _ts('updated_at'),
            _ts('last_login_at'),
            sa.UniqueConstraint('slug', name='uq_sso_providers_slug'),
            sa.CheckConstraint(_in('preset', PRESETS), name='ck_sso_providers_preset'),
            sa.CheckConstraint(_in('token_auth_method', TOKEN_AUTH_METHODS), name='ck_sso_providers_token_auth'),
            sa.CheckConstraint(_in('role_sync', ROLE_SYNC_MODES), name='ck_sso_providers_role_sync'),
            sa.CheckConstraint(_in('mfa_mode', MFA_MODES), name='ck_sso_providers_mfa_mode'),
        )
        op.create_index('ix_sso_providers_organization_id', 'sso_providers', ['organization_id'])

    if not _table_exists('user_identities'):
        op.create_table(
            'user_identities',
            _uuid('id', primary_key=True),
            _ts('created_at'),
            _uuid('user_id', sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            _uuid('provider_id', sa.ForeignKey('sso_providers.id', ondelete='CASCADE'), nullable=False),
            sa.Column('subject', sa.String(255), nullable=False),
            sa.Column('email', sa.String(255)),
            _ts('last_login_at'),
            sa.UniqueConstraint('provider_id', 'subject', name='uq_user_identities_provider_subject'),
        )
        op.create_index('ix_user_identities_user_id', 'user_identities', ['user_id'])


def downgrade():
    for table in ('user_identities', 'sso_providers'):
        if _table_exists(table):
            op.drop_table(table)
