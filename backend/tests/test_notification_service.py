"""W0-FND: notification_service persists extra_data and links to /dashboard."""
import types


def test_extra_data_persisted(app, db, users):
    from app.models import Notification
    from app.services.notification_service import NotificationService
    n = NotificationService.create_notification(users['Analyst'].id, 'system', 'hello',
                                                extra_data={'stage': 'overdue'})
    db.session.expire_all()
    assert db.session.get(Notification, n.id).extra_data == {'stage': 'overdue'}
    bulk = NotificationService.create_bulk_notifications([users['Analyst'].id], 'system', 'b',
                                                         extra_data={'k': 1})
    db.session.expire_all()
    assert db.session.get(Notification, bulk[0].id).extra_data == {'k': 1}


def test_action_urls_point_at_dashboard(app, monkeypatch):
    from app.services import notification_service as ns
    seen = []
    monkeypatch.setattr(ns.NotificationService, 'create_notification',
                        staticmethod(lambda **kw: seen.append(kw['action_url'])))
    ns.notify_user_assigned('u', types.SimpleNamespace(id='i1', incident_number=1, title='t'))
    ns.notify_task_assigned('u', types.SimpleNamespace(id='t1', incident_id='i1', title='t'))
    assert seen == ['/dashboard/incidents/i1', '/dashboard/incidents/i1?tab=tasks&row=t1']
