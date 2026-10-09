"""Optional RFC 3161 anchoring of the custody ledger head (evidence plan §3.8).

Stdlib + ``requests`` only (no new dependency). The ``TimeStampReq`` is built
by hand (fixed structure) and the ``TimeStampResp`` is parsed by a minimal DER
walker, only as far as needed to establish that the reply

* has PKIStatus ``granted`` (0) or ``grantedWithMods`` (1),
* carries a TimeStampToken whose TSTInfo ``messageImprint`` is SHA-256 of
  exactly the digest we sent, and whose ``nonce`` is the one we sent,
* and to read ``genTime``.

What this module deliberately does NOT do: verify the CMS signature or the
TSA certificate chain. ``cryptography`` has no CMS verify API, so a granted
anchor means "a TSA answered with a well-formed token bound to this head", not
"the signature is valid". Full verification is offline with
``openssl ts -verify`` (see assets/docs/configuration.md and the bundle
README). The raw token is stored untouched so it can be verified later.

The imprint is the 32-byte incident head hash itself (the ledger's
``entry_hash`` is already a SHA-256 hex digest), so the offline command is
``openssl ts -verify -digest <head_hash> -in token.der -token_in -CAfile ca.pem``.

Request hygiene: the URL comes from the environment only and is re-checked by
``validate_outbound_url`` (SSRF guard / ``OUTBOUND_URL_ALLOWLIST``) on every
call; redirects are not followed; connect/read timeouts, an overall deadline
and a response size cap apply; credentials embedded in the URL are never
stored or returned.
"""
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
from flask import current_app

from app.utils.url_validator import validate_outbound_url

SHA256_OID = '2.16.840.1.101.3.4.2.1'
SIGNED_DATA_OID = '1.2.840.113549.1.7.2'
TST_INFO_OID = '1.2.840.113549.1.9.16.1.4'

CONTENT_TYPE_REQUEST = 'application/timestamp-query'
STATUS_GRANTED = 0
STATUS_GRANTED_WITH_MODS = 1
ERROR_TEXT_MAX = 300

# DER tags
_INTEGER, _BIT_STRING, _OCTET_STRING, _NULL, _OID = 0x02, 0x03, 0x04, 0x05, 0x06
_BOOLEAN, _GENERALIZED_TIME, _SEQUENCE, _SET = 0x01, 0x18, 0x30, 0x31
_CONTEXT_0 = 0xA0


class TimestampError(Exception):
    """A TSA exchange that did not produce a usable token.

    ``code`` is one of: ``tsa_disabled`` (not configured), ``url_refused``,
    ``timeout``, ``connection_error``, ``http_error``, ``redirect``,
    ``response_too_large``, ``rejected`` (PKIStatus other than granted),
    ``malformed_response``, ``imprint_mismatch``, ``nonce_mismatch``.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# ── DER encoding (request) ──────────────────────────────────────────────────

def _der_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _der_length(len(content)) + content


def _der_integer(value: int) -> bytes:
    """Minimal two's-complement DER INTEGER (non-negative values only here)."""
    if value < 0:
        raise ValueError('negative integers are not supported')
    body = value.to_bytes(max(1, (value.bit_length() + 7) // 8), 'big')
    if body[0] & 0x80:
        body = b'\x00' + body
    return _tlv(_INTEGER, body)


def _der_oid(dotted: str) -> bytes:
    arcs = [int(a) for a in dotted.split('.')]
    body = bytearray([arcs[0] * 40 + arcs[1]])
    for arc in arcs[2:]:
        chunk = [arc & 0x7F]
        arc >>= 7
        while arc:
            chunk.append(0x80 | (arc & 0x7F))
            arc >>= 7
        body.extend(reversed(chunk))
    return _tlv(_OID, bytes(body))


def build_timestamp_request(digest: bytes, nonce: int | None) -> bytes:
    """DER ``TimeStampReq`` (RFC 3161 §2.4.1): version 1, messageImprint
    {SHA-256, ``digest``}, optional ``nonce``, certReq TRUE. No reqPolicy and
    no extensions."""
    if len(digest) != 32:
        raise ValueError('digest must be a 32-byte SHA-256 value')
    imprint = _tlv(_SEQUENCE, _tlv(_SEQUENCE, _der_oid(SHA256_OID) + _tlv(_NULL, b'')) + _tlv(_OCTET_STRING, digest))
    body = _der_integer(1) + imprint
    if nonce is not None:
        body += _der_integer(nonce)
    body += _tlv(_BOOLEAN, b'\xff')  # certReq TRUE (DER canonical TRUE)
    return _tlv(_SEQUENCE, body)


def new_nonce() -> int:
    """Random 64-bit nonce, never zero (fits ``custody_anchors.nonce`` NUMERIC(20,0))."""
    return secrets.randbits(64) or 1


# ── DER walking (response) ──────────────────────────────────────────────────

def _read_tlv(data: bytes, pos: int = 0):
    """(tag, content_start, content_end) of the element at ``pos``. Definite
    lengths only; anything else is malformed."""
    if pos + 2 > len(data):
        raise ValueError('truncated element')
    tag = data[pos]
    if tag & 0x1F == 0x1F:
        raise ValueError('multi-byte tags are not supported')
    first = data[pos + 1]
    start = pos + 2
    if first < 0x80:
        length = first
    elif first == 0x80:
        raise ValueError('indefinite length is not supported')
    else:
        n = first & 0x7F
        if n > 4 or start + n > len(data):
            raise ValueError('invalid length')
        length = int.from_bytes(data[start:start + n], 'big')
        start += n
    end = start + length
    if end > len(data):
        raise ValueError('element exceeds its container')
    return tag, start, end


def _children(data: bytes, start: int, end: int):
    """Direct children of a constructed element as (tag, content_start,
    content_end); each child starts where the previous one ends."""
    out, pos = [], start
    while pos < end:
        tag, cs, ce = _read_tlv(data, pos)
        if ce > end:
            raise ValueError('child exceeds its parent')
        out.append((tag, cs, ce))
        pos = ce
    return out


def _expect(children, index, tag, what):
    if len(children) <= index or children[index][0] != tag:
        raise ValueError(f'unexpected structure ({what})')
    return children[index]


def _decode_oid(content: bytes) -> str:
    if not content:
        raise ValueError('empty OID')
    first = content[0]
    arcs = [first // 40, first % 40] if first < 80 else [2, first - 80]
    value = 0
    for byte in content[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(value)
            value = 0
    return '.'.join(str(a) for a in arcs)


def _decode_uint(content: bytes) -> int:
    if not content or content[0] & 0x80:
        raise ValueError('expected a non-negative INTEGER')
    return int.from_bytes(content, 'big')


def _parse_gen_time(content: bytes) -> datetime:
    """GeneralizedTime ``YYYYMMDDHHMMSS[.f+]Z`` (UTC, as DER requires)."""
    text = content.decode('ascii')
    if not text.endswith('Z') or len(text) < 15:
        raise ValueError('genTime must be UTC GeneralizedTime')
    whole, _, frac = text[:-1].partition('.')
    if len(whole) != 14 or not whole.isdigit() or (frac and not frac.isdigit()):
        raise ValueError('malformed genTime')
    return datetime.strptime(whole, '%Y%m%d%H%M%S').replace(
        microsecond=int((frac + '000000')[:6]) if frac else 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class TokenInfo:
    gen_time: datetime
    imprint_algorithm: str
    imprint: bytes
    nonce: int | None
    policy: str
    serial_number: int


def parse_token(token: bytes) -> TokenInfo:
    """Read a TimeStampToken (a CMS ContentInfo wrapping SignedData whose
    encapsulated content is TSTInfo) down to the TSTInfo fields. The CMS
    signature is NOT checked. Raises ``ValueError`` on anything unexpected."""
    tag, cs, ce = _read_tlv(token, 0)
    if tag != _SEQUENCE or ce != len(token):
        raise ValueError('token is not a single SEQUENCE')
    content_info = _children(token, cs, ce)
    _, s, e = _expect(content_info, 0, _OID, 'contentType')
    if _decode_oid(token[s:e]) != SIGNED_DATA_OID:
        raise ValueError('token is not CMS SignedData')
    _, s, e = _expect(content_info, 1, _CONTEXT_0, 'content')
    sd_tag, s, e = _read_tlv(token, s)
    if sd_tag != _SEQUENCE:
        raise ValueError('SignedData is not a SEQUENCE')
    signed_data = _children(token, s, e)
    _, s, e = _expect(signed_data, 2, _SEQUENCE, 'encapContentInfo')
    encap = _children(token, s, e)
    _, s2, e2 = _expect(encap, 0, _OID, 'eContentType')
    if _decode_oid(token[s2:e2]) != TST_INFO_OID:
        raise ValueError('encapsulated content is not TSTInfo')
    _, s2, e2 = _expect(encap, 1, _CONTEXT_0, 'eContent')
    o_tag, s2, e2 = _read_tlv(token, s2)
    if o_tag != _OCTET_STRING:
        raise ValueError('eContent is not an OCTET STRING')
    tst = token[s2:e2]

    tag, cs, ce = _read_tlv(tst, 0)
    if tag != _SEQUENCE or ce != len(tst):
        raise ValueError('TSTInfo is not a single SEQUENCE')
    fields = _children(tst, cs, ce)
    _expect(fields, 0, _INTEGER, 'TSTInfo.version')
    _, s, e = _expect(fields, 1, _OID, 'TSTInfo.policy')
    policy = _decode_oid(tst[s:e])
    _, s, e = _expect(fields, 2, _SEQUENCE, 'messageImprint')
    imprint = _children(tst, s, e)
    _, s, e = _expect(imprint, 0, _SEQUENCE, 'hashAlgorithm')
    alg = _children(tst, s, e)
    _, s2, e2 = _expect(alg, 0, _OID, 'hashAlgorithm.algorithm')
    algorithm = _decode_oid(tst[s2:e2])
    _, s, e = _expect(imprint, 1, _OCTET_STRING, 'hashedMessage')
    hashed = tst[s:e]
    _, s, e = _expect(fields, 3, _INTEGER, 'serialNumber')
    serial = _decode_uint(tst[s:e])
    _, s, e = _expect(fields, 4, _GENERALIZED_TIME, 'genTime')
    gen_time = _parse_gen_time(tst[s:e])
    nonce = None
    for tag, s, e in fields[5:]:  # accuracy / ordering precede nonce
        if tag == _INTEGER:
            nonce = _decode_uint(tst[s:e])
            break
    return TokenInfo(gen_time=gen_time, imprint_algorithm=algorithm, imprint=hashed, nonce=nonce, policy=policy,
                     serial_number=serial)


def _safe_text(raw: bytes) -> str:
    text = ''.join(ch for ch in raw.decode('utf-8', 'replace') if ch.isprintable())
    return text[:ERROR_TEXT_MAX]


def _status_text(data: bytes, status_info) -> str:
    """Printable PKIFreeText of a rejection (untrusted remote text; trimmed)."""
    parts = []
    for tag, s, e in status_info[1:]:
        if tag == _SEQUENCE:  # PKIFreeText = SEQUENCE OF UTF8String
            for _, ts, te in _children(data, s, e):
                parts.append(_safe_text(data[ts:te]))
    return '; '.join(p for p in parts if p)


def parse_timestamp_response(data: bytes, *, digest: bytes, nonce: int) -> tuple[bytes, TokenInfo]:
    """Check a ``TimeStampResp`` against what was requested. Returns the raw
    ``TimeStampToken`` DER and its parsed fields, or raises ``TimestampError``
    (``rejected``, ``malformed_response``, ``imprint_mismatch``,
    ``nonce_mismatch``)."""
    try:
        tag, cs, ce = _read_tlv(data, 0)
        if tag != _SEQUENCE or ce != len(data):
            raise ValueError('response is not a single SEQUENCE')
        top = _children(data, cs, ce)
        _, s, e = _expect(top, 0, _SEQUENCE, 'PKIStatusInfo')
        status_info = _children(data, s, e)
        _, s, e = _expect(status_info, 0, _INTEGER, 'PKIStatus')
        status = _decode_uint(data[s:e])
        if status not in (STATUS_GRANTED, STATUS_GRANTED_WITH_MODS):
            detail = _status_text(data, status_info)
            raise TimestampError('rejected', f'TSA rejected the request (PKIStatus {status})'
                                 + (f': {detail}' if detail else ''))
        if len(top) != 2 or top[1][0] != _SEQUENCE:
            raise ValueError('granted response without a TimeStampToken')
        token = data[top[0][2]:top[1][2]]  # children are contiguous: token starts where PKIStatusInfo ends
        info = parse_token(token)
    except TimestampError:
        raise
    except (ValueError, UnicodeDecodeError, IndexError) as exc:
        raise TimestampError('malformed_response', f'Unusable TSA response: {exc}') from None
    if info.imprint_algorithm != SHA256_OID or info.imprint != digest:
        raise TimestampError('imprint_mismatch', 'The token does not cover the requested digest')
    if info.nonce != nonce:
        raise TimestampError('nonce_mismatch', 'The token does not carry the requested nonce')
    return token, info


# ── Configuration / transport ───────────────────────────────────────────────

def tsa_url() -> str:
    return (current_app.config.get('TSA_URL') or '').strip()


def is_enabled() -> bool:
    return bool(tsa_url())


def public_url(url: str) -> str:
    """The URL without userinfo, query or fragment: safe to store, show and
    ship in manifests (a TSA URL may carry basic-auth credentials)."""
    parts = urlsplit(url)
    host = parts.hostname or ''
    if ':' in host:
        host = f'[{host}]'
    netloc = host + (f':{parts.port}' if parts.port else '')
    return urlunsplit((parts.scheme, netloc, parts.path, '', ''))


def _post(url: str, request_der: bytes) -> bytes:
    cfg = current_app.config
    timeout = float(cfg.get('TSA_TIMEOUT_SECONDS', 10))
    cap = int(cfg.get('TSA_MAX_RESPONSE_BYTES', 65536))
    deadline = time.monotonic() + timeout
    try:
        resp = requests.post(url, data=request_der, headers={'Content-Type': CONTENT_TYPE_REQUEST,
                                                             'Accept': 'application/timestamp-reply'},
                             timeout=(timeout, timeout), allow_redirects=False, stream=True)
    except requests.Timeout:
        raise TimestampError('timeout', f'TSA did not answer within {timeout:g}s') from None
    except requests.RequestException as exc:
        raise TimestampError('connection_error', f'Could not reach the TSA ({type(exc).__name__})') from None
    try:
        if 300 <= resp.status_code < 400:
            raise TimestampError('redirect', f'TSA answered with a redirect (HTTP {resp.status_code}); '
                                             'redirects are not followed')
        if resp.status_code != 200:
            raise TimestampError('http_error', f'TSA answered HTTP {resp.status_code}')
        declared = resp.headers.get('Content-Length')
        if declared and declared.isdigit() and int(declared) > cap:
            raise TimestampError('response_too_large', f'TSA response exceeds {cap} bytes')
        body = bytearray()
        try:
            for chunk in resp.iter_content(chunk_size=8192):
                body.extend(chunk)
                if len(body) > cap:
                    raise TimestampError('response_too_large', f'TSA response exceeds {cap} bytes')
                if time.monotonic() > deadline:
                    raise TimestampError('timeout', f'TSA did not finish answering within {timeout:g}s')
        except requests.Timeout:
            raise TimestampError('timeout', f'TSA did not answer within {timeout:g}s') from None
        except requests.RequestException as exc:
            raise TimestampError('connection_error', f'TSA connection failed ({type(exc).__name__})') from None
        return bytes(body)
    finally:
        resp.close()


@dataclass(frozen=True)
class Timestamp:
    token_der: bytes
    nonce: int
    gen_time: datetime
    tsa_url: str  # public form (no credentials)


def request_timestamp(head_hash: str) -> Timestamp:
    """Ask the configured TSA to timestamp the 32-byte ledger head hash.

    Raises ``TimestampError`` for every failure, including ``tsa_disabled``
    when ``TSA_URL`` is empty and ``url_refused`` when the URL does not pass
    the outbound URL guard (checked on every call)."""
    url = tsa_url()
    if not url:
        raise TimestampError('tsa_disabled', 'RFC 3161 anchoring is not configured (TSA_URL is empty)')
    ok, reason = validate_outbound_url(url, allow_allowlisted_private=True)
    if not ok:
        raise TimestampError('url_refused', f'TSA_URL refused by the outbound URL policy: {reason}')
    try:
        digest = bytes.fromhex(head_hash)
    except ValueError:
        digest = b''
    if len(digest) != 32:
        raise ValueError('head_hash must be 64 hexadecimal characters')
    nonce = new_nonce()
    reply = _post(url, build_timestamp_request(digest, nonce))
    token, info = parse_timestamp_response(reply, digest=digest, nonce=nonce)
    return Timestamp(token_der=token, nonce=nonce, gen_time=info.gen_time, tsa_url=public_url(url))


def token_binding(token_der: bytes | None, head_hash: str, nonce) -> tuple[str, datetime | None]:
    """Re-check a stored token against its anchor row: ``('ok'|'mismatch'|
    'unparseable'|'missing', gen_time)``. Not a signature check."""
    if not token_der:
        return 'missing', None
    try:
        info = parse_token(bytes(token_der))
    except (ValueError, UnicodeDecodeError, IndexError):
        return 'unparseable', None
    ok = (info.imprint_algorithm == SHA256_OID and info.imprint.hex() == (head_hash or '').lower()
          and (nonce is None or info.nonce == int(nonce)))
    return ('ok' if ok else 'mismatch'), info.gen_time
