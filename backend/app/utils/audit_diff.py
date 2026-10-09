"""Before/after diffs for audit rows (`_integration.md` §1 #6).

PROVISIONAL COPY — the canonical module is owned by W0-FND. W0-RBAC needs it
for the role / organization diffs and merges after FND: on rebase, take
FND's version of this file and of the `@audit_log` merge in
`middleware/audit.py` (identical public API).

Diff shape everywhere: `{field: {from, to}}`; lists → `{added, removed}`;
sensitive fields → `{changed: true}`.
"""
from __future__ import annotations

import copy
from datetime import date, datetime
from uuid import UUID

from flask import g


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    return value


def snapshot(obj, fields) -> dict:
    """{field: deep-copied, JSON-safe value} for `fields` of `obj`."""
    return {f: _plain(copy.deepcopy(getattr(obj, f, None))) for f in fields}


def audit_changes(before: dict, after: dict) -> dict:
    """Diff two snapshots into the canonical shape (unchanged keys omitted)."""
    from app.middleware.audit import _SENSITIVE_KEYS

    changes = {}
    for key in list(before) + [k for k in after if k not in before]:
        old, new = _plain(before.get(key)), _plain(after.get(key))
        if old == new:
            continue
        if _SENSITIVE_KEYS.search(str(key)):
            changes[key] = {'changed': True}
        elif isinstance(old, list) or isinstance(new, list):
            old_l, new_l = old or [], new or []
            changes[key] = {
                'added': sorted((v for v in new_l if v not in old_l), key=str),
                'removed': sorted((v for v in old_l if v not in new_l), key=str),
            }
        else:
            changes[key] = {'from': old, 'to': new}
    return changes


def record_changes(before: dict, after: dict, **extra) -> dict:
    """Compute the diff and stash it for `@audit_log` (details.changes)."""
    changes = audit_changes(before, after)
    merged = dict(getattr(g, 'audit_changes', None) or {})
    merged.update(changes)
    g.audit_changes = merged
    if extra:
        g.audit_extra = {**(getattr(g, 'audit_extra', None) or {}), **extra}
    return changes
