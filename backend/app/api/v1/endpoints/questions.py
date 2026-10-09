"""Investigative questions: per-incident board API, cross-incident queue, library.

Reads need ``incidents:read``, writes ``incidents:update`` (a Viewer is
read-only). Every id in a body (owner, leads, evidence) is re-queried against
the incident; library questions are copied into the incident, never linked.
"""
from flask import g, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import accessible_incidents_query, get_current_user, require_incident_access, require_permission
from app.models import Incident, InvestigativeQuestion, QuestionLead
from app.services import question_library, question_service, realtime
from app.services.evidence_refs import EvidenceRefsError
from app.services.question_service import QuestionError
from app.utils.audit_diff import record_changes, snapshot
from app.utils.concurrency import commit_or_conflict, precondition, set_etag
from app.utils.pagination import ListArgsError, in_list, list_response, parse_uuid, severity_rank
from app.utils.validation import json_body

QUESTION_SORTABLE = {
    'order_index': InvestigativeQuestion.order_index,
    'created_at': InvestigativeQuestion.created_at,
    'updated_at': func.coalesce(InvestigativeQuestion.updated_at, InvestigativeQuestion.created_at),
    'priority': severity_rank(InvestigativeQuestion.priority),
    'status': InvestigativeQuestion.status,
    'phase': InvestigativeQuestion.phase,
    'facet': InvestigativeQuestion.facet,
}
QUESTION_FILTERS = {
    'status': (InvestigativeQuestion.status, in_list(InvestigativeQuestion.STATUSES)),
    'priority': (InvestigativeQuestion.priority, in_list(InvestigativeQuestion.PRIORITIES)),
    'phase': (InvestigativeQuestion.phase, 'int'),
    'owner_id': (InvestigativeQuestion.owner_id, 'uuid'),
    'facet': (InvestigativeQuestion.facet, 'eq'),
}
QUESTION_SEARCH = (InvestigativeQuestion.question, InvestigativeQuestion.description,
                   InvestigativeQuestion.answer, InvestigativeQuestion.facet)
MAX_QUESTIONS_PER_PAGE = 200


def _fail(exc):
    return jsonify(exc.to_dict()), exc.status


def _flag(name, default=False):
    raw = (request.args.get(name) or '').strip().lower()
    if not raw:
        return default
    if raw in ('true', '1', 'yes'):
        return True
    if raw in ('false', '0', 'no'):
        return False
    raise ListArgsError(f'{name} must be true or false', 'invalid_filter')


def _owner_me(query, user):
    """``owner=me`` filter (``owner_id`` is the explicit form)."""
    owner = (request.args.get('owner') or '').strip()
    if owner == 'me':
        return query.filter(InvestigativeQuestion.owner_id == user.id)
    if owner:
        raise ListArgsError('owner must be "me" (use owner_id for a user id)', 'invalid_filter')
    return query


def _load(incident_id, question_id):
    return InvestigativeQuestion.query.filter_by(id=question_id, incident_id=incident_id).first()


def _not_found():
    return jsonify({'error': 'not_found', 'message': 'Question not found'}), 404


# ── Per-incident board ───────────────────────────────────────────────────

@api_bp.route('/incidents/<uuid:incident_id>/questions', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_questions(incident_id):
    """List the incident's questions (utils/pagination.py contract; q over
    question/description/answer/facet).

    Filters: status, priority (comma lists), phase, owner_id, owner=me, facet,
    task_id (questions linked to that lead), include_archived. The response
    adds ``summary`` (progress over all non-archived questions, ignoring the
    filters) and every item carries server-resolved ``evidence`` and
    ``lead_ids``.
    """
    user = get_current_user()
    incident = g.incident
    query = InvestigativeQuestion.query.filter_by(incident_id=incident.id)
    if not _flag('include_archived'):
        query = query.filter_by(is_archived=False)
    query = _owner_me(query, user)
    task_id = request.args.get('task_id')
    if task_id:
        query = query.filter(InvestigativeQuestion.id.in_(
            select(QuestionLead.question_id).where(QuestionLead.task_id == parse_uuid('task_id', task_id))))
    body = list_response(
        query, sortable=QUESTION_SORTABLE, default_sort='order_index,created_at', id_col=InvestigativeQuestion.id,
        filters=QUESTION_FILTERS, search_columns=QUESTION_SEARCH, serialize=lambda q: q,
        max_per_page=MAX_QUESTIONS_PER_PAGE, extra={'summary': question_service.summary(incident.id)})
    body['items'] = question_service.serialize_many(body['items'], incident.id, user)
    return jsonify(body), 200


@api_bp.route('/incidents/<uuid:incident_id>/questions', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'create', 'question')
def create_question(incident_id):
    """Create a question: manual (``question`` + optional fields) or from the
    library (``library_ref`` + optional phase/priority/facet/owner_id).
    409 ``duplicate_question`` when it is already on the incident."""
    user = get_current_user()
    incident = g.incident
    data = json_body()
    try:
        question = question_service.create_question(incident, user, data)
        db.session.commit()
    except QuestionError as exc:
        db.session.rollback()
        return _fail(exc)
    except IntegrityError:  # a concurrent request added the same library question
        db.session.rollback()
        return jsonify({'error': 'duplicate_question', 'message': 'This question is already on the incident'}), 409
    realtime.emit_change(incident.id, 'question', 'created', obj=question)
    return jsonify(question_service.serialize_one(question, user)), 201


@api_bp.route('/incidents/<uuid:incident_id>/questions/bulk', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'bulk_add', 'question')
def bulk_add_questions(incident_id):
    """Add up to 100 library questions: ``{refs: ["ss:SSQ-001", ...]}``.

    A merge: questions already on the incident (same ref, or the same text)
    are skipped, never duplicated or resurrected. Unknown refs are a 400 for
    the whole request.
    """
    user = get_current_user()
    incident = g.incident
    data = json_body()
    refs = data.get('refs')
    if not isinstance(refs, list) or not refs or any(not isinstance(r, str) for r in refs):
        return jsonify({'error': 'bad_request', 'message': 'refs must be a non-empty list of library refs'}), 400
    if len(refs) > question_service.MAX_BULK_REFS:
        return jsonify({'error': 'bad_request',
                        'message': f'At most {question_service.MAX_BULK_REFS} refs per request'}), 400
    refs = list(dict.fromkeys(refs))
    unknown = [r[:50] for r in refs if question_library.get(r) is None]
    if unknown:
        return jsonify({'error': 'unknown_library_ref', 'message': 'Unknown library question', 'invalid': unknown}), 400
    created, skipped = [], []
    try:
        for ref in refs:
            try:
                question = question_service.create_question(incident, user, {'library_ref': ref})
            except QuestionError as exc:
                if exc.code == 'duplicate_question':
                    skipped.append({'ref': ref, 'reason': 'exists', 'existing_id': exc.extra.get('existing_id')})
                    continue
                raise
            db.session.flush()
            created.append(question)
        record_changes({}, {}, created=len(created), skipped=len(skipped))
        db.session.commit()
    except QuestionError as exc:
        db.session.rollback()
        return _fail(exc)
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'duplicate_question', 'message': 'A question was added concurrently; retry'}), 409
    if created:
        realtime.emit_resync(incident.id, ['questions'], 'questions_added')
    return jsonify({'created': question_service.serialize_many(created, incident.id, user),
                    'skipped': skipped}), 201


@api_bp.route('/incidents/<uuid:incident_id>/questions/<uuid:question_id>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_question(incident_id, question_id):
    question = _load(g.incident.id, question_id)
    if question is None:
        return _not_found()
    return set_etag(jsonify(question_service.serialize_one(question, get_current_user())), question), 200


@api_bp.route('/incidents/<uuid:incident_id>/questions/<uuid:question_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update', 'question')
def update_question(incident_id, question_id):
    """Edit and answer a question. ``status`` answered needs ``answer`` and
    ``confidence``; unanswerable needs an ``answer`` rationale; confidence
    ``confirmed`` needs at least one evidence ref. ``If-Match`` /
    ``expected_version`` guard against lost updates (409 ``conflict``)."""
    user = get_current_user()
    incident = g.incident
    data = json_body()
    question = _load(incident.id, question_id)
    if question is None:
        return _not_found()
    conflict = precondition(question)
    if conflict:
        return conflict, conflict.status_code
    before = snapshot(question, question_service.AUDITED_FIELDS)
    try:
        question_service.apply_update(incident, question, user, data)
    except QuestionError as exc:
        db.session.rollback()
        return _fail(exc)
    except EvidenceRefsError as exc:
        db.session.rollback()
        return exc.to_response()
    record_changes(before, snapshot(question, question_service.AUDITED_FIELDS))
    conflict = commit_or_conflict(question)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'question', 'updated', obj=question)
    return set_etag(jsonify(question_service.serialize_one(question, user)), question), 200


@api_bp.route('/incidents/<uuid:incident_id>/questions/<uuid:question_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'archive', 'question')
def archive_question(incident_id, question_id):
    """Archive (soft delete) a question. It leaves the default lists but stays
    in the database, so a template re-apply never resurrects it."""
    incident = g.incident
    question = _load(incident.id, question_id)
    if question is None:
        return _not_found()
    conflict = precondition(question)
    if conflict:
        return conflict, conflict.status_code
    before = snapshot(question, ('is_archived',))
    question_service.archive(question)
    record_changes(before, snapshot(question, ('is_archived',)))
    conflict = commit_or_conflict(question)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'question', 'deleted', id=question.id)
    return jsonify({'message': 'Question archived'}), 200


@api_bp.route('/incidents/<uuid:incident_id>/questions/<uuid:question_id>/leads', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'set_leads', 'question')
def set_question_leads(incident_id, question_id):
    """Replace the leads (tasks of this incident) linked to a question:
    ``{task_ids: [...]}``."""
    user = get_current_user()
    incident = g.incident
    data = json_body()
    question = _load(incident.id, question_id)
    if question is None:
        return _not_found()
    before = {'lead_ids': sorted(str(link.task_id) for link in question.lead_links)}
    try:
        ids = question_service.set_leads(incident, question, user, data.get('task_ids'))
    except QuestionError as exc:
        db.session.rollback()
        return _fail(exc)
    record_changes(before, {'lead_ids': sorted(ids)})
    # The links live in a child table, so touch the question: it bumps the
    # version and tells other clients to refetch.
    question.updated_at = func.now()
    conflict = commit_or_conflict(question)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'question', 'updated', obj=question)
    return set_etag(jsonify(question_service.serialize_one(question, user)), question), 200


@api_bp.route('/incidents/<uuid:incident_id>/question-links', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_question_links(incident_id):
    """``[{question_id, task_id}]`` for the incident's non-archived questions
    (the lead queue joins on it)."""
    rows = (db.session.query(QuestionLead.question_id, QuestionLead.task_id)
            .join(InvestigativeQuestion, InvestigativeQuestion.id == QuestionLead.question_id)
            .filter(InvestigativeQuestion.incident_id == g.incident.id, InvestigativeQuestion.is_archived.is_(False))
            .all())
    items = [{'question_id': str(q), 'task_id': str(t)} for q, t in rows]
    return jsonify({'items': items, 'total': len(items)}), 200


@api_bp.route('/incidents/<uuid:incident_id>/questions/report-data', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def question_report_data(incident_id):
    """Report-builder payload: answered / unanswerable / open questions with
    resolved evidence, linked leads and DFIQ attribution."""
    return jsonify(question_service.report_payload(g.incident, get_current_user())), 200


# ── Cross-incident queue (MCP, "my open questions") ──────────────────────

@api_bp.route('/questions', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_all_questions():
    """Questions across the incidents the caller can access.

    Filters: status, priority (comma lists), owner=me / owner_id, incident_id,
    phase. Each item carries a compact ``incident``. Visibility is
    ``accessible_incidents_query``: nothing from an incident the caller cannot
    see is ever returned.
    """
    user = get_current_user()
    visible = accessible_incidents_query(user).with_entities(Incident.id)
    query = InvestigativeQuestion.query.filter(InvestigativeQuestion.is_archived.is_(False),
                                               InvestigativeQuestion.incident_id.in_(visible))
    query = _owner_me(query, user)
    incident_id = request.args.get('incident_id')
    if incident_id:
        query = query.filter(InvestigativeQuestion.incident_id == parse_uuid('incident_id', incident_id))
    body = list_response(
        query, sortable=QUESTION_SORTABLE, default_sort='-priority,order_index', id_col=InvestigativeQuestion.id,
        filters=QUESTION_FILTERS, search_columns=QUESTION_SEARCH, serialize=lambda q: q,
        max_per_page=MAX_QUESTIONS_PER_PAGE)
    rows = body['items']
    ids = {q.incident_id for q in rows}
    incidents = {i.id: i for i in Incident.query.filter(Incident.id.in_(ids)).all()} if ids else {}
    items = []
    for q in rows:
        item = q.to_dict()
        inc = incidents.get(q.incident_id)
        item['incident'] = ({'id': str(inc.id), 'incident_number': inc.incident_number, 'title': inc.title,
                             'severity': inc.severity} if inc else None)
        items.append(item)
    body['items'] = items
    return jsonify(body), 200


# ── Library ──────────────────────────────────────────────────────────────

@api_bp.route('/questions/library', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def question_library_tree():
    """The built-in library: groups (scenarios / core) -> facets -> questions,
    plus the sources with their licence and attribution text."""
    return jsonify(question_library.load_library().tree()), 200


@api_bp.route('/questions/library/<string:ref>', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def question_library_detail(ref):
    qdef = question_library.get(ref)
    if qdef is None:
        return jsonify({'error': 'not_found', 'message': 'Library question not found'}), 404
    return jsonify(qdef.detail()), 200
