"""W0-FND: admin-configurable AI TLP policy, enforced in ai_service dispatch.

Org setting ai_tlp_policy {tlp: allow|local_only|block}; defaults red and
amber_strict -> local_only, others -> allow. local_only = ollama /
openai_compatible whose host is non-public AND on OUTBOUND_URL_ALLOWLIST.
"""
import os
import re
import socket

import pytest

TLPS = ['white', 'green', 'amber', 'amber_strict', 'red']
MODES = ['allow', 'local_only', 'block']
# provider kind -> provider name configured for it in the `ai_env` fixture
KINDS = {'cloud': 'openai', 'internal_allowlisted': 'ollama', 'internal_not_allowlisted': 'openai_compatible'}


@pytest.fixture
def ai_env(app, monkeypatch):
    """openai (cloud), ollama at a private allowlisted host, openai_compatible
    at a private host that is NOT allowlisted (env-configured endpoints)."""
    for k in ('OPENAI_API_KEY', 'GOOGLE_AI_API_KEY', 'OLLAMA_BASE_URL', 'OPENAI_BASE_URL',
              'OPENAI_COMPATIBLE_API_KEY'):
        monkeypatch.setitem(app.config, k, '')

    def configure(*kinds):
        if 'cloud' in kinds:
            monkeypatch.setitem(app.config, 'OPENAI_API_KEY', 'sk-test-only')
        if 'internal_allowlisted' in kinds:
            monkeypatch.setitem(app.config, 'OLLAMA_BASE_URL', 'http://ollama:11434')
        if 'internal_not_allowlisted' in kinds:
            monkeypatch.setitem(app.config, 'OPENAI_BASE_URL', 'http://vllm:8000/v1')
        if 'public_local' in kinds:
            monkeypatch.setitem(app.config, 'OLLAMA_BASE_URL', 'http://llm.example.com:11434')
    monkeypatch.setitem(app.config, 'OUTBOUND_URL_ALLOWLIST', ['ollama', 'llm.example.com'])
    addresses = {'ollama': '172.18.0.9', 'vllm': '172.18.0.10', 'llm.example.com': '93.184.216.34'}
    real = socket.getaddrinfo

    def fake(host, *a, **k):
        if host in addresses:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (addresses[host], 0))]
        return real(host, *a, **k)
    monkeypatch.setattr(socket, 'getaddrinfo', fake)
    return configure


@pytest.fixture
def policy(app, db, org_a):
    original = dict(org_a.settings or {})

    def set_(value):
        settings = dict(original)
        if value is None:
            settings.pop('ai_tlp_policy', None)
        else:
            settings['ai_tlp_policy'] = value
        org_a.settings = settings
        db.session.commit()
    set_(None)
    yield set_
    org_a.settings = original
    db.session.commit()


def _events(inc):
    from app.models import AuditLog
    return AuditLog.query.filter_by(action='ai_blocked_by_tlp', incident_id=inc.id).all()


@pytest.mark.parametrize('tlp', TLPS)
@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('kind', list(KINDS))
def test_policy_matrix(app, ai_env, policy, make_incident, tlp, mode, kind):
    from app.services.ai_service import ai_service, AIBlockedByTLP
    ai_env(kind)
    policy({tlp: mode})
    inc = make_incident(tlp=tlp)
    provider = KINDS[kind]
    expect_allowed = mode == 'allow' or (mode == 'local_only' and kind == 'internal_allowlisted')
    with app.test_request_context('/'):
        if expect_allowed:
            assert ai_service.select_provider(str(inc.organization_id), provider, incident_tlp=tlp,
                                              feature='test', incident_id=inc.id) == provider
            assert _events(inc) == []
        else:
            with pytest.raises(AIBlockedByTLP) as exc:
                ai_service.select_provider(str(inc.organization_id), provider, incident_tlp=tlp,
                                           feature='test', incident_id=inc.id)
            e = exc.value
            assert (e.status, e.code, e.tlp, e.mode, e.provider, e.explicit) == (
                403, 'ai_blocked_by_tlp', tlp, mode, provider, True)
            [ev] = _events(inc)
            assert ev.event_type == 'security_event'
            assert ev.details == {'feature': 'test', 'provider': provider, 'tlp': tlp, 'mode': mode}


@pytest.mark.parametrize('tlp,expected', [('white', 'allow'), ('green', 'allow'), ('amber', 'allow'),
                                          ('amber_strict', 'local_only'), ('red', 'local_only')])
def test_defaults_when_unset_or_invalid(app, policy, org_a, tlp, expected):
    from app.services.ai_service import ai_policy_mode, effective_ai_tlp_policy
    assert ai_policy_mode(str(org_a.id), tlp) == expected
    policy({'red': 'bogus', 'nope': 'allow'})
    assert ai_policy_mode(str(org_a.id), tlp) == expected
    assert effective_ai_tlp_policy(None)[tlp] == expected
    assert ai_policy_mode(str(org_a.id), 'unknown-tlp') == 'block'


def test_public_host_is_not_local(app, ai_env, policy, org_a):
    from app.services.ai_service import ai_service
    ai_env('public_local')
    assert ai_service.provider_locality('ollama', str(org_a.id)) == (False, 'public_host')


def test_auto_selection_prefers_allowed_provider(app, ai_env, policy, make_incident):
    from app.services.ai_service import ai_service
    ai_env('cloud', 'internal_allowlisted')
    inc = make_incident(tlp='red')
    with app.test_request_context('/'):
        assert ai_service.select_provider(str(inc.organization_id), None, incident_tlp='red',
                                          feature='t', incident_id=inc.id) == 'ollama'


def test_incident_tlp_is_required(app):
    from app.services.ai_service import ai_service
    with pytest.raises(TypeError):
        ai_service.generate_report('executive', {}, [], {}, {}, provider='openai')
    with pytest.raises(TypeError):
        ai_service.generate_summary_sync({}, [], {}, {})


def test_explicit_ai_feature_gets_403_and_event(app, ai_env, policy, users, auth, make_incident, monkeypatch):
    from app.services.ai_service import ai_service
    monkeypatch.setattr(ai_service, '_generate_openai_sync', lambda *a, **k: pytest.fail('LLM called'))
    ai_env('cloud')
    inc = make_incident(tlp='red')
    resp = auth(users['Administrator']).post(f'/api/v1/incidents/{inc.id}/reports/ai-generate', json={})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body['error'] == 'ai_blocked_by_tlp' and body['tlp'] == 'red' and body['mode'] == 'local_only'
    assert len(_events(inc)) == 1


def test_explicit_provider_on_pdf_report_gets_403(app, ai_env, policy, users, auth, make_incident):
    ai_env('cloud')
    inc = make_incident(tlp='amber_strict')
    resp = auth(users['Administrator']).post(f'/api/v1/incidents/{inc.id}/reports/generate-pdf',
                                             json={'provider': 'openai'})
    assert resp.status_code == 403 and resp.get_json()['provider'] == 'openai'


def test_auto_pdf_report_falls_back_to_deterministic(app, ai_env, policy, users, auth, make_incident,
                                                     monkeypatch):
    from app.models import Report
    from app.services.ai_service import ai_service
    monkeypatch.setattr(ai_service, '_generate_report_openai', lambda *a, **k: pytest.fail('LLM called'))
    ai_env('cloud')
    inc = make_incident(tlp='red')
    resp = auth(users['Administrator']).post(f'/api/v1/incidents/{inc.id}/reports/generate-pdf', json={})
    assert resp.status_code == 200 and resp.data.startswith(b'%PDF')
    assert resp.headers['X-SheetStorm-AI-Status'] == 'ai_blocked_by_tlp'
    report = Report.query.filter_by(incident_id=inc.id).one()
    assert report.ai_summary is None and report.ai_provider is None
    assert len(_events(inc)) == 1


def test_allowed_report_passes_incident_tlp(app, ai_env, policy, users, auth, make_incident, monkeypatch):
    from app.services.ai_service import ai_service
    seen = {}

    def fake(system_prompt, user_prompt, organization_id=None):
        seen['called'] = True
        return '# AI report'
    monkeypatch.setattr(ai_service, '_generate_report_openai', fake)
    ai_env('cloud')
    inc = make_incident(tlp='amber')
    resp = auth(users['Administrator']).post(f'/api/v1/incidents/{inc.id}/reports/generate-pdf', json={})
    assert resp.status_code == 200 and seen == {'called': True}
    assert 'X-SheetStorm-AI-Status' not in resp.headers


def test_playbook_summary_skipped(app, ai_env, policy, users, auth, make_incident):
    ai_env('cloud')
    admin = auth(users['Administrator'])
    inc = make_incident(tlp='red')
    pb = admin.post('/api/v1/playbooks', json={'name': 'PB-ai', 'definition': {'phases': [
        {'phase': 1, 'name': 'Identification', 'tasks': [{'title': 't'}],
         'actions': [{'key': 's', 'type': 'generate_summary', 'auto_run': True}]}]}})
    assert pb.status_code == 201, pb.get_json()
    result = admin.post(f'/api/v1/incidents/{inc.id}/playbooks/{pb.get_json()["id"]}/activate'
                        ).get_json()['actions_executed'][0]['result']
    assert result['status'] == 'skipped' and result['code'] == 'ai_blocked_by_tlp'
    assert len(_events(inc)) == 1


def test_providers_endpoint_reports_policy(app, ai_env, policy, users, auth, make_incident):
    ai_env('cloud', 'internal_allowlisted', 'internal_not_allowlisted')
    inc = make_incident(tlp='red')
    body = auth(users['Administrator']).get(
        f'/api/v1/incidents/{inc.id}/reports/types').get_json()
    assert body['policy_mode'] == 'local_only'
    by_name = {p['name']: p for p in body['providers']}
    assert by_name['openai'] == {'name': 'openai', 'allowed': False, 'reason': 'cloud_provider'}
    assert by_name['ollama'] == {'name': 'ollama', 'allowed': True, 'reason': 'local'}
    assert by_name['openai_compatible'] == {'name': 'openai_compatible', 'allowed': False,
                                            'reason': 'not_allowlisted'}
    assert body['ai_providers'] == ['ollama'] and body['ai_configured'] is True


def test_no_llm_calls_outside_ai_service():
    """Every LLM call must go through ai_service dispatch (TLP policy)."""
    root = os.path.join(os.path.dirname(__file__), '..', 'app')
    pattern = re.compile(r'import openai|from openai|google\.generativeai|/api/generate|'
                         r'chat\.completions|generate_content\(|anthropic')
    import ast

    def exempt_lines(path, source):
        # Integration connection tests (`_test_<type>` in integrations.py) only
        # send a fixed probe string, never incident data.
        if not path.endswith(os.path.join('endpoints', 'integrations.py')):
            return set()
        lines = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('_test_'):
                lines.update(range(node.lineno, node.end_lineno + 1))
        return lines

    offenders = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            path = os.path.join(dirpath, f)
            if not f.endswith('.py') or path.endswith(os.path.join('services', 'ai_service.py')):
                continue
            with open(path, encoding='utf-8') as fh:
                source = fh.read()
            exempt = exempt_lines(path, source)
            for n, line in enumerate(source.splitlines(), 1):
                if pattern.search(line) and n not in exempt:
                    offenders.append(f'{os.path.relpath(path, root)}:{n}')
    assert offenders == []
