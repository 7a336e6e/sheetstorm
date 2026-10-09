#!/usr/bin/env python3
"""SheetStorm chain-of-custody verifier (v3 ledger) — STDLIB ONLY.

This file is the single source of the custody entry payload (``entry_payload_v3``)
and of the verification rules. The backend imports it for its own checks and
the custody export bundle ships it unchanged next to ``hash_chain.py``, so
server-side and offline verification cannot drift.

Offline usage (on an extracted export bundle)::

    python3 verify_custody.py manifest.json [--hmac-key-file KEY] [--json]

Exit codes: 0 intact, 1 broken / tampered, 2 malformed input.

Ledger model
------------
Every v3 entry belongs to two hash chains at once: its evidence item's chain
(``seq`` / ``prev_hash``) and its incident's chain (``incident_seq`` /
``incident_prev_hash``)::

    entry_hash = link_hash('custody-v3', prev_hash + ':' + incident_prev_hash,
                           canonical_json(entry_payload_v3(row)))
    signature  = HMAC-SHA256(CUSTODY_SIGNING_KEY,
                             b'sheetstorm-custody-v3\\x00' + entry_hash)

A chain starts at ``genesis_hash('custody-v3', 'item'|'incident', id)`` or, if
the scope has legacy (pre-v3, unchained) rows, at their ``legacy_seal``, which
pins the legacy rows so deleting or reordering them later is detectable.
Tampering that happened *before* the upgrade to v3 cannot be detected.
"""
import hashlib
import hmac
import ipaddress
import json
import sys
import uuid
from datetime import datetime, timezone

try:  # inside the application
    from app.utils.hash_chain import canonical_json, genesis_hash, link_hash, hmac_hex, verify_linear_chain
except ImportError:  # pragma: no cover - offline bundle layout (hash_chain.py alongside)
    from hash_chain import canonical_json, genesis_hash, link_hash, hmac_hex, verify_linear_chain

DOMAIN = 'custody-v3'
CHAIN_VERSION = 3
SIGNATURE_PREFIX = b'sheetstorm-custody-v3\x00'

# Fields of the hashed payload (order irrelevant: canonical_json sorts keys).
PAYLOAD_FIELDS = (
    'id', 'incident_id', 'evidence_item_id', 'artifact_id', 'seq', 'incident_seq',
    'prev_hash', 'incident_prev_hash', 'action', 'performed_by', 'recipient_id',
    'external_party_id', 'transfer_method', 'ip_address', 'user_agent', 'purpose',
    'verification_result', 'created_at', 'extra_data',
)
_UUID_FIELDS = ('id', 'incident_id', 'evidence_item_id', 'artifact_id', 'performed_by',
                'recipient_id', 'external_party_id')
_INT_FIELDS = ('seq', 'incident_seq')

SIG_VALID = 'valid'
SIG_UNSIGNED_LEGACY = 'unsigned_legacy'
SIG_INVALID = 'invalid'
SIG_KEY_MISMATCH = 'key_mismatch'
SIG_NOT_CHECKED = 'not_checked'

# Reasons that prove a chain was altered (timestamp_regression is a warning).
BREAK_REASONS = ('prev_hash_mismatch', 'entry_hash_mismatch', 'seq_gap', 'seq_duplicate',
                 'head_mismatch', 'missing_entry')


def _get(row, name):
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def canon_uuid(value):
    if value is None or value == '':
        return None
    return str(uuid.UUID(str(value)))


def canon_ts(value):
    """UTC ISO-8601 with microseconds; accepts datetime or ISO string."""
    if value is None or value == '':
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def canon_ip(value):
    if value is None or value == '':
        return None
    try:
        return str(ipaddress.ip_interface(str(value)).ip)
    except ValueError:
        return str(value)


def _canon_str(value):
    return None if value is None else str(value)


def entry_payload_v3(row) -> dict:
    """The hashed payload of a v3 custody entry (dict or object ``row``).

    Every value is normalised to str/int/null (UUIDs lowercase, timestamps UTC
    with microseconds, IPs without prefix length) so the payload is identical
    whether it is rebuilt from the database or from an export manifest.
    """
    payload = {'v': CHAIN_VERSION}
    for name in PAYLOAD_FIELDS:
        value = _get(row, name)
        if name in _UUID_FIELDS:
            value = canon_uuid(value)
        elif name in _INT_FIELDS:
            value = None if value is None else int(value)
        elif name == 'created_at':
            value = canon_ts(value)
        elif name == 'ip_address':
            value = canon_ip(value)
        elif name == 'extra_data':
            value = value if isinstance(value, dict) else ({} if value is None else value)
        else:
            value = _canon_str(value)
        payload[name] = value
    return payload


def link_prev(row) -> str:
    """The prev value fed into the hash: both chains' previous hashes."""
    return f"{_get(row, 'prev_hash') or ''}:{_get(row, 'incident_prev_hash') or ''}"


def payload_bytes(row) -> bytes:
    return canonical_json(entry_payload_v3(row), strict=True)


def compute_entry_hash(row) -> str:
    return link_hash(DOMAIN, link_prev(row), payload_bytes(row))


def compute_signature(key, entry_hash: str) -> str:
    return hmac_hex(key, SIGNATURE_PREFIX + (entry_hash or '').encode('utf-8'))


def key_id(secret) -> str:
    """Fingerprint of a signing key (matches ``app.models.artifact.custody_key_id``)."""
    if isinstance(secret, bytes):
        secret = secret.decode('utf-8')
    return hashlib.sha256(b'sheetstorm-custody-key-id:' + (secret or '').encode()).hexdigest()[:16]


def legacy_seal(legacy_rows):
    """``sha256(canonical_json([[id, signature or '', created_at], ...]))``
    over legacy rows ordered by (created_at, id); None when there are none."""
    items = []
    for r in legacy_rows:
        items.append([canon_uuid(_get(r, 'id')), _get(r, 'signature') or '', canon_ts(_get(r, 'created_at'))])
    if not items:
        return None
    items.sort(key=lambda x: (x[2] or '', x[0] or ''))
    return hashlib.sha256(canonical_json(items, strict=True)).hexdigest()


def chain_genesis(scope, scope_id, legacy_rows):
    """(expected first prev_hash, 'genesis'|'legacy_seal')."""
    seal = legacy_seal(legacy_rows)
    if seal is not None:
        return seal, 'legacy_seal'
    return genesis_hash(DOMAIN, scope, canon_uuid(scope_id)), 'genesis'


def verify_chain(rows, scope, scope_id, legacy_rows=(), *, seq_attr='seq', prev_attr='prev_hash'):
    """Verify one chain (``rows`` = v3 rows of the scope, any order).

    Returns ``{length, head_seq, head_hash, genesis, breaks, warnings}``.
    """
    ordered = sorted(rows, key=lambda r: (_get(r, seq_attr) is None, _get(r, seq_attr) or 0))
    genesis, kind = chain_genesis(scope, scope_id, legacy_rows)
    failures = verify_linear_chain(
        ordered, DOMAIN, genesis, prev_attr, payload_bytes,
        hash_attr='entry_hash', seq_attr=seq_attr, ts_attr='created_at',
        link_prev_fn=link_prev, start_seq=1,
    )
    # created_at may be a datetime or a string; compare canonical strings only
    # where verify_linear_chain could not.
    breaks = [f for f in failures if f['reason'] != 'timestamp_regression']
    warnings = [f for f in failures if f['reason'] == 'timestamp_regression']
    head = ordered[-1] if ordered else None
    return {
        'length': len(ordered),
        'head_seq': _get(head, seq_attr) if head is not None else 0,
        'head_hash': _get(head, 'entry_hash') if head is not None else genesis,
        'genesis': kind,
        'breaks': breaks,
        'warnings': warnings,
    }


def signature_status(row, secret=None, *, legacy_status=None):
    """Classify a row's signature: valid / unsigned_legacy / invalid /
    key_mismatch (``not_checked`` when no key is given).

    v3 rows are checked against the *recomputed* entry hash, so editing any
    payload field invalidates the signature. A v3 row without a signature is
    ``invalid`` (only pre-v3 rows may be unsigned). Legacy (v1/v2) rows are
    classified by ``legacy_status`` (supplied by the backend, which owns the
    legacy payload formats) or reported unsigned/not_checked offline.
    """
    if _get(row, 'chain_version') != CHAIN_VERSION:
        if legacy_status is not None:
            return legacy_status
        return SIG_UNSIGNED_LEGACY if not _get(row, 'signature') else SIG_NOT_CHECKED
    sig = _get(row, 'signature')
    if not sig:
        return SIG_INVALID
    if secret is None:
        return SIG_NOT_CHECKED
    if _get(row, 'signature_key_id') and _get(row, 'signature_key_id') != key_id(secret):
        return SIG_KEY_MISMATCH
    try:
        expected = compute_signature(secret, compute_entry_hash(row))
    except (TypeError, ValueError):
        return SIG_INVALID
    return SIG_VALID if hmac.compare_digest(str(sig), expected) else SIG_INVALID


def overall_status(breaks, signatures):
    """intact | intact_with_unsigned_legacy | unverifiable | broken | compromised."""
    if signatures.get(SIG_INVALID):
        return 'compromised'
    if breaks:
        return 'broken'
    if signatures.get(SIG_KEY_MISMATCH):
        return 'unverifiable'
    if signatures.get(SIG_UNSIGNED_LEGACY):
        return 'intact_with_unsigned_legacy'
    return 'intact'


# ── Manifest verification (offline) ─────────────────────────────────────────

def verify_manifest(manifest, hmac_key=None):
    """Verify an export manifest (``{scope, incident_id, entries, heads, ...}``).

    ``entries``: every entry of the exported scope, v3 rows with all payload
    fields + ``entry_hash``/``signature``/``signature_key_id``/``chain_version``,
    legacy rows with at least ``id``/``signature``/``created_at``/
    ``evidence_item_id``/``chain_version: null``.
    ``heads``: ``{"items": {item_id: {seq, hash}}, "incident": {seq, hash}|null}``.
    """
    if not isinstance(manifest, dict) or not isinstance(manifest.get('entries'), list):
        raise ValueError('manifest must be an object with an "entries" list')
    entries = manifest['entries']
    scope = manifest.get('scope', 'item')
    incident_id = manifest.get('incident_id')
    heads = manifest.get('heads') or {}

    v3 = [e for e in entries if e.get('chain_version') == CHAIN_VERSION]
    legacy = [e for e in entries if e.get('chain_version') != CHAIN_VERSION]

    report = {'scope': scope, 'items': {}, 'incident_chain': None, 'breaks': [],
              'warnings': [], 'signatures': {}}

    item_ids = sorted({canon_uuid(e.get('evidence_item_id')) for e in entries if e.get('evidence_item_id')})
    for iid in item_ids:
        rows = [e for e in v3 if canon_uuid(e.get('evidence_item_id')) == iid]
        leg = [e for e in legacy if canon_uuid(e.get('evidence_item_id')) == iid]
        res = verify_chain(rows, 'item', iid, leg)
        expected = (heads.get('items') or {}).get(iid)
        if expected and rows and (expected.get('seq') != res['head_seq'] or expected.get('hash') != res['head_hash']):
            res['breaks'].append({'seq': res['head_seq'], 'id': None, 'reason': 'head_mismatch'})
        report['items'][iid] = res
        report['breaks'] += [dict(b, chain='item', evidence_item_id=iid) for b in res['breaks']]
        report['warnings'] += [dict(w, chain='item', evidence_item_id=iid) for w in res['warnings']]

    if scope == 'incident' and incident_id:
        res = verify_chain(v3, 'incident', incident_id, legacy, seq_attr='incident_seq',
                           prev_attr='incident_prev_hash')
        expected = heads.get('incident')
        if expected and (expected.get('seq') != res['head_seq'] or expected.get('hash') != res['head_hash']):
            res['breaks'].append({'seq': res['head_seq'], 'id': None, 'reason': 'head_mismatch'})
        report['incident_chain'] = res
        report['breaks'] += [dict(b, chain='incident') for b in res['breaks']]
        report['warnings'] += [dict(w, chain='incident') for w in res['warnings']]

    sigs = {}
    for e in entries:
        st = signature_status(e, hmac_key)
        sigs[st] = sigs.get(st, 0) + 1
    report['signatures'] = sigs
    report['status'] = overall_status(report['breaks'], sigs)
    return report


def _main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Verify a SheetStorm chain-of-custody export manifest.')
    parser.add_argument('manifest', help='manifest.json from a custody export bundle')
    parser.add_argument('--hmac-key-file', help='file holding CUSTODY_SIGNING_KEY (checks signatures)')
    parser.add_argument('--json', action='store_true', help='print the full report as JSON')
    args = parser.parse_args(argv)
    try:
        with open(args.manifest, encoding='utf-8') as fh:
            manifest = json.load(fh)
        key = None
        if args.hmac_key_file:
            with open(args.hmac_key_file, encoding='utf-8') as fh:
                key = fh.read().strip()
        report = verify_manifest(manifest, key)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'malformed input: {exc}', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(f"status: {report['status']}")
        for iid, res in sorted(report['items'].items()):
            print(f"item {iid}: {res['length']} entries, head seq {res['head_seq']}, genesis {res['genesis']}")
        if report['incident_chain'] is not None:
            res = report['incident_chain']
            print(f"incident chain: {res['length']} entries, head seq {res['head_seq']}")
        else:
            print('incident chain: not included')
        for b in report['breaks']:
            print(f"BREAK {b.get('chain')} seq={b.get('seq')} id={b.get('id')}: {b.get('reason')}")
        for w in report['warnings']:
            print(f"warning {w.get('chain')} seq={w.get('seq')}: {w.get('reason')}")
        print('signatures: ' + ', '.join(f'{k}={v}' for k, v in sorted(report['signatures'].items())))
    return 0 if report['status'] in ('intact', 'intact_with_unsigned_legacy', 'unverifiable') else 1


if __name__ == '__main__':  # pragma: no cover
    sys.exit(_main())
