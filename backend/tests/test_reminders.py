"""W3-RT-POST: due-date reminders for tasks and improvement actions
(`flask sheetstorm send-due-reminders`, the `send-due-reminders` job, the
`reminder_log` dedupe)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import realtime
from app.services.reminder_service import send_due_reminders

NOW = datetime.now(timezone.utc)


class Recorder:
    server = None

    def __init__(self):
        self.emits = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))


@pytest.fixture
def rt(app):
    rec = Recorder()
    realtime.set_emitter(rec)
    yield rec
    realtime.set_emitter(None)


@pytest.fixture
def world(app, db, make_user, make_incident):
    from app.models import Organization
    org = Organization(name='rem', slug=f'rem-{uuid.uuid4().hex[:8]}', settings={})
    db.session.add(org)
    db.session.commit()
    admin = make_user(org, roles=['Administrator'])
    analyst = make_user(org, roles=['Analyst'])
    inc = make_incident(org=org, creator=admin, title='Case', incident_number=12)
    return {'org': org, 'admin': admin, 'analyst': analyst, 'inc': inc}


def make_task(db, world, assignee=None, due=None, **fields):
    from app.models import Task
    task = Task(incident_id=fields.pop('incident', world['inc']).id, title=fields.pop('title', 'Image the DC'),
                assignee_id=(assignee or world['analyst']).id, due_date=due, created_by=world['admin'].id, **fields)
    db.session.add(task)
    db.session.commit()
    return task


def make_action(db, world, owner=None, due=None, **fields):
    from app.models import ImprovementAction
    action = ImprovementAction(
        organization_id=world['org'].id, incident_id=fields.pop('incident', world['inc']).id,
        incident_ref='#12 Case', title=fields.pop('title', 'Enable MFA'), owner_id=(owner or world['analyst']).id,
        due_date=due, created_by=fields.pop('created_by', world['admin']).id, **fields)
    db.session.add(action)
    db.session.commit()
    return action


def notes(db, user):
    from app.models import Notification
    db.session.expire_all()
    return Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at).all()


def run(world, **kw):
    """Only the test's own organization: the database is shared by every test."""
    return send_due_reminders(now=kw.pop('now', None), organization_ids=[world['org'].id], **kw)


def test_due_soon_then_overdue_each_sent_once(db, world, rt):
    task = make_task(db, world, due=NOW + timedelta(hours=3))
    summary = run(world)
    assert summary['errors'] == 0 and summary['tasks']['due_soon'] >= 1
    [n] = notes(db, world['analyst'])
    assert n.type == 'task_due' and 'due soon' in n.title and task.title in n.title
    assert n.incident_id == world['inc'].id
    assert n.action_url == f"/dashboard/incidents/{world['inc'].id}?tab=tasks&row={task.id}"
    assert n.extra_data == {'entity_type': 'task', 'entity_id': str(task.id), 'stage': 'due_soon',
                            'due_date': task.due_date.isoformat()}
    assert n.is_read is False

    run(world)
    assert len(notes(db, world['analyst'])) == 1          # second run: nothing new

    later = NOW + timedelta(hours=4)                      # the task is now overdue
    run(world, now=later)
    run(world, now=later)
    stages = [x.extra_data['stage'] for x in notes(db, world['analyst'])]
    assert stages == ['due_soon', 'overdue']


def test_notification_is_pushed_to_the_users_room_after_commit(db, world, rt):
    make_task(db, world, due=NOW + timedelta(hours=1))
    run(world)
    pushed = [(d, to) for e, d, to in rt.emits if e == 'notification' and to == f"user_{world['analyst'].id}"]
    assert len(pushed) == 1
    assert pushed[0][0]['type'] == 'task_due' and pushed[0][0]['user_id'] == str(world['analyst'].id)
    assert pushed[0][0]['extra_data']['stage'] == 'due_soon'


def test_changing_the_due_date_rearms_the_reminder(db, world, rt):
    task = make_task(db, world, due=NOW + timedelta(hours=2))
    run(world)
    task.due_date = NOW + timedelta(hours=5)
    db.session.commit()
    run(world)
    assert len(notes(db, world['analyst'])) == 2


@pytest.mark.parametrize('case', ['outside_window', 'no_due_date', 'completed', 'cancelled', 'no_assignee',
                                  'archived_incident', 'inactive_assignee', 'cross_org_assignee'])
def test_tasks_that_must_not_be_reminded(db, world, make_user, make_incident, users, rt, case):
    due = NOW + timedelta(hours=2)
    kw = {}
    assignee = world['analyst']
    if case == 'outside_window':
        due = NOW + timedelta(hours=72)
    elif case == 'no_due_date':
        due = None
    elif case in ('completed', 'cancelled'):
        kw['status'] = case
    elif case == 'archived_incident':
        kw['incident'] = make_incident(org=world['org'], creator=world['admin'], is_archived=True)
    elif case == 'inactive_assignee':
        assignee = make_user(world['org'], roles=['Analyst'], is_active=False)
    elif case == 'cross_org_assignee':
        assignee = users['Analyst']                        # a user of another organization
    task = make_task(db, world, assignee=assignee, due=due, **kw)
    if case == 'no_assignee':
        task.assignee_id = None
        db.session.commit()
    run(world)
    from app.models import Notification, ReminderLog
    assert Notification.query.filter_by(user_id=assignee.id).filter(
        Notification.extra_data['entity_id'].astext == str(task.id)).count() == 0
    assert ReminderLog.query.filter_by(entity_id=task.id).count() == 0


def test_window_hours_parameter(db, world, rt):
    make_task(db, world, due=NOW + timedelta(hours=30))
    run(world, window_hours=24)
    assert notes(db, world['analyst']) == []
    run(world, window_hours=48)
    assert len(notes(db, world['analyst'])) == 1


def test_dry_run_sends_and_records_nothing(db, world, rt):
    task = make_task(db, world, due=NOW + timedelta(hours=1))
    summary = run(world, dry_run=True)
    assert summary['dry_run'] is True and summary['tasks']['due_soon'] >= 1
    from app.models import ReminderLog
    assert notes(db, world['analyst']) == [] and ReminderLog.query.filter_by(entity_id=task.id).count() == 0
    assert rt.emits == []
    run(world)
    assert len(notes(db, world['analyst'])) == 1
    again = run(world, dry_run=True)                              # already sent: a dry run would send nothing for it
    from app.models import ReminderLog as RL
    assert RL.query.filter_by(entity_id=task.id).count() == 1
    assert again['errors'] == 0


def test_existing_reminder_log_row_blocks_a_duplicate(db, world, rt):
    from app.models import ReminderLog
    task = make_task(db, world, due=NOW + timedelta(hours=1))
    db.session.add(ReminderLog(entity_type='task', entity_id=task.id, stage='due_soon',
                               due_date_snapshot=task.due_date, sent_at=NOW))
    db.session.commit()
    run(world)
    assert notes(db, world['analyst']) == []


def test_claim_is_atomic_on_the_unique_constraint(db, world):
    from app.services.reminder_service import _claim
    due = NOW + timedelta(hours=1)
    eid = uuid.uuid4()
    assert _claim('task', eid, 'due_soon', due, NOW, dry_run=False) is True
    assert _claim('task', eid, 'due_soon', due, NOW, dry_run=False) is False     # same snapshot: no second claim
    assert _claim('task', eid, 'overdue', due, NOW, dry_run=False) is True        # other stage
    assert _claim('task', eid, 'due_soon', due + timedelta(hours=1), NOW, dry_run=False) is True  # re-armed
    db.session.rollback()


def test_improvement_action_reminders_owner_and_creator(db, world, make_user, rt):
    responder = make_user(world['org'], roles=['Incident Responder'])
    soon = make_action(db, world, due=NOW + timedelta(hours=5), title='soon', created_by=responder)
    gone = make_action(db, world, due=NOW - timedelta(days=1), title='overdue one', created_by=responder)
    done = make_action(db, world, due=NOW - timedelta(days=1), title='done one', status='done')
    run(world)
    owner_notes = notes(db, world['analyst'])
    by_title = {n.title: n for n in owner_notes}
    assert set(by_title) == {'Improvement action due soon: soon', 'Improvement action overdue: overdue one'}
    n = by_title['Improvement action overdue: overdue one']
    assert n.type == 'improvement_due' and n.action_url == f'/dashboard/improvements?id={gone.id}'
    assert n.extra_data['entity_type'] == 'improvement_action' and n.message.endswith('#12 Case')
    # the creator is told only about the overdue one (and only when it is someone else)
    creator_notes = notes(db, responder)
    assert [x.title for x in creator_notes] == ['Improvement action overdue: overdue one']
    assert soon.id and done.id
    run(world)
    assert len(notes(db, world['analyst'])) == 2 and len(notes(db, responder)) == 1


def test_orphaned_action_without_incident_is_still_reminded(db, world, rt):
    action = make_action(db, world, due=NOW + timedelta(hours=2))
    action.incident_id = None
    db.session.commit()
    run(world)
    [n] = notes(db, world['analyst'])
    assert n.incident_id is None and n.type == 'improvement_due'


def test_action_of_archived_incident_inactive_or_foreign_owner_is_skipped(db, world, make_user, make_incident, users, rt):
    archived = make_incident(org=world['org'], creator=world['admin'], is_archived=True)
    make_action(db, world, due=NOW + timedelta(hours=2), incident=archived)
    inactive = make_user(world['org'], roles=['Analyst'], is_active=False)
    make_action(db, world, due=NOW + timedelta(hours=2), owner=inactive)
    foreign = make_action(db, world, due=NOW + timedelta(hours=2))
    foreign.owner_id = users['Analyst'].id
    db.session.commit()
    run(world)
    reminders = lambda u: [n for n in notes(db, u) if n.type == 'improvement_due']  # noqa: E731
    assert reminders(world['analyst']) == [] and reminders(inactive) == [] and reminders(users['Analyst']) == []


def test_one_failing_organization_does_not_stop_the_others(db, world, org_a, rt, monkeypatch):
    from app.services import reminder_service
    make_task(db, world, due=NOW + timedelta(hours=1))
    real = reminder_service._remind_tasks

    def flaky(org_id, *a, **kw):
        if org_id == org_a.id:
            raise RuntimeError('boom')
        return real(org_id, *a, **kw)

    monkeypatch.setattr(reminder_service, '_remind_tasks', flaky)
    summary = send_due_reminders(organization_ids=[org_a.id, world['org'].id])
    assert summary['errors'] == 1
    assert len(notes(db, world['analyst'])) == 1


# ---------------------------------------------------------------------------
# CLI + job runner (lock, schedule)
# ---------------------------------------------------------------------------

def test_cli_command_prints_a_summary_and_honours_dry_run(app, db, world, rt):
    task = make_task(db, world, due=NOW + timedelta(hours=1))
    org = world['org'].slug
    res = app.test_cli_runner().invoke(
        args=['sheetstorm', 'send-due-reminders', '--dry-run', '--window-hours', '48', '--org', org])
    assert res.exit_code == 0, res.output
    assert '"dry_run": true' in res.output and '"window_hours": 48' in res.output
    assert notes(db, world['analyst']) == []
    res = app.test_cli_runner().invoke(args=['sheetstorm', 'send-due-reminders', '--org', org])
    assert res.exit_code == 0, res.output
    assert len(notes(db, world['analyst'])) == 1 and task.id
    bad = app.test_cli_runner().invoke(args=['sheetstorm', 'send-due-reminders', '--window-hours', '0'])
    assert bad.exit_code != 0


def test_job_is_registered_and_honours_the_run_lock(app, db, world, redis_client, rt, monkeypatch):
    from app import cli
    from app.services import reminder_service
    real = reminder_service.send_due_reminders       # the job runs for the test's organization only
    monkeypatch.setattr(reminder_service, 'send_due_reminders',
                        lambda **kw: real(organization_ids=[world['org'].id], **kw))
    assert 'send-due-reminders' in cli.JOBS
    job = cli.JOBS['send-due-reminders']
    assert job.every_seconds == 900 and job.lock_ttl >= 900
    make_task(db, world, due=NOW + timedelta(hours=1))
    redis_client.delete('jobs:last:send-due-reminders', 'jobs:lock:send-due-reminders')
    try:
        redis_client.set('jobs:lock:send-due-reminders', 'another-runner', ex=60)
        res = app.test_cli_runner().invoke(args=['sheetstorm', 'run-jobs', '--only', 'send-due-reminders'])
        assert 'send-due-reminders: locked' in res.output
        assert notes(db, world['analyst']) == []
        assert redis_client.get('jobs:lock:send-due-reminders') == b'another-runner'

        redis_client.delete('jobs:lock:send-due-reminders')
        res = app.test_cli_runner().invoke(args=['sheetstorm', 'run-jobs', '--only', 'send-due-reminders'])
        assert 'send-due-reminders: ok' in res.output, res.output
        assert len(notes(db, world['analyst'])) == 1
        res = app.test_cli_runner().invoke(args=['sheetstorm', 'run-jobs', '--only', 'send-due-reminders'])
        assert 'send-due-reminders: not_due' in res.output
        res = app.test_cli_runner().invoke(args=['sheetstorm', 'run-jobs', '--only', 'send-due-reminders', '--force'])
        assert 'send-due-reminders: ok' in res.output
        assert len(notes(db, world['analyst'])) == 1      # forced re-run: the reminder_log dedupes
    finally:
        redis_client.delete('jobs:last:send-due-reminders', 'jobs:lock:send-due-reminders')
