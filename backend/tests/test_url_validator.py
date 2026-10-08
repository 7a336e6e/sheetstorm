"""Item 9: SSRF validator — table-driven. DNS is mocked; no network access."""
import socket

import pytest

from app.utils.url_validator import validate_outbound_url


def _mock_dns(monkeypatch, *addresses):
    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        out = []
        for address in addresses:
            fam = socket.AF_INET6 if ':' in address else socket.AF_INET
            sockaddr = (address, port or 0, 0, 0) if fam == socket.AF_INET6 else (address, port or 0)
            out.append((fam, socket.SOCK_STREAM, 6, '', sockaddr))
        return out
    monkeypatch.setattr(socket, 'getaddrinfo', fake_getaddrinfo)


PUBLIC = [
    ('https://example.com/api', '93.184.216.34'),
    ('https://v6.example.com/', '2606:2800:220:1:248:1893:25c8:1946'),
]

NON_PUBLIC = [  # blocked by default; allowed only when allowlisted
    ('http://127.0.0.1/', '127.0.0.1'),
    ('http://10.0.0.1/', '10.0.0.1'),
    ('http://172.16.5.4/', '172.16.5.4'),
    ('http://192.168.1.10/', '192.168.1.10'),
    ('http://100.64.0.1/', '100.64.0.1'),            # CGNAT
    ('http://[::1]/', '::1'),
    ('http://[fd12::1]/', 'fd12::1'),                 # ULA
    ('http://[::ffff:10.0.0.1]/', '::ffff:10.0.0.1'),  # IPv4-mapped private
    ('http://[64:ff9b::a00:1]/', '64:ff9b::a00:1'),    # NAT64 -> 10.0.0.1
    ('http://[2002:a00:1::]/', '2002:a00:1::'),        # 6to4 -> 10.0.0.1
    ('http://192.0.2.10/', '192.0.2.10'),              # documentation / reserved
    ('http://240.0.0.1/', '240.0.0.1'),                # reserved
]

ALWAYS_BLOCKED = [  # blocked even when allowlisted
    ('http://169.254.169.254/latest/meta-data/', '169.254.169.254'),
    ('http://[fd00:ec2::254]/', 'fd00:ec2::254'),
    ('http://[fe80::1]/', 'fe80::1'),
    ('http://[::]/', '::'),
    ('http://0.0.0.0/', '0.0.0.0'),
    ('http://[::ffff:169.254.169.254]/', '::ffff:169.254.169.254'),
    ('http://224.0.0.1/', '224.0.0.1'),
]


@pytest.mark.parametrize('url,ip', PUBLIC)
def test_public_allowed(monkeypatch, url, ip):
    _mock_dns(monkeypatch, ip)
    assert validate_outbound_url(url, allowlist=[]) == (True, '')


@pytest.mark.parametrize('url,ip', NON_PUBLIC)
def test_non_public_blocked_by_default(monkeypatch, url, ip):
    _mock_dns(monkeypatch, ip)
    ok, reason = validate_outbound_url(url, allowlist=[])
    assert ok is False and reason
    # Self-hosted tier without an allowlist entry: still blocked.
    assert validate_outbound_url(url, allow_allowlisted_private=True, allowlist=[])[0] is False


@pytest.mark.parametrize('url,ip', NON_PUBLIC)
def test_non_public_allowed_when_allowlisted(monkeypatch, url, ip):
    _mock_dns(monkeypatch, ip)
    host = url.split('//')[1].split('/')[0].strip('[]')
    assert validate_outbound_url(url, allow_allowlisted_private=True, allowlist=[host])[0] is True
    # ...but never for the default (non-self-hosted) tier.
    assert validate_outbound_url(url, allowlist=[host])[0] is False


@pytest.mark.parametrize('url,ip', ALWAYS_BLOCKED)
def test_always_blocked_even_if_allowlisted(monkeypatch, url, ip):
    _mock_dns(monkeypatch, ip)
    host = url.split('//')[1].split('/')[0].strip('[]')
    allow = [host, '0.0.0.0/0', '::/0']
    assert validate_outbound_url(url, allow_allowlisted_private=True, allowlist=allow)[0] is False


def test_metadata_hostname_blocked_before_dns(monkeypatch):
    _mock_dns(monkeypatch, '93.184.216.34')
    assert validate_outbound_url('http://metadata.google.internal/computeMetadata/v1/',
                                 allow_allowlisted_private=True,
                                 allowlist=['metadata.google.internal'])[0] is False


def test_hostname_and_cidr_allowlist_forms(monkeypatch):
    _mock_dns(monkeypatch, '172.18.0.5')
    assert validate_outbound_url('http://ollama:11434', allow_allowlisted_private=True, allowlist=['ollama'])[0]
    assert validate_outbound_url('http://misp.corp.local', allow_allowlisted_private=True,
                                 allowlist=['.corp.local'])[0]
    assert validate_outbound_url('http://anything', allow_allowlisted_private=True,
                                 allowlist=['172.18.0.0/16'])[0]
    assert not validate_outbound_url('http://anything', allow_allowlisted_private=True,
                                     allowlist=['10.0.0.0/8'])[0]


def test_mixed_resolution_with_one_private_address_blocked(monkeypatch):
    _mock_dns(monkeypatch, '93.184.216.34', '10.0.0.1')
    assert validate_outbound_url('https://rebind.example', allowlist=[])[0] is False


@pytest.mark.parametrize('url', ['', None, 'ftp://example.com', 'file:///etc/passwd', 'http://', 'http://h:99999/'])
def test_malformed(url):
    assert validate_outbound_url(url, allowlist=[])[0] is False


def test_allowlist_read_from_config(app, monkeypatch):
    _mock_dns(monkeypatch, '172.18.0.5')
    monkeypatch.setitem(app.config, 'OUTBOUND_URL_ALLOWLIST', ['ollama'])
    with app.app_context():
        assert validate_outbound_url('http://ollama:11434', allow_allowlisted_private=True)[0] is True
        assert validate_outbound_url('http://other:11434', allow_allowlisted_private=True)[0] is False


def test_integration_test_endpoint_applies_tiers(app, db, users, auth, monkeypatch):
    """Self-hosted types honour the allowlist; webhooks never reach private hosts."""
    from app.models import Integration
    _mock_dns(monkeypatch, '10.1.2.3')
    admin = auth(users['Administrator'])
    created = {}
    for itype, cfg in (('misp', {'url': 'http://misp.internal'}), ('webhook', {'url': 'http://hook.internal'}),
                       ('ollama', {'base_url': 'http://ollama:11434'})):
        r = admin.post('/api/v1/integrations', json={'type': itype, 'name': f'{itype}-ssrf', 'config': cfg})
        created[itype] = r.get_json()['id']
    for itype in created:
        resp = admin.post(f'/api/v1/integrations/{created[itype]}/test')
        assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_url'

    monkeypatch.setitem(app.config, 'OUTBOUND_URL_ALLOWLIST', ['misp.internal', 'ollama', 'hook.internal'])
    import requests

    class R:
        status_code = 200

        def json(self):
            return {'models': []}
    monkeypatch.setattr(requests, 'get', lambda *a, **k: R())
    assert admin.post(f'/api/v1/integrations/{created["ollama"]}/test').status_code == 200
    # webhook is not a self-hosted type: allowlist does not open private ranges
    resp = admin.post(f'/api/v1/integrations/{created["webhook"]}/test')
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_url'
    for i in created.values():
        db.session.delete(db.session.get(Integration, i))
    db.session.commit()
