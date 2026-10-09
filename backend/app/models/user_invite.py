"""Pending user invitations (services/invite_service.py)."""
from datetime import datetime, timezone

from sqlalchemy import CHAR, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import BaseModel


class UserInvite(BaseModel):
    """An invitation to join an organization.

    Only the SHA-256 of the one-time token is stored; the token itself is
    returned once at creation and never persisted or logged.
    """
    __tablename__ = 'user_invites'

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=False)
    email = Column(String(255), nullable=False)  # stored lowercase
    name = Column(String(255))
    organizational_role = Column(String(150))
    role_ids = Column(JSONB, nullable=False, default=list, server_default='[]')
    team_ids = Column(JSONB, nullable=False, default=list, server_default='[]')
    token_hash = Column(CHAR(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    accepted_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    revoked_at = Column(DateTime(timezone=True))
    revoked_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))

    STATUSES = ('pending', 'accepted', 'revoked', 'expired')

    @property
    def status(self):
        if self.accepted_at:
            return 'accepted'
        if self.revoked_at:
            return 'revoked'
        if self.expires_at and self.expires_at <= datetime.now(timezone.utc):
            return 'expired'
        return 'pending'

    def to_dict(self, roles=None, teams=None, created_by=None):
        """Never includes the token hash. `roles`/`teams` are resolved
        [{id, name}] lists and `created_by` a {id, name} summary when known."""
        def iso(v):
            return v.isoformat() if v else None

        return {
            'id': str(self.id),
            'organization_id': str(self.organization_id),
            'email': self.email,
            'name': self.name,
            'organizational_role': self.organizational_role,
            'status': self.status,
            'role_ids': list(self.role_ids or []),
            'team_ids': list(self.team_ids or []),
            'roles': roles if roles is not None else [],
            'teams': teams if teams is not None else [],
            'expires_at': iso(self.expires_at),
            'accepted_at': iso(self.accepted_at),
            'accepted_user_id': str(self.accepted_user_id) if self.accepted_user_id else None,
            'revoked_at': iso(self.revoked_at),
            'created_by': created_by,
            'created_at': iso(self.created_at),
        }
