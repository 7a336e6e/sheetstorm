"""OpenID Connect single sign-on: identity providers and linked identities.

A provider belongs to one organization: it can only sign in users of that
organization and only creates users there. ``slug`` is global (it appears in
the public sign-in and callback URLs). The client secret is Fernet-encrypted
and never returned by the API.

``UserIdentity`` links a user to a provider subject (``sub``). After the first
sign-in the user is found by (provider, subject); the email is only used to
match or create the account the first time.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel

PRESETS = ('entra', 'okta', 'keycloak', 'google', 'authentik', 'auth0', 'generic')
TOKEN_AUTH_METHODS = ('client_secret_basic', 'client_secret_post', 'none')
ROLE_SYNC_MODES = ('first_login', 'every_login')
# sheetstorm: SheetStorm's own TOTP rules apply (enrolled users get the TOTP
#             step after the IdP).
# idp:        the IdP enforces MFA; SSO-only users of this provider are exempt
#             from SheetStorm TOTP enrollment and are not asked for a code.
# idp_amr:    as idp, but a sign-in whose ID token ``amr`` claim shows no
#             second factor is refused.
MFA_MODES = ('sheetstorm', 'idp', 'idp_amr')


class SsoProvider(BaseModel):
    __tablename__ = 'sso_providers'
    __table_args__ = (
        UniqueConstraint('slug', name='uq_sso_providers_slug'),
        Index('ix_sso_providers_organization_id', 'organization_id'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=False)
    slug = Column(String(40), nullable=False)
    display_name = Column(String(80), nullable=False)
    preset = Column(String(20), nullable=False, default='generic', server_default='generic')
    issuer = Column(String(500), nullable=False)
    client_id = Column(String(255), nullable=False)
    client_secret_encrypted = Column(LargeBinary)
    token_auth_method = Column(String(32), nullable=False, default='client_secret_basic',
                               server_default='client_secret_basic')
    scopes = Column(String(500), nullable=False, default='openid email profile',
                    server_default='openid email profile')
    email_claims = Column(JSONB, nullable=False, default=lambda: ['email'])
    name_claim = Column(String(100), nullable=False, default='name', server_default='name')
    groups_claim = Column(String(200))
    role_mappings = Column(JSONB, nullable=False, default=list)
    default_role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='SET NULL'))
    allowed_groups = Column(JSONB, nullable=False, default=list)
    allowed_domains = Column(JSONB, nullable=False, default=list)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default='true')
    show_on_login = Column(Boolean, nullable=False, default=True, server_default='true')
    auto_provision = Column(Boolean, nullable=False, default=False, server_default='false')
    link_existing = Column(Boolean, nullable=False, default=False, server_default='false')
    require_email_verified = Column(Boolean, nullable=False, default=True, server_default='true')
    role_sync = Column(String(20), nullable=False, default='first_login', server_default='first_login')
    mfa_mode = Column(String(20), nullable=False, default='sheetstorm', server_default='sheetstorm')
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))

    identities = relationship('UserIdentity', back_populates='provider', cascade='all, delete-orphan',
                              passive_deletes=True, lazy='dynamic')

    def __repr__(self):
        return f'<SsoProvider {self.slug}>'

    def to_dict(self):
        data = super().to_dict()
        data.pop('client_secret_encrypted', None)
        data['has_client_secret'] = self.client_secret_encrypted is not None
        data['identity_count'] = self.identities.count()
        return data


class UserIdentity(BaseModel):
    __tablename__ = 'user_identities'
    __table_args__ = (
        UniqueConstraint('provider_id', 'subject', name='uq_user_identities_provider_subject'),
        Index('ix_user_identities_user_id', 'user_id'),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey('sso_providers.id', ondelete='CASCADE'), nullable=False)
    subject = Column(String(255), nullable=False)
    email = Column(String(255))
    last_login_at = Column(DateTime(timezone=True))

    user = relationship('User')
    provider = relationship('SsoProvider', back_populates='identities')

    def __repr__(self):
        return f'<UserIdentity {self.provider_id}:{self.subject}>'
