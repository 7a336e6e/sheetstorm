"""W4-EVD-TSA: RFC 3161 anchoring (services/timestamp_service.py + the anchor endpoint).

No network: ``requests.post`` is mocked everywhere and DNS is never needed
(IP-literal TSA URLs). ``REAL_RESPONSE_B64`` is a genuine TimeStampResp made
offline with ``openssl ts -reply`` (throwaway EC CA, fixed request below), so
the parser is exercised against a real token, not only against our own
builder. The signature is intentionally not verified by the server.
"""
import base64
import uuid
from datetime import datetime, timezone

import pytest
import requests

from app.services import timestamp_service as tsa

# Request that produced REAL_RESPONSE_B64.
REAL_DIGEST = bytes.fromhex('ab' * 32)
REAL_NONCE = 0x8123456789ABCDEF
REAL_GEN_TIME = datetime(2026, 10, 9, 13, 55, 21, tzinfo=timezone.utc)
REAL_RESPONSE_B64 = (
    "MIIFUzADAgEAMIIFSgYJKoZIhvcNAQcCoIIFOzCCBTcCAQMxDzANBglghkgBZQMEAgEFADBzBgsq"
    "hkiG9w0BCRABBKBkBGIwYAIBAQYEKgMEATAxMA0GCWCGSAFlAwQCAQUABCCrq6urq6urq6urq6ur"
    "q6urq6urq6urq6urq6urq6urqwIBAhgPMjAyNjEwMDkxMzU1MjFaMAMCAQECCQCBI0VniavN76CC"
    "A1gwggG3MIIBXqADAgECAhQ4feMdb6ay2ZyeQ1M46Al38fGS0jAKBggqhkjOPQQDAjAhMR8wHQYD"
    "VQQDDBZTaGVldFN0b3JtIFRlc3QgVFNBIENBMCAXDTI2MTAwOTEzMDE1OFoYDzIxMjYwOTE1MTMw"
    "MTU4WjAeMRwwGgYDVQQDDBNTaGVldFN0b3JtIFRlc3QgVFNBMFkwEwYHKoZIzj0CAQYIKoZIzj0D"
    "AQcDQgAEeXMJ1TlMrYlbP1UPWJHNEl5NJZVv/a7V0zlqZguEL2moimaLtv/0824JuUvxJssj2utM"
    "A1ZOZ9fJAD+2P4W0r6N1MHMwCQYDVR0TBAIwADAOBgNVHQ8BAf8EBAMCB4AwFgYDVR0lAQH/BAww"
    "CgYIKwYBBQUHAwgwHQYDVR0OBBYEFGTYbKsNSzsuJDeMrmQElVVANwUhMB8GA1UdIwQYMBaAFGZf"
    "Y03au5YyaMEqy6gaeoYIvvldMAoGCCqGSM49BAMCA0cAMEQCIBh8a28v8JOWvHJY46WXvsdHqg6H"
    "+Cu4edi03akJZHzEAiAyLryddPvm7L9ffLXdXf2QwOu26xfmmbu8CtHAwDXsGzCCAZkwggE/oAMC"
    "AQICFGwsY3oJ0edESPixv8SL9CW2EQJ+MAoGCCqGSM49BAMCMCExHzAdBgNVBAMMFlNoZWV0U3Rv"
    "cm0gVGVzdCBUU0EgQ0EwIBcNMjYxMDA5MTMwMTU4WhgPMjEyNjA5MTUxMzAxNThaMCExHzAdBgNV"
    "BAMMFlNoZWV0U3Rvcm0gVGVzdCBUU0EgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAThp+t0"
    "A1AKsFlbEhqIMAhBlfoF+/QRBwpPEwyYmCe0qvqX+t9q5hoXD0BTWu12Sl2ts/pKwt/iVXKiNy+2"
    "Etxpo1MwUTAdBgNVHQ4EFgQUZl9jTdq7ljJowSrLqBp6hgi++V0wHwYDVR0jBBgwFoAUZl9jTdq7"
    "ljJowSrLqBp6hgi++V0wDwYDVR0TAQH/BAUwAwEB/zAKBggqhkjOPQQDAgNIADBFAiEAsb3/cD2A"
    "2+/IgKhOdYu0ygrfp/nf7dhWhd/isOzugbYCICMbsFul2NkVfdbgFdY/EIjAT7tdyg18Ntvm0+lu"
    "73ZTMYIBTjCCAUoCAQEwOTAhMR8wHQYDVQQDDBZTaGVldFN0b3JtIFRlc3QgVFNBIENBAhQ4feMd"
    "b6ay2ZyeQ1M46Al38fGS0jANBglghkgBZQMEAgEFAKCBpDAaBgkqhkiG9w0BCQMxDQYLKoZIhvcN"
    "AQkQAQQwHAYJKoZIhvcNAQkFMQ8XDTI2MTAwOTEzNTUyMVowLwYJKoZIhvcNAQkEMSIEII5r6rsl"
    "EUPslxKnSCUGVeotVL+Y4QOVPhu3gh5EBbM7MDcGCyqGSIb3DQEJEAIvMSgwJjAkMCIEIOMiUssu"
    "L0KtlfYwzCsg+KwCAyZFBOxHbxYoigs0F6xfMAoGCCqGSM49BAMCBEgwRgIhAJqkMjKsVuXmlPFU"
    "uZx88FpKrpvJK5NCFFfFIscT2v/uAiEAp1GoABCysyRzK+V/cTBnE9QSkiZJ9RYR6iIESOFCjX4="
)
# openssl ts -query -digest abab..ab -sha256 -cert -no_nonce  (byte for byte)
GOLDEN_NO_NONCE = ('30390201013031300d060960864801650304020105000420' + 'ab' * 32 + '0101ff')
# Same request with nonce 0x8123456789ABCDEF (positive INTEGER, so a leading 0x00).
GOLDEN_WITH_NONCE = ('30440201013031300d060960864801650304020105000420' + 'ab' * 32
                     + '0209008123456789abcdef' + '0101ff')


def test_request_encoder_golden_der():
    assert tsa.build_timestamp_request(REAL_DIGEST, None).hex() == GOLDEN_NO_NONCE
    assert tsa.build_timestamp_request(REAL_DIGEST, REAL_NONCE).hex() == GOLDEN_WITH_NONCE


@pytest.mark.parametrize('value,encoded', [
    (0, '020100'), (1, '020101'), (127, '02017f'), (128, '02020080'), (255, '020200ff'),
    (256, '02020100'), (2 ** 63, '02090080' + '00' * 7), (2 ** 64 - 1, '020900' + 'ff' * 8),
])
def test_integer_encoding_is_minimal_positive(value, encoded):
    assert tsa._der_integer(value).hex() == encoded


def test_length_and_oid_encoding():
    assert tsa._der_length(0x7F) == b'\x7f' and tsa._der_length(0x80) == b'\x81\x80'
    assert tsa._der_length(0x1234) == b'\x82\x12\x34'
    assert tsa._der_oid(tsa.SHA256_OID).hex() == '060960864801650304020' + '1'
    assert tsa._der_oid('1.2.840.113549.1.7.2').hex() == '06092a864886f70d010702'


def test_request_rejects_wrong_digest_size():
    with pytest.raises(ValueError):
        tsa.build_timestamp_request(b'\x00' * 31, 1)


def test_nonce_is_64_bit_and_nonzero():
    values = {tsa.new_nonce() for _ in range(50)}
    assert 0 not in values and all(0 < v < 2 ** 64 for v in values) and len(values) > 40


# ── Response parsing ────────────────────────────────────────────────────────

def _der(tag, content):
    return tsa._tlv(tag, content)


def fake_response(digest, nonce, *, status=0, gen_time='20261009120000Z', imprint=None, imprint_oid=None,
                  nonce_in_token=True, with_token=True, status_text=None):
    """A structurally valid TimeStampResp (unsigned: no signerInfo content)."""
    info = _der(0x30, tsa._der_integer(status)
                + (_der(0x30, _der(0x0C, status_text.encode())) if status_text else b''))
    if not with_token:
        return _der(0x30, info)
    tst = (tsa._der_integer(1) + tsa._der_oid('1.2.3.4.1')
           + _der(0x30, _der(0x30, tsa._der_oid(imprint_oid or tsa.SHA256_OID) + _der(0x05, b''))
                  + _der(0x04, imprint if imprint is not None else digest))
           + tsa._der_integer(7) + _der(0x18, gen_time.encode())
           + (tsa._der_integer(nonce) if nonce_in_token else b''))
    signed_data = _der(0x30, tsa._der_integer(3) + _der(0x31, b'')
                       + _der(0x30, tsa._der_oid(tsa.TST_INFO_OID) + _der(0xA0, _der(0x04, _der(0x30, tst))))
                       + _der(0x31, b''))
    token = _der(0x30, tsa._der_oid(tsa.SIGNED_DATA_OID) + _der(0xA0, signed_data))
    return _der(0x30, info + token)


def test_parses_a_real_openssl_response():
    reply = base64.b64decode(''.join(REAL_RESPONSE_B64.split()))
    token, info = tsa.parse_timestamp_response(reply, digest=REAL_DIGEST, nonce=REAL_NONCE)
    assert info.gen_time == REAL_GEN_TIME and info.nonce == REAL_NONCE and info.imprint == REAL_DIGEST
    assert info.imprint_algorithm == tsa.SHA256_OID and info.policy == '1.2.3.4.1'
    assert reply.endswith(token) and token[0] == 0x30 and len(token) < len(reply)
    assert tsa.parse_token(token) == info
    assert tsa.token_binding(token, 'ab' * 32, REAL_NONCE) == ('ok', REAL_GEN_TIME)
    assert tsa.token_binding(token, 'ac' * 32, REAL_NONCE)[0] == 'mismatch'
    assert tsa.token_binding(token, 'ab' * 32, 5)[0] == 'mismatch'
    assert tsa.token_binding(b'junk', 'ab' * 32, 5) == ('unparseable', None)
    assert tsa.token_binding(None, 'ab' * 32, 5) == ('missing', None)


def test_real_response_with_other_nonce_or_digest_is_refused():
    reply = base64.b64decode(''.join(REAL_RESPONSE_B64.split()))
    with pytest.raises(tsa.TimestampError) as exc:
        tsa.parse_timestamp_response(reply, digest=REAL_DIGEST, nonce=REAL_NONCE + 1)
    assert exc.value.code == 'nonce_mismatch'
    with pytest.raises(tsa.TimestampError) as exc:
        tsa.parse_timestamp_response(reply, digest=b'\x00' * 32, nonce=REAL_NONCE)
    assert exc.value.code == 'imprint_mismatch'


def test_synthetic_granted_response_parses_fractional_gen_time():
    reply = fake_response(REAL_DIGEST, 99, gen_time='20261009120000.250Z')
    _, info = tsa.parse_timestamp_response(reply, digest=REAL_DIGEST, nonce=99)
    assert info.gen_time == datetime(2026, 10, 9, 12, 0, 0, 250000, tzinfo=timezone.utc)
    _, info = tsa.parse_timestamp_response(fake_response(REAL_DIGEST, 99, status=1), digest=REAL_DIGEST, nonce=99)
    assert info.serial_number == 7  # grantedWithMods is accepted


def test_rejection_reports_the_status_and_sanitised_text():
    reply = fake_response(REAL_DIGEST, 1, status=2, with_token=False, status_text='bad\x00 alg\n' + 'x' * 500)
    with pytest.raises(tsa.TimestampError) as exc:
        tsa.parse_timestamp_response(reply, digest=REAL_DIGEST, nonce=1)
    assert exc.value.code == 'rejected' and 'PKIStatus 2' in exc.value.message
    assert '\x00' not in exc.value.message and '\n' not in exc.value.message and len(exc.value.message) < 400


@pytest.mark.parametrize('kwargs,code', [
    ({'imprint': b'\x01' * 32}, 'imprint_mismatch'),
    ({'imprint_oid': '1.3.14.3.2.26'}, 'imprint_mismatch'),   # SHA-1 imprint is not accepted
    ({'nonce_in_token': False}, 'nonce_mismatch'),
    ({'with_token': False}, 'malformed_response'),            # "granted" without a token
    ({'gen_time': '2026-10-09T12:00:00Z'}, 'malformed_response'),
    ({'gen_time': '20261009120000+0100'}, 'malformed_response'),
])
def test_bad_synthetic_responses(kwargs, code):
    reply = fake_response(REAL_DIGEST, 5, **kwargs)
    with pytest.raises(tsa.TimestampError) as exc:
        tsa.parse_timestamp_response(reply, digest=REAL_DIGEST, nonce=5)
    assert exc.value.code == code


@pytest.mark.parametrize('blob', [
    b'', b'\x30', b'\x30\x80\x00\x00', b'\x04\x01\x00', b'\x30\x05\x30\x00', b'\xff' * 40,
    bytes.fromhex('3003020100'),
])
def test_garbage_is_malformed_not_a_crash(blob):
    with pytest.raises(tsa.TimestampError) as exc:
        tsa.parse_timestamp_response(blob, digest=REAL_DIGEST, nonce=1)
    assert exc.value.code == 'malformed_response'


def test_trailing_bytes_and_truncation_are_refused():
    good = fake_response(REAL_DIGEST, 5)
    for blob in (good + b'\x00', good[:-3]):
        with pytest.raises(tsa.TimestampError) as exc:
            tsa.parse_timestamp_response(blob, digest=REAL_DIGEST, nonce=5)
        assert exc.value.code == 'malformed_response'


def test_public_url_strips_credentials_query_and_fragment():
    assert tsa.public_url('https://user:pw@tsa.example.com:8443/ts?key=1#f') == 'https://tsa.example.com:8443/ts'
    assert tsa.public_url('http://[2001:db8::1]:80/x') == 'http://[2001:db8::1]:80/x'




# ── Transport (requests mocked) ─────────────────────────────────────────────

class _FakeResp:
    def __init__(self, body=b'', status=200, headers=None, chunks=None, exc=None):
        self.status_code, self.headers = status, headers or {}
        self._chunks = chunks if chunks is not None else [body]
        self._exc = exc
        self.closed = False

    def iter_content(self, chunk_size=8192):
        for c in self._chunks:
            yield c
        if self._exc:
            raise self._exc

    def close(self):
        self.closed = True


@pytest.fixture
def tsa_on(app, monkeypatch):
    """TSA enabled with an IP-literal URL; the outbound guard is stubbed to pass
    (its own behaviour is covered in test_url_validator)."""
    monkeypatch.setitem(app.config, 'TSA_URL', 'https://user:secret@198.51.100.7/tsa?k=1')
    monkeypatch.setitem(app.config, 'TSA_TIMEOUT_SECONDS', 5)
    monkeypatch.setitem(app.config, 'TSA_MAX_RESPONSE_BYTES', 4096)
    monkeypatch.setattr(tsa, 'validate_outbound_url', lambda url, **kw: (True, ''))
    calls = []

    def install(responder):
        def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=True, stream=False):
            calls.append({'url': url, 'data': data, 'headers': headers, 'timeout': timeout,
                          'allow_redirects': allow_redirects, 'stream': stream})
            return responder(data)
        monkeypatch.setattr(tsa.requests, 'post', fake_post)
        return calls
    return install


def _granting(data):
    """Answer a request with a token for its own digest and nonce."""
    _, cs, ce = tsa._read_tlv(data, 0)
    kids = tsa._children(data, cs, ce)
    imprint = tsa._children(data, kids[1][1], kids[1][2])
    digest = data[imprint[1][1]:imprint[1][2]]
    nonce = tsa._decode_uint(data[kids[2][1]:kids[2][2]])
    return _FakeResp(fake_response(digest, nonce))


def test_request_timestamp_happy_path_and_request_hygiene(app, tsa_on):
    calls = tsa_on(_granting)
    with app.app_context():
        stamp = tsa.request_timestamp('cd' * 32)
    assert stamp.tsa_url == 'https://198.51.100.7/tsa'  # credentials and query never kept
    assert tsa.parse_token(stamp.token_der).imprint == bytes.fromhex('cd' * 32)
    call = calls[0]
    assert call['allow_redirects'] is False and call['stream'] is True and call['timeout'] == (5.0, 5.0)
    assert call['headers']['Content-Type'] == 'application/timestamp-query'


@pytest.mark.parametrize('responder,code', [
    (lambda d: _FakeResp(status=302, headers={'Location': 'http://127.0.0.1/'}), 'redirect'),
    (lambda d: _FakeResp(status=500), 'http_error'),
    (lambda d: _FakeResp(headers={'Content-Length': '999999'}), 'response_too_large'),
    (lambda d: _FakeResp(chunks=[b'\x00' * 3000, b'\x00' * 3000]), 'response_too_large'),
    (lambda d: _FakeResp(chunks=[b'\x30'], exc=requests.ReadTimeout()), 'timeout'),
    (lambda d: _FakeResp(body=b'not der'), 'malformed_response'),
])
def test_transport_failures(app, tsa_on, responder, code):
    tsa_on(responder)
    with app.app_context(), pytest.raises(tsa.TimestampError) as exc:
        tsa.request_timestamp('cd' * 32)
    assert exc.value.code == code


def test_connect_timeout_and_connection_error(app, tsa_on, monkeypatch):
    tsa_on(_granting)
    for raised, code in ((requests.ConnectTimeout(), 'timeout'), (requests.ConnectionError(), 'connection_error')):
        def boom(*a, _r=raised, **k):
            raise _r
        monkeypatch.setattr(tsa.requests, 'post', boom)
        with app.app_context(), pytest.raises(tsa.TimestampError) as exc:
            tsa.request_timestamp('cd' * 32)
        assert exc.value.code == code


def test_disabled_and_refused_url(app, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, 'TSA_URL', '')
        assert not tsa.is_enabled()
        with pytest.raises(tsa.TimestampError) as exc:
            tsa.request_timestamp('cd' * 32)
        assert exc.value.code == 'tsa_disabled'
        monkeypatch.setitem(app.config, 'TSA_URL', 'http://127.0.0.1:2020/tsa')  # loopback, not allowlisted
        with pytest.raises(tsa.TimestampError) as exc:
            tsa.request_timestamp('cd' * 32)
        assert exc.value.code == 'url_refused'


# ── Endpoint ────────────────────────────────────────────────────────────────

def _anchor_url(inc):
    return f'/api/v1/incidents/{inc.id}/evidence/custody/anchor'


def _registered_incident(auth_client, make_incident):
    inc = make_incident()
    resp = auth_client.post(f'/api/v1/incidents/{inc.id}/evidence',
                            json={'title': 'Disk', 'evidence_type': 'disk_image'})
    assert resp.status_code == 201, resp.get_json()
    return inc


@pytest.fixture
def admin_client(users, auth):
    return auth(users['Administrator'])


def test_anchor_disabled_is_400(app, admin_client, make_incident, monkeypatch):
    monkeypatch.setitem(app.config, 'TSA_URL', '')
    inc = _registered_incident(admin_client, make_incident)
    resp = admin_client.post(_anchor_url(inc), json={})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'tsa_disabled'


def test_anchor_refused_url_is_400_and_records_nothing(app, admin_client, make_incident, monkeypatch):
    from app.models import CustodyAnchor
    monkeypatch.setitem(app.config, 'TSA_URL', 'http://10.1.2.3/tsa')
    inc = _registered_incident(admin_client, make_incident)
    resp = admin_client.post(_anchor_url(inc), json={})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'tsa_url_refused'
    assert CustodyAnchor.query.filter_by(incident_id=inc.id, anchor_type='rfc3161').count() == 0


def test_anchor_granted_then_already_anchored_then_verify(app, admin_client, make_incident, tsa_on):
    from app.models import CustodyAnchor
    calls = tsa_on(_granting)
    inc = _registered_incident(admin_client, make_incident)
    resp = admin_client.post(_anchor_url(inc), json={})
    assert resp.status_code == 201, resp.get_json()
    anchor = resp.get_json()['anchor']
    assert anchor['status'] == 'granted' and anchor['token_binding'] == 'ok' and anchor['gen_time']
    assert 'secret' not in str(resp.get_json())
    row = CustodyAnchor.query.filter_by(incident_id=inc.id, anchor_type='rfc3161').one()
    assert row.tsa_url == 'https://198.51.100.7/tsa' and row.token_der

    again = admin_client.post(_anchor_url(inc), json={})
    assert again.status_code == 200 and again.get_json()['already_anchored'] is True
    assert len(calls) == 1  # the TSA is not asked twice for the same head

    verify = admin_client.get(f'/api/v1/incidents/{inc.id}/evidence/custody/verify').get_json()
    status = verify['anchor_status']
    assert status['tsa_configured'] and status['rfc3161_granted'] == 1 and status['current_head_anchored']
    assert status['signature_verified'] is False


def test_anchor_tsa_failure_is_recorded_and_502(app, admin_client, make_incident, tsa_on):
    from app.models import CustodyAnchor
    tsa_on(lambda d: _FakeResp(status=503))
    inc = _registered_incident(admin_client, make_incident)
    resp = admin_client.post(_anchor_url(inc), json={})
    body = resp.get_json()
    assert resp.status_code == 502 and body['error'] == 'tsa_failed' and body['reason'] == 'http_error'
    row = CustodyAnchor.query.filter_by(incident_id=inc.id, anchor_type='rfc3161').one()
    assert row.status == 'failed' and row.error.startswith('http_error') and row.token_der is None


def test_anchor_without_ledger_head_is_409(app, admin_client, make_incident, tsa_on):
    tsa_on(_granting)
    inc = make_incident()
    resp = admin_client.post(_anchor_url(inc), json={})
    assert resp.status_code == 409 and resp.get_json()['error'] == 'no_custody_head'


def test_anchor_needs_write_permission(app, users, auth, admin_client, make_incident, tsa_on):
    calls = tsa_on(_granting)
    inc = _registered_incident(admin_client, make_incident)
    viewer = auth(users['Viewer'])
    assert viewer.post(_anchor_url(inc), json={}).status_code in (403, 404)
    assert not calls


def test_anchor_rows_are_append_only(app, db, admin_client, make_incident, tsa_on):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    tsa_on(_granting)
    inc = _registered_incident(admin_client, make_incident)
    assert admin_client.post(_anchor_url(inc), json={}).status_code == 201
    with pytest.raises(DBAPIError):
        db.session.execute(text("UPDATE custody_anchors SET status = 'failed' WHERE incident_id = :i"),
                           {'i': inc.id})
        db.session.flush()
    db.session.rollback()
