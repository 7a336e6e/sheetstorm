"""Chain heads for the audit log hash chain (``ledger_heads``).

Append protocol (one transaction, see ``middleware.audit._write_audit_row``)::

    seq, prev = advance(chain_key)        # locks the head row (FOR UPDATE)
    row.chain_seq, row.prev_hash = seq, prev
    row.row_hash = audit_row_hash(...)    # keyed HMAC over the link payload
    session.add(row)
    commit_head(chain_key, seq, row.row_hash)
    session.commit()                      # releases the head lock

The head row lock serializes appends to one chain, so sequence numbers are
gap-free and every row links to its predecessor. The lock is held only for
the few statements between ``advance`` and the commit.

Chain keys: ``audit:<org_uuid>``, or ``audit:global`` for rows without an
organization. Audit only: the custody ledger keeps its own advisory lock +
``max(seq)`` (it has two chains per entry).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import text

from app import db
from app.utils.hash_chain import genesis_hash, hmac_hex

logger = logging.getLogger(__name__)

AUDIT_DOMAIN = 'audit-v1'
GLOBAL_SCOPE = 'global'

_warned_key_fallback = False


def audit_chain_key(organization_id) -> str:
    """``audit:<org>`` (or ``audit:global``) for an organization id."""
    return f'audit:{organization_id}' if organization_id else f'audit:{GLOBAL_SCOPE}'


def audit_genesis(organization_id) -> str:
    """The ``prev_hash`` of the first row of an org's chain."""
    if organization_id:
        return genesis_hash(AUDIT_DOMAIN, 'org', str(organization_id))
    return genesis_hash(AUDIT_DOMAIN, GLOBAL_SCOPE, GLOBAL_SCOPE)


def key_id(key: bytes) -> str:
    """Public identifier of a chain key (first 16 hex chars of its sha256)."""
    return hashlib.sha256(key).hexdigest()[:16]


def _as_bytes(value) -> bytes:
    return value.encode('utf-8') if isinstance(value, str) else bytes(value)


def ledger_key() -> tuple[bytes, str]:
    """``(key_bytes, key_id)`` of the current audit chain key.

    ``AUDIT_CHAIN_KEY``; falls back to ``SECRET_KEY`` (logged once) so a
    deployment without the key still writes a verifiable chain.
    """
    global _warned_key_fallback
    raw = current_app.config.get('AUDIT_CHAIN_KEY') or ''
    if not raw:
        raw = current_app.config.get('SECRET_KEY') or ''
        if not _warned_key_fallback:
            _warned_key_fallback = True
            logger.warning('AUDIT_CHAIN_KEY is not set; the audit hash chain is keyed with SECRET_KEY. '
                           'Set a dedicated AUDIT_CHAIN_KEY so rotating SECRET_KEY keeps the chain verifiable.')
    if not raw:
        raise RuntimeError('No audit chain key available (AUDIT_CHAIN_KEY / SECRET_KEY)')
    key = _as_bytes(raw)
    return key, key_id(key)


def known_keys() -> dict[str, bytes]:
    """``{key_id: key}`` for the current key and ``AUDIT_CHAIN_PREVIOUS_KEYS``."""
    current, current_id = ledger_key()
    keys = {current_id: current}
    for raw in current_app.config.get('AUDIT_CHAIN_PREVIOUS_KEYS') or ():
        k = _as_bytes(raw)
        keys.setdefault(key_id(k), k)
    return keys


def keyed_link_hash(key: bytes):
    """A ``hash_fn(domain, prev, payload)`` (``verify_linear_chain`` shape):
    HMAC-SHA256 over ``domain NUL prev NUL payload`` (``link_hash`` layout)."""
    def _hash(domain: str, prev_hash: str, payload: bytes) -> str:
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError('payload must be bytes')
        return hmac_hex(key, domain.encode('utf-8') + b'\x00' + prev_hash.encode('utf-8')
                        + b'\x00' + bytes(payload))
    return _hash


def advance(chain_key: str, session=None) -> tuple[int, str | None]:
    """Lock the chain head and return ``(next_seq, last_hash)``.

    Creates the head row on first use (``INSERT ... ON CONFLICT DO NOTHING``,
    safe under concurrency), then ``SELECT ... FOR UPDATE``. ``last_hash`` is
    None for an empty chain (callers use the genesis hash). Must be followed
    by :func:`commit_head` and a commit in the same transaction.
    """
    session = session or db.session
    session.execute(text(
        'INSERT INTO ledger_heads (chain_key, last_seq, purged_through_seq, updated_at) '
        'VALUES (:k, 0, 0, now()) ON CONFLICT (chain_key) DO NOTHING'), {'k': chain_key})
    row = session.execute(text(
        'SELECT last_seq, last_hash FROM ledger_heads WHERE chain_key = :k FOR UPDATE'),
        {'k': chain_key}).one()
    return int(row.last_seq) + 1, row.last_hash


def commit_head(chain_key: str, seq: int, row_hash: str, session=None) -> None:
    """Move the (locked) head to ``seq`` / ``row_hash``."""
    session = session or db.session
    session.execute(text(
        'UPDATE ledger_heads SET last_seq = :s, last_hash = :h, updated_at = :t WHERE chain_key = :k'),
        {'s': seq, 'h': row_hash, 't': datetime.now(timezone.utc), 'k': chain_key})


def get_head(chain_key: str, session=None):
    """The ``LedgerHead`` row (no lock), or None."""
    from app.models import LedgerHead
    session = session or db.session
    return session.get(LedgerHead, chain_key, populate_existing=True)


def lock_head(chain_key: str, session=None):
    """``SELECT ... FOR UPDATE`` the head row (purge); None if absent."""
    from app.models import LedgerHead
    session = session or db.session
    return (session.query(LedgerHead).filter_by(chain_key=chain_key)
            .with_for_update().populate_existing().one_or_none())


__all__ = [
    'AUDIT_DOMAIN', 'audit_chain_key', 'audit_genesis', 'key_id', 'ledger_key', 'known_keys',
    'keyed_link_hash', 'advance', 'commit_head', 'get_head', 'lock_head',
]
