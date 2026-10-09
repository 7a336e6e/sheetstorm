"""Items 2, 16, 17, 19: CORS / Socket.IO origins, error handler headers,
production-by-default config, cookie settings, removed dead middleware."""
import pytest


def test_cors_preflight_allows_csrf_header(app):
    client = app.test_client()
    resp = client.options('/api/v1/auth/refresh', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'X-CSRF-TOKEN, Content-Type',
    })
    assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:3000'
    assert 'x-csrf-token' in resp.headers.get('Access-Control-Allow-Headers', '').lower()
    assert resp.headers.get('Access-Control-Allow-Credentials') == 'true'


def test_cors_exposes_download_and_integrity_headers(app):
    resp = app.test_client().get('/api/v1/health', headers={'Origin': 'http://localhost:3000'})
    exposed = {h.strip().lower() for h in resp.headers.get('Access-Control-Expose-Headers', '').split(',')}
    assert {'content-disposition', 'x-report-sha256', 'x-report-id', 'etag'} <= exposed


def test_cors_rejects_unknown_origin(app):
    resp = app.test_client().get('/api/v1/health', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in resp.headers


def test_cors_origins_from_env_and_frontend_url(app):
    from app import _resolve_cors_origins

    class Fake:
        config = {'CORS_ORIGINS': ['https://a.example'], 'FRONTEND_URL': 'https://ui.example/'}
    origins, explicit = _resolve_cors_origins(Fake)
    assert explicit is True
    assert origins[:2] == ['https://a.example', 'https://ui.example']
    assert '*' not in origins

    class Empty:
        config = {'CORS_ORIGINS': [], 'FRONTEND_URL': ''}
    origins, explicit = _resolve_cors_origins(Empty)
    assert explicit is False and 'http://localhost:3000' in origins


@pytest.mark.parametrize('origin,environ,expected', [
    ('http://localhost:3000', {}, True),                                   # allowlisted
    (None, {}, True),                                                       # non-browser
    ('https://ir.corp.example', {'HTTP_HOST': 'ir.corp.example'}, True),    # same-origin
    ('https://ir.corp.example', {'HTTP_HOST': 'backend:5000',
                                 'HTTP_X_FORWARDED_HOST': 'ir.corp.example'}, True),  # behind proxy
    ('https://evil.example', {'HTTP_HOST': 'ir.corp.example'}, False),      # cross-site
    ('https://evil.example', None, False),
])
def test_socketio_origin_check(origin, environ, expected):
    from app import _make_socketio_origin_check
    check = _make_socketio_origin_check(['http://localhost:3000'])
    assert check(origin, environ) is expected


def test_http_exception_keeps_headers(app):
    resp = app.test_client().post('/api/v1/health')
    assert resp.status_code == 405
    assert 'GET' in resp.headers.get('Allow', '')
    assert resp.get_json()['error'] == 'method_not_allowed'


def test_unset_flask_env_means_production(monkeypatch):
    from app import create_app
    monkeypatch.delenv('FLASK_ENV', raising=False)
    # Production refuses the insecure built-in default secrets.
    import app.config as cfg
    monkeypatch.setattr(cfg.ProductionConfig, 'SECRET_KEY', 'dev-secret-key-change-in-production')
    with pytest.raises(RuntimeError, match='production'):
        create_app()


def test_cookie_and_jwt_settings(app):
    assert app.config['JWT_REFRESH_COOKIE_PATH'] == '/api/v1/auth'
    assert app.config['JWT_REFRESH_CSRF_COOKIE_PATH'] == '/'
    assert app.config['JWT_ACCESS_CSRF_COOKIE_PATH'] == '/'


def test_env_bool_override(monkeypatch):
    from app.config import _env_bool
    monkeypatch.setenv('JWT_COOKIE_SECURE', 'false')
    assert _env_bool('JWT_COOKIE_SECURE', True) is False
    monkeypatch.setenv('JWT_COOKIE_SECURE', 'true')
    assert _env_bool('JWT_COOKIE_SECURE', False) is True
    monkeypatch.delenv('JWT_COOKIE_SECURE')
    assert _env_bool('JWT_COOKIE_SECURE', True) is True


def test_testing_config_has_no_real_secrets(app):
    assert app.config['TESTING'] is True
    assert app.config['SECRET_KEY'].startswith('test-only')
    assert app.config['CUSTODY_SIGNING_KEY']


def test_dead_sanitize_middleware_removed(app):
    names = [f.__name__ for f in app.before_request_funcs.get(None, [])]
    assert 'sanitize_input' not in names
