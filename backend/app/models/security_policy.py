"""Per-organization security policy (services/security_policy.py).

One row per organization. ``policy`` holds the validated policy document
(``SecurityPolicy`` in the service); a missing row means the code defaults.
It lives in its own table rather than ``organizations.settings`` so that the
generic ``PUT /organization`` cannot write it unvalidated, and so writes are
protected by the optimistic-concurrency ``version``.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import BaseModel


class OrganizationSecurityPolicy(BaseModel):
    __tablename__ = 'organization_security_policies'

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=False, unique=True)
    policy = Column(JSONB, nullable=False, default=dict, server_default='{}')
    version = Column(Integer, nullable=False, default=1, server_default='1')
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))

    __mapper_args__ = {'version_id_col': version}

    def __repr__(self):
        return f'<OrganizationSecurityPolicy org={self.organization_id} v{self.version}>'
