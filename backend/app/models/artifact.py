"""Artifact and chain of custody models"""
import hashlib
import hmac
import ipaddress
import json as _json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, BigInteger, Index, event
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

logger = logging.getLogger(__name__)


def custody_key_id(secret: str) -> str:
    """Short, non-reversible fingerprint of a custody signing key.

    Stored with every signature so a key rotation is detectable (rows signed
    with a different key are reported as `key_mismatch`, not as tampered).
    """
    return hashlib.sha256(b'sheetstorm-custody-key-id:' + (secret or '').encode()).hexdigest()[:16]


def custody_signing_key() -> str:
    """The active custody HMAC key: CUSTODY_SIGNING_KEY, else SECRET_KEY."""
    from flask import current_app
    return current_app.config.get('CUSTODY_SIGNING_KEY') or current_app.config.get('SECRET_KEY', '')


def _canon_uuid(value):
    return str(uuid.UUID(str(value))) if value else None


def _canon_ip(value):
    if not value:
        return None
    try:
        return str(ipaddress.ip_interface(str(value)).ip)
    except ValueError:
        return str(value)


def _canon_ts(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


class Artifact(BaseModel):
    """Artifact model for evidence files."""
    __tablename__ = 'artifacts'
    __table_args__ = (
        Index('idx_artifact_incident_type', 'incident_id', 'mime_type'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    storage_path = Column(Text, nullable=False)
    storage_type = Column(String(50), default='local')
    mime_type = Column(String(255))
    file_size = Column(BigInteger, nullable=False)
    md5 = Column(String(32), nullable=False)
    sha256 = Column(String(64), nullable=False)
    sha512 = Column(String(128), nullable=False)
    description = Column(Text)
    source = Column(String(255))
    collected_at = Column(DateTime(timezone=True))
    is_verified = Column(Boolean, default=True)
    verification_status = Column(String(50), default='verified')
    last_verified_at = Column(DateTime(timezone=True))
    extra_data = Column(JSONB, default=dict)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Acquisition provenance (forensic defensibility)
    acquired_at = Column(DateTime(timezone=True))
    acquisition_method = Column(String(100))
    acquisition_tool = Column(String(150))
    source_host = Column(String(255))

    # Preservation / legal hold
    legal_hold_until = Column(DateTime(timezone=True))
    is_locked = Column(Boolean, default=False, nullable=False)

    # Relationships
    incident = relationship('Incident', back_populates='artifacts')
    uploader = relationship('User')
    chain_of_custody = relationship('ChainOfCustody', back_populates='artifact', lazy='dynamic', cascade='all, delete-orphan')

    STORAGE_TYPES = ['local', 's3', 'google_drive']
    VERIFICATION_STATUSES = ['verified', 'mismatch', 'pending']

    def __repr__(self):
        return f'<Artifact {self.original_filename}>'

    @property
    def under_legal_hold(self) -> bool:
        if self.is_locked:
            return True
        if self.legal_hold_until:
            return self.legal_hold_until > datetime.now(timezone.utc)
        return False

    def to_dict(self, include_custody=False):
        """Convert to dictionary."""
        data = super().to_dict()
        data['uploader'] = {'id': str(self.uploader.id), 'name': self.uploader.name} if self.uploader else None
        data['under_legal_hold'] = self.under_legal_hold

        if include_custody:
            data['chain_of_custody'] = [coc.to_dict() for coc in self.chain_of_custody.order_by(ChainOfCustody.created_at.desc()).limit(50)]

        return data


class ChainOfCustody(BaseModel):
    """Chain of custody log for artifacts."""
    __tablename__ = 'chain_of_custody'

    artifact_id = Column(UUID(as_uuid=True), ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False)
    action = Column(String(50), nullable=False)
    performed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    ip_address = Column(INET)
    user_agent = Column(Text)
    purpose = Column(Text)
    recipient_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    verification_result = Column(String(50))
    signature = Column(String(64))  # HMAC-SHA256 tamper-evidence over the record
    signature_key_id = Column(String(16))  # fingerprint of the signing key (rotation detection)
    extra_data = Column(JSONB, default=dict)

    # Relationships
    artifact = relationship('Artifact', back_populates='chain_of_custody')
    performer = relationship('User', foreign_keys=[performed_by])
    recipient = relationship('User', foreign_keys=[recipient_id])

    ACTIONS = ['upload', 'view', 'download', 'transfer', 'verify', 'export', 'delete', 'legal_hold']

    def __repr__(self):
        return f'<ChainOfCustody {self.action} by {self.performed_by}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['ip_address'] = str(self.ip_address) if self.ip_address else None
        data['performer'] = {'id': str(self.performer.id), 'name': self.performer.name} if self.performer else None
        data['recipient'] = {'id': str(self.recipient.id), 'name': self.recipient.name} if self.recipient else None
        return data

    # Signature states reported by signature_status()
    SIG_VALID = 'valid'
    SIG_UNSIGNED_LEGACY = 'unsigned_legacy'   # NULL signature: pre-dates signing
    SIG_INVALID = 'invalid'                   # does not match: altered record
    SIG_KEY_MISMATCH = 'key_mismatch'         # signed with a different (rotated) key

    def _payload_v1(self) -> str:
        """Original (pre key-id) payload — kept to verify rows signed before
        signature_key_id existed."""
        return _json.dumps({
            'artifact_id': str(self.artifact_id),
            'action': self.action,
            'performed_by': str(self.performed_by),
            'recipient_id': str(self.recipient_id) if self.recipient_id else None,
            'purpose': self.purpose,
            'verification_result': self.verification_result,
            'extra_data': self.extra_data or {},
        }, sort_keys=True, default=str)

    def _payload_v2(self) -> str:
        """Canonical payload covering every immutable field of the record."""
        return _json.dumps({
            'v': 2,
            'id': _canon_uuid(self.id),
            'artifact_id': _canon_uuid(self.artifact_id),
            'action': self.action,
            'performed_by': _canon_uuid(self.performed_by),
            'recipient_id': _canon_uuid(self.recipient_id),
            'ip_address': _canon_ip(self.ip_address),
            'user_agent': self.user_agent,
            'purpose': self.purpose,
            'verification_result': self.verification_result,
            'created_at': _canon_ts(self.created_at),
            'extra_data': self.extra_data or {},
        }, sort_keys=True, separators=(',', ':'), default=str)

    @staticmethod
    def _hmac(secret: str, payload: str) -> str:
        return hmac.new((secret or '').encode(), payload.encode(), hashlib.sha256).hexdigest()

    def compute_signature(self, secret: str) -> str:
        """Deterministic HMAC-SHA256 over the immutable custody fields."""
        return self._hmac(secret, self._payload_v2())

    def sign(self, secret: str) -> None:
        self.signature = self.compute_signature(secret)
        self.signature_key_id = custody_key_id(secret)

    def signature_status(self, secret: str, legacy_secret: str = None) -> str:
        """Classify this record's signature (see SIG_* constants).

        `legacy_secret` verifies rows signed before signature_key_id existed
        (those were signed with SECRET_KEY over the v1 payload).
        """
        if not self.signature:
            return self.SIG_UNSIGNED_LEGACY
        if not self.signature_key_id:
            expected = self._hmac(legacy_secret if legacy_secret is not None else secret, self._payload_v1())
            return self.SIG_VALID if hmac.compare_digest(self.signature, expected) else self.SIG_INVALID
        if self.signature_key_id != custody_key_id(secret):
            return self.SIG_KEY_MISMATCH
        return self.SIG_VALID if hmac.compare_digest(self.signature, self.compute_signature(secret)) else self.SIG_INVALID

    def verify_signature(self, secret: str) -> bool:
        """Whether the stored signature still matches the record (untampered)."""
        return self.signature_status(secret) == self.SIG_VALID


@event.listens_for(ChainOfCustody, 'before_insert')
def _coc_before_insert(mapper, connection, target):
    """Stamp id/created_at/signed_at and a tamper-evident HMAC signature.

    id and created_at are assigned here (not left to column defaults, which
    run after this hook) so they are covered by the signature.
    """
    if target.id is None:
        target.id = uuid.uuid4()
    if target.created_at is None:
        target.created_at = datetime.now(timezone.utc)
    ed = dict(target.extra_data or {})
    ed.setdefault('signed_at', datetime.now(timezone.utc).isoformat())
    target.extra_data = ed
    try:
        target.sign(custody_signing_key())
    except Exception:
        # Never block evidence logging, but make the failure loud: the row
        # will be reported as unsigned in custody exports.
        logger.exception('Chain-of-custody signing failed for entry %s', target.id)
