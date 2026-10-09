"""Record provenance + clock-skew normalization (decision-log-provenance §3.4).

* ``validate`` / ``apply`` - endpoint-facing: validate the provenance keys of a
  create/update body, link the source artifact / evidence item (same incident
  only), derive the normalized UTC timestamp from the raw one and snapshot the
  host clock skew used.
* ``normalize`` - ``raw_timestamp`` + ``source_timezone`` + skew -> UTC.
* ``verify`` / ``unverify`` - second-analyst verification.
* ``reapply_host_skew`` - explicit, audited re-normalization after a host's
  skew changed.

Normalization rules (the UTC value is *derived*, never guessed):

* A raw timestamp with an explicit offset (``Z``, ``+02:00``) is converted.
* A naive raw timestamp is localized with ``source_timezone`` (IANA key or
  ``UTC+HH:MM``), else the host's ``timezone``; with neither it is a 400.
* DST gaps (nonexistent local time) and folds (ambiguous local time) are 400s
  that list the candidates; ``fold`` (0 = first occurrence) disambiguates.
* Day/month-ambiguous formats (``03/04/2026``) are rejected; ISO 8601 is
  always unambiguous.
* ``utc = local_utc - host_clock_skew`` (skew = host clock minus true UTC).

URLs and other references are stored as text and never fetched.
"""
import re
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as _dtparser
from flask import jsonify
from sqlalchemy import and_

from app import db
from app.models import (CompromisedHost, HostBasedIndicator, MalwareTool, NetworkIndicator,
                        TimelineEvent)
from app.models.artifact import Artifact
from app.models.evidence import EvidenceItem
from app.models.provenance import (PROVENANCE_INPUT_FIELDS, PROVENANCE_LEVELS, SOURCE_RECORD_TYPES,
                                   TIMESTAMP_DERIVATIONS, TIMESTAMP_TYPES)
from app.utils.audit_diff import record_changes
from app.utils.pagination import enum

# Host clock skew bound: +-7 days.
SKEW_LIMIT_SECONDS = CompromisedHost.CLOCK_SKEW_LIMIT_SECONDS
# A computed value this close to the stored one counts as "the same".
MISMATCH_TOLERANCE = timedelta(seconds=1)
MAX_REAPPLY_RECORDS = 5000

FIELD_LIMITS = {
    'source_record_ref': 1000,
    'raw_timestamp': 100,
    'source_timezone': 64,
    'extraction_tool': 150,
    'extraction_tool_version': 50,
}
_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f]')  # includes tab / CR / LF
_TZ_NAME_RE = re.compile(r'^(UTC|[A-Za-z_]+(/[A-Za-z0-9_+\-]+)*)$')
_TZ_OFFSET_RE = re.compile(r'^UTC([+-])(\d{2}):(\d{2})$')
_YEAR_FIRST_RE = re.compile(r'^\s*\d{4}\D')

# kind -> (model, update permission, realtime entity)
RECORD_KINDS = {
    'timeline_event': (TimelineEvent, 'timeline:update', 'timeline_event'),
    'network_ioc': (NetworkIndicator, 'network_iocs:update', 'network_ioc'),
    'host_ioc': (HostBasedIndicator, 'host_iocs:update', 'host_ioc'),
    'malware': (MalwareTool, 'malware:update', 'malware'),
}
KIND_ALIASES = {'host_indicator': 'host_ioc', 'network_indicator': 'network_ioc'}
# Malware has several time columns; the raw timestamp's MACB type picks one.
MALWARE_TIME_ATTRS = {'modified': 'modification_time', 'accessed': 'access_time', 'born': 'creation_time'}
_ALL_TIME_ATTRS = ('timestamp', 'datetime', 'modification_time', 'access_time', 'creation_time')


class ProvenanceError(Exception):
    """A 400 (default) with a stable ``error`` code and optional extra keys."""

    def __init__(self, code, message, status=400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def to_dict(self):
        return {'error': self.code, 'message': self.message, **self.extra}

    def to_response(self):
        return jsonify(self.to_dict()), self.status


def resolve_kind(name):
    kind = KIND_ALIASES.get(name, name)
    if kind not in RECORD_KINDS:
        raise ProvenanceError('bad_request',
                              f"record_type must be one of: {', '.join(sorted(RECORD_KINDS))}")
    return kind


def kind_of(record):
    for kind, (model, _perm, _entity) in RECORD_KINDS.items():
        if isinstance(record, model):
            return kind
    raise TypeError(f'{type(record).__name__} has no provenance')


# --------------------------------------------------------------------------
# Time zones and normalization
# --------------------------------------------------------------------------

@lru_cache(maxsize=512)
def _zone(name):
    return ZoneInfo(name)


def parse_timezone(name):
    """``tzinfo`` for an IANA key (``Europe/Berlin``), ``UTC`` or a fixed
    ``UTC+HH:MM`` offset; ProvenanceError ``invalid_timezone`` otherwise."""
    if not isinstance(name, str):
        raise ProvenanceError('invalid_timezone', 'source_timezone must be a string')
    m = _TZ_OFFSET_RE.match(name)
    if m:
        hours, minutes = int(m.group(2)), int(m.group(3))
        if hours > 14 or minutes > 59:
            raise ProvenanceError('invalid_timezone', f'Invalid UTC offset: {name}')
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(delta if m.group(1) == '+' else -delta)
    if not _TZ_NAME_RE.match(name):
        raise ProvenanceError('invalid_timezone',
                              'source_timezone must be an IANA name (Europe/Berlin), UTC or UTC+HH:MM')
    if name == 'UTC':
        return timezone.utc
    try:
        return _zone(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ProvenanceError('invalid_timezone', f'Unknown time zone: {name}')


def _parse_raw(raw):
    """dateutil parse that refuses incomplete, ambiguous or unknown-zone input."""
    if not isinstance(raw, str) or not raw.strip():
        raise ProvenanceError('invalid_raw_timestamp', 'raw_timestamp must be a non-empty string')
    first, second = datetime(2000, 1, 1, 0, 0, 0), datetime(2001, 2, 2, 1, 1, 1)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', _dtparser.UnknownTimezoneWarning)
            a = _dtparser.parse(raw, default=first)
            b = _dtparser.parse(raw, default=second)
            # Parser defaults fill missing fields; a field that follows the
            # default was not in the string.
            if (a.year, a.month, a.day, a.hour, a.minute) != (b.year, b.month, b.day, b.hour, b.minute):
                raise ProvenanceError(
                    'incomplete_raw_timestamp',
                    'raw_timestamp needs a year, month, day, hour and minute (ISO 8601 is best)')
            if not _YEAR_FIRST_RE.match(raw):
                a_day = _dtparser.parse(raw, default=first, dayfirst=True)
                b_day = _dtparser.parse(raw, default=first, dayfirst=False)
                if (a_day.month, a_day.day) != (b_day.month, b_day.day):
                    raise ProvenanceError(
                        'ambiguous_date',
                        'raw_timestamp is day/month ambiguous; rewrite it as YYYY-MM-DD HH:MM:SS')
    except ProvenanceError:
        raise
    except _dtparser.UnknownTimezoneWarning:
        raise ProvenanceError(
            'unknown_timezone_abbreviation',
            'raw_timestamp contains a time zone abbreviation that cannot be resolved; '
            'use a numeric offset (+02:00) or set source_timezone')
    except (ValueError, OverflowError, TypeError):
        raise ProvenanceError('invalid_raw_timestamp', 'raw_timestamp is not a recognizable date/time')
    return a


@dataclass
class Normalized:
    utc: datetime
    skew_applied: int
    timezone_used: str
    offset_seconds: int

    def to_dict(self):
        return {'utc': self.utc.isoformat(), 'skew_applied': self.skew_applied,
                'timezone_used': self.timezone_used, 'offset_seconds': self.offset_seconds}


def normalize(raw_timestamp, source_timezone=None, skew_seconds=None, fold=None, default_timezone=None):
    """Raw timestamp string -> :class:`Normalized` (``.utc`` is aware UTC)."""
    parsed = _parse_raw(raw_timestamp)
    skew = int(skew_seconds or 0)
    if parsed.tzinfo is not None:
        local_utc = parsed.astimezone(timezone.utc)
        used, offset = 'offset in raw_timestamp', int(parsed.utcoffset().total_seconds())
    else:
        name = source_timezone or default_timezone
        if not name:
            raise ProvenanceError('source_timezone_required',
                                  'source_timezone is required for a raw_timestamp without an offset')
        tz = parse_timezone(name)
        local_utc, offset = _localize(parsed, tz, name, fold)
        used = name
    try:
        utc = local_utc - timedelta(seconds=skew)
    except OverflowError:
        raise ProvenanceError('invalid_raw_timestamp', 'raw_timestamp is out of range')
    return Normalized(utc=utc, skew_applied=skew, timezone_used=used, offset_seconds=offset)


def _localize(naive, tz, name, fold):
    """Naive wall-clock in ``tz`` -> (aware UTC datetime, offset seconds)."""
    first = naive.replace(tzinfo=tz, fold=0)
    # Nonexistent (DST gap): the round trip lands on a different wall time.
    try:
        round_trip = first.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    except (OverflowError, ValueError):
        raise ProvenanceError('invalid_raw_timestamp', 'raw_timestamp is out of range')
    if round_trip != naive:
        raise ProvenanceError(
            'nonexistent_local_time',
            f'{naive.isoformat(sep=" ")} does not exist in {name} (daylight-saving gap)')
    second = naive.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():  # DST fold: the wall time happens twice
        if fold not in (0, 1):
            raise ProvenanceError(
                'ambiguous_local_time',
                f'{naive.isoformat(sep=" ")} is ambiguous in {name} (daylight-saving fold); '
                'send fold=0 for the first occurrence or fold=1 for the second',
                candidates=[first.astimezone(timezone.utc).isoformat(),
                            second.astimezone(timezone.utc).isoformat()])
        chosen = second if fold == 1 else first
    else:
        chosen = first
    return chosen.astimezone(timezone.utc), int(chosen.utcoffset().total_seconds())


def validate_skew(value):
    """``int`` seconds within the bound, or ProvenanceError."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProvenanceError('invalid_clock_skew', 'clock_skew_seconds must be an integer')
    if abs(value) > SKEW_LIMIT_SECONDS:
        raise ProvenanceError('invalid_clock_skew',
                              f'clock_skew_seconds must be within +-{SKEW_LIMIT_SECONDS} (7 days)')
    return value


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _clean_text(data, key, limit):
    value = data[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProvenanceError('bad_request', f'{key} must be a string')
    value = value.strip()
    if not value:
        return None
    if len(value) > limit:
        raise ProvenanceError('bad_request', f'{key} must be at most {limit} characters')
    if _CONTROL_RE.search(value):
        raise ProvenanceError('bad_request', f'{key} must not contain control characters or line breaks')
    return value


def _clean_uuid(data, key):
    value = data[key]
    if value in (None, ''):
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ProvenanceError('bad_request', f'{key} must be a UUID')


def validate(data):
    """Validated copy of the provenance keys present in ``data``.

    Keys: PROVENANCE_INPUT_FIELDS, ``timestamp_derivation`` (``manual`` /
    ``imported`` assert the analyst's own value; ``computed`` is server-set
    and means "derive it") and ``fold`` (0|1). Absent keys stay absent; empty
    strings clear. Raises ProvenanceError.
    """
    out = {}
    for key, limit in FIELD_LIMITS.items():
        if key in data:
            out[key] = _clean_text(data, key, limit)
    for key in ('source_artifact_id', 'source_evidence_id'):
        if key in data:
            out[key] = _clean_uuid(data, key)
    for key, allowed in (('source_record_type', SOURCE_RECORD_TYPES),
                         ('timestamp_type', TIMESTAMP_TYPES)):
        if key in data:
            value = _clean_text(data, key, 30)
            if value is not None and value not in allowed:
                raise ProvenanceError('bad_request', f"Invalid {key}: {value!r}. Valid values: {list(allowed)}")
            out[key] = value
    if 'timestamp_derivation' in data:
        value = _clean_text(data, 'timestamp_derivation', 20)
        if value is not None and value not in TIMESTAMP_DERIVATIONS:
            raise ProvenanceError(
                'bad_request',
                f"Invalid timestamp_derivation: {value!r}. Valid values: {list(TIMESTAMP_DERIVATIONS)}")
        out['timestamp_derivation'] = value
    if out.get('source_timezone'):
        parse_timezone(out['source_timezone'])
    if 'fold' in data and data['fold'] is not None:
        if isinstance(data['fold'], bool) or data['fold'] not in (0, 1):
            raise ProvenanceError('bad_request', 'fold must be 0 or 1')
        out['fold'] = int(data['fold'])
    return out


def _check_links(record, cleaned):
    """Source artifact / evidence item must belong to the record's incident
    (and therefore its organization)."""
    if cleaned.get('source_artifact_id'):
        found = Artifact.query.filter_by(id=cleaned['source_artifact_id'],
                                         incident_id=record.incident_id).first()
        if not found:
            raise ProvenanceError('invalid_source_artifact', 'source_artifact_id is not an artifact of this incident')
    if cleaned.get('source_evidence_id'):
        found = EvidenceItem.query.filter_by(id=cleaned['source_evidence_id'],
                                             incident_id=record.incident_id).first()
        if not found:
            raise ProvenanceError('invalid_source_evidence',
                                  'source_evidence_id is not an evidence item of this incident')


# --------------------------------------------------------------------------
# List filters
# --------------------------------------------------------------------------

def list_filters(model):
    """Extra ``filters=`` for a list endpoint (utils/pagination.py kinds):
    ``provenance_level`` (none|partial|full|verified), ``source_artifact_id``,
    ``source_evidence_id`` and ``unverified=true`` (provenance recorded but not
    yet verified)."""
    level = model.provenance_level_expr()
    return {
        'provenance_level': (level, enum(PROVENANCE_LEVELS)),
        'source_artifact_id': (model.source_artifact_id, 'uuid'),
        'source_evidence_id': (model.source_evidence_id, 'uuid'),
        'unverified': (and_(model.provenance_verified_at.is_(None), level != 'none'), 'flag'),
    }


# --------------------------------------------------------------------------
# Apply (create / update)
# --------------------------------------------------------------------------

def timestamp_attr(record, timestamp_type=None):
    """Name of the record's normalized-time column, or None (a malware entry
    whose MACB type is not modified / accessed / born has none)."""
    if isinstance(record, (TimelineEvent, NetworkIndicator)):
        return 'timestamp'
    if isinstance(record, HostBasedIndicator):
        return 'datetime'
    if isinstance(record, MalwareTool):
        return MALWARE_TIME_ATTRS.get(timestamp_type or record.timestamp_type)
    raise TypeError(f'{type(record).__name__} has no provenance')


_TRACKED = PROVENANCE_INPUT_FIELDS + ('timestamp_derivation', 'clock_skew_applied_seconds',
                                      'provenance_verified_by', 'provenance_verified_at') + _ALL_TIME_ATTRS


def snapshot(record):
    """Provenance + time columns now (raw values); call **before** an update
    mutates the record so :func:`apply` can tell what changed."""
    return {f: getattr(record, f) for f in _TRACKED if hasattr(record, f)}


def host_for(record):
    """The record's linked host (same incident), or None."""
    if not record.host_id:
        return None
    return CompromisedHost.query.filter_by(id=record.host_id, incident_id=record.incident_id).first()


def apply(record, data, *, before=None, host=None, creating=False):
    """Apply the provenance keys of ``data`` to ``record`` (mutates only).

    ``before`` is :func:`snapshot` taken before the endpoint changed the
    record (omit on create). ``host`` is the record's host *after* the
    endpoint's own changes (:func:`host_for`). Call before commit; raises
    :class:`ProvenanceError` (the endpoint's error handler rolls back).
    """
    cleaned = validate(data)
    _check_links(record, cleaned)
    before = before or {}

    for key in PROVENANCE_INPUT_FIELDS:
        if key in cleaned:
            setattr(record, key, cleaned[key])

    explicit = cleaned.get('timestamp_derivation')
    if explicit == 'computed':
        explicit = None  # server-set: "derive it"
    attr = timestamp_attr(record)
    raw = record.raw_timestamp
    # Derivation re-runs only for a real change: clients that resend the whole
    # record (MCP, old forms) must not trip over a host skew edited since.
    touched = (creating or 'fold' in cleaned or explicit is not None
               or any(k in cleaned and cleaned[k] != before.get(k)
                      for k in ('raw_timestamp', 'source_timezone', 'timestamp_type')))
    current = getattr(record, attr) if attr else None
    ts_changed = bool(before) and bool(attr) and before.get(attr) != current

    if raw and attr and touched:
        skew = host.clock_skew_seconds if host is not None else None
        result = normalize(raw, record.source_timezone, skew, cleaned.get('fold'),
                           default_timezone=host.timezone if host is not None else None)
        if current is None:
            setattr(record, attr, result.utc)
            record.timestamp_derivation = 'computed'
            record.clock_skew_applied_seconds = skew
        elif abs(current - result.utc) <= MISMATCH_TOLERANCE:
            record.timestamp_derivation = explicit or 'computed'
            record.clock_skew_applied_seconds = skew if record.timestamp_derivation == 'computed' else None
        elif explicit:
            record.timestamp_derivation = explicit
            record.clock_skew_applied_seconds = None
        else:
            raise ProvenanceError(
                'timestamp_mismatch',
                'The timestamp does not match raw_timestamp + source_timezone + host clock skew. '
                'Use the computed value, or send timestamp_derivation="manual" to keep yours.',
                computed=result.to_dict())
    else:
        if explicit:
            record.timestamp_derivation = explicit
            if explicit != 'computed':
                record.clock_skew_applied_seconds = None
        elif ts_changed and record.timestamp_derivation == 'computed':
            # The analyst overrode a derived time: it is now a manual fact.
            record.timestamp_derivation = 'manual'
            record.clock_skew_applied_seconds = None

    after = snapshot(record)
    changed = {k for k in after if before and after.get(k) != before.get(k)} if before else set()
    cleared = False
    material = changed - {'provenance_verified_by', 'provenance_verified_at'}
    if record.provenance_verified_at is not None and material:
        record.provenance_verified_by = None
        record.provenance_verified_at = None
        cleared = True
        after = snapshot(record)
    if before and after != before:
        extra = {'provenance_verification_cleared': True} if cleared else {}
        diff_before = {k: v for k, v in before.items() if after.get(k) != v}
        diff_after = {k: after[k] for k in diff_before}
        record_changes(diff_before, diff_after, **extra)


def copy_provenance(src, dst):
    """Copy the provenance of ``src`` onto a record derived from it (e.g. the
    host IOC created by mark-as-IOC). Verification is not inherited."""
    for key in PROVENANCE_INPUT_FIELDS + ('timestamp_derivation', 'clock_skew_applied_seconds'):
        setattr(dst, key, getattr(src, key))


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

def verify(record, actor):
    """Second-analyst verification. 400 ``same_analyst`` (creator), 400
    ``no_provenance`` (nothing to verify), 409 ``already_verified``."""
    if record.provenance_level == 'none':
        raise ProvenanceError('no_provenance', 'This record has no provenance to verify')
    if record.provenance_verified_at is not None:
        raise ProvenanceError('already_verified', 'Provenance is already verified', status=409)
    if record.created_by == actor.id:
        raise ProvenanceError('same_analyst', 'Provenance must be verified by a different analyst than the creator')
    record.provenance_verified_by = actor.id
    record.provenance_verified_at = datetime.now(timezone.utc)


def unverify(record, actor, *, may_override=False):
    """Clear verification: only the verifier, or a user who ``may_override``."""
    if record.provenance_verified_at is None:
        raise ProvenanceError('not_verified', 'Provenance is not verified', status=409)
    if record.provenance_verified_by != actor.id and not may_override:
        raise ProvenanceError('forbidden', 'Only the verifier can withdraw a verification', status=403)
    record.provenance_verified_by = None
    record.provenance_verified_at = None


# --------------------------------------------------------------------------
# Clock skew re-normalization
# --------------------------------------------------------------------------

def reapply_host_skew(host, *, dry_run=True):
    """Re-derive events / IOCs of ``host`` that were ``computed`` from a raw
    timestamp under a different skew than the host has now.

    ``new = stored + (skew_applied - host_skew)``: only the skew delta moves
    the value, so DST folds never need re-deciding. Returns
    ``{'dry_run', 'count', 'old_skew'..., 'changes': [...]}`` where each change
    is ``{kind, id, field, old, new, old_skew, new_skew}``; when not a dry run
    the rows are updated (versions bump) and verification of changed rows is
    cleared. The caller commits and audits.
    """
    new_skew = host.clock_skew_seconds
    new_value = new_skew or 0
    changes, rows = [], []
    for kind, (model, _perm, _entity) in RECORD_KINDS.items():
        query = model.query.filter(
            model.incident_id == host.incident_id,
            model.host_id == host.id,
            model.timestamp_derivation == 'computed',
            model.raw_timestamp.isnot(None),
        )
        for record in query.all():
            attr = timestamp_attr(record)
            if not attr:
                continue
            current = getattr(record, attr)
            old_skew = record.clock_skew_applied_seconds or 0
            if current is None or old_skew == new_value:
                continue
            updated = current + timedelta(seconds=old_skew - new_value)
            changes.append({'kind': kind, 'id': str(record.id), 'field': attr,
                            'old': current.isoformat(), 'new': updated.isoformat(),
                            'old_skew': old_skew, 'new_skew': new_value})
            rows.append((record, attr, updated))
            if len(rows) > MAX_REAPPLY_RECORDS:
                raise ProvenanceError('too_many_records',
                                      f'More than {MAX_REAPPLY_RECORDS} records would change; narrow the scope')
    if not dry_run:
        for record, attr, updated in rows:
            setattr(record, attr, updated)
            record.clock_skew_applied_seconds = new_skew
            record.provenance_verified_by = None
            record.provenance_verified_at = None
    return {'dry_run': dry_run, 'count': len(changes), 'changes': changes}


def preview(raw_timestamp, source_timezone=None, host=None, fold=None):
    """Live-form preview: ``Normalized.to_dict()`` for a raw timestamp."""
    skew = host.clock_skew_seconds if host is not None else None
    result = normalize(raw_timestamp, source_timezone, skew, fold,
                       default_timezone=host.timezone if host is not None else None)
    return result.to_dict()
