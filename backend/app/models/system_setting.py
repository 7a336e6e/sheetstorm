"""Platform-wide settings, one JSON document per key.

Platform-level because some settings apply before any organization is known
(e.g. rate limits on login, key ``rate_limits``, owned by W4-RL). Writes use
the optimistic-concurrency ``version`` (``precondition(row, required=True,
body_key='version')``) and are restricted to platform admins.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import BaseModel


class SystemSetting(BaseModel):
    __tablename__ = 'system_settings'

    key = Column(String(64), nullable=False, unique=True)
    value = Column(JSONB, nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default='1')
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = Column(DateTime(timezone=True))

    __mapper_args__ = {'version_id_col': version}

    @classmethod
    def get_value(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row is not None else default

    def __repr__(self):
        return f'<SystemSetting {self.key} v{self.version}>'
