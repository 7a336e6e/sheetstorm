#!/usr/bin/env python3
"""A minimal OpenID Connect provider for end-to-end tests. TEST USE ONLY.

Standard library only (RSA key generation and RS256 signing in pure Python),
so it adds no dependency to the project. It implements what SheetStorm's SSO
uses: discovery, an authorization page with one button per test user
(authorization code flow, PKCE S256 enforced), the token endpoint
(client_secret_basic or client_secret_post), userinfo and JWKS.

Environment:
  MOCK_OIDC_ISSUER       issuer and back-channel base URL, as the backend
                         reaches it (default http://mock-oidc:9000)
  MOCK_OIDC_PUBLIC_URL   base URL the browser uses for /authorize
                         (default: the issuer)
  MOCK_OIDC_CLIENT_ID / MOCK_OIDC_CLIENT_SECRET (default sheetstorm-e2e / mock-secret)
  MOCK_OIDC_USERS        JSON list of users (default: USERS below)
  PORT                   listen port (default 9000)
"""
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlencode, urlparse

ISSUER = os.environ.get('MOCK_OIDC_ISSUER', 'http://mock-oidc:9000').rstrip('/')
PUBLIC_URL = os.environ.get('MOCK_OIDC_PUBLIC_URL', ISSUER).rstrip('/')
CLIENT_ID = os.environ.get('MOCK_OIDC_CLIENT_ID', 'sheetstorm-e2e')
CLIENT_SECRET = os.environ.get('MOCK_OIDC_CLIENT_SECRET', 'mock-secret')
PORT = int(os.environ.get('PORT', '9000'))

USERS = [
    {'id': 'alice', 'name': 'Alice Lead', 'email': 'alice@mock-idp.example', 'email_verified': True,
     'groups': ['ir-leads'], 'amr': ['pwd', 'mfa']},
    {'id': 'bob', 'name': 'Bob Analyst', 'email': 'bob@mock-idp.example', 'email_verified': True,
     'groups': ['ir-analysts'], 'amr': ['pwd']},
    {'id': 'carol', 'name': 'Carol Outsider', 'email': 'carol@mock-idp.example', 'email_verified': True,
     'groups': [], 'amr': ['pwd']},
    {'id': 'dave', 'name': 'Dave Unverified', 'email': 'dave@mock-idp.example', 'email_verified': False,
     'groups': ['ir-analysts'], 'amr': ['pwd']},
    {'id': 'erin', 'name': 'Erin Totp', 'email': 'erin@mock-idp.example', 'email_verified': True,
     'groups': ['ir-analysts'], 'amr': ['pwd']},
]
if os.environ.get('MOCK_OIDC_USERS'):
    USERS = json.loads(os.environ['MOCK_OIDC_USERS'])
USERS_BY_ID = {u['id']: u for u in USERS}


# ── RSA (pure Python) ─────────────────────────────────────────────────────

def _probably_prime(n, rounds=40):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        x = pow(secrets.randbelow(n - 3) + 2, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _probably_prime(candidate):
            return candidate


def _rsa_key(bits=2048, e=65537):
    while True:
        p, q = _prime(bits // 2), _prime(bits // 2)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return {'n': p * q, 'e': e, 'd': pow(e, -1, phi)}


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _int_bytes(i):
    return i.to_bytes((i.bit_length() + 7) // 8, 'big')


_SHA256_DIGEST_INFO = bytes.fromhex('3031300d060960864801650304020105000420')


def _rs256(key, signing_input):
    k = (key['n'].bit_length() + 7) // 8
    t = _SHA256_DIGEST_INFO + hashlib.sha256(signing_input).digest()
    em = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return pow(int.from_bytes(em, 'big'), key['d'], key['n']).to_bytes(k, 'big')


KEY = _rsa_key()
KID = 'mock-' + hashlib.sha256(_int_bytes(KEY['n'])).hexdigest()[:12]
JWKS = {'keys': [{'kty': 'RSA', 'use': 'sig', 'alg': 'RS256', 'kid': KID,
                  'n': _b64url(_int_bytes(KEY['n'])), 'e': _b64url(_int_bytes(KEY['e']))}]}


def _jwt(claims):
    header = _b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT', 'kid': KID}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f'{header}.{payload}'.encode()
    return f'{header}.{payload}.{_b64url(_rs256(KEY, signing_input))}'


# ── Protocol state ────────────────────────────────────────────────────────

CODES, TOKENS = {}, {}
LOCK = threading.Lock()


def _claims(user):
    return {'sub': f"mock-{user['id']}", 'email': user['email'], 'email_verified': user.get('email_verified', True),
            'name': user['name'], 'preferred_username': user['id'], 'groups': user.get('groups', []),
            'amr': user.get('amr', ['pwd'])}


DISCOVERY = {
    'issuer': ISSUER,
    'authorization_endpoint': f'{PUBLIC_URL}/authorize',
    'token_endpoint': f'{ISSUER}/token',
    'userinfo_endpoint': f'{ISSUER}/userinfo',
    'jwks_uri': f'{ISSUER}/jwks',
    'response_types_supported': ['code'],
    'subject_types_supported': ['public'],
    'id_token_signing_alg_values_supported': ['RS256'],
    'code_challenge_methods_supported': ['S256'],
    'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post'],
    'scopes_supported': ['openid', 'email', 'profile', 'groups'],
    'claims_supported': ['sub', 'email', 'email_verified', 'name', 'groups', 'amr'],
}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Mock IdP sign-in</title></head>
<body style="font-family:sans-serif;max-width:420px;margin:60px auto">
<h1>Mock IdP</h1><p>Test identity provider. Choose a user:</p>
<form method="post" action="/authorize">{hidden}{buttons}</form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # one line per request
        print('mock-oidc:', self.command, self.path.split('?')[0], *args[1:2], flush=True)

    def _send(self, status, body, ctype='application/json', headers=None):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == 'application/json' else body).encode()
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _form(self):
        length = int(self.headers.get('Content-Length') or 0)
        return {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == '/.well-known/openid-configuration':
            return self._send(200, DISCOVERY)
        if url.path == '/jwks':
            return self._send(200, JWKS)
        if url.path == '/healthz':
            return self._send(200, {'ok': True})
        if url.path == '/userinfo':
            token = (self.headers.get('Authorization') or '').removeprefix('Bearer ')
            with LOCK:
                claims = TOKENS.get(token)
            return self._send(200, claims) if claims else self._send(401, {'error': 'invalid_token'})
        if url.path == '/authorize':
            if q.get('client_id') != CLIENT_ID or q.get('response_type') != 'code' or not q.get('redirect_uri'):
                return self._send(400, {'error': 'invalid_request'})
            if q.get('code_challenge_method') != 'S256' or not q.get('code_challenge'):
                return self._send(400, {'error': 'invalid_request', 'error_description': 'PKCE S256 required'})
            keep = ('client_id', 'redirect_uri', 'state', 'nonce', 'code_challenge', 'scope')
            hidden = ''.join(f'<input type="hidden" name="{k}" value="{html.escape(q.get(k, ""))}">' for k in keep)
            buttons = ''.join(
                f'<p><button type="submit" name="user" value="{html.escape(u["id"])}">'
                f'Sign in as {html.escape(u["name"])}</button></p>' for u in USERS)
            return self._send(200, PAGE.format(hidden=hidden, buttons=buttons), 'text/html; charset=utf-8')
        return self._send(404, {'error': 'not_found'})

    def do_POST(self):
        path = urlparse(self.path).path
        form = self._form()
        if path == '/authorize':
            user = USERS_BY_ID.get(form.get('user'))
            if not user:
                return self._send(400, {'error': 'unknown user'})
            code = secrets.token_urlsafe(24)
            with LOCK:
                CODES[code] = {**form, 'user': user, 'expires': time.time() + 120}
            target = form['redirect_uri'] + ('&' if '?' in form['redirect_uri'] else '?') + \
                urlencode({'code': code, 'state': form.get('state', '')})
            return self._send(302, b'', 'text/plain', {'Location': target})
        if path == '/token':
            auth = self.headers.get('Authorization') or ''
            if auth.startswith('Basic '):
                client_id, _, secret = base64.b64decode(auth[6:]).decode().partition(':')
                client_id, secret = unquote(client_id), unquote(secret)
            else:
                client_id, secret = form.get('client_id'), form.get('client_secret')
            if client_id != CLIENT_ID or not hmac.compare_digest(secret or '', CLIENT_SECRET):
                return self._send(401, {'error': 'invalid_client'})
            with LOCK:
                entry = CODES.pop(form.get('code', ''), None)
            if (not entry or entry['expires'] < time.time() or form.get('grant_type') != 'authorization_code'
                    or form.get('redirect_uri') != entry['redirect_uri']):
                return self._send(400, {'error': 'invalid_grant'})
            challenge = _b64url(hashlib.sha256(form.get('code_verifier', '').encode()).digest())
            if challenge != entry['code_challenge']:
                return self._send(400, {'error': 'invalid_grant', 'error_description': 'PKCE verification failed'})
            now = int(time.time())
            claims = _claims(entry['user'])
            id_token = _jwt({**claims, 'iss': ISSUER, 'aud': CLIENT_ID, 'iat': now, 'exp': now + 300,
                             'nonce': entry.get('nonce'), 'auth_time': now})
            access_token = secrets.token_urlsafe(24)
            with LOCK:
                TOKENS[access_token] = claims
            return self._send(200, {'access_token': access_token, 'token_type': 'Bearer', 'expires_in': 300,
                                    'id_token': id_token})
        return self._send(404, {'error': 'not_found'})


if __name__ == '__main__':
    print(f'mock-oidc: issuer {ISSUER}, browser URL {PUBLIC_URL}, kid {KID}, port {PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
