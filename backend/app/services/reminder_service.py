"""Due-date reminders for tasks and improvement actions (W3-RT-POST).

``send_due_reminders`` is run by ``flask sheetstorm send-due-reminders`` and,
every 15 minutes, by the jobs runner (``flask sheetstorm run-jobs``).

For each organization (queries stay ``organization_id``-scoped) it selects
open tasks / improvement actions whose due date is within the window or
already past, whose assignee/owner is an active user of the same
organization, and whose incident is not archived. The stage is ``overdue``
when the due date has passed, else ``due_soon``.

Idempotence: a row is inserted into ``reminder_log`` first with
``INSERT ... ON CONFLICT DO NOTHING RETURNING id`` on the unique
``(entity_type, entity_id, stage, due_date_snapshot)``; only a newly inserted
row produces a notification, in the same transaction. Two overlapping runs
therefore notify once, and changing a due date re-arms both stages.
Notifications are pushed to ``user_<id>`` after commit through
``realtime.emit_to_user`` (write-only Redis emitter under the CLI).
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_HOURS = 24
BATCH_SIZE = 500
TASK_DONE_STATUSES = ('completed', 'cancelled')
STAGES = ('due_soon', 'overdue')


def stage_for(due_date, now):
    return 'overdue' if due_date < now else 'due_soon'


def _claim(entity_type, entity_id, stage, due_date, now, dry_run):
    """True when this (entity, stage, due-date) has not been reminded yet.
    Unless ``dry_run`` the claim is recorded (and survives only if the caller
    commits)."""
    from app.models import ReminderLog
    if dry_run:
        return not db.session.query(ReminderLog.id).filter_by(
            entity_type=entity_type, entity_id=entity_id, stage=stage, due_date_snapshot=due_date).first()
    stmt = pg_insert(ReminderLog).values(
        entity_type=entity_type, entity_id=entity_id, stage=stage,
        due_date_snapshot=due_date, sent_at=now, created_at=now,
    ).on_conflict_do_nothing(constraint='uq_reminder_log_entity_stage').returning(ReminderLog.id)
    return db.session.execute(stmt).scalar() is not None


def _due_text(due_date):
    return due_date.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def _task_batches(org_id, horizon, batch_size):
    from app.models import Incident, Task, User
    last = None
    while True:
        query = (db.session.query(Task, Incident)
                 .join(Incident, Incident.id == Task.incident_id)
                 .join(User, User.id == Task.assignee_id)
                 .filter(Incident.organization_id == org_id,
                         Incident.is_archived.is_(False),
                         User.is_active.is_(True),
                         User.organization_id == org_id,
                         Task.due_date.isnot(None),
                         Task.due_date <= horizon,
                         or_(Task.status.is_(None), Task.status.notin_(TASK_DONE_STATUSES))))
        if last is not None:
            query = query.filter(Task.id > last)
        rows = query.order_by(Task.id).limit(batch_size).all()
        if not rows:
            return
        last = rows[-1][0].id
        yield rows


def _action_batches(org_id, horizon, batch_size):
    from app.models import ImprovementAction, Incident, User
    from app.models.post_incident import ACTION_OPEN_STATUSES
    last = None
    while True:
        query = (db.session.query(ImprovementAction)
                 .join(User, User.id == ImprovementAction.owner_id)
                 .outerjoin(Incident, Incident.id == ImprovementAction.incident_id)
                 .filter(ImprovementAction.organization_id == org_id,
                         ImprovementAction.status.in_(ACTION_OPEN_STATUSES),
                         ImprovementAction.due_date.isnot(None),
                         ImprovementAction.due_date <= horizon,
                         User.is_active.is_(True),
                         User.organization_id == org_id,
                         or_(ImprovementAction.incident_id.is_(None), Incident.is_archived.is_(False))))
        if last is not None:
            query = query.filter(ImprovementAction.id > last)
        rows = query.order_by(ImprovementAction.id).limit(batch_size).all()
        if not rows:
            return
        last = rows[-1].id
        yield rows


def _notification(user_id, ntype, title, message, incident_id, action_url, extra):
    from app.models import Notification
    n = Notification(user_id=user_id, type=ntype, title=title[:255], message=message,
                     incident_id=incident_id, action_url=action_url, extra_data=extra)
    db.session.add(n)
    return n


def _remind_tasks(org_id, horizon, now, dry_run, batch_size, summary, pending):
    for rows in _task_batches(org_id, horizon, batch_size):
        for task, incident in rows:
            stage = stage_for(task.due_date, now)
            if not _claim('task', task.id, stage, task.due_date, now, dry_run):
                continue
            summary['tasks'][stage] += 1
            if dry_run:
                continue
            label = 'overdue' if stage == 'overdue' else 'due soon'
            pending.append(_notification(
                task.assignee_id, 'task_due', f'Task {label}: {task.title}',
                f'Due {_due_text(task.due_date)} - Incident #{incident.incident_number} {incident.title}',
                incident.id, f'/dashboard/incidents/{incident.id}?tab=tasks&row={task.id}',
                {'entity_type': 'task', 'entity_id': str(task.id), 'stage': stage,
                 'due_date': task.due_date.isoformat()}))
        if not dry_run:
            db.session.commit()
            push_notifications(pending)


def _remind_actions(org_id, horizon, now, dry_run, batch_size, summary, pending):
    from app.models import User
    for rows in _action_batches(org_id, horizon, batch_size):
        for action in rows:
            stage = stage_for(action.due_date, now)
            if not _claim('improvement_action', action.id, stage, action.due_date, now, dry_run):
                continue
            summary['improvement_actions'][stage] += 1
            if dry_run:
                continue
            label = 'overdue' if stage == 'overdue' else 'due soon'
            message = f'Due {_due_text(action.due_date)}' + (f' - {action.incident_ref}' if action.incident_ref else '')
            extra = {'entity_type': 'improvement_action', 'entity_id': str(action.id), 'stage': stage,
                     'due_date': action.due_date.isoformat()}
            url = f'/dashboard/improvements?id={action.id}'
            pending.append(_notification(action.owner_id, 'improvement_due',
                                         f'Improvement action {label}: {action.title}', message,
                                         action.incident_id, url, extra))
            # An overdue action also tells its creator when that is someone else.
            if stage == 'overdue' and action.created_by and action.created_by != action.owner_id:
                creator = db.session.get(User, action.created_by)
                if creator is not None and creator.is_active and creator.organization_id == org_id:
                    pending.append(_notification(creator.id, 'improvement_due',
                                                 f'Improvement action overdue: {action.title}', message,
                                                 action.incident_id, url, extra))
        if not dry_run:
            db.session.commit()
            push_notifications(pending)


def push_notifications(pending):
    """Push committed notifications to their users' rooms and clear the list."""
    from app.services import realtime
    for notification in pending:
        try:
            realtime.emit_to_user(str(notification.user_id), 'notification', notification.to_dict())
        except Exception:
            logger.warning('reminder: could not push notification %s', notification.id, exc_info=True)
    pending.clear()


def send_due_reminders(window_hours=DEFAULT_WINDOW_HOURS, dry_run=False, now=None, batch_size=BATCH_SIZE,
                       organization_ids=None):
    """Create the due / overdue reminders that have not been sent yet.

    Returns ``{'window_hours', 'dry_run', 'tasks': {due_soon, overdue},
    'improvement_actions': {due_soon, overdue}, 'errors': n}``. With
    ``dry_run`` nothing is written; the counts are what a real run would send.
    ``organization_ids`` limits the run to those organizations.
    An organization that fails is rolled back and counted in ``errors``
    (the others still run); the caller decides whether that is fatal.
    """
    from app.models import Organization
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=window_hours)
    summary = {'window_hours': window_hours, 'dry_run': dry_run,
               'tasks': dict.fromkeys(STAGES, 0), 'improvement_actions': dict.fromkeys(STAGES, 0), 'errors': 0}
    orgs = db.session.query(Organization.id).order_by(Organization.id)
    if organization_ids is not None:
        orgs = orgs.filter(Organization.id.in_(list(organization_ids)))
    for org_id in [o[0] for o in orgs.all()]:
        pending = []
        try:
            _remind_tasks(org_id, horizon, now, dry_run, batch_size, summary, pending)
            _remind_actions(org_id, horizon, now, dry_run, batch_size, summary, pending)
            if not dry_run:
                db.session.commit()
                push_notifications(pending)
        except Exception:
            logger.exception('reminder: organization %s failed', org_id)
            db.session.rollback()
            summary['errors'] += 1
    return summary
