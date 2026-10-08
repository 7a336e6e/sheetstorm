"""Hash-chain primitives shared by the custody ledger, the audit log and the
decision log.

STDLIB ONLY: this file is shipped unchanged inside custody export bundles next
to ``verify_custody.py`` so evidence can be verified offline without the
application installed. Do not import anything from ``app`` or third-party
packages at module level (``advisory_xact_lock`` imports SQLAlchemy lazily;
it is never used by the offline verifier).

Domains in use: ``custody-v3``, ``audit-v1``, ``decision-v1``.
Advisory-lock keys: ``custody:<incident_id>``, ``audit:<org_id>``.
"""
import hashlib
import hmac
import json
import math

__all__ = [
    'canonical_json', 'genesis_hash', 'link_hash', 'hmac_hex',
    'advisory_xact_lock', 'verify_linear_chain',
]


def _check_strict(obj, path='$'):
    """Reject anything that does not round-trip byte-identically through JSON
    and Postgres JSONB: floats (incl. NaN/inf), non-str keys, non-JSON types."""
    if obj is None or isinstance(obj, (bool, str)):
        return
    if isinstance(obj, int):
        return
    if isinstance(obj, float):
        raise ValueError(f'canonical_json(strict): float not allowed at {path}')
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check_strict(v, f'{path}[{i}]')
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ValueError(f'canonical_json(strict): non-str key {k!r} at {path}')
            _check_strict(v, f'{path}.{k}')
        return
    raise ValueError(f'canonical_json(strict): unsupported type {type(obj).__name__} at {path}')


def _to_lenient(obj):
    """Lenient normalisation: unknown types -> str, non-finite floats -> str,
    non-str keys -> str. Deterministic, never raises."""
    if obj is None or isinstance(obj, (bool, str, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else str(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_lenient(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _to_lenient(v) for k, v in obj.items()}
    return str(obj)


def canonical_json(obj, *, strict=True) -> bytes:
    """Canonical UTF-8 JSON bytes: sorted keys, no whitespace, no ASCII escaping.

    strict=True (custody, decisions) raises ValueError on floats, NaN, non-str
    keys and any non-JSON type, so values must be normalised to str/int/bool/
    null before hashing. strict=False (audit) converts such values with str().
    """
    if strict:
        _check_strict(obj)
    else:
        obj = _to_lenient(obj)
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def genesis_hash(domain: str, scope: str, scope_id) -> str:
    """Deterministic first ``prev_hash`` of a chain (hex sha256)."""
    return hashlib.sha256(f'sheetstorm:{domain}:genesis:{scope}:{scope_id}'.encode('utf-8')).hexdigest()


def link_hash(domain: str, prev_hash: str, payload: bytes) -> str:
    """sha256(domain NUL prev_hash NUL payload) as hex."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError('link_hash payload must be bytes (use canonical_json)')
    if not isinstance(prev_hash, str):
        raise TypeError('link_hash prev_hash must be str')
    return hashlib.sha256(
        domain.encode('utf-8') + b'\x00' + prev_hash.encode('utf-8') + b'\x00' + bytes(payload)
    ).hexdigest()


def hmac_hex(key, data) -> str:
    """HMAC-SHA256 hex digest; str key/data are UTF-8 encoded."""
    if isinstance(key, str):
        key = key.encode('utf-8')
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def advisory_xact_lock(session, key: str) -> None:
    """Take a Postgres transaction-scoped advisory lock on ``key``.

    Released automatically at COMMIT/ROLLBACK. Serialises appends to one chain
    (e.g. ``custody:<incident_id>``, ``audit:<org_id>``).
    """
    from sqlalchemy import text  # lazy: keeps this module stdlib-only
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))'), {'k': key})


def _get(row, name):
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def verify_linear_chain(rows, domain, genesis, prev_attr, payload_fn, *,
                        hash_attr='entry_hash', seq_attr='seq', id_attr='id',
                        ts_attr='created_at', link_prev_fn=None, hash_fn=None,
                        start_seq=None):
    """Verify a single linear chain. ``rows`` must be ordered by sequence.

    Each row (dict or object) has ``seq_attr``, ``id_attr``, ``prev_attr`` (the
    stored previous hash) and ``hash_attr`` (the stored entry hash).
    ``payload_fn(row) -> bytes`` rebuilds the hashed payload.
    ``link_prev_fn(row) -> str`` gives the prev value fed into the hash
    (default: the stored prev hash; custody combines both chains' prevs).
    ``hash_fn(domain, prev, payload) -> hex`` defaults to ``link_hash`` (the
    audit log passes a keyed HMAC variant). ``start_seq``: expected first seq
    (None = accept whatever the first row has, e.g. after a purge).

    Returns ``[{seq, id, reason}]`` with reason in ``prev_hash_mismatch``,
    ``entry_hash_mismatch``, ``seq_gap``, ``seq_duplicate`` or
    ``timestamp_regression`` (a warning, not proof of tampering).
    """
    hash_fn = hash_fn or link_hash
    failures = []
    expected_prev = genesis
    last_seq = None
    last_ts = None
    first = True

    for row in rows:
        seq = _get(row, seq_attr)
        rid = _get(row, id_attr)
        rid = str(rid) if rid is not None else None

        def fail(reason, _seq=seq, _rid=rid):
            failures.append({'seq': _seq, 'id': _rid, 'reason': reason})

        if first:
            if start_seq is not None and seq != start_seq:
                fail('seq_gap')
        elif seq is None or last_seq is None or seq <= last_seq:
            fail('seq_duplicate')
        elif seq != last_seq + 1:
            fail('seq_gap')

        stored_prev = _get(row, prev_attr)
        if not isinstance(stored_prev, str) or not hmac.compare_digest(stored_prev, expected_prev):
            fail('prev_hash_mismatch')

        stored_hash = _get(row, hash_attr)
        link_prev = link_prev_fn(row) if link_prev_fn else stored_prev
        try:
            recomputed = hash_fn(domain, link_prev if isinstance(link_prev, str) else '', payload_fn(row))
        except (TypeError, ValueError):
            recomputed = None
        if (not isinstance(stored_hash, str) or recomputed is None
                or not hmac.compare_digest(stored_hash, recomputed)):
            fail('entry_hash_mismatch')

        ts = _get(row, ts_attr)
        if ts is not None and last_ts is not None:
            try:
                if ts < last_ts:
                    fail('timestamp_regression')
            except TypeError:
                pass
        if ts is not None:
            last_ts = ts

        # Continue from the STORED hash so one tampered row is reported once
        # instead of cascading into every later row.
        expected_prev = stored_hash if isinstance(stored_hash, str) else ''
        if seq is not None:
            last_seq = seq if last_seq is None else max(last_seq, seq)
        first = False

    return failures
