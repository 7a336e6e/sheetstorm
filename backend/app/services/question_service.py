"""Investigative questions: validation, transitions, leads, summary, report data.

Endpoints stay thin and call these functions. Anything a client sends is
validated here (``QuestionError`` -> JSON error with a status), and every id
(owner, lead, evidence) is re-queried against the incident's own organization
and incident, never trusted.

Importing this module registers the ``question`` evidence-ref type and gives
the ``question`` realtime entity its serializer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func

from app import db
from app.models import InvestigativeQuestion, QuestionLead, Task, User
from app.services import question_library, realtime
from app.services.evidence_refs import (EvidenceRefsError, normalize_refs, register_ref_type, resolve_refs,
                                        validate_refs)

MAX_QUESTION_LENGTH = 1000
MAX_DESCRIPTION_LENGTH = 5000
MAX_ANSWER_LENGTH = 20000
MAX_FACET_LENGTH = 255
MAX_EVIDENCE_REFS = 50
MAX_LEADS_PER_QUESTION = 100
MAX_BULK_REFS = 100
MAX_QUESTIONS_PER_INCIDENT = 1000

# Evidence a question answer may cite.
QUESTION_EVIDENCE_TYPES = ('timeline_event', 'host', 'account', 'network_ioc', 'host_ioc', 'malware',
                           'artifact', 'evidence_item', 'case_note', 'task')

EDITABLE_FIELDS = ('question', 'description', 'facet', 'status', 'answer', 'confidence', 'priority',
                   'phase', 'owner_id', 'evidence_refs', 'order_index')
AUDITED_FIELDS = ('question', 'description', 'facet', 'status', 'answer', 'confidence', 'priority',
                  'phase', 'owner_id', 'evidence_refs', 'order_index', 'is_archived')


class QuestionError(Exception):
    """A request problem: ``status`` + JSON ``error`` code + message."""

    def __init__(self, message, code='bad_request', status=400, **extra):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.extra = extra

    def to_dict(self):
        return {'error': self.code, 'message': self.message, **self.extra}


def normalize_text(value) -> str:
    """Case- and whitespace-insensitive form used to detect duplicates."""
    return ' '.join(str(value or '').casefold().split())


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------

def _text(value, field, max_len, required=False):
    if value is None:
        if required:
            raise QuestionError(f'{field} is required')
        return None
    if not isinstance(value, str):
        raise QuestionError(f'{field} must be a string')
    value = value.strip()
    if required and not value:
        raise QuestionError(f'{field} is required')
    if len(value) > max_len:
        raise QuestionError(f'{field} must be at most {max_len} characters')
    return value or None


def _choice(value, choices, field, allow_none=False):
    if value is None and allow_none:
        return None
    if value not in choices:
        raise QuestionError(f'Invalid {field}: {value!r}. Valid values: {list(choices)}')
    return value


def _phase(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 6:
        raise QuestionError('phase must be an integer from 1 to 6')
    return value


def _order_index(value):
    if isinstance(value, bool) or not isinstance(value, int) or not -1_000_000 <= value <= 1_000_000:
        raise QuestionError('order_index must be an integer')
    return value


def validate_owner(owner_id, incident):
    """An active user of the incident's organization who can see the incident."""
    if owner_id in (None, ''):
        return None
    from app.middleware.rbac import user_can_access_incident
    try:
        uid = uuid.UUID(str(owner_id))
    except (ValueError, TypeError):
        raise QuestionError('owner_id must be a UUID', 'invalid_owner')
    owner = User.query.filter_by(id=uid, organization_id=incident.organization_id).first()
    if owner is None or not owner.is_active or getattr(owner, 'deactivated_at', None) is not None:
        raise QuestionError('owner_id must be an active user of this organization', 'invalid_owner')
    if not user_can_access_incident(owner, incident):
        raise QuestionError('owner cannot access this incident', 'invalid_owner')
    return owner.id


def _ref_key(ref):
    if not isinstance(ref, dict):
        return None
    norm = normalize_refs([ref])
    return (norm[0]['evidence_type'], norm[0]['evidence_id']) if norm else None


def validate_evidence(incident, refs, existing=None):
    """Canonical, de-duplicated refs; new ones must exist **in this incident**
    (400 ``invalid_evidence_refs``). Refs already stored on the question are
    kept without re-checking, so editing a question whose cited record was
    since deleted still works."""
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise EvidenceRefsError('evidence_refs must be a list')
    if len(refs) > MAX_EVIDENCE_REFS:
        raise EvidenceRefsError(f'At most {MAX_EVIDENCE_REFS} evidence references are allowed')
    kept = {(r['evidence_type'], r['evidence_id']) for r in normalize_refs(existing or [])}
    positions, fresh = [], []
    for index, ref in enumerate(refs):
        if _ref_key(ref) in kept:
            continue
        positions.append(index)
        fresh.append(ref)
    try:
        validate_refs(incident.id, fresh, allowed=QUESTION_EVIDENCE_TYPES, max_refs=MAX_EVIDENCE_REFS)
    except EvidenceRefsError as exc:
        for item in exc.invalid:
            if 'index' in item:
                item['index'] = positions[item['index']]
        raise
    return normalize_refs(refs)


def validate_task_ids(incident, task_ids):
    """Tasks of this incident (400 ``invalid_leads`` otherwise)."""
    if not isinstance(task_ids, list) or any(not isinstance(t, str) for t in task_ids):
        raise QuestionError('task_ids must be a list of task ids', 'invalid_leads')
    if len(task_ids) > MAX_LEADS_PER_QUESTION:
        raise QuestionError(f'At most {MAX_LEADS_PER_QUESTION} leads can be linked', 'invalid_leads')
    ids = []
    for raw in task_ids:
        try:
            tid = uuid.UUID(raw)
        except ValueError:
            raise QuestionError('task_ids must contain UUIDs', 'invalid_leads', invalid=[raw[:50]])
        if tid not in ids:
            ids.append(tid)
    if ids:
        found = {r[0] for r in db.session.query(Task.id).filter(Task.incident_id == incident.id,
                                                                Task.id.in_(ids)).all()}
        missing = [str(t) for t in ids if t not in found]
        if missing:
            raise QuestionError('Every lead must be a task of this incident', 'invalid_leads', invalid=missing)
    return ids


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------

def _check_capacity(incident, adding=1):
    count = InvestigativeQuestion.query.filter_by(incident_id=incident.id).count()
    if count + adding > MAX_QUESTIONS_PER_INCIDENT:
        raise QuestionError(f'An incident can hold at most {MAX_QUESTIONS_PER_INCIDENT} questions',
                            'too_many_questions', 409)


def _next_order(incident_id):
    top = db.session.query(func.max(InvestigativeQuestion.order_index)).filter_by(incident_id=incident_id).scalar()
    return (top or 0) + 1


def find_duplicate(incident_id, *, dedupe_key=None, text=None):
    """Existing question (archived included) with this dedupe key or the same
    normalised text."""
    q = InvestigativeQuestion.query.filter_by(incident_id=incident_id)
    if dedupe_key:
        hit = q.filter_by(dedupe_key=dedupe_key).first()
        if hit:
            return hit
    if text:
        wanted = normalize_text(text)
        for row_id, row_text in q.with_entities(InvestigativeQuestion.id, InvestigativeQuestion.question).all():
            if normalize_text(row_text) == wanted:
                return db.session.get(InvestigativeQuestion, row_id)
    return None


def create_question(incident, user, data):
    """Create a manual question or add a library question (``library_ref``).

    409 ``duplicate_question`` {existing_id} when it is already on the
    incident (same library ref, or the same text ignoring case/whitespace).
    """
    _check_capacity(incident)
    library_ref = data.get('library_ref')
    owner_id = validate_owner(data.get('owner_id'), incident) if 'owner_id' in data else None
    if library_ref is not None:
        if not isinstance(library_ref, str) or question_library.get(library_ref) is None:
            raise QuestionError('Unknown library question', 'unknown_library_ref')
        overrides = {}
        if data.get('phase') is not None:
            overrides['phase'] = _phase(data['phase'])
        if data.get('priority') is not None:
            overrides['priority'] = _choice(data['priority'], InvestigativeQuestion.PRIORITIES, 'priority')
        if data.get('facet') is not None:
            overrides['facet'] = _text(data['facet'], 'facet', MAX_FACET_LENGTH)
        fields = question_library.to_question_kwargs(library_ref, overrides)
    else:
        fields = {
            'question': _text(data.get('question'), 'question', MAX_QUESTION_LENGTH, required=True),
            'description': _text(data.get('description'), 'description', MAX_DESCRIPTION_LENGTH),
            'facet': _text(data.get('facet'), 'facet', MAX_FACET_LENGTH),
            'phase': _phase(data.get('phase')),
            'priority': _choice(data.get('priority') or 'medium', InvestigativeQuestion.PRIORITIES, 'priority'),
            'source': 'manual', 'source_ref': None, 'dedupe_key': None, 'guidance': [],
        }
    dup = find_duplicate(incident.id, dedupe_key=fields.get('dedupe_key'), text=fields['question'])
    if dup is not None:
        raise QuestionError('This question is already on the incident', 'duplicate_question', 409,
                            existing_id=str(dup.id))
    fields['owner_id'] = owner_id
    fields.setdefault('order_index', _next_order(incident.id))
    question = InvestigativeQuestion(incident_id=incident.id, created_by=user.id, **fields)
    db.session.add(question)
    return question


def apply_update(incident, question, user, data):
    """Apply a PUT body to ``question`` (not committed). Validates everything
    first, then mutates; enforces the status transition rules."""
    unknown = sorted(k for k in data if k not in EDITABLE_FIELDS + ('expected_version',))
    if unknown:
        raise QuestionError(f'Unknown field: {unknown[0]}', 'unknown_field')

    changes = {}
    if 'question' in data:
        changes['question'] = _text(data['question'], 'question', MAX_QUESTION_LENGTH, required=True)
    if 'description' in data:
        changes['description'] = _text(data['description'], 'description', MAX_DESCRIPTION_LENGTH)
    if 'facet' in data:
        changes['facet'] = _text(data['facet'], 'facet', MAX_FACET_LENGTH)
    if 'answer' in data:
        answer = data['answer']
        if answer is not None and not isinstance(answer, str):
            raise QuestionError('answer must be a string')
        if answer is not None and len(answer) > MAX_ANSWER_LENGTH:
            raise QuestionError(f'answer must be at most {MAX_ANSWER_LENGTH} characters')
        changes['answer'] = answer if answer and answer.strip() else None
    if 'confidence' in data:
        changes['confidence'] = _choice(data['confidence'], InvestigativeQuestion.CONFIDENCES, 'confidence',
                                        allow_none=True)
    if 'priority' in data:
        changes['priority'] = _choice(data['priority'], InvestigativeQuestion.PRIORITIES, 'priority')
    if 'phase' in data:
        changes['phase'] = _phase(data['phase'])
    if 'order_index' in data:
        changes['order_index'] = _order_index(data['order_index'])
    if 'status' in data:
        changes['status'] = _choice(data['status'], InvestigativeQuestion.STATUSES, 'status')
    if 'owner_id' in data:
        changes['owner_id'] = validate_owner(data['owner_id'], incident)
    if 'evidence_refs' in data:
        changes['evidence_refs'] = validate_evidence(incident, data['evidence_refs'], question.evidence_refs)

    status = changes.get('status', question.status)
    answer = changes['answer'] if 'answer' in changes else question.answer
    confidence = changes['confidence'] if 'confidence' in changes else question.confidence
    refs = changes['evidence_refs'] if 'evidence_refs' in changes else (question.evidence_refs or [])
    if status == 'answered':
        if not answer:
            raise QuestionError('An answered question needs an answer', 'answer_required')
        if not confidence:
            raise QuestionError('An answered question needs a confidence level', 'confidence_required')
    if status == 'unanswerable' and not answer:
        raise QuestionError('An unanswerable question needs a rationale in the answer field', 'answer_required')
    if confidence == 'confirmed' and not refs:
        raise QuestionError('Confidence "confirmed" needs at least one evidence reference',
                            'evidence_required')

    was_resolved = question.status in ('answered', 'unanswerable')
    for field, value in changes.items():
        setattr(question, field, value)
    if status in ('answered', 'unanswerable') and not was_resolved:
        question.answered_at = datetime.now(timezone.utc)
        question.answered_by = user.id
    elif status in ('open', 'in_progress') and was_resolved:
        # Reopened: keep the text, clear who/when resolved it.
        question.answered_at = None
        question.answered_by = None
    return question


def set_leads(incident, question, user, task_ids):
    """Replace the question's linked leads; returns the new ``lead_ids``."""
    ids = validate_task_ids(incident, task_ids)
    current = {link.task_id: link for link in question.lead_links}
    for task_id, link in current.items():
        if task_id not in ids:
            question.lead_links.remove(link)
    for task_id in ids:
        if task_id not in current:
            question.lead_links.append(QuestionLead(task_id=task_id, created_by=user.id))
    return [str(t) for t in ids]


def archive(question):
    question.is_archived = True
    return question


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def lead_ids_map(question_ids):
    if not question_ids:
        return {}
    out = {}
    rows = QuestionLead.query.filter(QuestionLead.question_id.in_(question_ids)).all()
    for row in rows:
        out.setdefault(row.question_id, []).append(str(row.task_id))
    return {k: sorted(v) for k, v in out.items()}


def serialize_many(questions, incident_id, user):
    """Dicts with server-resolved ``evidence`` (labels only for records the
    ``user`` may read) and ``lead_ids``; one query per type and one for links."""
    leads = lead_ids_map([q.id for q in questions])
    items = [q.to_dict(lead_ids=leads.get(q.id, [])) for q in questions]
    union = [ref for item in items for ref in (item.get('evidence_refs') or [])]
    resolved = {}
    if union:
        resolved = {(r['evidence_type'], r['evidence_id']): r
                    for r in resolve_refs(incident_id, union, user=user)}
    for item in items:
        item['evidence'] = [resolved[(r['evidence_type'], r['evidence_id'])]
                            for r in normalize_refs(item.get('evidence_refs') or [])
                            if (r['evidence_type'], r['evidence_id']) in resolved]
    return items


def serialize_one(question, user):
    return serialize_many([question], question.incident_id, user)[0]


def _socket_serializer(question):
    """Realtime payload: refs without labels (recipients' read permissions
    differ; clients read labels over REST)."""
    data = question.to_dict()
    data['evidence'] = [dict(r, label=None, missing=False) for r in normalize_refs(question.evidence_refs or [])]
    return data


# ---------------------------------------------------------------------------
# Summary and report data
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}


def summary(incident_id):
    """Progress over the incident's non-archived questions:
    ``{total, open, in_progress, answered, unanswerable, resolved, progress,
    open_high_priority, top_open}``. ``progress`` is resolved/total (0-1)."""
    rows = (InvestigativeQuestion.query
            .filter_by(incident_id=incident_id, is_archived=False)
            .with_entities(InvestigativeQuestion.id, InvestigativeQuestion.question, InvestigativeQuestion.status,
                           InvestigativeQuestion.priority, InvestigativeQuestion.phase)
            .all())
    counts = {s: 0 for s in InvestigativeQuestion.STATUSES}
    open_rows = []
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
        if r.status in ('open', 'in_progress'):
            open_rows.append(r)
    total = len(rows)
    resolved = counts['answered'] + counts['unanswerable']
    open_rows.sort(key=lambda r: (_PRIORITY_ORDER.get(r.priority, 9), r.phase or 9, str(r.id)))
    return {
        'total': total,
        **counts,
        'resolved': resolved,
        'progress': round(resolved / total, 4) if total else 0,
        'open_high_priority': sum(1 for r in open_rows if r.priority in ('critical', 'high')),
        'top_open': [{'id': str(r.id), 'question': r.question, 'priority': r.priority, 'status': r.status,
                      'phase': r.phase} for r in open_rows[:5]],
    }


def report_payload(incident, user):
    """Everything a report needs about the investigation's questions, ordered
    phase -> facet -> order_index, with resolved evidence and linked leads."""
    questions = (InvestigativeQuestion.query.filter_by(incident_id=incident.id, is_archived=False).all())
    questions.sort(key=lambda q: (q.phase if q.phase is not None else 99, (q.facet or '').casefold(),
                                  q.order_index or 0, q.created_at.isoformat() if q.created_at else ''))
    items = serialize_many(questions, incident.id, user)

    link_rows = QuestionLead.query.filter(QuestionLead.question_id.in_([q.id for q in questions])).all() \
        if questions else []
    task_ids = {row.task_id for row in link_rows}
    tasks = {t.id: t for t in Task.query.filter(Task.id.in_(task_ids)).all()} if task_ids else {}
    by_question = {}
    for row in link_rows:
        t = tasks.get(row.task_id)
        if t is not None:
            by_question.setdefault(row.question_id, []).append(
                {'id': str(t.id), 'title': t.title, 'status': t.status, 'lead_outcome': t.lead_outcome})

    out = []
    for q, item in zip(questions, items):
        out.append({
            'id': item['id'], 'question': q.question, 'facet': q.facet, 'phase': q.phase, 'priority': q.priority,
            'status': q.status, 'answer': q.answer, 'confidence': q.confidence,
            'answered_at': item['answered_at'], 'answered_by': item['answered_by_user'],
            'source': q.source, 'source_ref': q.source_ref,
            'evidence': item['evidence'], 'leads': by_question.get(q.id, []),
        })
    groups = {s: [x for x in out if x['status'] == s] for s in InvestigativeQuestion.STATUSES}
    data = {
        'incident_id': str(incident.id),
        'summary': summary(incident.id),
        'questions': out,
        'answered': groups['answered'],
        'unanswerable': groups['unanswerable'],
        'open': groups['open'] + groups['in_progress'],
    }
    if any(q.source == 'dfiq' for q in questions):
        data['attribution'] = question_library.DFIQ_SOURCE['attribution']
    return data


def _register():
    register_ref_type('question', InvestigativeQuestion, label='question', permission='incidents:read')
    realtime.register_entity('question', 'questions', 'incidents:read', _socket_serializer)


_register()
