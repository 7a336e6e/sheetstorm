"""Evidence register and chain-of-custody exports (evidence plan §3.7).

Formats
    item custody   json | csv | pdf (``custody/item_report.html``) |
                   form (printable chain-of-custody form, ``custody/item_form.html``) |
                   bundle (ZIP)
    register       csv | pdf (``custody/register.html``, landscape) | bundle (ZIP)

Every PDF goes through ``services/pdf_render.render_pdf`` (autoescaped Jinja,
WeasyPrint with every URL fetch refused) and every CSV cell through
``utils/csv_safe.csv_safe``.

Bundles (stdlib ``zipfile``, spooled to disk past 16 MB) hold
``manifest.json`` (every entry's full v3 payload + entry_hash + signature +
key id, the chain heads and anchors), ``entries.csv``, ``chain_of_custody.pdf``,
the stdlib verifier ``verify_custody.py`` + ``hash_chain.py`` copied unchanged
from ``app/utils``, ``README.txt`` and ``SHA256SUMS``. Archive member names
are fixed constants, never user input. The HMAC key is never exported.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone

from app.models.artifact import custody_key_id, custody_signing_key
from app.services.pdf_render import render_pdf
from app.utils import verify_custody as vc
from app.utils.csv_safe import csv_safe

MANIFEST_SCHEMA_VERSION = 1
SPOOL_MAX_BYTES = 16 * 1024 * 1024
VERIFIER_FILES = ('verify_custody.py', 'hash_chain.py')
_UTILS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'utils')

OK_STATUSES = ('intact', 'intact_with_unsigned_legacy')

STATUS_LABELS = {
    'intact': 'INTACT',
    'intact_with_unsigned_legacy': 'INTACT (includes unsigned entries that pre-date signing)',
    'unverifiable': 'UNVERIFIABLE (entries signed with a different key)',
    'broken': 'BROKEN (entries missing, reordered or altered)',
    'compromised': 'COMPROMISED (a signature does not match its entry)',
}

SIGNATURE_LABELS = {
    vc.SIG_VALID: 'valid',
    vc.SIG_UNSIGNED_LEGACY: 'unsigned (pre-dates signing)',
    vc.SIG_KEY_MISMATCH: 'signed with a different key (key rotated)',
    vc.SIG_INVALID: 'TAMPERED',
}

# Actions shown in the printable form's custody table.
FORM_ACTIONS = ('check_out', 'transfer', 'check_in', 'dispose')

ENTRY_CSV_COLUMNS = (
    'seq', 'incident_seq', 'evidence_number', 'timestamp_utc', 'action', 'performed_by', 'recipient',
    'transfer_method', 'purpose', 'verification_result', 'ip_address', 'signature_status', 'link_status',
    'entry_hash',
)
REGISTER_CSV_COLUMNS = (
    'evidence_number', 'type', 'title', 'serial_number', 'seal_number', 'custody_state', 'holder',
    'storage_location', 'primary_hash', 'acquired_at', 'acquired_by', 'legal_hold', 'last_verification',
    'chain_status', 'voided',
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec='seconds')


def _display_ts(value):
    """``2026-10-09 14:03:11 UTC`` for printed documents."""
    if value is None:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


# ── Item / entry views ──────────────────────────────────────────────────────

def active_hashes(item) -> list:
    """Recorded acquisition hashes that are not superseded."""
    return [h for h in (item.acquisition_hashes or []) if isinstance(h, dict) and not h.get('superseded')]


def current_hash(item, algorithm):
    for h in reversed(active_hashes(item)):
        if h.get('algorithm') == algorithm:
            return h.get('value')
    return None


def primary_hash(item) -> str:
    """``sha256:<hex>`` when recorded, else the first active hash."""
    hashes = active_hashes(item)
    for preferred in ('sha256', 'sha512', 'sha1', 'md5'):
        for h in hashes:
            if h.get('algorithm') == preferred:
                return f"{preferred}:{h.get('value')}"
    return ''


def holder_label(item) -> str:
    holder = item.holder_dict()
    if holder['type'] == 'party':
        party = item.current_holder_party
        org = f' ({party.organization_name})' if party is not None and party.organization_name else ''
        return f"{holder['name']}{org} [external]"
    if holder['type'] == 'user':
        return holder['name'] or ''
    return f"Storage: {holder['name']}" if holder['name'] else 'Storage'


def _party_label(snap) -> str:
    if not isinstance(snap, dict):
        return ''
    parts = [snap.get('name') or '']
    if snap.get('organization_name'):
        parts.append(snap['organization_name'])
    if snap.get('role'):
        parts.append(snap['role'].replace('_', ' '))
    return ', '.join(p for p in parts if p)


def _performer(entry) -> str:
    ed = entry.extra_data or {}
    if ed.get('performer_name'):
        return ed['performer_name']
    return entry.performer.name if entry.performer is not None else str(entry.performed_by or '')


def _recipient(entry) -> str:
    ed = entry.extra_data or {}
    if entry.external_party_id and isinstance(ed.get('party'), dict):
        return _party_label(ed['party'])
    if isinstance(ed.get('recipient'), dict):
        return ed['recipient'].get('name') or ''
    if entry.recipient is not None:
        return entry.recipient.name
    return ''


def link_status_by_id(verification) -> dict:
    """{entry_id: 'reason[,reason]'} for every entry the verifier flagged."""
    out = {}
    for b in verification.get('breaks', []):
        if b.get('id'):
            out.setdefault(str(b['id']), []).append(b['reason'])
    return {k: ','.join(sorted(set(v))) for k, v in out.items()}


def acknowledgments(entries) -> dict:
    """{acknowledged entry id: acknowledge entry} for ``acknowledge`` rows."""
    acks = {}
    for e in entries:
        if e.action == 'acknowledge':
            target = (e.extra_data or {}).get('acknowledges')
            if target:
                acks[str(target)] = e
    return acks


def entry_rows(entries, verification) -> list:
    """Plain dict rows (templates, CSV, JSON) for ledger entries."""
    statuses = verification.get('signature_status_by_id', {})
    links = link_status_by_id(verification)
    acks = acknowledgments(entries)
    rows = []
    for e in entries:
        ed = e.extra_data or {}
        eid = str(e.id)
        sig = statuses.get(eid)
        ack = acks.get(eid)
        rows.append({
            'id': eid,
            'seq': e.seq,
            'incident_seq': e.incident_seq,
            'chain_version': e.chain_version,
            'evidence_number': ed.get('evidence_number') or '',
            'created_at': _iso(e.created_at),
            'timestamp': _display_ts(e.created_at),
            'action': e.action,
            'performed_by': _performer(e),
            'recipient': _recipient(e),
            'transfer_method': e.transfer_method or '',
            'purpose': e.purpose or '',
            'verification_result': e.verification_result or '',
            'ip_address': str(e.ip_address) if e.ip_address else '',
            'signature_status': sig,
            'signature_label': SIGNATURE_LABELS.get(sig, sig or ''),
            'link_status': links.get(eid) or ('legacy' if not e.is_chained else 'ok'),
            'entry_hash': e.entry_hash or '',
            'acknowledged_by_entry_id': str(ack.id) if ack is not None else None,
            'acknowledged_by': (ack.extra_data or {}).get('typed_name') if ack is not None else None,
            'state_after': ed.get('state_after'),
        })
    return rows


def _form_rows(entries, rows_by_id) -> list:
    """Custody-table rows of the printable form (one per check_out/transfer/
    check_in/dispose): released by, received by, purpose, method, location."""
    out = []
    for e in entries:
        if e.action not in FORM_ACTIONS:
            continue
        ed = e.extra_data or {}
        row = rows_by_id[str(e.id)]
        state = ed.get('state_after') or {}
        location = state.get('storage_location') or ''
        if e.action in ('check_out', 'transfer'):
            released, received = row['performed_by'], row['recipient']
            method = e.transfer_method or ''
            if ed.get('tracking_number'):
                method = f"{method} (tracking {ed['tracking_number']})".strip()
            location = ''
        elif e.action == 'check_in':
            frm = ed.get('received_from') or {}
            released = frm.get('name') or ''
            if e.external_party_id and isinstance(ed.get('party'), dict):
                released = _party_label(ed['party'])
            received = row['performed_by']
            seal = 'seal intact' if ed.get('seal_intact') else 'SEAL NOT INTACT'
            method = seal + (f", new seal {ed['seal_number']}" if ed.get('seal_number') else '')
        else:  # dispose
            released = row['performed_by']
            received = (ed.get('method') or '').replace('_', ' ')
            method = f"witness: {ed['witness_name']}" if ed.get('witness_name') else ''
            location = ''
        out.append({
            'timestamp': row['timestamp'],
            'action': e.action.replace('_', ' '),
            'released_by': released,
            'received_by': received,
            'purpose': e.purpose or '',
            'method': method,
            'location': location,
            'acknowledged_by': row['acknowledged_by'] or '',
        })
    return out


def _verification_history(entries, rows_by_id) -> list:
    out = []
    for e in entries:
        if e.action != 'verify':
            continue
        ed = e.extra_data or {}
        out.append({
            'timestamp': rows_by_id[str(e.id)]['timestamp'],
            'performed_by': rows_by_id[str(e.id)]['performed_by'],
            'algorithm': ed.get('algorithm') or '',
            'result': e.verification_result or '',
            'method': ed.get('method') or '',
            'tool': ed.get('tool') or '',
        })
    return out


def item_view(item) -> dict:
    """Header fields of an item for documents."""
    return {
        'id': str(item.id),
        'evidence_number': item.evidence_number,
        'display_id': item.display_id,
        'evidence_type': item.evidence_type,
        'title': item.title,
        'description': item.description or '',
        'make': item.make or '',
        'model': item.model or '',
        'serial_number': item.serial_number or '',
        'media_type': item.media_type or '',
        'capacity_bytes': item.capacity_bytes,
        'seal_number': item.seal_number or '',
        'bag_number': item.bag_number or '',
        'storage_location': item.storage_location or '',
        'condition_notes': item.condition_notes or '',
        'acquired_at': _display_ts(item.acquired_at),
        'acquired_by': (item.acquired_by.name if item.acquired_by is not None else '') or item.acquired_by_name or '',
        'acquired_from': item.acquired_from or '',
        'acquisition_method': item.acquisition_method or '',
        'acquisition_tool': ' '.join(p for p in (item.acquisition_tool, item.acquisition_tool_version) if p),
        'source_host': item.source_host_label or '',
        'parent': item.parent.evidence_number if item.parent is not None else '',
        'custody_state': item.custody_state,
        'holder': holder_label(item),
        'under_legal_hold': item.under_legal_hold,
        'voided': item.is_voided,
        'void_reason': item.void_reason or '',
        'last_verification': item.last_verification_result or '',
        'hashes': [{'algorithm': h.get('algorithm'), 'value': h.get('value'), 'source': h.get('source'),
                    'recorded_at': _display_ts(h.get('recorded_at')), 'superseded': bool(h.get('superseded'))}
                   for h in (item.acquisition_hashes or []) if isinstance(h, dict)],
        'weak_hashes_only': item.weak_hashes_only,
    }


def incident_view(incident) -> dict:
    return {'id': str(incident.id), 'incident_number': incident.incident_number, 'title': incident.title,
            'tlp': incident.tlp, 'case': f'CASE-{incident.incident_number}' if incident.incident_number else ''}


def _chain_view(verification, chain_key):
    chain = verification.get(chain_key) or {}
    status = verification.get('status')
    return {
        'status': status,
        'status_label': STATUS_LABELS.get(status, (status or '').upper()),
        'head_seq': chain.get('head_seq'),
        'head_hash': chain.get('head_hash'),
        'length': chain.get('length'),
        'genesis': chain.get('genesis'),
        'breaks': verification.get('breaks', []),
        'notes': verification.get('notes', []),
        'signatures': verification.get('signatures', {}),
    }


def _common(generated_by):
    return {
        'generated_at': _display_ts(now_utc()),
        'generated_by': getattr(generated_by, 'name', None) or '',
        'signing_key_id': custody_key_id(custody_signing_key()),
    }


# ── Item custody exports ────────────────────────────────────────────────────

def annotated_entries(entries, verification) -> list:
    """``entry.to_dict()`` + signature_status, link_status and
    acknowledged_by_entry_id (API list and JSON export)."""
    rows = {r['id']: r for r in entry_rows(entries, verification)}
    out = []
    for e in entries:
        d = e.to_dict()
        r = rows[str(e.id)]
        d['signature_status'] = r['signature_status']
        d['link_status'] = r['link_status']
        d['acknowledged_by_entry_id'] = r['acknowledged_by_entry_id']
        out.append(d)
    return out


def item_report(incident, item, entries, verification, generated_by) -> dict:
    """JSON custody report of one item."""
    summary = {k: v for k, v in verification.items() if k != 'signature_status_by_id'}
    return {
        'schema_version': MANIFEST_SCHEMA_VERSION,
        'generated_at': _iso(now_utc()),
        'generated_by': {'id': str(generated_by.id), 'name': generated_by.name} if generated_by else None,
        'incident': incident_view(incident),
        'item': item.to_dict(),
        'entries': annotated_entries(entries, verification),
        'verification': summary,
        'signing_key_id': custody_key_id(custody_signing_key()),
    }


def entries_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(ENTRY_CSV_COLUMNS)
    for r in rows:
        w.writerow([csv_safe(v) for v in (
            r['seq'], r['incident_seq'], r['evidence_number'], r['created_at'], r['action'], r['performed_by'],
            r['recipient'], r['transfer_method'], r['purpose'], r['verification_result'], r['ip_address'],
            r['signature_status'], r['link_status'], r['entry_hash'],
        )])
    return buf.getvalue()


def item_context(incident, item, entries, verification, generated_by, blank_rows=0) -> dict:
    rows = entry_rows(entries, verification)
    by_id = {r['id']: r for r in rows}
    return {
        **_common(generated_by),
        'incident': incident_view(incident),
        'item': item_view(item),
        'entries': rows,
        'custody_rows': _form_rows(entries, by_id),
        'verifications': _verification_history(entries, by_id),
        'chain': _chain_view(verification, 'item_chain'),
        'blank_rows': list(range(blank_rows)),
    }


def item_pdf(context) -> bytes:
    return render_pdf('custody/item_report.html', **context)


def item_form_pdf(context) -> bytes:
    return render_pdf('custody/item_form.html', **context)


# ── Register exports ────────────────────────────────────────────────────────

def item_chain_statuses(verification, entries) -> dict:
    """{item_id: overall status} from one incident-wide verification."""
    statuses = verification.get('signature_status_by_id', {})
    sigs = {}
    for e in entries:
        st = statuses.get(str(e.id))
        if st is None:
            continue
        bucket = sigs.setdefault(str(e.evidence_item_id), {})
        bucket[st] = bucket.get(st, 0) + 1
    out = {}
    for iid, res in (verification.get('items') or {}).items():
        out[iid] = vc.overall_status(res.get('breaks', []), sigs.get(iid, {}))
    return out


def register_rows(items, chain_status) -> list:
    rows = []
    for it in items:
        rows.append({
            'id': str(it.id),
            'evidence_number': it.evidence_number,
            'type': it.evidence_type,
            'title': it.title,
            'serial_number': it.serial_number or '',
            'seal_number': it.seal_number or '',
            'custody_state': it.custody_state,
            'holder': holder_label(it),
            'storage_location': it.storage_location or '',
            'primary_hash': primary_hash(it),
            'acquired_at': _iso(it.acquired_at) or '',
            'acquired_at_display': _display_ts(it.acquired_at),
            'acquired_by': (it.acquired_by.name if it.acquired_by is not None else '') or it.acquired_by_name or '',
            'legal_hold': 'yes' if it.under_legal_hold else 'no',
            'last_verification': it.last_verification_result or '',
            'chain_status': chain_status.get(str(it.id), ''),
            'voided': 'yes' if it.is_voided else 'no',
        })
    return rows


def register_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(REGISTER_CSV_COLUMNS)
    for r in rows:
        w.writerow([csv_safe(r[c]) for c in REGISTER_CSV_COLUMNS])
    return buf.getvalue()


def register_context(incident, rows, verification, generated_by, entries=None) -> dict:
    return {
        **_common(generated_by),
        'incident': incident_view(incident),
        'rows': rows,
        'chain': _chain_view(verification, 'incident_chain'),
        'entries': entry_rows(entries, verification) if entries is not None else None,
    }


def register_pdf(context) -> bytes:
    return render_pdf('custody/register.html', **context)


# ── Bundles ─────────────────────────────────────────────────────────────────

def manifest_entry(entry) -> dict:
    """One ledger entry as the offline verifier reads it."""
    if entry.is_chained:
        data = vc.entry_payload_v3(entry)
        data.update({'entry_hash': entry.entry_hash, 'signature': entry.signature,
                     'signature_key_id': entry.signature_key_id, 'chain_version': entry.chain_version})
        return data
    return {
        'id': str(entry.id),
        'evidence_item_id': str(entry.evidence_item_id),
        'incident_id': str(entry.incident_id),
        'artifact_id': str(entry.artifact_id) if entry.artifact_id else None,
        'action': entry.action,
        'performed_by': str(entry.performed_by) if entry.performed_by else None,
        'signature': entry.signature,
        'signature_key_id': entry.signature_key_id,
        'created_at': vc.canon_ts(entry.created_at),
        'chain_version': None,
    }


def anchor_dict(anchor) -> dict:
    data = anchor.to_dict()
    data['token_der'] = base64.b64encode(anchor.token_der).decode('ascii') if anchor.token_der else None
    return data


def build_manifest(*, scope, incident, items, entries, heads, anchors, verification, generated_by) -> dict:
    """``scope`` = 'item' (one item chain; incident chain not included) or
    'incident' (every item chain + the incident chain)."""
    return {
        'schema_version': MANIFEST_SCHEMA_VERSION,
        'format': 'sheetstorm-custody-manifest',
        'scope': scope,
        'domain': vc.DOMAIN,
        'generated_at': _iso(now_utc()),
        'generated_by': {'id': str(generated_by.id), 'name': generated_by.name} if generated_by else None,
        'incident_id': str(incident.id),
        'incident': incident_view(incident),
        'items': [it.to_dict() for it in items],
        'entries': [manifest_entry(e) for e in entries],
        'heads': heads,
        'anchors': [anchor_dict(a) for a in anchors],
        'signing_key_id': custody_key_id(custody_signing_key()),
        'server_verification': {'status': verification.get('status'), 'breaks': verification.get('breaks', []),
                                'signatures': verification.get('signatures', {}),
                                'notes': verification.get('notes', [])},
    }


_ANCHOR_README = (
    "\nExternal anchors (RFC 3161 timestamps)\n"
    "  Anchors of type rfc3161 carry a base64 TimeStampToken (token_der) that a timestamp authority\n"
    "  issued for the 32-byte incident head hash (head_hash). SheetStorm checks the token's structure,\n"
    "  digest and nonce when it is received but does NOT verify the authority's signature; do that here\n"
    "  with OpenSSL 1.1.1+ and the authority's CA certificate (get it from the operator):\n"
    "  First extract the tokens (this block is one shell command, deliberately not indented):\n"
    "python3 - <<'EOF'\n"
    "import base64, json\n"
    "for a in json.load(open('manifest.json'))['anchors']:\n"
    "    if a['anchor_type'] == 'rfc3161' and a.get('token_der'):\n"
    "        open('anchor_%s.tst' % a['id'], 'wb').write(base64.b64decode(a['token_der']))\n"
    "        print(a['id'], a['head_hash'])\n"
    "EOF\n"
    "  Then, per anchor:\n"
    "    openssl ts -verify -in anchor_<id>.tst -token_in -digest <head_hash> -CAfile tsa-ca.pem\n"
    "  Add -untrusted intermediates.pem if the chain needs it. \"Verification: OK\" proves the authority\n"
    "  signed that head hash at the time shown by: openssl ts -reply -in anchor_<id>.tst -token_in -text\n"
    "  Anchors of type export_manifest only record that the head was handed out in an export.\n"
)


def readme_text(scope, incident, item=None) -> str:
    what = f'evidence item {item.display_id}' if item is not None else (
        f"the evidence register of {incident_view(incident)['case'] or incident.id}")
    incident_line = ('The manifest covers one item chain; the incident chain is not included.'
                     if scope == 'item' else
                     'The manifest covers every item chain and the incident-wide chain.')
    return (
        f"SheetStorm chain-of-custody bundle for {what}\n"
        f"Generated {_display_ts(now_utc())}\n\n"
        "Contents\n"
        "  manifest.json         every ledger entry (full hashed payload, entry_hash, HMAC signature,\n"
        "                        signing key id), the chain heads and any anchors\n"
        "  entries.csv           the same entries as a spreadsheet\n"
        "  chain_of_custody.pdf  human-readable report\n"
        "  verify_custody.py     offline verifier (Python 3 standard library only)\n"
        "  hash_chain.py         hash-chain primitives used by the verifier\n"
        "  SHA256SUMS            SHA-256 of every other file in this bundle\n\n"
        "Verify offline (no SheetStorm installation or network needed)\n"
        "  sha256sum -c SHA256SUMS\n"
        "  python3 verify_custody.py manifest.json\n"
        "  python3 verify_custody.py manifest.json --hmac-key-file KEY   # with the custodian's signing key\n\n"
        "Exit status: 0 intact, 1 broken or tampered, 2 malformed input.\n"
        f"{incident_line}\n"
        "Without the signing key the verifier recomputes every entry hash and every chain link\n"
        "(anyone can check this); the key additionally checks the HMAC signatures.\n"
        "Entries recorded before the hash-chained ledger (chain_version null) cannot be checked\n"
        "individually; they are sealed by the first chained entry.\n\n"
        "Privacy: the manifest contains staff IP addresses and user agents, because they are part\n"
        "of each entry's hashed payload.\n"
        f"{_ANCHOR_README if scope == 'incident' else ''}"
    )


def verifier_sources() -> dict:
    """The shipped verifier files, byte-identical to ``app/utils``."""
    out = {}
    for name in VERIFIER_FILES:
        with open(os.path.join(_UTILS_DIR, name), 'rb') as fh:
            out[name] = fh.read()
    return out


def build_bundle(files: dict):
    """ZIP ``files`` ({fixed name: bytes|str}) plus ``SHA256SUMS`` into a
    spooled temporary file positioned at 0."""
    blobs = {name: (data.encode('utf-8') if isinstance(data, str) else data) for name, data in files.items()}
    sums = ''.join(f'{hashlib.sha256(blobs[n]).hexdigest()}  {n}\n' for n in sorted(blobs))
    blobs['SHA256SUMS'] = sums.encode('ascii')
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES)
    with zipfile.ZipFile(spool, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        stamp = now_utc().timetuple()[:6]
        for name in sorted(blobs):
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, blobs[name])
    spool.seek(0)
    return spool


def manifest_json(manifest) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, default=str)
