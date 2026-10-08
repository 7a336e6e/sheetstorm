"""Items 10, 17: AI-provider and integration lookups are organization-scoped
(never another org's integration) and openai_compatible never receives the
real OPENAI_API_KEY."""
import json
import socket

import pytest


@pytest.fixture
def integration(app, db):
    from app.models import Integration
    from app.services.encryption_service import encryption_service
    created = []

    def make(org, user, itype, config=None, creds=None, name=None):
        i = Integration(organization_id=org.id, type=itype, name=name or f'{itype}-{len(created)}',
                        is_enabled=True, config=config or {}, created_by=user.id,
                        credentials_encrypted=encryption_service.encrypt(json.dumps(creds)) if creds else None)
        db.session.add(i)
        db.session.commit()
        created.append(i)
        return i
    yield make
    for i in created:
        db.session.delete(i)
    db.session.commit()


@pytest.fixture(autouse=True)
def _no_env_ai(app, monkeypatch):
    for k in ('OPENAI_API_KEY', 'GOOGLE_AI_API_KEY', 'OLLAMA_BASE_URL', 'OPENAI_BASE_URL',
              'OPENAI_COMPATIBLE_API_KEY'):
        monkeypatch.setitem(app.config, k, '')


def test_openai_key_never_leaks_across_orgs(app, users, org_b, integration):
    from app.services.ai_service import ai_service
    integration(org_b, users['admin_b'], 'openai', creds={'api_key': 'sk-org-b'})
    with app.app_context():
        assert ai_service.openai_api_key(str(users['Administrator'].organization_id)) is None
        assert ai_service.get_available_providers(str(users['Administrator'].organization_id)) == []
        assert ai_service.get_available_providers(None) == []
        assert ai_service.openai_api_key(str(org_b.id)) == 'sk-org-b'
        assert ai_service.get_available_providers(str(org_b.id)) == ['openai']


def test_report_types_endpoint_scoped(app, users, auth, org_b, integration, make_incident):
    integration(org_b, users['admin_b'], 'openai', creds={'api_key': 'sk-org-b'})
    inc = make_incident()
    body = auth(users['Administrator']).get(f'/api/v1/incidents/{inc.id}/reports/types').get_json()
    assert body.get('providers', []) == [] and body.get('ai_configured') is False


def test_ollama_url_requires_allowlist(app, users, org_a, integration, monkeypatch):
    from app.services.ai_service import ai_service
    monkeypatch.setattr(socket, 'getaddrinfo',
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('172.18.0.9', 0))])
    integration(org_a, users['Administrator'], 'ollama', config={'base_url': 'http://ollama:11434'})
    with app.app_context():
        monkeypatch.setitem(app.config, 'OUTBOUND_URL_ALLOWLIST', [])
        assert ai_service.ollama_base_url(str(org_a.id)) is None
        monkeypatch.setitem(app.config, 'OUTBOUND_URL_ALLOWLIST', ['ollama'])
        assert ai_service.ollama_base_url(str(org_a.id)) == 'http://ollama:11434'


def test_metadata_llm_endpoint_refused(app, users, org_a, integration, monkeypatch):
    from app.services.ai_service import ai_service
    monkeypatch.setattr(socket, 'getaddrinfo',
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 0))])
    monkeypatch.setitem(app.config, 'OUTBOUND_URL_ALLOWLIST', ['meta'])
    integration(org_a, users['Administrator'], 'openai_compatible', config={'base_url': 'http://meta/v1'})
    with app.app_context():
        assert ai_service._resolve_openai_compatible(str(org_a.id)) == (None, None, None)


def test_openai_compatible_env_uses_its_own_key(app, monkeypatch):
    from app.services.ai_service import ai_service
    monkeypatch.setitem(app.config, 'OPENAI_API_KEY', 'sk-REAL-openai')
    monkeypatch.setitem(app.config, 'OPENAI_BASE_URL', 'http://vllm:8000/v1')
    with app.app_context():
        assert ai_service._resolve_openai_compatible(None)[2] == 'sk-local'
        monkeypatch.setitem(app.config, 'OPENAI_COMPATIBLE_API_KEY', 'sk-compat')
        assert ai_service._resolve_openai_compatible(None)[2] == 'sk-compat'


def test_integration_config_resolver_scoped(app, users, org_a, org_b, integration):
    from app.services.integration_config import config_resolver
    integration(org_b, users['admin_b'], 'google_drive', creds={'client_id': 'b-id', 'client_secret': 'b-sec'})
    with app.app_context():
        # Without/with another org: only env defaults, never org B's secrets.
        assert 'client_id' not in (config_resolver.get_credentials('google_drive') or {})
        assert 'client_id' not in (config_resolver.get_credentials('google_drive', str(org_a.id)) or {})
        assert config_resolver.get_credentials('google_drive', str(org_b.id))['client_id'] == 'b-id'
        assert config_resolver.get_config('google_drive') == {}


def test_drive_oauth_config_scoped(app, users, org_a, org_b, integration):
    from app.services.google_drive_service import google_drive_service
    integration(org_b, users['admin_b'], 'google_drive', creds={'client_id': 'b-id', 'client_secret': 'b-sec'})
    with app.app_context():
        assert google_drive_service.is_configured(str(org_b.id)) is True
        assert google_drive_service.is_configured(str(org_a.id)) is False
        assert google_drive_service.get_oauth_config(str(org_a.id))['client_id'] == ''


def test_github_login_ignores_tenant_oauth_app(app, users, org_b, integration):
    from app.api.v1.endpoints.auth import _get_github_credentials
    integration(org_b, users['admin_b'], 'oauth_github', creds={'client_id': 'evil', 'client_secret': 'x'})
    with app.test_request_context():
        assert _get_github_credentials()[0] != 'evil'
