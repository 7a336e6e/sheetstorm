"""User and authentication models"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, LargeBinary, Text, and_, func, or_
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import BaseModel
from app import db
import bcrypt


class Role(BaseModel):
    """Role model for RBAC.

    `organization_id IS NULL` marks a global system role (immutable, shared
    by every tenant); custom roles always belong to one organization. Names
    are unique case-insensitively among system roles and within an org, and
    custom roles cannot shadow a system role name.
    """
    __tablename__ = 'roles'

    name = Column(String(100), nullable=False)
    description = Column(String(500))
    permissions = Column(JSONB, default=list)
    is_system = Column(Boolean, default=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=True)

    # Relationships
    user_roles = relationship('UserRole', back_populates='role', lazy='dynamic')

    def __repr__(self):
        return f'<Role {self.name}>'

    def has_permission(self, permission):
        """Check if role has a specific permission."""
        return permission in (self.permissions or [])

    def applies_to_org(self, org_id):
        """A role only counts for users of its own org (system roles: all)."""
        if self.organization_id is None:
            return bool(self.is_system)
        return self.organization_id == org_id

    @classmethod
    def visible_to(cls, org_id):
        """Query of the roles an org may see and assign: system + its own."""
        return cls.query.filter(or_(
            and_(cls.organization_id.is_(None), cls.is_system.is_(True)),
            cls.organization_id == org_id,
        ))

    @classmethod
    def resolve(cls, name, org_id):
        """Case-insensitive name lookup among the roles visible to `org_id`.

        System names cannot be shadowed by custom roles, so at most one row
        matches; a system role wins if legacy data ever disagrees.
        """
        if not name or not isinstance(name, str):
            return None
        return (cls.visible_to(org_id)
                .filter(func.lower(cls.name) == name.strip().lower())
                .order_by(cls.organization_id.isnot(None))
                .first())


class User(BaseModel):
    """User model."""
    __tablename__ = 'users'

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255))
    name = Column(String(255), nullable=False)
    avatar_url = Column(String(500))
    auth_provider = Column(String(50), default='local')
    auth_provider_id = Column(String(255))
    supabase_id = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255))
    mfa_backup_codes = Column(Text)  # Comma-separated backup codes
    last_login = Column(DateTime(timezone=True))
    password_changed_at = Column(DateTime(timezone=True))
    organizational_role = Column(String(150))
    updated_at = Column(DateTime(timezone=True))
    # Per-user UI preferences. Keys are allowlisted by PATCH /auth/me/preferences
    # (PREFERENCE_KEYS); never store arbitrary client JSON here.
    preferences = Column(JSONB, nullable=False, default=dict, server_default='{}')

    # ── Account lifecycle (W1-LIFE-BE, migration user_lifecycle) ──────────
    # Login lockout: counter + lock expiry (services/user_lifecycle.py).
    failed_login_count = Column(Integer, nullable=False, default=0, server_default='0')
    locked_until = Column(DateTime(timezone=True))
    # Restricted session until the user changes their password
    # (middleware/account_state.py: 403 password_change_required).
    must_change_password = Column(Boolean, nullable=False, default=False, server_default='false')
    deactivated_at = Column(DateTime(timezone=True))
    deactivated_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    deactivation_reason = Column(String(500))
    # ── end account lifecycle ────────────────────────────────────────────

    # ── API keys (W2-APIK, migration add_api_keys) ────────────────────────
    # Non-human owner of API keys: never logs in interactively (no password,
    # synthetic svc-…@service.invalid email, auth_provider 'service').
    is_service_account = Column(Boolean, nullable=False, default=False, server_default='false')
    # ── end API keys ─────────────────────────────────────────────────────

    # Relationships
    organization = relationship('Organization', back_populates='users')
    user_roles = relationship('UserRole', back_populates='user', lazy='joined', cascade='all, delete-orphan', foreign_keys='UserRole.user_id')
    sessions = relationship('Session', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    password_history = relationship('PasswordHistory', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    team_memberships = relationship('TeamMember', back_populates='user', lazy='joined', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.email}>'

    def set_password(self, password):
        """Hash and set the user's password."""
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        self.password_changed_at = datetime.now(timezone.utc)

    def check_password(self, password):
        """Verify password against hash."""
        if not self.password_hash:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    @property
    def is_locked(self):
        """True while a login lockout is in force."""
        return bool(self.locked_until and self.locked_until > datetime.now(timezone.utc))

    @property
    def roles(self):
        """Get list of role objects."""
        return [ur.role for ur in self.user_roles]

    @property
    def role_names(self):
        """Get list of role names."""
        return [ur.role.name for ur in self.user_roles]

    @property
    def role_permissions(self):
        """Union of the permissions of all roles (additive; no role restricts
        another), ignoring any API-key scope limit. Roles of a foreign org are
        ignored even if a stray user_roles row exists. Use `permissions` for
        authorization; this is for the owner's incident visibility and for
        API-key scope validation."""
        perms = set()
        for user_role in self.user_roles:
            role = user_role.role
            if role and role.permissions and role.applies_to_org(self.organization_id):
                perms.update(role.permissions)
        return sorted(perms)

    @property
    def permissions(self):
        """Effective permissions: `role_permissions`, intersected with the
        key's scopes when the current request is authenticated by an API-key
        token for this user (evaluated per request, so an owner downgrade
        shrinks the key at once and scopes can never grow)."""
        perms = self.role_permissions
        from app.utils.token_scopes import current_scope_limit
        limit = current_scope_limit(self.id)
        if limit is None:
            return perms
        return [p for p in perms if p in limit]

    def has_permission(self, permission):
        """Check if user has a specific permission."""
        return permission in self.permissions

    def has_any_permission(self, permissions):
        """Check if user has any of the specified permissions."""
        user_perms = set(self.permissions)
        return bool(user_perms.intersection(permissions))

    def has_all_permissions(self, permissions):
        """Check if user has all specified permissions."""
        user_perms = set(self.permissions)
        return all(p in user_perms for p in permissions)

    def has_role(self, role_name):
        """Check if user has a role by name. Display / sync only — never use
        a role name for an authorization decision (check a permission)."""
        return role_name in self.role_names

    @property
    def teams(self):
        """Get list of team summaries."""
        return [
            {'id': str(tm.team.id), 'name': tm.team.name}
            for tm in self.team_memberships if tm.team
        ]

    def to_summary(self):
        """Lightweight representation for embedding in other resources."""
        return {
            'id': str(self.id),
            'name': self.name,
            'avatar_url': self.avatar_url,
            'roles': self.role_names,
        }

    def to_dict(self, include_permissions=False):
        """Convert to dictionary, excluding sensitive fields."""
        data = {
            'id': str(self.id),
            'email': self.email,
            'name': self.name,
            'avatar_url': self.avatar_url,
            'auth_provider': self.auth_provider,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'mfa_enabled': self.mfa_enabled,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'roles': self.role_names,
            'organizational_role': self.organizational_role,
            'teams': self.teams,
            'organization_id': str(self.organization_id) if self.organization_id else None,
            'preferences': dict(self.preferences or {}),
            'is_locked': self.is_locked,
            'locked_until': self.locked_until.isoformat() if self.is_locked else None,
            'must_change_password': bool(self.must_change_password),
            'is_service_account': bool(self.is_service_account),
            'deactivated_at': self.deactivated_at.isoformat() if self.deactivated_at else None,
        }
        if include_permissions:
            data['permissions'] = self.permissions
        return data

    def to_admin_dict(self, include_permissions=False):
        """to_dict plus account-state details for holders of users:manage."""
        data = self.to_dict(include_permissions=include_permissions)
        deactivator = None
        if self.deactivated_by:
            other = db.session.get(User, self.deactivated_by)
            deactivator = {'id': str(self.deactivated_by), 'name': other.name if other else None}
        data.update({
            'failed_login_count': self.failed_login_count or 0,
            'deactivated_by': deactivator,
            'deactivation_reason': self.deactivation_reason,
            'password_changed_at': self.password_changed_at.isoformat() if self.password_changed_at else None,
        })
        return data


class UserRole(BaseModel):
    """User-Role association model."""
    __tablename__ = 'user_roles'

    # Override BaseModel's created_at — this table uses granted_at instead
    created_at = None

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    granted_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship('User', back_populates='user_roles', foreign_keys=[user_id])
    role = relationship('Role', back_populates='user_roles')


class PasswordHistory(BaseModel):
    """Password history for preventing reuse."""
    __tablename__ = 'password_history'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Relationships
    user = relationship('User', back_populates='password_history')


class Session(BaseModel):
    """A sign-in session (services/session_service.py).

    One row per interactive sign-in; its id is the ``sid`` claim of every
    access/refresh token minted for it. Refresh rotation keeps the row and
    updates ``refresh_jti``/``expires_at``. Revoking the row blocklists its
    tokens (``revoked_session:<sid>`` in Redis, checked by is_token_revoked).
    API-key tokens carry no sid and have no row.
    """
    __tablename__ = 'sessions'

    # ── Session columns (W3-SEC, migration security_policy_sessions) ──────
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    token_hash = Column(String(255))  # legacy, unused
    refresh_token_hash = Column(String(255))  # legacy, unused
    refresh_jti = Column(String(64))
    ip_address = Column(INET)
    user_agent = Column(String(500))
    auth_method = Column(String(32))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(32))
    # ── end session columns ──────────────────────────────────────────────

    # Relationships
    user = relationship('User', back_populates='sessions')

    @property
    def is_valid(self):
        """Check if session is still valid."""
        if self.revoked_at:
            return False
        return datetime.now(timezone.utc) < self.expires_at

    def to_dict(self, current_sid=None):
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'ip_address': str(self.ip_address) if self.ip_address else None,
            'user_agent': self.user_agent,
            'auth_method': self.auth_method,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'current': current_sid is not None and str(self.id) == str(current_sid),
        }
