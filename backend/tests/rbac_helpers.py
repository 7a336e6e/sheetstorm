"""Fixtures for the RBAC / guardrail tests (imported into test modules).

Everything is created in throw-away organizations so the shared session
data (orgs A/B and their seeded users) is never disabled or demoted.
"""
import uuid

import pytest

from conftest import TEST_PASSWORD


@pytest.fixture
def new_org(app, db):
    """new_org(slug=None, **settings) -> Organization"""
    from app.models import Organization

    def make(slug=None, settings=None):
        org = Organization(name='t', slug=slug or f'org-{uuid.uuid4().hex[:10]}', settings=settings or {})
        db.session.add(org)
        db.session.commit()
        return org
    return make


@pytest.fixture
def default_org(app, db):
    """The `default` org (registration / Supabase / platform org), created once."""
    from app.models import Organization
    org = Organization.query.filter_by(slug='default').first()
    if not org:
        org = Organization(name='Default Organization', slug='default', settings={})
        db.session.add(org)
        db.session.commit()
    return org


@pytest.fixture
def make_role(app, db):
    """make_role(org, perms, name=None) -> custom Role in `org`"""
    from app.models import Role

    def make(org, perms, name=None):
        role = Role(name=name or f'role-{uuid.uuid4().hex[:10]}', description='', permissions=sorted(perms),
                    is_system=False, organization_id=org.id)
        db.session.add(role)
        db.session.commit()
        return role
    return make


@pytest.fixture
def make_user(app, db, make_role):
    """make_user(org, perms=None, roles=(), active=True) -> User

    `perms` creates a dedicated custom role; `roles` are system role names.
    """
    from app.models import Role, User, UserRole

    def make(org, perms=None, roles=(), active=True):
        u = User(email=f'u-{uuid.uuid4().hex[:12]}@rbac.test', name='rbac', organization_id=org.id,
                 auth_provider='local', is_active=active, is_verified=True)
        u.set_password(TEST_PASSWORD)
        db.session.add(u)
        db.session.flush()
        assigned = [Role.query.filter(Role.organization_id.is_(None), Role.name == n).one() for n in roles]
        if perms is not None:
            assigned.append(make_role(org, perms))
        for role in assigned:
            db.session.add(UserRole(user_id=u.id, role_id=role.id, organization_id=org.id))
        db.session.commit()
        return u
    return make


@pytest.fixture
def emitted(monkeypatch):
    """Captured socketio.emit calls: [(event, payload, room)]."""
    from app import socketio
    calls = []
    monkeypatch.setattr(socketio, 'emit',
                        lambda event, payload=None, room=None, to=None, **kw:
                        calls.append((event, payload, room or to)))
    return calls


def security_events(db, action):
    from app.models import AuditLog
    q = AuditLog.query.filter_by(event_type='security_event', action=action)
    return q.order_by(AuditLog.created_at.desc()).all()


def last_audit(db, action, resource_type):
    from app.models import AuditLog
    db.session.expire_all()
    return (AuditLog.query.filter_by(action=action, resource_type=resource_type)
            .order_by(AuditLog.created_at.desc()).first())
