"""Audited, irreversible incident purge (the ONLY body of
``DELETE /incidents/<id>/permanent``; .plans/_integration.md §1 #23, C6).

Order (do not change):

1. Legal-hold check on artifacts **and** evidence items -> ``PurgeBlocked`` (409).
2. ``log_security_event('incident_ledger_purged', {heads...})``: the final
   incident/item ledger heads are written to the audit log *before* anything
   is deleted. If that row cannot be written the purge is aborted.
3. ``pre`` steps (inside the delete transaction, before the delete).
4. ``SELECT set_config('sheetstorm.custody_purge', <incident_id>, true)``:
   the transaction-local GUC is the only thing ``custody_append_only()``
   accepts for a DELETE on ``chain_of_custody`` / ``custody_anchors``, and
   only for rows of that incident.
5. ``db.session.delete(incident)``: evidence, artifacts and the ledger go via
   the DB ``ON DELETE CASCADE`` (``passive_deletes``; the ORM never touches
   them row by row).
6. Commit.
7. ``post_commit`` steps (failures are logged, never raised: the purge is done).

Feature work packages register steps instead of editing the endpoint::

    from app.services.incident_purge import register_purge_step
    register_purge_step('report_files', delete_report_files, phase='post_commit')

A step is ``fn(ctx: PurgeContext)``. In ``pre`` steps ``ctx.incident`` is the
live ORM object; steps may stash values in ``ctx.data`` for a later
``post_commit`` step (e.g. user ids to evict). In ``post_commit`` steps
``ctx.incident`` is None (the row is gone): use ``ctx.incident_id``,
``ctx.organization_id`` and ``ctx.data``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import func, or_, text

from app import db

logger = logging.getLogger(__name__)

PHASES = ('pre', 'post_commit')
MAX_ITEM_HEADS_IN_EVENT = 500

_STEPS: dict[str, list] = {'pre': [], 'post_commit': []}


@dataclass
class PurgeContext:
    incident_id: str
    organization_id: str
    incident_number: Optional[int]
    title: str
    actor: Any
    heads: dict
    incident: Any = None
    data: dict = field(default_factory=dict)


class PurgeBlocked(Exception):
    """409: evidence under legal hold."""
    status = 409

    def __init__(self, held_artifact_ids, held_evidence_item_ids):
        self.held_artifact_ids = [str(i) for i in held_artifact_ids]
        self.held_evidence_item_ids = [str(i) for i in held_evidence_item_ids]
        parts = []
        if self.held_artifact_ids:
            parts.append(f'{len(self.held_artifact_ids)} artifact(s)')
        if self.held_evidence_item_ids:
            parts.append(f'{len(self.held_evidence_item_ids)} evidence item(s)')
        self.message = (f"{' and '.join(parts)} are under legal hold; release the hold(s) before "
                        'permanently deleting this incident')
        super().__init__(self.message)

    def to_dict(self):
        return {'error': 'conflict', 'code': 'legal_hold', 'message': self.message,
                'held_artifact_ids': self.held_artifact_ids,
                'held_evidence_item_ids': self.held_evidence_item_ids}


class PurgeError(Exception):
    """The purge could not be recorded or executed (nothing was deleted)."""
    status = 500

    def __init__(self, message, status=500):
        super().__init__(message)
        self.message = message
        self.status = status

    def to_dict(self):
        return {'error': 'purge_failed', 'message': self.message}


def register_purge_step(name: str, fn: Callable[[PurgeContext], None], phase: str = 'pre') -> None:
    """Register (or replace, by name) a purge step. ``phase``: 'pre' | 'post_commit'."""
    if phase not in PHASES:
        raise ValueError(f'phase must be one of {PHASES}')
    if not name or not callable(fn):
        raise ValueError('name and callable fn are required')
    for ph in PHASES:
        _STEPS[ph] = [(n, f) for n, f in _STEPS[ph] if n != name]
    _STEPS[phase].append((name, fn))


def registered_steps(phase: str) -> list:
    return [n for n, _ in _STEPS[phase]]


def _held(incident_id):
    """Ids of artifacts and items with an active hold (column queries only:
    nothing is loaded into the session, so the ORM cannot cascade them)."""
    from app.models import Artifact, EvidenceItem
    now = datetime.now(timezone.utc)

    def active(model):
        return or_(model.is_locked.is_(True), model.legal_hold_until > now)

    arts = [r[0] for r in db.session.query(Artifact.id)
            .filter(Artifact.incident_id == incident_id, active(Artifact)).all()]
    items = [r[0] for r in db.session.query(EvidenceItem.id)
             .filter(EvidenceItem.incident_id == incident_id, active(EvidenceItem)).all()]
    return arts, items


def _counts(incident_id):
    from app.models import Artifact, ChainOfCustody, CustodyAnchor, EvidenceItem

    def count(model):
        return db.session.query(func.count(model.id)).filter(model.incident_id == incident_id).scalar() or 0

    return {'item_count': count(EvidenceItem), 'artifact_count': count(Artifact),
            'entry_count': count(ChainOfCustody), 'anchor_count': count(CustodyAnchor)}


def purge_incident(incident, actor) -> dict:
    """Permanently delete ``incident`` (see module docstring for the order).

    Raises ``PurgeBlocked`` (409) when evidence is under legal hold and
    ``PurgeError`` when the purge could not be recorded or committed (nothing
    deleted). Returns a summary ``{incident_id, heads, counts}``.
    """
    from app.middleware.audit import log_security_event
    from app.services.custody_ledger import CustodyLedger

    iid = str(incident.id)

    # (1) legal holds
    held_artifacts, held_items = _held(incident.id)
    if held_artifacts or held_items:
        raise PurgeBlocked(held_artifacts, held_items)

    # (2) record the final ledger heads before anything is deleted
    heads = CustodyLedger.heads(incident.id)
    counts = _counts(incident.id)
    item_heads = dict(sorted(heads['items'].items())[:MAX_ITEM_HEADS_IN_EVENT])
    inc_head = heads['incident'] or {}
    details = {
        'incident_id': iid,
        'incident_number': incident.incident_number,
        'title': incident.title,
        'incident_head_seq': inc_head.get('seq'),
        'incident_head_hash': inc_head.get('hash'),
        'item_heads': item_heads,
        'item_heads_truncated': len(heads['items']) > len(item_heads),
        **counts,
    }
    ctx = PurgeContext(incident_id=iid, organization_id=str(incident.organization_id),
                       incident_number=incident.incident_number, title=incident.title,
                       actor=actor, heads=heads, incident=incident)
    event = log_security_event('incident_ledger_purged', resource_type='incident', resource_id=incident.id,
                               incident_id=incident.id, details=details, user=actor)
    if event is None:
        raise PurgeError('The purge could not be recorded in the audit log; nothing was deleted', status=503)

    try:
        # (3) pre steps
        for name, fn in list(_STEPS['pre']):
            fn(ctx)
        # (4) allow the ledger cascade for this incident only (transaction-local)
        db.session.execute(text("SELECT set_config('sheetstorm.custody_purge', :iid, true)"), {'iid': iid})
        # (5) delete; evidence + ledger go through the DB cascade
        db.session.delete(incident)
        # (6) commit
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception('Incident purge failed for %s', iid)
        raise PurgeError(f'Incident purge failed: {exc.__class__.__name__}') from exc

    # (7) post-commit steps
    ctx.incident = None
    for name, fn in list(_STEPS['post_commit']):
        try:
            fn(ctx)
        except Exception:
            logger.exception('Incident purge post-commit step %r failed for %s', name, iid)

    return {'incident_id': iid, 'heads': heads, 'counts': counts}
