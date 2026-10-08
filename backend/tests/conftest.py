"""Shared pytest fixtures for the SheetStorm backend.

The suite runs against a REAL PostgreSQL + Redis (see tests/run_in_docker.sh,
which provisions throwaway containers). Required environment:

    TEST_DATABASE_URL  postgresql://.../<name containing "test">
    TEST_REDIS_URL     redis://host:6379/<db>
    DB_INIT_DIR        directory with database/init/*.sql (optional; when set
                       the test database is wiped and rebuilt from the init
                       SQL + the full Alembic chain once per session)

Safety: the database is only wiped when its name contains "test".
"""
import glob
import os
import uuid
from urllib.parse import urlparse

import pytest

# Test-only secrets must be in the environment before `app` is imported
# (EncryptionService reads FERNET_KEY at construction time).
os.environ.setdefault('FERNET_KEY', 'dGVzdC1vbmx5LWZlcm5ldC1rZXktMzJieXRlcyEhISE=')
os.environ.setdefault('REDIS_URL', os.environ.get('TEST_REDIS_URL', 'memory://'))

ROLE_NAMES = ['Administrator', 'Incident Responder', 'Analyst', 'Manager', 'Operator', 'Viewer']
TEST_PASSWORD = 'Sup3r-Secret-Passw0rd!'


def _require_test_db_url():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.exit('TEST_DATABASE_URL is not set — run tests via tests/run_in_docker.sh', returncode=2)
    dbname = urlparse(url).path.lstrip('/')
    if 'test' not in dbname:
        pytest.exit(f'Refusing to use database {dbname!r}: name must contain "test"', returncode=2)
    return url


def _reset_database(engine, init_dir):
    """Drop everything and rebuild from database/init/*.sql (fresh install)."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public'))
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for path in sorted(glob.glob(os.path.join(init_dir, '*.sql'))):
            with open(path, encoding='utf-8') as fh:
                cur.execute(fh.read())
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(scope='session')
def app():
    _require_test_db_url()
    from app import create_app, db
    import app as app_pkg

    application = create_app('testing')
    with application.app_context():
        init_dir = os.environ.get('DB_INIT_DIR')
        if init_dir:
            db.engine.dispose()
            _reset_database(db.engine, init_dir)
            from flask_migrate import upgrade
            upgrade()
            # alembic's fileConfig() disables already-created loggers; undo
            # that so log assertions keep working in-process.
            import logging
            for lg in logging.root.manager.loggerDict.values():
                if isinstance(lg, logging.Logger):
                    lg.disabled = False
        if app_pkg.redis_client is not None:
            app_pkg.redis_client.flushdb()
        _seed(db)
        yield application
        db.session.remove()


def _seed(db):
    from app.models import Organization, User, Role, UserRole
    from app.services.mitre_suggest_service import save_patterns

    def org(slug):
        o = Organization.query.filter_by(slug=slug).first()
        if not o:
            o = Organization(name=slug, slug=slug, settings={})
            db.session.add(o)
            db.session.flush()
        return o

    org_a, org_b = org('test-org-a'), org('test-org-b')

    def user(email, org_, role_name):
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=email.split('@')[0], organization_id=org_.id,
                     auth_provider='local', is_active=True, is_verified=True)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
            role = Role.query.filter_by(name=role_name).one()
            db.session.add(UserRole(user_id=u.id, role_id=role.id, organization_id=org_.id))
        return u

    for name in ROLE_NAMES:
        user(f"{name.lower().replace(' ', '_')}@a.test", org_a, name)
    user('admin@b.test', org_b, 'Administrator')
    db.session.commit()

    pattern = {'technique': 'T1059', 'tactic': 'execution', 'name': 'Command and Scripting Interpreter',
               'keywords': ['powershell', 'cmd.exe'], 'regex': [], 'weight': 0.8}
    save_patterns([pattern], str(org_a.id))
    save_patterns([dict(pattern, technique='T1046', name='Network Service Discovery',
                        tactic='discovery', keywords=['nmap'])], str(org_b.id))


@pytest.fixture
def db(app):
    from app import db as _db
    yield _db
    _db.session.rollback()


@pytest.fixture
def org_a(app):
    from app.models import Organization
    return Organization.query.filter_by(slug='test-org-a').one()


@pytest.fixture
def org_b(app):
    from app.models import Organization
    return Organization.query.filter_by(slug='test-org-b').one()


@pytest.fixture
def users(app):
    """{'Administrator': User, ..., 'Viewer': User, 'admin_b': User} (org A unless noted)."""
    from app.models import User
    result = {name: User.query.filter_by(email=f"{name.lower().replace(' ', '_')}@a.test").one()
              for name in ROLE_NAMES}
    result['admin_b'] = User.query.filter_by(email='admin@b.test').one()
    return result


class AuthClient:
    """Test client that authenticates as a user via Bearer header or cookies."""

    def __init__(self, app, user, mode='bearer'):
        from app.api.v1.endpoints.auth import issue_tokens
        self.app = app
        self.user = user
        self.mode = mode
        self.client = app.test_client()
        with app.app_context():
            self.access_token, self.refresh_token = issue_tokens(user)
        if mode == 'cookie':
            from flask_jwt_extended import get_csrf_token
            with app.app_context():
                self.csrf = get_csrf_token(self.access_token)
            self.client.set_cookie('access_token_cookie', self.access_token)
            self.client.set_cookie('csrf_access_token', self.csrf)

    def _headers(self, method, headers):
        headers = dict(headers or {})
        if self.mode == 'bearer':
            headers.setdefault('Authorization', f'Bearer {self.access_token}')
        elif method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            headers.setdefault('X-CSRF-TOKEN', self.csrf)
        return headers

    def open(self, method, path, **kwargs):
        kwargs['headers'] = self._headers(method, kwargs.get('headers'))
        return self.client.open(path, method=method, **kwargs)

    def get(self, path, **kw):
        return self.open('GET', path, **kw)

    def post(self, path, **kw):
        return self.open('POST', path, **kw)

    def put(self, path, **kw):
        return self.open('PUT', path, **kw)

    def patch(self, path, **kw):
        return self.open('PATCH', path, **kw)

    def delete(self, path, **kw):
        return self.open('DELETE', path, **kw)


@pytest.fixture
def auth(app):
    """auth(user, mode='bearer'|'cookie') -> AuthClient"""
    def make(user, mode='bearer'):
        return AuthClient(app, user, mode)
    return make


@pytest.fixture
def make_incident(app, db, org_a, users):
    """make_incident(org=None, creator=None, tlp='amber', assign=[users], **fields) -> Incident"""
    from app.models import Incident, IncidentAssignment

    def make(org=None, creator=None, tlp='amber', assign=(), **fields):
        org = org or org_a
        creator = creator or (users['admin_b'] if org.slug == 'test-org-b' else users['Administrator'])
        inc = Incident(organization_id=org.id, title=fields.pop('title', f'Incident {uuid.uuid4().hex[:8]}'),
                       severity=fields.pop('severity', 'high'), status=fields.pop('status', 'open'),
                       phase=fields.pop('phase', 1), tlp=tlp, created_by=creator.id, **fields)
        db.session.add(inc)
        db.session.flush()
        for u in assign:
            db.session.add(IncidentAssignment(incident_id=inc.id, user_id=u.id, assigned_by=creator.id))
        db.session.commit()
        return inc
    return make


@pytest.fixture
def redis_client(app):
    import app as app_pkg
    return app_pkg.redis_client
