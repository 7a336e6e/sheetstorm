"""User and authentication models"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import BaseModel
from app import db
import bcrypt


class Role(BaseModel):
    """Role model for RBAC."""
    __tablename__ = 'roles'

    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500))
    permissions = Column(JSONB, default=list)
    is_system = Column(Boolean, default=False)

    # Relationships
    user_roles = relationship('UserRole', back_populates='role', lazy='dynamic')

    def __repr__(self):
        return f'<Role {self.name}>'

    def has_permission(self, permission):
        """Check if role has a specific permission."""
        return permission in self.permissions


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
    def roles(self):
        """Get list of role objects."""
        return [ur.role for ur in self.user_roles]

    @property
    def role_names(self):
        """Get list of role names."""
        return [ur.role.name for ur in self.user_roles]

    @property
    def permissions(self):
        """Get combined permissions from all roles."""
        perms = set()
        for user_role in self.user_roles:
            if user_role.role and user_role.role.permissions:
                perms.update(user_role.role.permissions)
        return list(perms)

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
        """Check if user has a specific role."""
        return role_name in self.role_names

    @property
    def teams(self):
        """Get list of team summaries."""
        return [
            {'id': str(tm.team.id), 'name': tm.team.name}
            for tm in self.team_memberships if tm.team
        ]

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
        }
        if include_permissions:
            data['permissions'] = self.permissions
        return data


class UserRole(BaseModel):
    """User-Role association model."""
    __tablename__ = 'user_roles'

    # Override BaseModel's created_at — this table uses granted_at instead
    created_at = None

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    granted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
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
    """Session model for token management."""
    __tablename__ = 'sessions'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(String(255), nullable=False)
    refresh_token_hash = Column(String(255))
    ip_address = Column(INET)
    user_agent = Column(String(500))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship('User', back_populates='sessions')

    @property
    def is_valid(self):
        """Check if session is still valid."""
        if self.revoked_at:
            return False
        return datetime.now(timezone.utc) < self.expires_at
