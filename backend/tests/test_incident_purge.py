"""W1-EVD-CORE: services/incident_purge.py — order of the audited purge
(.plans/_integration.md §1 #23) and the step registry."""
import pytest
from sqlalchemy import text


@pytest.fixture
def steps(monkeypatch):
    """Isolated step registry (restored after the test)."""
    from app.services import incident_purge
    monkeypatch.setattr(incident_purge, '_STEPS', {'pre': [], 'post_commit': []})
    return incident_purge


@pytest.fixture
def archived(app, db, users, make_incident, make_evidence, make_artifact):
    inc = make_incident()
    make_evidence(inc)
    make_artifact(inc)
    inc.is_archived = True
    db.session.commit()
    return inc


def _state(db, iid):
    from app.models import AuditLog, ChainOfCustody, Incident
    return {
        'event': AuditLog.query.filter_by(action='incident_ledger_purged', resource_id=iid).count(),
        'entries': ChainOfCustody.query.filter_by(incident_id=iid).count(),
        'incident': db.session.get(Incident, iid) is not None,
        'guc': db.session.execute(text("SELECT current_setting('sheetstorm.custody_purge', true)")).scalar(),
    }


def test_purge_order_pre_then_guc_then_delete_commit_then_post(app, db, users, archived, steps):
    iid = archived.id
    seen = []

    def pre(ctx):
        assert ctx.incident is not None and ctx.incident.id == iid
        st = _state(db, iid)
        # (2) already recorded, (4) not yet set, nothing deleted.
        assert st['event'] == 1 and st['entries'] == 3 and st['incident'] and st['guc'] in (None, '')
        ctx.data['members'] = ['u1']
        seen.append('pre')

    def post(ctx):
        assert ctx.incident is None and ctx.incident_id == str(iid)
        assert ctx.data['members'] == ['u1'] and ctx.heads['incident']['seq'] == 3
        db.session.expire_all()
        st = _state(db, iid)
        assert st['entries'] == 0 and not st['incident']
        seen.append('post')

    steps.register_purge_step('test_pre', pre)
    steps.register_purge_step('test_post', post, phase='post_commit')
    assert steps.registered_steps('pre') == ['test_pre']
    summary = steps.purge_incident(archived, users['Administrator'])
    assert seen == ['pre', 'post']
    assert summary['counts'] == {'item_count': 2, 'artifact_count': 1, 'entry_count': 3, 'anchor_count': 0}


def test_failing_pre_step_aborts_without_deleting(app, db, users, archived, steps):
    iid = archived.id

    def boom(ctx):
        raise RuntimeError('pre step failed')
    steps.register_purge_step('boom', boom)
    with pytest.raises(steps.PurgeError):
        steps.purge_incident(archived, users['Administrator'])
    db.session.expire_all()
    st = _state(db, iid)
    assert st['incident'] and st['entries'] == 3
    # The heads were still logged before the attempt (defensible record).
    assert st['event'] == 1


def test_failing_post_step_does_not_undo_the_purge(app, db, users, archived, steps):
    iid = archived.id
    steps.register_purge_step('bad_post', lambda ctx: 1 / 0, phase='post_commit')
    steps.purge_incident(archived, users['Administrator'])
    db.session.expire_all()
    assert not _state(db, iid)['incident']


def test_register_purge_step_validation_and_replace(steps):
    with pytest.raises(ValueError):
        steps.register_purge_step('x', lambda c: None, phase='later')
    steps.register_purge_step('x', lambda c: None)
    steps.register_purge_step('x', lambda c: None, phase='post_commit')
    assert steps.registered_steps('pre') == [] and steps.registered_steps('post_commit') == ['x']


def test_purge_endpoint_requires_archive_and_permission(app, users, auth, make_incident):
    inc = make_incident()
    admin = auth(users['Administrator'])
    assert admin.delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 404  # not archived
    assert admin.post(f'/api/v1/incidents/{inc.id}/archive').status_code == 200
    assert auth(users['Analyst']).delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 403
    assert admin.delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 200


def test_permanent_delete_audit_row_written_after_purge(app, db, users, auth, archived):
    """@audit_log on the purge endpoint writes its row after the incident is
    gone: audit_logs has no FK to incidents any more (W1-AUD-BE), so the row
    keeps the dangling incident_id instead of failing."""
    from flask import g
    from app.models import AuditLog, Incident
    iid = archived.id
    g.pop('incident', None)  # the shared test app context may hold an earlier request's incident
    assert auth(users['Administrator']).delete(f'/api/v1/incidents/{iid}/permanent').status_code == 200
    db.session.expire_all()
    assert db.session.get(Incident, iid) is None
    row = AuditLog.query.filter_by(action='permanent_delete', resource_type='incident', resource_id=iid).one()
    assert row.status_code == 200 and row.incident_id == iid and row.chain_seq is not None
    assert AuditLog.query.filter_by(action='incident_ledger_purged', resource_id=iid).count() == 1
