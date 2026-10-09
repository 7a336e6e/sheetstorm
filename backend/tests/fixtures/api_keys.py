"""API-key fixtures (tests/test_api_keys.py).

Keys are created through the service and exchanged through the real
``POST /auth/token`` endpoint; secrets never leave the test process.
"""
import uuid

import pytest


@pytest.fixture
def key_org(app, db):
    """A fresh organization (settings, caps and key names stay isolated)."""
    from app.models import Organization
    tag = uuid.uuid4().hex[:8]
    org = Organization(name=f'keys-{tag}', slug=f'keys-{tag}', settings={})
    db.session.add(org)
    db.session.commit()
    return org


@pytest.fixture
def make_api_key(app, db):
    """make_api_key(owner, scopes, *, name=None, created_by=None, expires_in_days=None)
    -> (ApiKey, full_key)"""
    from app.services import api_key_service

    def make(owner, scopes, *, name=None, created_by=None, expires_in_days=None):
        key, full = api_key_service.create_key(
            owner, created_by or owner, name=name or f'key-{uuid.uuid4().hex[:8]}', scopes=scopes,
            expires_in_days=expires_in_days)
        db.session.commit()
        return key, full
    return make


class KeyClient:
    """Test client authenticated with an API-key access token (Bearer)."""

    def __init__(self, app, token):
        self.client = app.test_client()
        self.token = token

    def open(self, method, path, **kw):
        headers = dict(kw.pop('headers', None) or {})
        headers.setdefault('Authorization', f'Bearer {self.token}')
        return self.client.open(path, method=method, headers=headers, **kw)

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
def exchange_key(app):
    """exchange_key(full_key) -> response of POST /auth/token."""
    def run(full_key, **kw):
        return app.test_client().post('/api/v1/auth/token', json={'api_key': full_key}, **kw)
    return run


@pytest.fixture
def key_client(app, exchange_key):
    """key_client(full_key) -> KeyClient holding a freshly exchanged token."""
    def make(full_key):
        resp = exchange_key(full_key)
        assert resp.status_code == 200, resp.get_json()
        return KeyClient(app, resp.get_json()['access_token'])
    return make
