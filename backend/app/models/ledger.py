"""Hash-chain head table (``ledger_heads``), used by the audit log chain.

One row per chain, keyed by ``chain_key`` (``audit:<org_uuid>`` or
``audit:global`` for rows without an organization). The row is locked
(``SELECT ... FOR UPDATE``) while a new entry is appended, so appends to one
chain are serialized; see ``services/ledger.py``.
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB

from app import db


class LedgerHead(db.Model):
    __tablename__ = 'ledger_heads'

    chain_key = Column(String(100), primary_key=True)
    last_seq = Column(BigInteger, nullable=False, default=0, server_default='0')
    last_hash = Column(String(64))
    # Retention purge: rows with seq <= purged_through_seq were deleted;
    # anchor_hash is the row_hash of the last deleted row (the prev_hash the
    # first remaining row must carry).
    purged_through_seq = Column(BigInteger, nullable=False, default=0, server_default='0')
    anchor_hash = Column(String(64))
    last_verified_at = Column(DateTime(timezone=True))
    last_verify_ok = Column(Boolean)
    last_verify_summary = Column(JSONB)
    updated_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f'<LedgerHead {self.chain_key} seq={self.last_seq}>'

    def to_dict(self):
        return {
            'chain_key': self.chain_key,
            'last_seq': self.last_seq,
            'last_hash': self.last_hash,
            'purged_through_seq': self.purged_through_seq,
            'anchor_hash': self.anchor_hash,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
            'last_verify_ok': self.last_verify_ok,
            'last_verify_summary': self.last_verify_summary,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
