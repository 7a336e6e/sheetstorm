"""OpenID Connect single sign-on: the sign-in flow against a fake IdP (real
RSA/EC signatures, PKCE and client authentication checked), the account,
group, role and MFA rules, and the admin API.

Claim sets mimic Entra ID, Okta and Keycloak (tests/fixtures/sso.py).
"""
import time
import uuid
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest

from tests.fixtures.sso import CLIENT_SECRET, ISSUER, entra_claims, keycloak_claims, okta_claims

API = '/api/v1'


def _location(resp):
    return urlparse(resp.headers['Location'])


def _sso_error(resp):
    assert resp.status_code == 302, resp.get_data(as_text=True)
    loc = _location(resp)
    assert loc.path == '/login', resp.headers['Location']
    return parse_qs(loc.query).get('sso_error', [None])[0]


def _signed_in(resp, path='/dashboard'):
    assert resp.status_code == 302, resp.get_data(as_text=True)
    assert resp.headers['Location'] == path, resp.headers['Location']
    cookies = resp.headers.getlist('Set-Cookie')
    assert any(c.startswith('access_token_cookie=') and 'Max-Age=0' not in c for c in cookies)
    return cookies


def _user(email):
    from app.models import User
    return User.query.filter(User.email == email).first()


def _role_names(user):
    from app import db
    db.session.refresh(user)
    return sorted(ur.role.name for ur in user.user_roles)


def _role_id(name):
    from app.models import Role
    return str(Role.query.filter_by(name=name, is_system=True).one().id)


def _last_auth_event(action='sso_login'):
    from app.models import AuditLog
    return (AuditLog.query.filter_by(action=action).order_by(AuditLog.created_at.desc()).first())


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(users):
    return users['Administrator']


# ── Happy paths ─────────────────────────────────────────────────────

def test_first_sign_in_creates_the_user_with_mapped_roles(client, fake_idp, make_sso_provider, sso_login, org_a,
                                                          admin, db):
    provider = make_sso_provider(org_a, admin, auto_provision=True, groups_claim='realm_access.roles',
                                 role_mappings=[{'group': 'IR-Admin', 'role_id': _role_id('Analyst')}])
    resp = sso_login(client, fake_idp, provider, keycloak_claims())
    _signed_in(resp)

    user = _user('lead@lab.example')
    assert user.organization_id == org_a.id
    assert user.auth_provider == 'oidc' and user.password_hash is None and user.is_verified
    assert user.name == 'Lead Investigator'
    assert _role_names(user) == ['Analyst']  # group matching ignores case
    me = client.get(f'{API}/auth/me')
    assert me.status_code == 200 and me.get_json()['email'] == 'lead@lab.example'
    event = _last_auth_event()
    assert event.details['provider'] == provider.slug and event.details['created'] is True
    # Single-use state: the cookie is cleared after the callback.
    assert any(c.startswith('sheetstorm_sso_state=;') for c in resp.headers.getlist('Set-Cookie'))


def test_returning_user_is_found_by_subject_even_after_an_email_change(client, fake_idp, make_sso_provider,
                                                                      sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    user_id = _user('responder@acme.example').id
    resp = sso_login(client, fake_idp, provider, okta_claims(email='renamed@acme.example'))
    _signed_in(resp)
    from app.models.sso import UserIdentity
    identity = UserIdentity.query.filter_by(provider_id=provider.id).one()
    assert identity.user_id == user_id and identity.email == 'renamed@acme.example'
    assert _user('renamed@acme.example') is None  # the account itself is not renamed


def test_next_path_is_kept_but_never_an_open_redirect(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(), next='/dashboard/incidents'),
               '/dashboard/incidents')
    for evil in ('//evil.example/x', 'https://evil.example', '/\\evil.example', 'javascript:alert(1)'):
        _signed_in(sso_login(client, fake_idp, provider, okta_claims(), next=evil), '/dashboard')


def test_es256_tokens_and_client_secret_post(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    fake_idp.extra_jwks.append(fake_idp.jwk(fake_idp.ec_key, kid='ec-1', alg='ES256'))
    provider = make_sso_provider(org_a, admin, auto_provision=True, token_auth_method='client_secret_post')
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(), token_opts={'alg': 'ES256', 'kid': 'ec-1'}))


def test_userinfo_fills_claims_the_id_token_lacks(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, groups_claim='groups',
                                 role_mappings=[{'group': 'IR-Responders', 'role_id': _role_id('Incident Responder')}])
    claims = {'sub': 'okta-thin'}
    info = {'sub': 'okta-thin', 'email': 'thin@acme.example', 'email_verified': True, 'groups': ['IR-Responders']}
    _signed_in(sso_login(client, fake_idp, provider, claims, userinfo=info))
    assert _role_names(_user('thin@acme.example')) == ['Incident Responder']

    bad = {'sub': 'someone-else', 'email': 'x@acme.example', 'email_verified': True}
    assert _sso_error(sso_login(client, fake_idp, provider, {'sub': 'okta-thin2'}, userinfo=bad)) == 'token_invalid'


def test_entra_shaped_tokens_with_app_roles(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    # Entra sends no email_verified: such a provider is configured with
    # require_email_verified off and maps app roles (`roles`).
    provider = make_sso_provider(org_a, admin, preset='entra', auto_provision=True, require_email_verified=False,
                                 email_claims=['email', 'preferred_username'], groups_claim='roles',
                                 role_mappings=[{'group': 'SheetStorm.Responder',
                                                 'role_id': _role_id('Incident Responder')}])
    _signed_in(sso_login(client, fake_idp, provider, entra_claims()))
    assert _role_names(_user('analyst@contoso.example')) == ['Incident Responder']


# ── Protocol and token validation ───────────────────────────────────

@pytest.mark.parametrize('token_opts', [
    {'iss': 'https://evil.example/realms/ir'},
    {'aud': 'another-client'},
    {'exp': int(time.time()) - 3600, 'iat': int(time.time()) - 7200},
    {'nonce': 'not-the-nonce'},
    {'alg': 'none'},
    {'alg': 'HS256'},
    {'aud': ['sheetstorm-web', 'other'], 'azp': 'other'},
    {'sub': ''},
])
def test_invalid_id_tokens_are_refused(client, fake_idp, make_sso_provider, sso_login, org_a, admin, token_opts):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    resp = sso_login(client, fake_idp, provider, okta_claims(), token_opts=token_opts)
    assert _sso_error(resp) == 'token_invalid'
    assert _user('responder@acme.example') is None
    assert _last_auth_event().details['reason'] == 'token_invalid'


@pytest.mark.parametrize('alg', ['none', 'HS256', 'HS512'])
def test_disallowed_algorithms_are_refused_before_any_key_lookup(client, fake_idp, make_sso_provider, sso_login,
                                                                 org_a, admin, alg):
    # Key confusion: an IdP JWKS without "alg" (Entra omits it) must not let an
    # HMAC token "signed" with public material through.
    fake_idp.publish = False
    bare = fake_idp.jwk()
    bare.pop('alg')
    fake_idp.extra_jwks.append(bare)
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    resp = sso_login(client, fake_idp, provider, okta_claims(), token_opts={'alg': alg})
    assert _sso_error(resp) == 'token_invalid'
    assert 'is not allowed' in _last_auth_event().details['detail']


def test_a_token_signed_by_an_unpublished_key_is_refused(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    from cryptography.hazmat.primitives.asymmetric import rsa
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims(),
                                token_opts={'key': rogue})) == 'token_invalid'


def test_key_rotation_refetches_the_jwks_once(client, fake_idp, make_sso_provider, sso_login, org_a, admin, app):
    from cryptography.hazmat.primitives.asymmetric import rsa
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))  # caches the JWKS
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fake_idp.rsa_key, fake_idp.kid = new_key, 'rsa-2'
    jwks_calls = sum(1 for _, url in fake_idp.calls if url.endswith('/certs'))
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    assert sum(1 for _, url in fake_idp.calls if url.endswith('/certs')) == jwks_calls + 1


def test_the_state_is_single_use_and_bound_to_the_browser(client, app, fake_idp, make_sso_provider, sso_login,
                                                         org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    start = client.get(f'{API}/auth/sso/{provider.slug}/start')
    code, state = fake_idp.authorize(start.headers['Location'], okta_claims())
    # Another browser (no state cookie) cannot complete this sign-in.
    other = app.test_client()
    assert _sso_error(other.get(f'{API}/auth/sso/{provider.slug}/callback?code={code}&state={state}')) \
        == 'state_invalid'
    # The state was consumed by that attempt: replaying it fails too.
    assert _sso_error(client.get(f'{API}/auth/sso/{provider.slug}/callback?code={code}&state={state}')) \
        == 'state_invalid'
    # A tampered state is unknown.
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims(), tamper_state=True)) == 'state_invalid'


def test_state_of_another_provider_is_refused(client, fake_idp, make_sso_provider, org_a, admin):
    first = make_sso_provider(org_a, admin, auto_provision=True)
    second = make_sso_provider(org_a, admin, auto_provision=True)
    start = client.get(f'{API}/auth/sso/{first.slug}/start')
    code, state = fake_idp.authorize(start.headers['Location'], okta_claims())
    assert _sso_error(client.get(f'{API}/auth/sso/{second.slug}/callback?code={code}&state={state}')) \
        == 'state_invalid'


def test_pkce_and_client_secret_are_sent(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, client_secret='wrong-secret')
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims())) == 'token_invalid'
    assert 'invalid_client' in _last_auth_event().details['detail']


def test_idp_error_and_disabled_provider(client, fake_idp, make_sso_provider, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    start = client.get(f'{API}/auth/sso/{provider.slug}/start')
    state = parse_qs(_location(start).query)['state'][0]
    resp = client.get(f'{API}/auth/sso/{provider.slug}/callback?error=access_denied&state={state}')
    assert _sso_error(resp) == 'access_denied'

    provider.is_enabled = False
    from app import db
    db.session.commit()
    assert _sso_error(client.get(f'{API}/auth/sso/{provider.slug}/start')) == 'provider_unavailable'
    assert _sso_error(client.get(f'{API}/auth/sso/no-such-idp/start')) == 'provider_unavailable'


def test_discovery_issuer_must_match(client, fake_idp, make_sso_provider, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    fake_idp.discovery_overrides = {'issuer': 'https://idp.example.test/realms/other'}
    assert _sso_error(client.get(f'{API}/auth/sso/{provider.slug}/start')) == 'provider_unavailable'


def test_http_issuers_and_private_hosts_are_refused_by_default(app, org_a, admin, make_sso_provider):
    from app.services import sso_service
    provider = make_sso_provider(org_a, admin, issuer='http://keycloak.internal/realms/ir')
    with app.test_request_context():
        with pytest.raises(sso_service.SsoError) as exc:
            sso_service._http('GET', provider.issuer)
        assert exc.value.code == 'provider_unavailable' and 'non-https' in exc.value.detail
        with pytest.raises(sso_service.SsoError) as exc:
            sso_service._http('GET', 'https://127.0.0.1/realms/ir/.well-known/openid-configuration')
        assert 'non-public' in exc.value.detail or 'blocked' in exc.value.detail


# ── Accounts ────────────────────────────────────────────────────────

def test_existing_account_needs_linking_enabled(client, fake_idp, make_sso_provider, sso_login, org_a, admin,
                                                make_user):
    local = make_user(org_a, roles=['Analyst'], email=f'local-{uuid.uuid4().hex[:6]}@lab.example')
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    assert _sso_error(sso_login(client, fake_idp, provider, keycloak_claims(email=local.email))) == 'account_exists'

    provider.link_existing = True
    from app import db
    db.session.commit()
    _signed_in(sso_login(client, fake_idp, provider, keycloak_claims(email=local.email)))
    from app.models.sso import UserIdentity
    assert UserIdentity.query.filter_by(provider_id=provider.id, user_id=local.id).count() == 1
    assert _last_auth_event().details['linked'] is True
    # A second IdP subject claiming the same email cannot take the account.
    assert _sso_error(sso_login(client, fake_idp, provider,
                                keycloak_claims(email=local.email, sub='another-subject'))) == 'account_conflict'


def test_linking_requires_a_verified_email(client, fake_idp, make_sso_provider, sso_login, org_a, admin, make_user):
    local = make_user(org_a, roles=['Analyst'], email=f'unverified-{uuid.uuid4().hex[:6]}@contoso.example')
    provider = make_sso_provider(org_a, admin, link_existing=True, email_claims=['email', 'preferred_username'])
    assert _sso_error(sso_login(client, fake_idp, provider, entra_claims(email=local.email))) == 'email_unverified'
    # preferred_username never counts as verified.
    claims = keycloak_claims(sub='kc-2', email=None, preferred_username=local.email)
    claims.pop('email')
    assert _sso_error(sso_login(client, fake_idp, provider, claims)) == 'email_unverified'


def test_an_email_of_another_organization_is_never_used(client, fake_idp, make_sso_provider, sso_login, org_a,
                                                        admin, users):
    provider = make_sso_provider(org_a, admin, auto_provision=True, link_existing=True)
    resp = sso_login(client, fake_idp, provider, okta_claims(email=users['admin_b'].email))
    assert _sso_error(resp) == 'account_conflict'


def test_no_account_without_auto_provisioning(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin)
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims())) == 'no_account'
    assert _user('responder@acme.example') is None


def test_missing_email_and_domain_rules(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, allowed_domains=['acme.example'])
    assert _sso_error(sso_login(client, fake_idp, provider, {'sub': 'no-email'})) == 'email_missing'
    assert _sso_error(sso_login(client, fake_idp, provider, keycloak_claims())) == 'domain_not_allowed'
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))


def test_allowed_groups_gate_the_sign_in(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, groups_claim='groups',
                                 allowed_groups=['ir-responders'])
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims(groups=['Everyone']))) == 'group_not_allowed'
    assert _user('responder@acme.example') is None
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))


def test_disabled_and_locked_accounts_are_refused(client, fake_idp, make_sso_provider, sso_login, org_a, admin, db):
    from datetime import datetime, timedelta, timezone
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    user = _user('responder@acme.example')
    user.is_active = False
    db.session.commit()
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims())) == 'account_disabled'
    user.is_active = True
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.session.commit()
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims())) == 'account_disabled'


def test_sso_only_accounts_cannot_use_password_sign_in(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    resp = client.post(f'{API}/auth/login', json={'email': 'responder@acme.example', 'password': 'anything-1A!'})
    assert resp.status_code == 401


# ── Roles ───────────────────────────────────────────────────────────

def test_default_role_without_a_matching_group(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, groups_claim='groups',
                                 role_mappings=[{'group': 'IR-Leads', 'role_id': _role_id('Manager')}],
                                 default_role_id=_role_id('Analyst'))
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    assert _role_names(_user('responder@acme.example')) == ['Analyst']


def test_policy_default_role_when_nothing_is_configured(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    assert _role_names(_user('responder@acme.example')) == ['Viewer']


def test_every_login_sync_follows_the_idp(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, groups_claim='groups', role_sync='every_login',
                                 role_mappings=[{'group': 'IR-Responders', 'role_id': _role_id('Incident Responder')},
                                                {'group': 'IR-Leads', 'role_id': _role_id('Manager')}])
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    user = _user('responder@acme.example')
    assert _role_names(user) == ['Incident Responder']
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(groups=['IR-Leads'])))
    assert _role_names(user) == ['Manager']
    assert _last_auth_event().details['roles_synced'] is True


def test_first_login_mode_keeps_later_role_changes(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, groups_claim='groups',
                                 role_mappings=[{'group': 'IR-Responders', 'role_id': _role_id('Incident Responder')},
                                                {'group': 'IR-Leads', 'role_id': _role_id('Manager')}])
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(groups=['IR-Leads'])))
    assert _role_names(_user('responder@acme.example')) == ['Incident Responder']


def test_role_sync_never_removes_the_last_admin(client, fake_idp, make_sso_provider, sso_login, db, make_user):
    from app.models import Organization
    org = Organization(name='sso-solo', slug=f'sso-solo-{uuid.uuid4().hex[:6]}', settings={})
    db.session.add(org)
    db.session.commit()
    editor = make_user(org, roles=['Administrator'])
    provider = make_sso_provider(org, editor, auto_provision=True, groups_claim='groups', role_sync='every_login',
                                 role_mappings=[{'group': 'IR-Admins', 'role_id': _role_id('Administrator')}])
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(email='solo@acme.example', groups=['IR-Admins'])))
    sso_admin = _user('solo@acme.example')
    # The editor leaves: the SSO user is now the only administrator.
    editor.is_active = False
    db.session.commit()
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(email='solo@acme.example', groups=[])))
    assert _role_names(sso_admin) == ['Administrator']
    from app.models import AuditLog
    assert AuditLog.query.filter_by(action='sso_role_sync_blocked').count() >= 1


def test_mapping_an_editor_can_no_longer_grant_is_ignored(client, fake_idp, make_sso_provider, sso_login, org_a,
                                                          make_user, db):
    editor = make_user(org_a, perms=['users:manage', 'roles:manage', 'users:read'])
    provider = make_sso_provider(org_a, editor, auto_provision=True, groups_claim='groups',
                                 role_mappings=[{'group': 'IR-Responders', 'role_id': _role_id('Administrator')}])
    _signed_in(sso_login(client, fake_idp, provider, okta_claims()))
    assert _role_names(_user('responder@acme.example')) == ['Viewer']
    from app.models import AuditLog
    assert AuditLog.query.filter_by(action='sso_role_mapping_ignored').count() >= 1


# ── MFA ─────────────────────────────────────────────────────────────

def test_sheetstorm_totp_is_asked_after_the_idp(client, fake_idp, make_sso_provider, sso_login, org_a, admin,
                                                make_user, db):
    local = make_user(org_a, roles=['Analyst'], email=f'totp-{uuid.uuid4().hex[:6]}@lab.example')
    secret = pyotp.random_base32()
    local.mfa_enabled, local.mfa_secret = True, secret
    db.session.commit()
    provider = make_sso_provider(org_a, admin, link_existing=True)
    resp = sso_login(client, fake_idp, provider, keycloak_claims(email=local.email), next='/dashboard/incidents')
    assert resp.status_code == 302
    loc = _location(resp)
    assert loc.path == '/login' and parse_qs(loc.query) == {'sso': ['mfa'], 'next': ['/dashboard/incidents']}
    cookies = resp.headers.getlist('Set-Cookie')
    assert not any(c.startswith('access_token_cookie=') for c in cookies)
    assert any(c.startswith('sheetstorm_sso_mfa=') and 'HttpOnly' in c for c in cookies)

    bad = client.post(f'{API}/auth/mfa/complete', json={'mfa_code': '000000'})
    assert bad.status_code == 401
    ok = client.post(f'{API}/auth/mfa/complete', json={'mfa_code': pyotp.TOTP(secret).now()})
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()['user']['email'] == local.email
    assert any(c.startswith('sheetstorm_sso_mfa=;') for c in ok.headers.getlist('Set-Cookie'))
    assert _last_auth_event('sso_login_mfa').details['success'] is True


def test_idp_mfa_mode_skips_totp_and_enrollment(client, fake_idp, make_sso_provider, sso_login, set_policy, db,
                                                make_user):
    from app.models import Organization
    from app.services import security_policy
    org = Organization(name='sso-mfa', slug=f'sso-mfa-{uuid.uuid4().hex[:6]}', settings={})
    db.session.add(org)
    db.session.commit()
    editor = make_user(org, roles=['Administrator'])
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 0}})

    trusting = make_sso_provider(org, editor, auto_provision=True, mfa_mode='idp')
    _signed_in(sso_login(client, fake_idp, trusting, okta_claims(email='trust@acme.example')))
    assert security_policy.mfa_enrollment_required(_user('trust@acme.example')) is False

    plain = make_sso_provider(org, editor, auto_provision=True)
    _signed_in(sso_login(client, fake_idp, plain, okta_claims(email='plain@acme.example', sub='plain-sub')))
    assert security_policy.mfa_enrollment_required(_user('plain@acme.example')) is True


def test_idp_amr_mode_requires_a_second_factor(client, fake_idp, make_sso_provider, sso_login, org_a, admin):
    provider = make_sso_provider(org_a, admin, auto_provision=True, mfa_mode='idp_amr')
    assert _sso_error(sso_login(client, fake_idp, provider, okta_claims(amr=['pwd']))) == 'mfa_required'
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(amr=['pwd', 'hwk'])))


# ── Public provider list ────────────────────────────────────────────

def test_public_provider_list(client, make_sso_provider, org_a, admin):
    shown = make_sso_provider(org_a, admin, display_name='Shown IdP')
    hidden = make_sso_provider(org_a, admin, show_on_login=False)
    disabled = make_sso_provider(org_a, admin, is_enabled=False)
    data = client.get(f'{API}/auth/sso/providers').get_json()
    slugs = {p['slug'] for p in data['providers']}
    assert shown.slug in slugs and hidden.slug not in slugs and disabled.slug not in slugs
    entry = next(p for p in data['providers'] if p['slug'] == shown.slug)
    assert set(entry) == {'slug', 'name', 'preset', 'start_url'}
    assert entry['start_url'] == f'{API}/auth/sso/{shown.slug}/start'
    assert isinstance(data['github'], bool)


# ── Admin API ───────────────────────────────────────────────────────

def _payload(**over):
    body = {'slug': f'corp-{uuid.uuid4().hex[:6]}', 'display_name': 'Corp SSO', 'preset': 'okta', 'issuer': ISSUER,
            'client_id': 'sheetstorm-web', 'client_secret': CLIENT_SECRET, 'groups_claim': 'groups',
            'auto_provision': True}
    body.update(over)
    return body


@pytest.fixture
def cleanup_providers(app, db):
    yield
    from app.models.sso import SsoProvider
    db.session.rollback()
    SsoProvider.query.filter(SsoProvider.slug.like('corp-%')).delete(synchronize_session=False)
    db.session.commit()


def test_admin_crud_round_trip(auth, users, cleanup_providers):
    api = auth(users['Administrator'])
    created = api.post(f'{API}/admin/sso-providers', json=_payload(
        role_mappings=[{'group': 'IR-Responders', 'role_id': _role_id('Analyst')}]))
    assert created.status_code == 201, created.get_json()
    data = created.get_json()
    assert data['has_client_secret'] is True and 'client_secret' not in data
    assert 'client_secret_encrypted' not in data
    assert data['redirect_uri'].endswith(f"/api/v1/auth/sso/{data['slug']}/callback")
    pid = data['id']

    listing = api.get(f'{API}/admin/sso-providers').get_json()
    listed = listing['items']
    assert any(p['id'] == pid for p in listed)
    assert listing['redirect_uri_template'].endswith('/api/v1/auth/sso/{slug}/callback')
    assert listing['redirect_uri_template'].replace('{slug}', data['slug']) == data['redirect_uri']
    assert all(p['id'] != pid for p in auth(users['admin_b']).get(f'{API}/admin/sso-providers').get_json()['items'])

    upd = api.put(f'{API}/admin/sso-providers/{pid}', json={'display_name': 'Renamed', 'mfa_mode': 'idp'})
    assert upd.status_code == 200 and upd.get_json()['display_name'] == 'Renamed'
    assert upd.get_json()['has_client_secret'] is True  # omitted secret is kept
    cleared = api.put(f'{API}/admin/sso-providers/{pid}', json={'client_secret': ''})
    assert cleared.get_json()['has_client_secret'] is False

    from app.models import AuditLog
    rows = AuditLog.query.filter_by(resource_type='sso_provider').all()
    assert rows and all(CLIENT_SECRET not in str(r.details) for r in rows)

    assert api.delete(f'{API}/admin/sso-providers/{pid}').get_json() == {'deleted': True, 'identities_removed': 0}
    assert api.get(f'{API}/admin/sso-providers/{pid}').status_code == 404


def test_admin_api_permissions(auth, users, make_user, org_a, cleanup_providers):
    assert auth(users['Analyst']).get(f'{API}/admin/sso-providers').status_code == 403
    pid = auth(users['Administrator']).post(f'{API}/admin/sso-providers', json=_payload()).get_json()['id']
    other_org = auth(users['admin_b'])
    assert other_org.get(f'{API}/admin/sso-providers/{pid}').status_code == 404
    assert other_org.put(f'{API}/admin/sso-providers/{pid}', json={'display_name': 'x'}).status_code == 404
    assert other_org.delete(f'{API}/admin/sso-providers/{pid}').status_code == 404

    # users:manage alone may configure a provider but not hand out roles.
    manager = make_user(org_a, perms=['users:manage', 'users:read'])
    resp = auth(manager).post(f'{API}/admin/sso-providers', json=_payload(default_role_id=_role_id('Analyst')))
    assert resp.status_code == 403
    # ...and with roles:manage, never roles carrying permissions it lacks.
    role_admin = make_user(org_a, perms=['users:manage', 'roles:manage', 'users:read'])
    resp = auth(role_admin).post(f'{API}/admin/sso-providers', json=_payload(
        role_mappings=[{'group': 'x', 'role_id': _role_id('Administrator')}]))
    assert resp.status_code == 403 and resp.get_json()['error'] == 'privilege_escalation'
    # Editing a provider that maps such roles is refused as well.
    resp = auth(role_admin).put(f'{API}/admin/sso-providers/{pid}', json={'display_name': 'x'})
    assert resp.status_code == 200  # this provider maps no roles
    mapped = auth(users['Administrator']).put(f'{API}/admin/sso-providers/{pid}', json={
        'role_mappings': [{'group': 'x', 'role_id': _role_id('Administrator')}]})
    assert mapped.status_code == 200
    assert auth(role_admin).put(f'{API}/admin/sso-providers/{pid}', json={'display_name': 'y'}).status_code == 403


def test_admin_validation(auth, users, app, monkeypatch, cleanup_providers):
    api = auth(users['Administrator'])
    assert api.post(f'{API}/admin/sso-providers', json=_payload(slug='X')).status_code == 400
    assert api.post(f'{API}/admin/sso-providers', json=_payload(scopes='email')).status_code == 400
    assert api.post(f'{API}/admin/sso-providers', json=_payload(unknown=1)).status_code == 400
    resp = api.post(f'{API}/admin/sso-providers', json=_payload(role_mappings=[{'group': 'g',
                                                                                'role_id': str(uuid.uuid4())}]))
    assert resp.status_code == 400 and resp.get_json()['error'] == 'unknown_role'
    http = _payload(issuer='http://keycloak.lab/realms/ir')
    assert api.post(f'{API}/admin/sso-providers', json=http).status_code == 400
    monkeypatch.setitem(app.config, 'SSO_ALLOW_HTTP_ISSUERS', True)
    assert api.post(f'{API}/admin/sso-providers', json=http).status_code == 201
    dup = api.post(f'{API}/admin/sso-providers', json=_payload(slug=http['slug']))
    assert dup.status_code == 409


def test_admin_test_endpoint_reports_the_configuration(auth, users, fake_idp, cleanup_providers):
    api = auth(users['Administrator'])
    pid = api.post(f'{API}/admin/sso-providers', json=_payload()).get_json()['id']
    report = api.post(f'{API}/admin/sso-providers/{pid}/test').get_json()
    assert report['ok'] is True, report
    names = {c['name'] for c in report['checks']}
    assert {'discovery', 'signing keys', 'ID token algorithm', 'PKCE', 'client authentication', 'scopes'} <= names
    fake_idp.discovery_overrides = {'issuer': 'https://elsewhere.example'}
    report = api.post(f'{API}/admin/sso-providers/{pid}/test').get_json()
    assert report['ok'] is False and report['checks'][0]['name'] == 'discovery'


def test_deleting_a_provider_unlinks_but_keeps_users(auth, users, client, fake_idp, sso_login, cleanup_providers):
    api = auth(users['Administrator'])
    data = api.post(f'{API}/admin/sso-providers', json=_payload()).get_json()
    from app import db
    from app.models.sso import SsoProvider
    provider = db.session.get(SsoProvider, uuid.UUID(data['id']))
    _signed_in(sso_login(client, fake_idp, provider, okta_claims(email='keep@acme.example')))
    assert api.delete(f"{API}/admin/sso-providers/{data['id']}").get_json()['identities_removed'] == 1
    user = _user('keep@acme.example')
    assert user is not None
    db.session.delete(user)
    db.session.commit()


# ── Schema ──────────────────────────────────────────────────────────

def test_sso_models_match_the_migration(app, db):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    tables = {'sso_providers', 'user_identities'}
    with db.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={'compare_type': True}), db.metadata)

    def flatten(items):
        for d in items:
            yield from (flatten(d) if isinstance(d, list) else [d])

    problems = []
    for d in flatten(diffs):
        kind = d[0]
        if kind in ('add_table', 'remove_table') and d[1].name in tables:
            problems.append(d)
        elif kind in ('add_column', 'remove_column') and d[2] in tables:
            problems.append(d)
        elif kind in ('add_index', 'remove_index', 'add_constraint', 'remove_constraint') and \
                getattr(getattr(d[1], 'table', None), 'name', None) in tables:
            problems.append(d)
        elif kind.startswith('modify_') and d[2] in tables:
            problems.append(d)
    assert not problems, problems
