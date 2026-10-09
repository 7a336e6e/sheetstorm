"""Typed, incident-scoped references to evidence records.

One shape everywhere (tasks, questions, decision-log links, provenance):

    {"evidence_type": "<registered type>", "evidence_id": "<uuid>"}

Every referenced record must exist **in the same incident**; labels shown to
users are always resolved server-side (client-supplied labels are not trusted).

Built-in types: timeline_event, host, account, network_ioc, host_ioc, malware,
artifact, case_note, task (aliases host_indicator -> host_ioc,
network_indicator -> network_ioc). Features register their own types with
``register_ref_type`` (evidence_item, question, decision, response_action).
"""
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, Union

DEFAULT_MAX_REFS = 50


class EvidenceRefsError(ValueError):
    """400 ``invalid_evidence_refs``; ``invalid`` lists the offending entries."""
    status = 400
    code = 'invalid_evidence_refs'

    def __init__(self, message, invalid=None):
        super().__init__(message)
        self.message = message
        self.invalid = invalid or []

    def to_dict(self):
        return {'error': self.code, 'message': self.message, 'invalid': self.invalid}

    def to_response(self):
        from flask import jsonify
        return jsonify(self.to_dict()), self.status


@dataclass
class RefType:
    name: str
    model: type
    label: Union[str, Callable]
    incident_col: str = 'incident_id'
    aliases: tuple = ()
    permission: Optional[str] = None

    def label_for(self, obj) -> str:
        if callable(self.label):
            value = self.label(obj)
        else:
            value = getattr(obj, self.label, None)
        value = '' if value is None else str(value)
        return value if len(value) <= 200 else value[:200] + '…'


_REGISTRY: dict = {}
_ALIASES: dict = {}


def register_ref_type(name, model, *, label, incident_col='incident_id', aliases=(), permission=None):
    """Register (or replace) an evidence reference type.

    label: attribute name or ``callable(obj) -> str``.
    incident_col: the model column holding the incident id.
    permission: read permission a user needs to see the record's label.
    """
    if not name or not isinstance(name, str):
        raise ValueError('ref type name required')
    _REGISTRY[name] = RefType(name, model, label, incident_col, tuple(aliases), permission)
    for alias in aliases:
        _ALIASES[alias] = name


def ref_types() -> dict:
    """{name: RefType} of every registered type."""
    _ensure_builtins()
    return dict(_REGISTRY)


def canonical_type(evidence_type):
    _ensure_builtins()
    if not isinstance(evidence_type, str):
        return None
    t = evidence_type.strip()
    t = _ALIASES.get(t, t)
    return t if t in _REGISTRY else None


def _parse_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def normalize_refs(refs):
    """Canonical, de-duplicated refs (order kept); malformed entries are dropped.

    Use ``validate_refs`` at trust boundaries: it reports malformed entries
    instead of dropping them.
    """
    if not isinstance(refs, (list, tuple)):
        return []
    out, seen = [], set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        etype = canonical_type(ref.get('evidence_type'))
        eid = _parse_uuid(ref.get('evidence_id'))
        if not etype or not eid or (etype, eid) in seen:
            continue
        seen.add((etype, eid))
        out.append({'evidence_type': etype, 'evidence_id': eid})
    return out


def validate_refs(incident_id, refs, *, allowed=None, max_refs=DEFAULT_MAX_REFS):
    """Validate client-supplied refs against ``incident_id``.

    Returns the normalised, de-duplicated list. Raises ``EvidenceRefsError``
    (400 ``invalid_evidence_refs``) when ``refs`` is not a list, has more than
    ``max_refs`` entries, or any entry is malformed, of an unknown / disallowed
    type, or does not exist in this incident (cross-incident ids included).
    One ``id IN (...)`` query per type.
    """
    _ensure_builtins()
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise EvidenceRefsError('evidence_refs must be a list')
    if len(refs) > max_refs:
        raise EvidenceRefsError(f'At most {max_refs} evidence references are allowed')
    allowed_set = None
    if allowed is not None:
        allowed_set = {canonical_type(a) or a for a in allowed}

    invalid, wanted, seen = [], {}, set()
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            invalid.append({'index': index, 'reason': 'not_an_object'})
            continue
        raw_type = ref.get('evidence_type')
        etype = canonical_type(raw_type)
        eid = _parse_uuid(ref.get('evidence_id'))
        if not etype:
            invalid.append({'index': index, 'evidence_type': str(raw_type)[:50], 'reason': 'unknown_type'})
            continue
        if allowed_set is not None and etype not in allowed_set:
            invalid.append({'index': index, 'evidence_type': etype, 'reason': 'type_not_allowed'})
            continue
        if not eid:
            invalid.append({'index': index, 'evidence_type': etype, 'reason': 'invalid_id'})
            continue
        if (etype, eid) in seen:
            continue
        seen.add((etype, eid))
        wanted.setdefault(etype, []).append((index, eid))

    for etype, items in wanted.items():
        found = _existing_ids(etype, incident_id, [eid for _, eid in items])
        for index, eid in items:
            if eid not in found:
                invalid.append({'index': index, 'evidence_type': etype, 'evidence_id': eid,
                                'reason': 'not_found'})

    if invalid:
        invalid.sort(key=lambda x: x['index'])
        raise EvidenceRefsError('Invalid evidence references', invalid)

    out = []
    for ref in refs:
        etype = canonical_type(ref.get('evidence_type'))
        eid = _parse_uuid(ref.get('evidence_id'))
        item = {'evidence_type': etype, 'evidence_id': eid}
        if item not in out:
            out.append(item)
    return out


def _existing_ids(etype, incident_id, ids):
    rt = _REGISTRY[etype]
    model = rt.model
    rows = (model.query.with_entities(model.id)
            .filter(model.id.in_(ids), getattr(model, rt.incident_col) == incident_id)
            .all())
    return {str(r[0]) for r in rows}


def resolve_refs(incident_id, refs, *, user=None):
    """Resolve refs to ``[{evidence_type, evidence_id, label, missing}]``.

    Batched (one query per type), scoped to ``incident_id``: a ref to a deleted
    or foreign record comes back with ``missing: True`` and no label. With
    ``user``, records of a type the user may not read get ``label: None`` and
    ``restricted: True``.
    """
    _ensure_builtins()
    norm = normalize_refs(refs)
    by_type = {}
    for ref in norm:
        by_type.setdefault(ref['evidence_type'], []).append(ref['evidence_id'])

    objects = {}
    for etype, ids in by_type.items():
        rt = _REGISTRY[etype]
        model = rt.model
        for obj in model.query.filter(model.id.in_(ids),
                                      getattr(model, rt.incident_col) == incident_id).all():
            objects[(etype, str(obj.id))] = obj

    out = []
    for ref in norm:
        etype, eid = ref['evidence_type'], ref['evidence_id']
        rt = _REGISTRY[etype]
        obj = objects.get((etype, eid))
        item = {'evidence_type': etype, 'evidence_id': eid, 'label': None, 'missing': obj is None}
        if obj is not None:
            if user is not None and rt.permission and not user.has_permission(rt.permission):
                item['restricted'] = True
            else:
                item['label'] = rt.label_for(obj)
        out.append(item)
    return out


# ── Built-in types ────────────────────────────────────────────────────────

def _host_ioc_label(o):
    return f'{o.artifact_type}: {o.artifact_value}'


def _account_label(o):
    return f'{o.domain}\\{o.account_name}' if o.domain else o.account_name


def _timeline_label(o):
    ts = o.timestamp.isoformat() if o.timestamp else ''
    return f'{ts} {o.activity or ""}'.strip()


_builtins_loaded = False


def _ensure_builtins():
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    from app.models import (TimelineEvent, CompromisedHost, CompromisedAccount, NetworkIndicator,
                            HostBasedIndicator, MalwareTool, Artifact, CaseNote, Task)
    builtins = [
        ('timeline_event', TimelineEvent, _timeline_label, (), 'timeline:read'),
        ('host', CompromisedHost, 'hostname', (), 'hosts:read'),
        ('account', CompromisedAccount, _account_label, (), 'accounts:read'),
        ('network_ioc', NetworkIndicator, 'dns_ip', ('network_indicator',), 'network_iocs:read'),
        ('host_ioc', HostBasedIndicator, _host_ioc_label, ('host_indicator',), 'host_iocs:read'),
        ('malware', MalwareTool, 'file_name', (), 'malware:read'),
        ('artifact', Artifact, 'original_filename', (), 'artifacts:read'),
        ('case_note', CaseNote, 'title', (), 'incidents:read'),
        ('task', Task, 'title', (), 'tasks:read'),
    ]
    for name, model, label, aliases, perm in builtins:
        if name not in _REGISTRY:  # a feature may have overridden it already
            register_ref_type(name, model, label=label, aliases=aliases, permission=perm)
