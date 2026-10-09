"""Scoped API keys (services/api_key_service.py).

A key belongs to an owner user: a human (personal key) or a service account
(``users.is_service_account``). Only the peppered HMAC of the secret is
stored; the full key (``ssk_<lookup>_<secret>``) is returned once at creation
or rotation and never persisted or logged. ``prefix`` (``ssk_<lookup>``) is
public and indexed for the exchange lookup.

``revoked_at`` may lie in the future: a rotation with a grace period
schedules the old key's revocation (it stays usable until then and no longer
counts for the per-owner name uniqueness).
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from app.models.base import BaseModel

HASH_ALG = 'hmac-sha256-v1'
REVOKE_REASONS = ('manual', 'rotated', 'owner_disabled', 'owner_deleted', 'owner_force_logout',
                  'owner_password_reset', 'owner_mfa_reset', 'service_account_deleted')


class ApiKey(BaseModel):
    __tablename__ = 'api_keys'
    __table_args__ = (
        CheckConstraint('expires_at > created_at', name='ck_api_keys_expiry_after_creation'),
        Index('ix_api_keys_org_revoked', 'organization_id', 'revoked_at'),
        Index('ix_api_keys_owner', 'owner_user_id'),
        # Plus the partial unique index uq_api_keys_owner_name_active on
        # (owner_user_id, lower(name)) WHERE revoked_at IS NULL (migration).
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    prefix = Column(String(32), nullable=False, unique=True)
    key_hash = Column(String(64), nullable=False)
    hash_alg = Column(String(32), nullable=False, default=HASH_ALG, server_default=HASH_ALG)
    scopes = Column(JSONB, nullable=False, default=list, server_default='[]')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True))
    last_used_ip = Column(INET)
    use_count = Column(Integer, nullable=False, default=0, server_default='0')
    rotated_from_id = Column(UUID(as_uuid=True), ForeignKey('api_keys.id', ondelete='SET NULL'))
    revoked_at = Column(DateTime(timezone=True))
    revoked_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    revoked_reason = Column(String(200))
    updated_at = Column(DateTime(timezone=True))

    STATUSES = ('active', 'expired', 'revoked')

    def __repr__(self):
        return f'<ApiKey {self.prefix}>'

    def is_revoked(self, now=None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.revoked_at is not None and self.revoked_at <= now

    def is_expired(self, now=None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.expires_at is not None and self.expires_at <= now

    @property
    def status(self) -> str:
        now = datetime.now(timezone.utc)
        if self.is_revoked(now):
            return 'revoked'
        if self.is_expired(now):
            return 'expired'
        return 'active'

    def to_dict(self, owner=None):
        """Never includes ``key_hash`` (nor, obviously, the secret).
        `owner` is the owner User when already loaded."""
        def iso(v):
            return v.isoformat() if v else None

        data = {
            'id': str(self.id),
            'organization_id': str(self.organization_id),
            'owner_user_id': str(self.owner_user_id),
            'name': self.name,
            'description': self.description,
            'prefix': self.prefix,
            'hash_alg': self.hash_alg,
            'scopes': list(self.scopes or []),
            'status': self.status,
            'expires_at': iso(self.expires_at),
            'last_used_at': iso(self.last_used_at),
            'last_used_ip': str(self.last_used_ip) if self.last_used_ip else None,
            'use_count': self.use_count or 0,
            'rotated_from_id': str(self.rotated_from_id) if self.rotated_from_id else None,
            'revoked_at': iso(self.revoked_at),
            'revoked_by': str(self.revoked_by) if self.revoked_by else None,
            'revoked_reason': self.revoked_reason,
            'created_by': str(self.created_by) if self.created_by else None,
            'created_at': iso(self.created_at),
            'updated_at': iso(self.updated_at),
        }
        if owner is not None:
            data['owner'] = {
                'id': str(owner.id),
                'name': owner.name,
                'email': owner.email,
                'is_service_account': bool(getattr(owner, 'is_service_account', False)),
            }
        return data
