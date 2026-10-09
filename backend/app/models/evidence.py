"""Evidence register: evidence items, external custody parties, ledger anchors.

An ``EvidenceItem`` is the *thing* (a phone, an E01 set, a sealed bag, an
uploaded file). It may have 0..n stored ``Artifact`` copies. The custody
ledger (``chain_of_custody``) is keyed on the item; see
``app/services/custody_ledger.py``. ``custody_state`` / holder / location /
verification columns are a projection of the ledger, written only by
``CustodyLedger``.

Items are never hard-deleted except by the audited incident purge
(``services/incident_purge.py``); a mistake is voided (tombstone).
"""
from datetime import datetime, timezone

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index,
                        Integer, Numeric, LargeBinary, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel

EVIDENCE_TYPES = (
    'disk_image', 'memory_capture', 'triage_package', 'logical_collection', 'mobile_device',
    'storage_media', 'computer_system', 'network_capture', 'cloud_export', 'log_export',
    'document', 'digital_file', 'other',
)
CUSTODY_STATES = ('in_storage', 'checked_out', 'transferred', 'disposed')
HASH_ALGORITHMS = {'md5': 32, 'sha1': 40, 'sha256': 64, 'sha512': 128}
HASH_SOURCES = ('tool_reported', 'computed_on_upload', 'computed_in_lab')
PARTY_ROLES = ('counsel', 'law_enforcement', 'third_party_lab', 'insurer', 'client', 'regulator',
               'courier', 'other')
TRANSFER_METHODS = ('hand_delivery', 'courier', 'registered_mail', 'secure_file_transfer', 'internal', 'other')
ANCHOR_TYPES = ('rfc3161', 'export_manifest')
ANCHOR_STATUSES = ('granted', 'failed')

MAX_PARENT_DEPTH = 32


def _sql_in(values):
    return ', '.join(f"'{v}'" for v in values)


class CustodyParty(BaseModel):
    """External custody party (counsel, lab, law enforcement...), org-scoped.

    Deactivated, never deleted. Ledger rows snapshot party details into their
    signed ``extra_data``, so later edits here cannot rewrite history.
    """
    __tablename__ = 'custody_parties'
    __table_args__ = (
        CheckConstraint(f'role IN ({_sql_in(PARTY_ROLES)})', name='ck_custody_parties_role'),
        Index('idx_custody_parties_org', 'organization_id'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    organization_name = Column(String(255))
    role = Column(String(40), nullable=False, default='other', server_default='other')
    email = Column(String(255))
    phone = Column(String(60))
    address = Column(Text)
    notes = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    creator = relationship('User', foreign_keys=[created_by])

    def snapshot(self) -> dict:
        """Signed-ledger snapshot (str/None values only)."""
        return {
            'id': str(self.id),
            'name': self.name,
            'organization_name': self.organization_name,
            'role': self.role,
            'email': self.email,
            'phone': self.phone,
        }

    def to_dict(self):
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        return data


class EvidenceItem(BaseModel):
    """A registered piece of evidence (``EV-0007`` within its incident)."""
    __tablename__ = 'evidence_items'
    __table_args__ = (
        UniqueConstraint('incident_id', 'sequence_number', name='uq_evidence_items_incident_seq'),
        CheckConstraint(f'evidence_type IN ({_sql_in(EVIDENCE_TYPES)})', name='ck_evidence_items_type'),
        CheckConstraint(f'custody_state IN ({_sql_in(CUSTODY_STATES)})', name='ck_evidence_items_custody_state'),
        CheckConstraint("last_verification_result IS NULL OR last_verification_result IN ('match', 'mismatch')",
                        name='ck_evidence_items_verification'),
        Index('idx_evidence_items_incident', 'incident_id'),
        Index('idx_evidence_items_org', 'organization_id'),
        Index('idx_evidence_items_parent', 'parent_id'),
        Index('idx_evidence_items_hashes', 'acquisition_hashes', postgresql_using='gin',
              postgresql_ops={'acquisition_hashes': 'jsonb_path_ops'}),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    evidence_type = Column(String(40), nullable=False, default='other')
    title = Column(String(255), nullable=False)
    description = Column(Text)
    condition_notes = Column(Text)
    media_type = Column(String(120))
    make = Column(String(120))
    model = Column(String(120))
    serial_number = Column(String(120))
    capacity_bytes = Column(BigInteger)
    seal_number = Column(String(120))
    bag_number = Column(String(120))
    storage_location = Column(String(500))
    acquired_at = Column(DateTime(timezone=True))
    acquired_by_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    acquired_by_name = Column(String(255))
    acquired_from = Column(String(500))
    acquisition_method = Column(String(100))
    acquisition_tool = Column(String(150))
    acquisition_tool_version = Column(String(60))
    source_host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id', ondelete='SET NULL'))
    source_host_label = Column(String(255))
    acquisition_hashes = Column(JSONB, nullable=False, default=list, server_default='[]')
    parent_id = Column(UUID(as_uuid=True), ForeignKey('evidence_items.id'))
    derivation_note = Column(Text)
    # Ledger projection (written by CustodyLedger only)
    custody_state = Column(String(20), nullable=False, default='in_storage', server_default='in_storage')
    current_holder_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    current_holder_party_id = Column(UUID(as_uuid=True), ForeignKey('custody_parties.id'))
    expected_return_at = Column(DateTime(timezone=True))
    last_verified_at = Column(DateTime(timezone=True))
    last_verification_result = Column(String(20))
    # Preservation (same semantics as artifacts)
    legal_hold_until = Column(DateTime(timezone=True))
    is_locked = Column(Boolean, nullable=False, default=False, server_default='false')
    # Tombstone ("entered in error"); the number is never reused
    voided_at = Column(DateTime(timezone=True))
    voided_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    void_reason = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    extra_data = Column(JSONB, default=dict)
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    incident = relationship('Incident', back_populates='evidence_items')
    creator = relationship('User', foreign_keys=[created_by])
    acquired_by = relationship('User', foreign_keys=[acquired_by_user_id])
    current_holder_user = relationship('User', foreign_keys=[current_holder_user_id])
    current_holder_party = relationship('CustodyParty', foreign_keys=[current_holder_party_id])
    voider = relationship('User', foreign_keys=[voided_by])
    source_host = relationship('CompromisedHost', foreign_keys=[source_host_id])
    parent = relationship('EvidenceItem', remote_side='EvidenceItem.id', foreign_keys=[parent_id],
                          back_populates='children')
    # The ledger and stored copies are never deleted through the ORM: only the
    # DB-level incident cascade (under the purge GUC) removes them.
    children = relationship('EvidenceItem', back_populates='parent', lazy='dynamic', passive_deletes='all')
    artifacts = relationship('Artifact', back_populates='evidence_item', lazy='dynamic', passive_deletes='all')
    custody_entries = relationship('ChainOfCustody', back_populates='evidence_item', lazy='dynamic',
                                   passive_deletes='all')

    def __repr__(self):
        return f'<EvidenceItem {self.evidence_number}>'

    @property
    def evidence_number(self) -> str:
        return f'EV-{(self.sequence_number or 0):04d}'

    @property
    def display_id(self) -> str:
        num = self.incident.incident_number if self.incident is not None else None
        return f'CASE-{num}/{self.evidence_number}' if num is not None else self.evidence_number

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    @property
    def own_legal_hold(self) -> bool:
        if self.is_locked:
            return True
        if self.legal_hold_until:
            return self.legal_hold_until > datetime.now(timezone.utc)
        return False

    @property
    def under_legal_hold(self) -> bool:
        """Own hold, or any ancestor's hold (parent walk, max depth 32)."""
        node, depth = self, 0
        while node is not None and depth <= MAX_PARENT_DEPTH:
            if node.own_legal_hold:
                return True
            node = node.parent
            depth += 1
        return False

    @property
    def weak_hashes_only(self) -> bool:
        algs = {h.get('algorithm') for h in (self.acquisition_hashes or []) if isinstance(h, dict)}
        return bool(algs) and not (algs & {'sha256', 'sha512'})

    def summary(self) -> dict:
        return {'id': str(self.id), 'evidence_number': self.evidence_number, 'title': self.title,
                'evidence_type': self.evidence_type, 'voided': self.is_voided}

    def holder_dict(self):
        if self.current_holder_party is not None:
            p = self.current_holder_party
            return {'type': 'party', 'id': str(p.id), 'name': p.name}
        if self.current_holder_user is not None:
            u = self.current_holder_user
            return {'type': 'user', 'id': str(u.id), 'name': u.name}
        return {'type': 'storage', 'id': None, 'name': self.storage_location}

    def to_dict(self):
        data = super().to_dict()
        data['evidence_number'] = self.evidence_number
        data['display_id'] = self.display_id
        data['under_legal_hold'] = self.under_legal_hold
        data['weak_hashes_only'] = self.weak_hashes_only
        data['holder'] = self.holder_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['parent'] = self.parent.summary() if self.parent is not None else None
        return data


class CustodyAnchor(BaseModel):
    """External anchor of an incident ledger head (RFC 3161 token or a head
    hash handed out in an export manifest). Append-only (trigger)."""
    __tablename__ = 'custody_anchors'
    __table_args__ = (
        CheckConstraint(f'anchor_type IN ({_sql_in(ANCHOR_TYPES)})', name='ck_custody_anchors_type'),
        CheckConstraint(f'status IN ({_sql_in(ANCHOR_STATUSES)})', name='ck_custody_anchors_status'),
        Index('idx_custody_anchors_incident', 'incident_id'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    incident_seq = Column(Integer, nullable=False)
    head_hash = Column(String(64), nullable=False)
    anchor_type = Column(String(30), nullable=False)
    tsa_url = Column(Text)
    nonce = Column(Numeric(20, 0))
    token_der = Column(LargeBinary)
    status = Column(String(20), nullable=False)
    error = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'incident_id': str(self.incident_id),
            'incident_seq': self.incident_seq,
            'head_hash': self.head_hash,
            'anchor_type': self.anchor_type,
            'tsa_url': self.tsa_url,
            'nonce': str(self.nonce) if self.nonce is not None else None,
            'status': self.status,
            'error': self.error,
            'created_by': str(self.created_by) if self.created_by else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
