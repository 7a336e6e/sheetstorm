"""Audit log governance: query filters, export, chain verification, retention
purge and the per-org audit settings.

Shared entry points:

* :func:`build_audit_query` (list, export, stats, facets and the
  user-lifecycle "user activity" endpoint all use it; never re-implement it)
* :func:`export_chunks` (CSV / JSONL generator, formula-injection safe)
* :func:`verify_chain` (keyed hash-chain verification, stores the result on
  the chain head)
* :func:`purge_org` (retention purge; CLI only)
* :func:`get_audit_settings` / :func:`register_held_incidents_source`
"""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

from flask import current_app
from sqlalchemy import and_, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import CIDR

from app import db
from app.models import AuditLog
from app.services import ledger
from app.utils.csv_safe import csv_safe
from app.utils.hash_chain import canonical_json, verify_linear_chain
from app.utils.pagination import ListArgsError, escape_like
from app.utils.validation import parse_datetime

logger = logging.getLogger(__name__)

# Deep-offset cap for list paging (use date filters to go further back).
MAX_PAGE_DEPTH = 100_000
MAX_RETENTION_DAYS = 36_500
LEGAL_HOLD_REASON_MAX = 500
VERIFY_BATCH = 2000

# Org settings keys owned by /admin/audit-settings (never writable through
# PUT /organization: OrgSettings is extra='forbid').
AUDIT_SETTINGS_KEYS = ('audit_retention_days', 'legal_hold', 'legal_hold_reason',
                       'legal_hold_set_by', 'legal_hold_set_at')

# Public sort names -> columns (client input never names a column).
SORTABLE = {
    'created_at': AuditLog.created_at,
    'event_type': AuditLog.event_type,
    'action': AuditLog.action,
    'user_email': AuditLog.user_email,
    'status_code': AuditLog.status_code,
    'resource_type': AuditLog.resource_type,
    'chain_seq': AuditLog.chain_seq,
}
DEFAULT_SORT = '-created_at'
SEARCH_COLUMNS = (AuditLog.action, AuditLog.user_email, AuditLog.resource_type, AuditLog.request_path)

STATUS_CLASSES = {
    'success': lambda c: c < 400,
    'client_error': lambda c: and_(c >= 400, c < 500),
    'server_error': lambda c: c >= 500,
    'denied': lambda c: c.in_((401, 403)),
}

# The filter params build_audit_query understands (export echoes these).
FILTER_PARAMS = ('user_id', 'user_email', 'start_date', 'end_date', 'event_type', 'action',
                 'action_contains', 'resource_type', 'resource_id', 'incident_id', 'status',
                 'status_code', 'ip', 'has_changes', 'q', 'search')


class AuditFilterError(ListArgsError):
    """400 ``invalid_filter`` for a bad audit filter value."""

    def __init__(self, message: str):
        super().__init__(message, 'invalid_filter')


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def _uuid(name, raw):
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, AttributeError):
        raise AuditFilterError(f'{name} must be a UUID')


def _get(args, name):
    value = args.get(name) if args is not None else None
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def build_audit_query(org_id, args: Optional[Mapping] = None):
    """``AuditLog`` query for one organization with the filters in ``args``.

    ``args``: a Mapping (``request.args`` or a dict). Unknown keys are
    ignored. Raises :class:`AuditFilterError` (400) on a bad value. The base
    filter is always ``organization_id == org_id``.
    """
    if org_id is None:
        raise ValueError('build_audit_query needs an organization id')
    args = args or {}
    query = AuditLog.query.filter(AuditLog.organization_id == _uuid('organization_id', org_id))

    value = _get(args, 'user_id')
    if value:
        query = query.filter(AuditLog.user_id == _uuid('user_id', value))

    value = _get(args, 'user_email')
    if value:
        if len(value) > 255:
            raise AuditFilterError('user_email is too long')
        query = query.filter(func.lower(AuditLog.user_email) == value.lower())

    start = end = None
    value = _get(args, 'start_date')
    if value:
        start = parse_datetime(value, 'start_date')
        query = query.filter(AuditLog.created_at >= start)
    value = _get(args, 'end_date')
    if value:
        end = parse_datetime(value, 'end_date')
        query = query.filter(AuditLog.created_at <= end)
    if start and end and start > end:
        raise AuditFilterError('start_date must not be after end_date')

    value = _get(args, 'event_type')
    if value:
        types = [t.strip() for t in value.split(',') if t.strip()]
        bad = [t for t in types if t not in AuditLog.EVENT_TYPES]
        if not types or bad:
            raise AuditFilterError(
                f"invalid event_type {bad[0] if bad else value!r}; allowed: {', '.join(AuditLog.EVENT_TYPES)}")
        query = query.filter(AuditLog.event_type.in_(types))

    value = _get(args, 'action')
    if value:
        if len(value) > 100:
            raise AuditFilterError('action is too long')
        query = query.filter(AuditLog.action == value)
    value = _get(args, 'action_contains')
    if value:
        if len(value) > 100:
            raise AuditFilterError('action_contains is too long')
        query = query.filter(AuditLog.action.ilike(f'%{escape_like(value)}%', escape='\\'))

    value = _get(args, 'resource_type')
    if value:
        if len(value) > 100:
            raise AuditFilterError('resource_type is too long')
        query = query.filter(AuditLog.resource_type == value)
    value = _get(args, 'resource_id')
    if value:
        query = query.filter(AuditLog.resource_id == _uuid('resource_id', value))
    value = _get(args, 'incident_id')
    if value:
        query = query.filter(AuditLog.incident_id == _uuid('incident_id', value))

    value = _get(args, 'status')
    if value:
        if value in STATUS_CLASSES:
            query = query.filter(STATUS_CLASSES[value](AuditLog.status_code))
        elif value.isdigit() and 100 <= int(value) <= 599:
            query = query.filter(AuditLog.status_code == int(value))
        else:
            raise AuditFilterError(
                f"invalid status {value!r}; use {', '.join(STATUS_CLASSES)} or an HTTP status code")
    value = _get(args, 'status_code')
    if value:
        if not value.isdigit() or not 100 <= int(value) <= 599:
            raise AuditFilterError('status_code must be an HTTP status code')
        query = query.filter(AuditLog.status_code == int(value))

    value = _get(args, 'ip')
    if value:
        try:
            net = ipaddress.ip_network(value, strict=False)
        except ValueError:
            raise AuditFilterError('ip must be an IP address or CIDR')
        query = query.filter(AuditLog.ip_address.op('<<=')(cast(str(net), CIDR)))

    value = _get(args, 'has_changes')
    if value:
        flag = value.lower()
        if flag in ('true', '1', 'yes'):
            query = query.filter(AuditLog.details.has_key('changes'))  # noqa: W601 (JSONB ?)
        elif flag not in ('false', '0', 'no'):
            raise AuditFilterError('has_changes must be true or false')

    value = _get(args, 'q') or _get(args, 'search')
    if value:
        if len(value) > 200:
            raise AuditFilterError('q must be at most 200 characters')
        pattern = f'%{escape_like(value)}%'
        query = query.filter(or_(*(c.ilike(pattern, escape='\\') for c in SEARCH_COLUMNS)))

    return query


def filters_echo(args: Mapping) -> dict:
    """The filter params present in ``args`` (recorded with an export)."""
    return {k: str(args.get(k))[:200] for k in FILTER_PARAMS if args.get(k) not in (None, '')}


def check_page_depth(page: int, per_page: int) -> None:
    if page * per_page > MAX_PAGE_DEPTH:
        raise AuditFilterError(
            f'page too deep (page * per_page must be <= {MAX_PAGE_DEPTH}); narrow the date range instead')


def count_capped(query, cap: int) -> int:
    """``min(count, cap + 1)`` without counting the whole table."""
    sub = query.order_by(None).with_entities(AuditLog.id).limit(cap + 1).subquery()
    return db.session.execute(select(func.count()).select_from(sub)).scalar() or 0


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _cell(row, column):
    value = getattr(row, column)
    if column == 'details':
        return value if value is not None else {}
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def export_record(row) -> dict:
    return {c: _cell(row, c) for c in AuditLog.CSV_COLUMNS}


def export_chunks(query, fmt: str, *, chunk_rows: int = 500):
    """Yield the export body for ``query`` (already ordered / limited).

    CSV: every cell goes through ``csv_safe`` (formula injection); details are
    canonical JSON. JSONL: one JSON object per line, unescaped (not a
    spreadsheet format).
    """
    if fmt not in ('csv', 'jsonl'):
        raise ValueError(f'unsupported export format {fmt!r}')
    buf = io.StringIO()
    writer = csv.writer(buf) if fmt == 'csv' else None
    if writer:
        writer.writerow(AuditLog.CSV_COLUMNS)
    pending = 0
    for row in query.yield_per(1000):
        record = export_record(row)
        if writer:
            record['details'] = canonical_json(record['details'], strict=False).decode('utf-8')
            writer.writerow([csv_safe(record[c]) for c in AuditLog.CSV_COLUMNS])
        else:
            buf.write(json.dumps(record, ensure_ascii=False, default=str, sort_keys=False) + '\n')
        pending += 1
        if pending >= chunk_rows:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
            pending = 0
    tail = buf.getvalue()
    if tail:
        yield tail


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_audit_settings(org) -> dict:
    stored = (org.settings or {}) if org is not None else {}
    retention = stored.get('audit_retention_days')
    return {
        'audit_retention_days': retention if isinstance(retention, int) and not isinstance(retention, bool) else None,
        'legal_hold': stored.get('legal_hold') is True,
        'legal_hold_reason': stored.get('legal_hold_reason'),
        'legal_hold_set_by': stored.get('legal_hold_set_by'),
        'legal_hold_set_at': stored.get('legal_hold_set_at'),
        'min_retention_days': current_app.config.get('AUDIT_RETENTION_MIN_DAYS', 365),
        'max_retention_days': MAX_RETENTION_DAYS,
    }


def retention_cutoff(retention_days: int, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    floor = int(current_app.config.get('AUDIT_RETENTION_MIN_DAYS', 365))
    return now - timedelta(days=max(int(retention_days), floor))


# ---------------------------------------------------------------------------
# Legal holds (incidents whose audit rows the purge must keep)
# ---------------------------------------------------------------------------

_HELD_SOURCES: list[Callable] = []


def register_held_incidents_source(fn: Callable) -> Callable:
    """Register ``fn(org_id, now) -> selectable of incident ids`` under hold
    (e.g. the evidence register adds held evidence items)."""
    if fn not in _HELD_SOURCES:
        _HELD_SOURCES.append(fn)
    return fn


def _artifact_holds(org_id, now):
    from app.models import Artifact, Incident
    return (select(Artifact.incident_id)
            .join(Incident, Incident.id == Artifact.incident_id)
            .where(Incident.organization_id == org_id,
                   or_(Artifact.is_locked.is_(True), Artifact.legal_hold_until > now)))


register_held_incidents_source(_artifact_holds)


def held_incident_ids(org_id, now=None) -> set:
    now = now or datetime.now(timezone.utc)
    held = set()
    for source in _HELD_SOURCES:
        held.update(i for i in db.session.execute(source(org_id, now)).scalars() if i is not None)
    return held


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------

_REASONS = {
    'entry_hash_mismatch': 'hash_mismatch',
    'prev_hash_mismatch': 'prev_hash_mismatch',
    'seq_gap': 'gap',
    'seq_duplicate': 'duplicate',
}


def _chain_filter(org_id):
    if org_id is None:
        return AuditLog.organization_id.is_(None)
    return AuditLog.organization_id == org_id


def verify_chain(org_id, *, max_failures: int = 50, store: bool = True) -> dict:
    """Verify one organization's audit chain (``org_id=None``: the global chain).

    Checks, from the head snapshot taken at the start: the first row is
    ``purged_through_seq + 1`` and links to ``anchor_hash`` (or the genesis
    hash); sequence numbers have no gaps; each ``prev_hash`` equals the
    previous ``row_hash``; each keyed ``row_hash`` recomputes; and the last
    row matches the head (tail truncation). Rows signed with a key that is
    neither ``AUDIT_CHAIN_KEY`` nor in ``AUDIT_CHAIN_PREVIOUS_KEYS`` are
    counted as ``unverifiable_rotated_key`` (not failures).

    Returns a summary; ``store`` saves it on the chain head.
    """
    chain_key = ledger.audit_chain_key(org_id)
    head = ledger.get_head(chain_key)
    head_seq = int(head.last_seq) if head else 0
    head_hash = head.last_hash if head else None
    purged = int(head.purged_through_seq) if head else 0
    anchor = (head.anchor_hash if head else None) or ledger.audit_genesis(org_id)

    keys = ledger.known_keys()
    current_row = {}

    def payload_fn(row):
        current_row['row'] = row
        return row.chain_payload()

    def hash_fn(domain, prev, payload):
        key = keys.get(current_row['row'].chain_key_id)
        if key is None:
            raise ValueError('unknown chain key')
        return ledger.keyed_link_hash(key)(domain, prev, payload)

    failures = []
    failure_count = 0
    rotated = 0
    checked = 0
    expected_prev, expected_seq = anchor, purged + 1
    last_seq = last_hash = first_seq = None

    def run(batch):
        nonlocal failure_count, rotated, expected_prev, expected_seq, last_seq, last_hash
        unknown = {r.chain_seq for r in batch if r.chain_key_id not in keys}
        found = verify_linear_chain(batch, ledger.AUDIT_DOMAIN, expected_prev, 'prev_hash', payload_fn,
                                    hash_attr='row_hash', seq_attr='chain_seq', id_attr='id',
                                    ts_attr='_no_timestamp_check', hash_fn=hash_fn,
                                    start_seq=expected_seq)
        for f in found:
            if f['reason'] == 'entry_hash_mismatch' and f['seq'] in unknown:
                rotated += 1
                continue
            failure_count += 1
            if len(failures) < max_failures:
                failures.append({'seq': f['seq'], 'id': f['id'], 'reason': _REASONS.get(f['reason'], f['reason'])})
        tail = batch[-1]
        last_seq, last_hash = tail.chain_seq, tail.row_hash
        expected_prev = tail.row_hash if isinstance(tail.row_hash, str) else ''
        expected_seq = tail.chain_seq + 1 if tail.chain_seq is not None else expected_seq

    rows = (AuditLog.query
            .filter(_chain_filter(org_id), AuditLog.chain_seq.isnot(None), AuditLog.chain_seq <= head_seq)
            .order_by(AuditLog.chain_seq.asc(), AuditLog.id.asc())
            .yield_per(VERIFY_BATCH))
    batch = []
    for row in rows:
        if first_seq is None:
            first_seq = row.chain_seq
        batch.append(row)
        checked += 1
        if len(batch) >= VERIFY_BATCH:
            run(batch)
            batch = []
    if batch:
        run(batch)

    # Tail truncation / head mismatch.
    if head_seq > purged and (last_seq != head_seq or last_hash != head_hash):
        failure_count += 1
        if len(failures) < max_failures:
            failures.append({'seq': head_seq, 'id': None, 'reason': 'head_mismatch'})

    legacy = (db.session.query(func.count(AuditLog.id))
              .filter(_chain_filter(org_id), AuditLog.chain_seq.is_(None)).scalar() or 0)

    now = datetime.now(timezone.utc)
    summary = {
        'ok': failure_count == 0,
        'organization_id': str(org_id) if org_id else None,
        'chain_key': chain_key,
        'checked': checked,
        'failure_count': failure_count,
        'failures': failures,
        'unverifiable_rotated_key': rotated,
        'legacy_unchained': legacy,
        'head_seq': head_seq,
        'head_hash': head_hash,
        'purged_through_seq': purged,
        'first_seq': first_seq,
        'last_seq': last_seq,
        'key_id': ledger.ledger_key()[1],
        'verified_at': now.isoformat(),
    }
    if store and head is not None:
        stored = {k: v for k, v in summary.items() if k != 'failures'}
        stored['failures'] = failures[:10]
        db.session.execute(text(
            'UPDATE ledger_heads SET last_verified_at = :t, last_verify_ok = :ok, '
            'last_verify_summary = CAST(:s AS jsonb) WHERE chain_key = :k'),
            {'t': now, 'ok': summary['ok'], 's': json.dumps(stored), 'k': chain_key})
        db.session.commit()
    return summary


def chain_status(org_id) -> dict:
    """Head + last verification of an org's chain (for status / headers)."""
    head = ledger.get_head(ledger.audit_chain_key(org_id))
    return {
        'head_seq': int(head.last_seq) if head else 0,
        'head_hash': head.last_hash if head else None,
        'purged_through_seq': int(head.purged_through_seq) if head else 0,
        'last_verified_at': head.last_verified_at.isoformat() if head and head.last_verified_at else None,
        'last_verify_ok': head.last_verify_ok if head else None,
    }


# ---------------------------------------------------------------------------
# Retention purge (CLI only: `flask sheetstorm purge-audit-logs`)
# ---------------------------------------------------------------------------

def _enable_purge_guc():
    db.session.execute(text("SELECT set_config('sheetstorm.audit_purge', 'on', true)"))


def purge_org(org, *, now: Optional[datetime] = None, dry_run: bool = False,
              batch_size: Optional[int] = None) -> dict:
    """Apply the org's retention to its audit rows.

    Skips (and audits the skip) when a legal hold is set; does nothing when
    retention is unset (keep forever). Otherwise deletes legacy (unchained)
    rows older than the cutoff and the contiguous chained prefix older than
    the cutoff, stopping at the first row that belongs to an incident under
    legal hold or is newer than the cutoff. Each batch is its own transaction
    that moves ``purged_through_seq`` / ``anchor_hash`` so the remaining chain
    still verifies. Returns a summary.
    """
    from app.middleware.audit import log_audit_event

    now = now or datetime.now(timezone.utc)
    batch_size = int(batch_size or current_app.config.get('AUDIT_PURGE_BATCH_SIZE', 10000))
    settings = get_audit_settings(org)
    summary = {'organization': org.slug, 'organization_id': str(org.id), 'dry_run': dry_run}

    if settings['legal_hold']:
        summary['status'] = 'skipped_legal_hold'
        if not dry_run:
            log_audit_event('system_event', 'audit_purge_skipped', resource_type='audit_log',
                            details={'reason': 'legal_hold'}, organization_id=org.id,
                            actor_label='system:purge')
        return summary
    if settings['audit_retention_days'] is None:
        summary['status'] = 'no_retention'
        return summary

    retention = settings['audit_retention_days']
    cutoff = retention_cutoff(retention, now)
    held = held_incident_ids(org.id, now)
    org_rows = AuditLog.organization_id == org.id
    legacy_conds = [org_rows, AuditLog.chain_seq.is_(None), AuditLog.created_at < cutoff]
    if held:
        legacy_conds.append(or_(AuditLog.incident_id.is_(None), AuditLog.incident_id.notin_(held)))

    chain_key = ledger.audit_chain_key(org.id)
    head = ledger.get_head(chain_key)
    purged_through = int(head.purged_through_seq) if head else 0
    head_seq = int(head.last_seq) if head else 0
    keep_clause = AuditLog.created_at >= cutoff
    if held:
        keep_clause = or_(keep_clause, AuditLog.incident_id.in_(held))
    first_kept = (db.session.query(func.min(AuditLog.chain_seq))
                  .filter(org_rows, AuditLog.chain_seq.isnot(None), AuditLog.chain_seq > purged_through,
                          keep_clause).scalar())
    stop = (int(first_kept) - 1) if first_kept is not None else head_seq

    summary.update({'status': 'ok', 'cutoff': cutoff.isoformat(), 'retention_days': retention,
                    'held_incidents': len(held)})
    if dry_run:
        summary['legacy_deleted'] = AuditLog.query.filter(*legacy_conds).count()
        summary['chained_deleted'] = (AuditLog.query.filter(
            org_rows, AuditLog.chain_seq > purged_through, AuditLog.chain_seq <= stop).count()
            if stop > purged_through else 0)
        summary['purged_through_seq'] = max(stop, purged_through)
        db.session.commit()
        return summary

    legacy_deleted = 0
    while True:
        ids = select(AuditLog.id).where(*legacy_conds).limit(batch_size).scalar_subquery()
        _enable_purge_guc()
        deleted = db.session.execute(AuditLog.__table__.delete().where(AuditLog.id.in_(ids))).rowcount
        db.session.commit()
        legacy_deleted += deleted or 0
        if not deleted:
            break

    chained_deleted = 0
    anchor_hash = head.anchor_hash if head else None
    lo = purged_through
    while lo < stop:
        hi = min(lo + batch_size, stop)
        _enable_purge_guc()
        locked = ledger.lock_head(chain_key)
        if locked is None or int(locked.purged_through_seq) != lo:
            db.session.rollback()
            raise RuntimeError(f'audit chain head for {org.slug} moved during purge')
        anchor_hash = db.session.query(AuditLog.row_hash).filter(
            org_rows, AuditLog.chain_seq == hi).scalar()
        if not anchor_hash:
            db.session.rollback()
            raise RuntimeError(f'audit chain row {hi} of {org.slug} is missing; run verify-audit-chain')
        deleted = db.session.execute(AuditLog.__table__.delete().where(
            AuditLog.organization_id == org.id, AuditLog.chain_seq > lo, AuditLog.chain_seq <= hi)).rowcount
        locked.purged_through_seq = hi
        locked.anchor_hash = anchor_hash
        locked.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        chained_deleted += deleted or 0
        lo = hi

    summary.update({'legacy_deleted': legacy_deleted, 'chained_deleted': chained_deleted,
                    'purged_through_seq': lo, 'anchor_hash': anchor_hash})
    if legacy_deleted or chained_deleted:
        log_audit_event('system_event', 'audit_purge', resource_type='audit_log',
                        details={k: summary[k] for k in ('cutoff', 'retention_days', 'legacy_deleted',
                                                         'chained_deleted', 'purged_through_seq',
                                                         'anchor_hash', 'held_incidents')},
                        organization_id=org.id, actor_label='system:purge')
    return summary


__all__ = [
    'AuditFilterError', 'SORTABLE', 'DEFAULT_SORT', 'MAX_PAGE_DEPTH', 'AUDIT_SETTINGS_KEYS',
    'build_audit_query', 'filters_echo', 'check_page_depth', 'count_capped', 'export_record',
    'export_chunks', 'get_audit_settings', 'retention_cutoff', 'register_held_incidents_source',
    'held_incident_ids', 'verify_chain', 'chain_status', 'purge_org',
]
