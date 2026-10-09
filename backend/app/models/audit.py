"""Audit log model"""
import ipaddress
import math
from datetime import timezone

from sqlalchemy import BigInteger, Column, String, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel
from app.utils.hash_chain import canonical_json


def _norm_ip(value):
    """Stable text form of an INET value (written and read back alike)."""
    if value is None:
        return None
    text = str(value)
    try:
        return str(ipaddress.ip_address(text.split('/', 1)[0]))
    except ValueError:
        return text


def _norm_json(value):
    """JSONB round-trip normal form: integral floats become ints (Postgres
    numeric prints 1e20 as an integer), everything else unchanged."""
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {k: _norm_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm_json(v) for v in value]
    return value


def _str_or_none(value):
    return str(value) if value is not None else None


class AuditLog(BaseModel):
    """Audit log model for tracking all system actions.

    Append-only: a DB trigger rejects UPDATE / DELETE / TRUNCATE (except the
    retention purge, which sets ``sheetstorm.audit_purge``). There are no
    foreign keys, so deleting a user / incident / org never rewrites a row and
    the original ids survive. Rows are written only by
    ``middleware.audit._write_audit_row``, which links each row into the
    org's keyed hash chain (``chain_seq`` / ``prev_hash`` / ``row_hash``).
    Rows from before the chain existed have NULL chain columns (legacy).
    """
    __tablename__ = 'audit_logs'

    organization_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True))
    user_email = Column(String(255))
    event_type = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(UUID(as_uuid=True))
    incident_id = Column(UUID(as_uuid=True))
    ip_address = Column(INET)
    user_agent = Column(Text)
    request_method = Column(String(10))
    request_path = Column(Text)
    request_query_params = Column(JSONB, default=dict)
    request_body_summary = Column(JSONB, default=dict)
    content_type = Column(String(255))
    referrer = Column(Text)
    origin = Column(String(255))
    status_code = Column(Integer)
    duration_ms = Column(Float)
    # Cloudflare geo headers
    geo_country = Column(String(100))
    geo_city = Column(String(255))
    geo_region = Column(String(255))
    cf_ray = Column(String(100))
    # Browser/device parsed from user-agent
    browser = Column(String(100))
    os = Column(String(100))
    device_type = Column(String(50))
    details = Column(JSONB, default=dict)
    # Keyed hash chain (services/ledger.py); NULL on legacy rows.
    chain_seq = Column(BigInteger)
    prev_hash = Column(String(64))
    row_hash = Column(String(64))
    chain_key_id = Column(String(16))

    # Read-only joins (no FKs: ids may dangle after a hard delete).
    organization = relationship('Organization', primaryjoin='foreign(AuditLog.organization_id) == Organization.id',
                                viewonly=True)
    user = relationship('User', primaryjoin='foreign(AuditLog.user_id) == User.id', viewonly=True)
    incident = relationship('Incident', primaryjoin='foreign(AuditLog.incident_id) == Incident.id',
                            viewonly=True)

    EVENT_TYPES = [
        'authentication', 'authorization', 'data_access', 'data_modification',
        'admin_action', 'security_event', 'system_event'
    ]

    # Export column order (CSV header / JSONL keys).
    CSV_COLUMNS = [
        'created_at', 'event_type', 'action', 'user_email', 'user_id', 'resource_type', 'resource_id',
        'incident_id', 'ip_address', 'request_method', 'request_path', 'status_code', 'geo_country',
        'browser', 'os', 'details', 'chain_seq', 'row_hash',
    ]

    def chain_payload(self) -> bytes:
        """Canonical bytes hashed into ``row_hash`` (with ``prev_hash``).

        Identical whether computed before insert or from the stored row:
        ``details`` is canonicalized before insert, timestamps are UTC with
        microseconds, ids are strings.
        """
        created = self.created_at
        if created is not None:
            created = created.astimezone(timezone.utc).isoformat(timespec='microseconds')
        return canonical_json([
            self.prev_hash, _str_or_none(self.id), _str_or_none(self.organization_id), self.chain_seq,
            created, _str_or_none(self.user_id), self.user_email, self.event_type, self.action,
            self.resource_type, _str_or_none(self.resource_id), _str_or_none(self.incident_id),
            _norm_ip(self.ip_address), self.request_method, self.request_path, self.status_code,
            _norm_json(self.details if self.details is not None else {}),
        ], strict=False)

    def __repr__(self):
        return f'<AuditLog {self.event_type}: {self.action}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['ip_address'] = str(self.ip_address) if self.ip_address else None
        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'name': self.user.name,
            'role': ', '.join(self.user.role_names) if self.user.role_names else None,
        } if self.user else None
        data['incident'] = {
            'id': str(self.incident.id),
            'title': self.incident.title,
        } if self.incident else None
        return data
