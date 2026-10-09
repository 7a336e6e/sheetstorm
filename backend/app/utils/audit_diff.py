"""Before/after diffs for audit records — one shape everywhere.

    {field: {'from': a, 'to': b}}          scalar / dict / mixed change
    {field: {'added': [...], 'removed': [...]}}   list of scalars
    {field: {'changed': True}}             sensitive field (values never stored)

Nested dicts are diffed one level deep with dotted keys (``settings.timezone``).
Strings are truncated to 500 characters, lists to 100 items and the diff to 100
keys (then ``'_truncated': True`` is added).

Endpoints wrapped in ``@audit_log`` call ``record_changes(before, after)``; the
decorator stores the result under ``details.changes`` (never broadcast over
WebSocket: ``changes`` is a private detail key).
"""
import datetime as _dt
import decimal
import hashlib
import ipaddress
import uuid

from flask import g

MAX_STR = 500
MAX_LIST = 100
MAX_KEYS = 100

_MISSING = object()


def _is_sensitive(key) -> bool:
    from app.middleware.audit import _SENSITIVE_KEYS
    return bool(_SENSITIVE_KEYS.search(str(key)))


def _json_safe(value):
    """JSON-serialisable copy of ``value`` (uuid/datetime/ip/decimal -> str)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (uuid.UUID, decimal.Decimal, ipaddress._BaseAddress, ipaddress._BaseNetwork)):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f'<binary sha256:{hashlib.sha256(bytes(value)).hexdigest()[:16]}>'
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((_json_safe(v) for v in value), key=lambda x: (str(type(x)), str(x)))
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def snapshot(obj, fields) -> dict:
    """``{field: json_safe(getattr(obj, field))}`` for each field name."""
    if obj is None:
        return {}
    return {f: _json_safe(getattr(obj, f, None)) for f in fields}


def _clip(value):
    if isinstance(value, str) and len(value) > MAX_STR:
        return value[:MAX_STR] + '…'
    if isinstance(value, list):
        return [_clip(v) for v in value[:MAX_LIST]]
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    return value


def _scalar_list(value) -> bool:
    return isinstance(value, list) and all(
        v is None or isinstance(v, (str, int, float, bool)) for v in value)


def _same(before, after) -> bool:
    """Absent and None are the same value."""
    return (None if before is _MISSING else before) == (None if after is _MISSING else after)


def _diff_value(before, after):
    """Diff entry for one changed value (both already json-safe)."""
    b = [] if before is _MISSING or before is None else before
    a = [] if after is _MISSING or after is None else after
    if _scalar_list(b) and _scalar_list(a) and (isinstance(before, list) or isinstance(after, list)):
        added = [v for v in a if v not in b]
        removed = [v for v in b if v not in a]
        if added or removed:
            return {'added': _clip(added), 'removed': _clip(removed)}
        # Same members, different order.
        return {'from': _clip(b), 'to': _clip(a)}
    return {'from': _clip(None if before is _MISSING else before),
            'to': _clip(None if after is _MISSING else after)}


def audit_changes(before: dict, after: dict) -> dict:
    """Changed keys only, in the shape described in the module docstring."""
    before = _json_safe(before or {})
    after = _json_safe(after or {})
    changes = {}
    for key in sorted(set(before) | set(after)):
        b = before.get(key, _MISSING)
        a = after.get(key, _MISSING)
        if _same(b, a):
            continue
        if _is_sensitive(key):
            changes[key] = {'changed': True}
            continue
        if isinstance(b, dict) or isinstance(a, dict):
            bd = b if isinstance(b, dict) else {}
            ad = a if isinstance(a, dict) else {}
            if (b not in (_MISSING, None) and not isinstance(b, dict)) or \
                    (a not in (_MISSING, None) and not isinstance(a, dict)):
                changes[key] = _diff_value(b, a)  # type changed (dict <-> scalar)
                continue
            for sub in sorted(set(bd) | set(ad)):
                sb = bd.get(sub, _MISSING)
                sa = ad.get(sub, _MISSING)
                if _same(sb, sa):
                    continue
                dotted = f'{key}.{sub}'
                changes[dotted] = {'changed': True} if _is_sensitive(sub) else _diff_value(sb, sa)
            continue
        changes[key] = _diff_value(b, a)

    if len(changes) > MAX_KEYS:
        changes = {k: changes[k] for k in list(changes)[:MAX_KEYS]}
        changes['_truncated'] = True
    return changes


def record_changes(before, after, **extra) -> dict:
    """Compute the diff and stash it on ``g`` for ``@audit_log``.

    Repeated calls in one request merge. ``extra`` (e.g. ``target_email``) is
    merged into the audit record's ``details``. Returns the diff.
    """
    changes = audit_changes(before, after)
    merged = dict(getattr(g, 'audit_changes', None) or {})
    merged.update(changes)
    g.audit_changes = merged
    if extra:
        g.audit_extra = {**(getattr(g, 'audit_extra', None) or {}), **_json_safe(extra)}
    return changes
