"""Fake OpenID Connect identity provider for the SSO tests.

``FakeIdP`` holds real RSA and EC keys and signs ID tokens with PyJWT; it
replaces ``sso_service._http`` and answers discovery, JWKS, token (client
authentication and PKCE are checked like a real IdP) and userinfo requests.
``sso_login`` drives the whole browser flow through the Flask test client:
start -> (the user "signs in" at the IdP) -> callback.

Claim presets mimic real IdPs: ``entra_claims`` (no email_verified, GUID
groups, app roles, amr), ``okta_claims`` (groups scope), ``keycloak_claims``
(realm_access.roles, email_verified).
"""
import base64
import hashlib
import json
import time
import uuid
from urllib.parse import parse_qs, unquote, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

ISSUER = 'https://idp.example.test/realms/ir'
CLIENT_ID = 'sheetstorm-web'
CLIENT_SECRET = 'top-secret:with/odd+chars'


class FakeIdP:
    def __init__(self, issuer=ISSUER):
        self.issuer = issuer
        self.client_id = CLIENT_ID
        self.client_secret = CLIENT_SECRET
        self.rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.ec_key = ec.generate_private_key(ec.SECP256R1())
        self.kid = 'rsa-1'
        self.extra_jwks = []          # additional public JWKs to publish
        self.publish = True           # publish the RSA key at all
        self.discovery_overrides = {}
        self.userinfo = {}            # access_token -> claims
        self.codes = {}
        self.calls = []

    # ── keys and tokens ──────────────────────────────────────────────
    def jwk(self, key=None, kid=None, alg='RS256'):
        key = key or self.rsa_key
        algo = jwt.algorithms.RSAAlgorithm if isinstance(key, rsa.RSAPrivateKey) else jwt.algorithms.ECAlgorithm
        data = json.loads(algo.to_jwk(key.public_key()))
        data.update(kid=kid or self.kid, use='sig', alg=alg)
        return data

    def jwks(self):
        return ([self.jwk()] if self.publish else []) + list(self.extra_jwks)

    def discovery_doc(self):
        base = self.issuer
        return {
            'issuer': self.issuer,
            'authorization_endpoint': f'{base}/protocol/openid-connect/auth',
            'token_endpoint': f'{base}/protocol/openid-connect/token',
            'userinfo_endpoint': f'{base}/protocol/openid-connect/userinfo',
            'jwks_uri': f'{base}/protocol/openid-connect/certs',
            'id_token_signing_alg_values_supported': ['RS256', 'ES256'],
            'code_challenge_methods_supported': ['S256'],
            'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post'],
            'scopes_supported': ['openid', 'email', 'profile', 'groups'],
            **self.discovery_overrides,
        }

    def id_token(self, params, claims, *, key=None, alg='RS256', kid=None, headers=None, **over):
        now = int(time.time())
        body = {'iss': self.issuer, 'aud': self.client_id, 'iat': now, 'exp': now + 300,
                'nonce': params.get('nonce'), 'sub': 'user-1'}
        body.update(claims)
        body.update(over)
        hdr = {'kid': kid or self.kid, **(headers or {})}
        if alg == 'none':
            return jwt.encode(body, None, algorithm='none', headers=hdr)
        if alg.startswith('HS'):
            return jwt.encode(body, self.client_secret, algorithm=alg, headers=hdr)
        return jwt.encode(body, key or (self.ec_key if alg.startswith('ES') else self.rsa_key),
                          algorithm=alg, headers=hdr)

    # ── the browser leg at the IdP ───────────────────────────────────
    def authorize(self, auth_url, claims, *, token_opts=None, userinfo=None):
        """The user signs in: validate the authorization request, return
        (code, state) for the callback."""
        parsed = urlparse(auth_url)
        assert f'{parsed.scheme}://{parsed.netloc}{parsed.path}' == self.discovery_doc()['authorization_endpoint']
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        assert params['response_type'] == 'code'
        assert params['client_id'] == self.client_id
        assert params['code_challenge_method'] == 'S256'
        assert 'openid' in params['scope'].split()
        code = uuid.uuid4().hex
        self.codes[code] = {'params': params, 'claims': claims, 'token_opts': token_opts or {},
                            'userinfo': userinfo}
        return code, params['state']

    # ── replacement for sso_service._http ───────────────────────────
    def http(self, method, url, **kwargs):
        self.calls.append((method, url))
        doc = self.discovery_doc()
        if url == self.issuer.rstrip('/') + '/.well-known/openid-configuration':
            return 200, json.dumps(doc).encode(), 'application/json'
        if url == doc['jwks_uri']:
            return 200, json.dumps({'keys': self.jwks()}).encode(), 'application/json'
        if url == doc['token_endpoint'] and method == 'POST':
            return self._token(kwargs.get('data') or {}, kwargs.get('headers') or {})
        if url == doc['userinfo_endpoint']:
            token = (kwargs.get('headers') or {}).get('Authorization', '').removeprefix('Bearer ')
            if token not in self.userinfo:
                return 401, b'{"error":"invalid_token"}', 'application/json'
            return 200, json.dumps(self.userinfo[token]).encode(), 'application/json'
        return 404, b'not found', 'text/plain'

    def _token(self, data, headers):
        def error(err, status=400):
            return status, json.dumps({'error': err}).encode(), 'application/json'

        auth = headers.get('Authorization', '')
        if auth.startswith('Basic '):
            user, _, pw = base64.b64decode(auth[6:]).decode().partition(':')
            client_id, secret = unquote(user), unquote(pw)
        else:
            client_id, secret = data.get('client_id'), data.get('client_secret')
        if client_id != self.client_id or secret != self.client_secret:
            return error('invalid_client', 401)
        entry = self.codes.pop(data.get('code'), None)  # single use
        if entry is None or data.get('grant_type') != 'authorization_code':
            return error('invalid_grant')
        params = entry['params']
        if data.get('redirect_uri') != params['redirect_uri']:
            return error('invalid_grant')
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(data.get('code_verifier', '').encode()).digest()).rstrip(b'=').decode()
        if challenge != params['code_challenge']:
            return error('invalid_grant')
        access_token = uuid.uuid4().hex
        if entry['userinfo'] is not None:
            self.userinfo[access_token] = entry['userinfo']
        body = {'access_token': access_token, 'token_type': 'Bearer', 'expires_in': 300,
                'id_token': self.id_token(params, entry['claims'], **entry['token_opts'])}
        return 200, json.dumps(body).encode(), 'application/json'


def entra_claims(email='analyst@contoso.example', sub='AAAAAAAAAAAAAAAAAAAAAIkzqFVrSaSaFHy782bbtaQ', **extra):
    # Entra ID v2 ID token: no email_verified, groups are object ids, app roles
    # in `roles`, amr lists the methods used.
    return {'sub': sub, 'oid': '00000000-0000-0000-66f3-3332eca7ea81', 'tid': '72f988bf-0000-0000-0000-2d7cd011db47',
            'name': 'Ana Lyst', 'preferred_username': email, 'email': email,
            'groups': ['8f3a6e2c-1b2d-4c5e-9f00-112233445566'], 'roles': ['SheetStorm.Responder'],
            'amr': ['pwd', 'mfa'], **extra}


def okta_claims(email='responder@acme.example', sub='00u1abcd2EFGHijk3l4m', **extra):
    return {'sub': sub, 'email': email, 'email_verified': True, 'name': 'Res Ponder',
            'groups': ['Everyone', 'IR-Responders'], 'amr': ['pwd', 'otp', 'mfa'], **extra}


def keycloak_claims(email='lead@lab.example', sub='f81d4fae-7dec-11d0-a765-00a0c91e6bf6', **extra):
    return {'sub': sub, 'email': email, 'email_verified': True, 'name': 'Lead Investigator',
            'preferred_username': 'lead', 'realm_access': {'roles': ['offline_access', 'ir-admin']}, **extra}


@pytest.fixture
def fake_idp(app, monkeypatch):
    from app.services import sso_service
    idp = FakeIdP()
    monkeypatch.setattr(sso_service, '_http', idp.http)
    return idp


@pytest.fixture
def make_sso_provider(app, db):
    """make_sso_provider(org, editor, **fields) -> SsoProvider (deleted after the test)."""
    from app.models.sso import SsoProvider
    from app.services import sso_service
    created = []

    def make(org, editor=None, **fields):
        data = dict(slug=f'idp-{uuid.uuid4().hex[:8]}', display_name='Test IdP', preset='keycloak',
                    issuer=ISSUER, client_id=CLIENT_ID, email_claims=['email'], role_mappings=[],
                    allowed_groups=[], allowed_domains=[], created_by=editor.id if editor else None,
                    updated_by=editor.id if editor else None)
        secret = fields.pop('client_secret', CLIENT_SECRET)
        data.update(fields)
        provider = SsoProvider(organization_id=org.id, **data)
        sso_service.set_client_secret(provider, secret)
        db.session.add(provider)
        db.session.commit()
        created.append(provider.id)
        return provider

    yield make

    # Users the sign-ins created go with their provider; linked local users stay.
    from app.models import User
    from app.models.sso import UserIdentity
    db.session.rollback()
    for pid in created:
        for identity in UserIdentity.query.filter_by(provider_id=pid).all():
            user = db.session.get(User, identity.user_id)
            if user is not None and user.auth_provider == 'oidc':
                db.session.delete(user)
        row = db.session.get(SsoProvider, pid)
        if row is not None:
            db.session.delete(row)
    db.session.commit()


@pytest.fixture
def sso_login(app):
    """sso_login(client, idp, provider, claims, next=None, token_opts=None,
    userinfo=None) -> the callback response (a redirect)."""
    def run(client, idp, provider, claims, next=None, token_opts=None, userinfo=None, tamper_state=False):
        url = f'/api/v1/auth/sso/{provider.slug}/start'
        if next is not None:
            url += f'?next={next}'
        start = client.get(url)
        assert start.status_code == 302, start.get_data(as_text=True)
        code, state = idp.authorize(start.headers['Location'], claims, token_opts=token_opts, userinfo=userinfo)
        if tamper_state:
            state = state[:-2] + ('AA' if not state.endswith('AA') else 'BB')
        return client.get(f'/api/v1/auth/sso/{provider.slug}/callback?code={code}&state={state}')
    return run
