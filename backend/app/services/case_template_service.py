"""Case templates: validation, resolution and (idempotent) application.

``apply`` seeds an incident from a template: questions, leads, a playbook,
defaults and custom-field definitions. It runs inside the caller's
transaction (no commit), locks the incident row, and is a **merge**: whatever
already exists is skipped, never duplicated, replaced or resurrected, so
applying twice (or two templates that share questions) is safe.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (CaseTemplate, Incident, IncidentCaseTemplate, IncidentPlaybook, InvestigativeQuestion,
                        Playbook, QuestionLead, Task)
from app.schemas.case_template import BUILTIN_REF_RE, MAX_BODY_BYTES, CaseTemplateDefinition
from app.services import builtin_templates, question_library
from app.services.playbook_service import PlaybookService
from app.services.question_service import find_duplicate, normalize_text

ALL_PARTS = ('questions', 'leads', 'playbook', 'custom_fields')
SEVERITY_RANK = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
TLP_RANK = {'white': 0, 'green': 1, 'amber': 2, 'amber_strict': 3, 'red': 4}
MAX_CUSTOM_TEXT = 2000


class TemplateError(Exception):
    """A request problem: ``status`` + JSON ``error`` code + message."""

    def __init__(self, message, code='bad_request', status=400, **extra):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.extra = extra

    def to_dict(self):
        return {'error': self.code, 'message': self.message, **self.extra}


@dataclass
class ResolvedTemplate:
    kind: str                       # 'builtin' | 'org'
    key: str
    name: str
    version: int
    definition: CaseTemplateDefinition
    row: Optional[CaseTemplate] = None
    is_active: bool = True

    @property
    def builtin_key(self):
        return self.key if self.kind == 'builtin' else None

    @property
    def ref(self):
        return f'builtin:{self.key}' if self.kind == 'builtin' else str(self.row.id)


# ---------------------------------------------------------------------------
# Validation of client-supplied definitions
# ---------------------------------------------------------------------------

def check_body_size(request):
    size = request.content_length
    if size is None:
        size = len(request.get_data())
    if size > MAX_BODY_BYTES:
        raise TemplateError(f'Request body must be at most {MAX_BODY_BYTES // 1024} KB',
                            'payload_too_large', 400)


def _fields(exc: ValidationError):
    out = {}
    for err in exc.errors():
        loc = '.'.join(str(p) for p in err['loc']) or 'body'
        out.setdefault(loc, err['msg'])
    return out


def validate_body(raw, model, org_id):
    """Validate a POST / PUT body with ``model`` (``CaseTemplateWrite`` or
    ``CaseTemplateUpdate``) and its references; 400 ``validation_error`` with
    a ``fields`` map otherwise."""
    if not isinstance(raw, dict):
        raise TemplateError('A JSON object body is required', 'validation_error', fields={})
    try:
        body = model.model_validate(raw)
    except ValidationError as exc:
        fields = _fields(exc)
        raise TemplateError('Invalid template', 'validation_error', fields=fields)
    defn = body.definition
    if defn is not None:
        problems = builtin_templates.check_library_refs(defn)
        if defn.playbook and defn.playbook.playbook_id is not None:
            owned = Playbook.query.filter_by(id=defn.playbook.playbook_id, organization_id=org_id).first()
            if owned is None:
                problems.append('playbook_id is not a playbook of your organization')
        if problems:
            raise TemplateError('Invalid template', 'validation_error', fields={'definition': '; '.join(problems)})
    return body


def definition_json(defn: CaseTemplateDefinition) -> dict:
    return defn.model_dump(mode='json', exclude_none=True)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def parse_ref(ref):
    """``('builtin', key)`` | ``('org', uuid)`` | None."""
    if not isinstance(ref, str):
        return None
    if BUILTIN_REF_RE.match(ref):
        return 'builtin', ref.split(':', 1)[1]
    try:
        return 'org', uuid.UUID(ref)
    except ValueError:
        return None


DISABLED_BUILTINS_KEY = 'disabled_builtin_templates'


def disabled_builtins(org_id) -> set:
    """Keys of the built-in templates this organization switched off. Stored
    in ``organizations.settings`` (not an OrgSettings field: it is written
    only through PUT /case-templates/builtin:<key>)."""
    from app.models import Organization
    org = db.session.get(Organization, org_id) if org_id else None
    keys = ((org.settings or {}) if org is not None else {}).get(DISABLED_BUILTINS_KEY) or []
    return {k for k in keys if isinstance(k, str)}


def set_builtin_active(org, key, active: bool) -> bool:
    """Switch a built-in template on/off for ``org`` (caller commits).
    Returns the previous active state."""
    settings = dict(org.settings or {})
    disabled = set(settings.get(DISABLED_BUILTINS_KEY) or [])
    was_active = key not in disabled
    if active:
        disabled.discard(key)
    else:
        disabled.add(key)
    settings[DISABLED_BUILTINS_KEY] = sorted(disabled)
    org.settings = settings  # reassign: JSON column change detection
    return was_active


def resolve(org_id, ref, *, require_active=True) -> Optional[ResolvedTemplate]:
    """The template addressed by ``ref`` ("builtin:<key>" or an org template
    uuid of ``org_id``), or None if it does not exist. With ``require_active``
    a deactivated org template raises 409 ``template_inactive``."""
    parsed = parse_ref(ref)
    if parsed is None:
        return None
    kind, ident = parsed
    if kind == 'builtin':
        data = builtin_templates.get_case_template(ident)
        if data is None:
            return None
        if require_active and ident in disabled_builtins(org_id):
            raise TemplateError('This template is deactivated for your organization', 'template_inactive', 409)
        return ResolvedTemplate('builtin', ident, data['name'], 1,
                                CaseTemplateDefinition.model_validate(data['definition']))
    row = CaseTemplate.query.filter_by(id=ident, organization_id=org_id).first()
    if row is None:
        return None
    if require_active and not row.is_active:
        raise TemplateError('This template is deactivated', 'template_inactive', 409)
    try:
        defn = CaseTemplateDefinition.model_validate(row.definition or {})
    except ValidationError:
        raise TemplateError('This template is invalid and cannot be applied', 'invalid_template', 409)
    return ResolvedTemplate('org', row.key, row.name, row.version, defn, row, row.is_active)


def summary_counts(definition: dict) -> dict:
    """Counts shown in pickers: ``{questions, leads, custom_fields, playbook}``."""
    definition = definition or {}
    pb = definition.get('playbook') or {}
    return {
        'questions': len(definition.get('questions') or []),
        'leads': len(definition.get('leads') or []),
        'custom_fields': len(definition.get('custom_fields') or []),
        'playbook': pb.get('builtin') or (str(pb['playbook_id']) if pb.get('playbook_id') else None),
    }


def describe(defn: dict, org_id) -> dict:
    """Definition detail with the names behind refs (for the editor/picker)."""
    defn = defn or {}
    questions = []
    for q in defn.get('questions') or []:
        ref = q.get('ref')
        if ref:
            qdef = question_library.get(ref)
            questions.append({'ref': ref, 'question': qdef.question if qdef else None,
                              'facet': q.get('facet') or (qdef.facet if qdef else None),
                              'phase': q.get('phase') if q.get('phase') is not None else (qdef.phase if qdef else None),
                              'priority': q.get('priority') or (qdef.priority if qdef else None),
                              'source': qdef.source if qdef else None})
        else:
            questions.append({'key': q.get('key'), 'question': q.get('question'), 'facet': q.get('facet'),
                              'phase': q.get('phase'), 'priority': q.get('priority'), 'source': 'template'})
    playbook = None
    pb = defn.get('playbook')
    if pb and pb.get('builtin'):
        data = builtin_templates.get_playbook(pb['builtin'])
        playbook = {'kind': 'builtin', 'id': f"builtin:{pb['builtin']}", 'name': data['name'] if data else None}
    elif pb and pb.get('playbook_id'):
        row = Playbook.query.filter_by(id=pb['playbook_id'], organization_id=org_id).first()
        playbook = {'kind': 'org', 'id': str(pb['playbook_id']), 'name': row.name if row else None}
    return {'questions': questions, 'playbook': playbook}


def clone_key(org_id, base_key):
    """A free org key ``<base>-copy[-n]`` (<= 64 chars)."""
    base = base_key[:55]
    taken = {k for (k,) in db.session.query(CaseTemplate.key).filter(
        CaseTemplate.organization_id == org_id, CaseTemplate.key.like(f'{base}-copy%')).all()}
    candidate = f'{base}-copy'
    n = 1
    while candidate in taken:
        n += 1
        candidate = f'{base}-copy-{n}'
    return candidate


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------

def custom_field_definitions(incident_id) -> list:
    """Effective definitions: every applied template's, merged by key in
    application order (the first definition of a key wins)."""
    merged = {}
    rows = (IncidentCaseTemplate.query.filter_by(incident_id=incident_id)
            .order_by(IncidentCaseTemplate.applied_at.asc(), IncidentCaseTemplate.created_at.asc()).all())
    for row in rows:
        for d in row.custom_field_defs or []:
            merged.setdefault(d.get('key'), d)
    return list(merged.values())


def validate_custom_values(definitions, values):
    """Normalised ``{key: value}`` (``None`` clears a key) or 400."""
    if not isinstance(values, dict):
        raise TemplateError('values must be an object', 'validation_error')
    by_key = {d['key']: d for d in definitions}
    out = {}
    for key, value in values.items():
        d = by_key.get(key)
        if d is None:
            raise TemplateError(f'Unknown custom field: {str(key)[:64]}', 'unknown_custom_field')
        if value is None or (isinstance(value, str) and not value.strip()):
            if d.get('required'):
                raise TemplateError(f'{d["label"]} is required', 'validation_error', field=key)
            out[key] = None
            continue
        ftype = d['type']
        if ftype == 'text':
            if not isinstance(value, str) or len(value) > MAX_CUSTOM_TEXT:
                raise TemplateError(f'{d["label"]} must be text of at most {MAX_CUSTOM_TEXT} characters',
                                    'validation_error', field=key)
        elif ftype == 'number':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise TemplateError(f'{d["label"]} must be a number', 'validation_error', field=key)
        elif ftype == 'boolean':
            if not isinstance(value, bool):
                raise TemplateError(f'{d["label"]} must be true or false', 'validation_error', field=key)
        elif ftype == 'date':
            try:
                if not isinstance(value, str):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                raise TemplateError(f'{d["label"]} must be a date (YYYY-MM-DD)', 'validation_error', field=key)
        elif ftype == 'select':
            if value not in (d.get('options') or []):
                raise TemplateError(f'{d["label"]} must be one of {d.get("options")}', 'validation_error',
                                    field=key)
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def _skip(result, kind, ref, reason):
    result['skipped'].append({'kind': kind, 'ref': ref, 'reason': reason})


def _apply_defaults(incident, defn, result, *, creating, apply_defaults, explicit_fields):
    d = defn.defaults
    if not creating and not apply_defaults:
        return
    explicit = set(explicit_fields or ())

    def record(field, old, new):
        setattr(incident, field, new)
        result['defaults_applied'].append({'field': field, 'from': old, 'to': new})

    if d.severity:
        if creating:
            if 'severity' not in explicit and incident.severity != d.severity:
                record('severity', incident.severity, d.severity)
        elif SEVERITY_RANK.get(d.severity, 0) > SEVERITY_RANK.get(incident.severity, 0):
            record('severity', incident.severity, d.severity)  # only ever raised
    if d.tlp:
        if creating:
            if 'tlp' not in explicit and incident.tlp != d.tlp:
                record('tlp', incident.tlp, d.tlp)
        elif TLP_RANK.get(d.tlp, 0) > TLP_RANK.get(incident.tlp, 0):
            record('tlp', incident.tlp, d.tlp)  # only ever raised
    if d.classification:
        if creating:
            if 'classification' not in explicit and incident.classification != d.classification:
                record('classification', incident.classification, d.classification)
        elif not incident.classification:
            record('classification', incident.classification, d.classification)


def _apply_questions(incident, tpl, user, result):
    """Create the template's questions; returns {ident: question} for linking
    (created or already present)."""
    defn = tpl.definition
    existing = InvestigativeQuestion.query.filter_by(incident_id=incident.id).all()
    by_dedupe = {q.dedupe_key: q for q in existing if q.dedupe_key}
    by_text = {}
    for q in existing:
        by_text.setdefault(normalize_text(q.question), q)
    order = max([q.order_index or 0 for q in existing] or [0])
    mapping = {}
    for entry in defn.questions:
        ident = entry.ident
        if entry.ref:
            overrides = {k: getattr(entry, k) for k in ('phase', 'priority', 'facet')}
            fields = question_library.to_question_kwargs(entry.ref, overrides)
        else:
            fields = {'question': entry.question.strip(), 'description': entry.description, 'facet': entry.facet,
                      'phase': entry.phase, 'priority': entry.priority or 'medium', 'source': 'template',
                      'source_ref': f'tpl:{tpl.key}:{entry.key}', 'dedupe_key': f'tpl:{tpl.key}:{entry.key}',
                      'guidance': []}
        hit = by_dedupe.get(fields['dedupe_key']) or by_text.get(normalize_text(fields['question']))
        if hit is not None:
            mapping[ident] = hit
            _skip(result, 'question', ident, 'exists')
            continue
        order += 1
        question = InvestigativeQuestion(incident_id=incident.id, created_by=user.id, order_index=order, **fields)
        try:
            with db.session.begin_nested():
                db.session.add(question)
                db.session.flush()
        except IntegrityError:
            # A concurrent request added the same dedupe key: treat as existing.
            winner = find_duplicate(incident.id, dedupe_key=fields['dedupe_key'])
            if winner is not None:
                mapping[ident] = winner
            _skip(result, 'question', ident, 'exists')
            continue
        by_dedupe[fields['dedupe_key']] = question
        by_text[normalize_text(fields['question'])] = question
        mapping[ident] = question
        result['created']['questions'] += 1
    return mapping


def _apply_leads(incident, tpl, user, mapping, result):
    defn = tpl.definition
    if not defn.leads:
        return
    allowed = user.has_permission('tasks:create')
    existing = Task.query.filter_by(incident_id=incident.id).all()
    by_key = {}
    by_title = {}
    for t in existing:
        k = (t.extra_data or {}).get('template_lead_key')
        if k:
            by_key[k] = t
        by_title.setdefault(normalize_text(t.title), t)
    for lead in defn.leads:
        marker = f'{tpl.key}:{lead.key}'
        task = by_key.get(marker) or by_title.get(normalize_text(lead.title))
        if task is None:
            if not allowed:
                _skip(result, 'lead', lead.key, 'forbidden')
                continue
            task = Task(
                incident_id=incident.id, title=lead.title.strip(), description=lead.description,
                priority=lead.priority or 'medium', phase=lead.phase, task_type=lead.task_type,
                investigation_direction=lead.investigation_direction, status='pending',
                extra_data={'template_lead_key': marker, 'case_template': tpl.key},
                evidence_refs=[], created_by=user.id)
            db.session.add(task)
            db.session.flush()
            by_key[marker] = task
            by_title[normalize_text(task.title)] = task
            result['created']['leads'] += 1
        else:
            _skip(result, 'lead', lead.key, 'exists')
        # Link the lead to the questions it answers (also for existing pairs).
        for target in lead.answers:
            question = mapping.get(target)
            if question is None:
                continue
            link = QuestionLead.query.filter_by(question_id=question.id, task_id=task.id).first()
            if link is None:
                db.session.add(QuestionLead(question_id=question.id, task_id=task.id, created_by=user.id))
                db.session.flush()
                result['created']['links'] += 1


def _apply_playbook(incident, tpl, user, result):
    ref = tpl.definition.playbook
    if ref is None:
        return None
    if ref.builtin:
        data = builtin_templates.get_playbook(ref.builtin)
        if data is None:
            _skip(result, 'playbook', f'builtin:{ref.builtin}', 'missing')
            return None
        label, name, definition = f'builtin:{ref.builtin}', data['name'], data['definition']
        playbook_id, builtin_key = None, ref.builtin
    else:
        row = Playbook.query.filter_by(id=ref.playbook_id, organization_id=incident.organization_id).first()
        if row is None:
            _skip(result, 'playbook', str(ref.playbook_id), 'missing')
            return None
        label, name, definition = str(row.id), row.name, row.definition or {}
        playbook_id, builtin_key = row.id, None
    instances = IncidentPlaybook.query.filter_by(incident_id=incident.id).all()
    for inst in instances:
        if (builtin_key and inst.builtin_key == builtin_key) or (playbook_id and inst.playbook_id == playbook_id):
            result['playbook'] = {'status': 'already_active', 'name': name}
            _skip(result, 'playbook', label, 'already_active')
            return None
    if any(inst.completed_at is None for inst in instances):
        result['playbook'] = {'status': 'existing_playbook', 'name': name}
        _skip(result, 'playbook', label, 'existing_playbook')  # never replace an active playbook
        return None
    inst = PlaybookService.build_instance(incident, name=name, definition=copy.deepcopy(definition), user=user,
                                          playbook_id=playbook_id, builtin_key=builtin_key)
    db.session.flush()
    result['playbook'] = {'status': 'activated', 'name': name}
    return inst


def apply(incident, tpl: ResolvedTemplate, user, *, apply_defaults=False, include=ALL_PARTS, dry_run=False,
          explicit_fields=None, creating=False):
    """Apply ``tpl`` to ``incident`` inside the caller's transaction.

    Returns ``{'created': {questions, leads, links}, 'skipped': [...],
    'playbook': {...}|None, 'defaults_applied': [...], 'custom_fields_added':
    n, 'dry_run': bool}`` and a ``playbook_instance`` key (the new
    IncidentPlaybook or None) for the caller. Does not commit. With
    ``dry_run`` everything is computed and then rolled back.
    ``creating=True`` (incident just created) fills only fields the request
    did not set (``explicit_fields``); later applies only raise TLP/severity
    and set classification when empty, and only with ``apply_defaults``.
    """
    include = set(include or ALL_PARTS)
    if not creating:
        # Serialize concurrent applies on one incident.
        db.session.query(Incident.id).filter(Incident.id == incident.id).with_for_update().one()
    result = {'created': {'questions': 0, 'leads': 0, 'links': 0}, 'skipped': [], 'playbook': None,
              'defaults_applied': [], 'custom_fields_added': 0, 'dry_run': bool(dry_run)}

    _apply_defaults(incident, tpl.definition, result, creating=creating, apply_defaults=apply_defaults,
                    explicit_fields=explicit_fields)
    mapping = _apply_questions(incident, tpl, user, result) if 'questions' in include else {}
    if 'leads' in include:
        _apply_leads(incident, tpl, user, mapping, result)
    instance = _apply_playbook(incident, tpl, user, result) if 'playbook' in include else None

    defs = [d.model_dump(mode='json', exclude_none=True) for d in tpl.definition.custom_fields] \
        if 'custom_fields' in include else []
    known = {d.get('key') for d in custom_field_definitions(incident.id)}
    result['custom_fields_added'] = sum(1 for d in defs if d['key'] not in known)

    if dry_run:
        db.session.rollback()
        result['playbook_instance'] = None
        return result

    summary = {k: result[k] for k in ('created', 'skipped', 'playbook', 'defaults_applied', 'custom_fields_added')}
    db.session.add(IncidentCaseTemplate(
        incident_id=incident.id,
        case_template_id=tpl.row.id if tpl.row is not None else None,
        builtin_key=tpl.builtin_key, template_key=tpl.key, template_name=tpl.name,
        template_version=tpl.version, custom_field_defs=defs, result=summary,
        applied_by=user.id, applied_at=datetime.now(timezone.utc)))
    db.session.flush()
    result['playbook_instance'] = instance
    return result


def public_result(result):
    """The JSON-safe part of an ``apply`` result."""
    return {k: v for k, v in result.items() if k != 'playbook_instance'}
