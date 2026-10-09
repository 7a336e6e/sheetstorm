"""`flask sheetstorm repair-orphans`: rows whose foreign keys point at nothing.

Orphans are created the only way they can exist: with foreign-key triggers
bypassed (`session_replication_role = replica`), as on installs where parents
were deleted that way. NOT NULL references are deleted (and reported), nullable
ones are cleared.
"""
import json
import uuid

from sqlalchemy import text


def _make_orphans(db, incident):
    ghost = uuid.uuid4()
    db.session.execute(text('SET session_replication_role = replica'))
    db.session.execute(text(
        "INSERT INTO notifications (id, user_id, type, title, is_read, created_at) "
        "VALUES (:id, :u, 'system', 'orphan-test', false, now())"), {'id': uuid.uuid4(), 'u': ghost})
    db.session.execute(text('UPDATE incidents SET created_by = :u WHERE id = :i'), {'u': ghost, 'i': incident.id})
    db.session.execute(text('SET session_replication_role = origin'))
    db.session.commit()
    return ghost


def test_report_then_repair(app, db, users, make_incident, tmp_path):
    from app.models import Incident, Notification
    inc = make_incident()
    ghost = _make_orphans(db, inc)
    runner = app.test_cli_runner()

    out = runner.invoke(args=['sheetstorm', 'repair-orphans']).output
    assert 'notifications.user_id -> users.id: 1 orphaned row(s) (delete)' in out
    assert 'incidents.created_by -> users.id: 1 orphaned row(s) (reassign (needs --reassign-to))' in out
    assert 'Report only' in out
    assert Notification.query.filter_by(user_id=ghost).count() == 1  # nothing changed

    # Without --reassign-to the required author reference is left (never deleted).
    report = tmp_path / 'repair.json'
    result = runner.invoke(args=['sheetstorm', 'repair-orphans', '--apply', '--report', str(report)])
    assert result.exit_code == 0, result.output
    assert 'Repaired: 1 row(s) deleted, 0 reference(s) cleared, 0 reassigned.' in result.output
    assert 'Left as is: incidents.created_by' in result.output
    db.session.expire_all()
    assert Notification.query.filter_by(user_id=ghost).count() == 0
    assert db.session.get(Incident, inc.id) is not None  # the incident itself is never deleted

    data = json.loads(report.read_text())
    assert data['deleted_rows'][0]['table'] == 'notifications'
    assert data['deleted_rows'][0]['row']['title'] == 'orphan-test'

    admin = users['Administrator']
    result = runner.invoke(args=['sheetstorm', 'repair-orphans', '--apply', '--reassign-to', admin.email.upper()])
    assert '1 reassigned' in result.output, result.output
    db.session.expire_all()
    assert db.session.get(Incident, inc.id).created_by == admin.id
    assert 'No orphaned rows found.' in runner.invoke(args=['sheetstorm', 'repair-orphans']).output
    assert runner.invoke(args=['sheetstorm', 'repair-orphans', '--reassign-to', 'nobody@x.test']).exit_code != 0


def test_clean_database_reports_nothing(app):
    assert 'No orphaned rows found.' in app.test_cli_runner().invoke(args=['sheetstorm', 'repair-orphans']).output
