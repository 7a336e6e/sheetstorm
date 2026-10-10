"""OpenID Connect single sign-on endpoints.

Public (sign-in), see services/sso_service.py for the protocol details:
  GET /auth/sso/providers           enabled providers for the login page
  GET /auth/sso/<slug>/start        302 to the IdP (sets the state cookie)
  GET /auth/sso/<slug>/callback     302 back to the app, signed in, or to
                                    /login?sso_error=<code>; with SheetStorm
                                    TOTP enrolled: /login?sso=mfa (the
                                    pre-auth token is an httpOnly cookie that
                                    POST /auth/mfa/complete reads)

Admin (``users:manage``, own organization only; mapping roles also needs
``roles:manage`` and the caller must hold every permission the roles grant):
  GET/POST /admin/sso-providers, GET/PUT/DELETE /admin/sso-providers/<id>,
  POST /admin/sso-providers/<id>/test
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import current_app, jsonify, redirect, request, url_for
from flask_jwt_extended import create_access_token, jwt_required
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log, log_auth_event
from app.middleware.rbac import get_current_user, require_permission
from app.models import Role
from app.models.sso import SsoProvider
from app.schemas.api_keys import validation_fields
from app.schemas.sso import RoleMapping, SsoProviderUpdate, SsoProviderWrite
from app.services import sso_service as sso
from app.services.rate_limit_settings import limited
from app.services.sso_service import MFA_COOKIE, STATE_COOKIE, STATE_TTL, SsoError
from app.utils.audit_diff import record_changes, snapshot

AUDIT_FIELDS = (
    'slug', 'display_name', 'preset', 'issuer', 'client_id', 'token_auth_method', 'scopes', 'email_claims',
    'name_claim', 'groups_claim', 'role_mappings', 'default_role_id', 'allowed_groups', 'allowed_domains',
    'is_enabled', 'show_on_login', 'auto_provision', 'link_existing', 'require_email_verified', 'role_sync',
    'mfa_mode',
)


def _cookie_secure() -> bool:
    return bool(current_app.config.get('JWT_COOKIE_SECURE', True))


def _login_redirect(code):
    return redirect(sso.frontend_url(f'/login?sso_error={code}'), code=302)


def _clear_state(resp):
    resp.delete_cookie(STATE_COOKIE, path='/', secure=_cookie_secure(), httponly=True, samesite='Lax')
    return resp


def _log_failure(slug, err):
    log_auth_event('sso_login', user=err.user, success=False,
                   details={'provider': str(slug)[:40], 'reason': err.code, 'detail': (err.detail or '')[:500]})


# ── Public sign-in ──────────────────────────────────────────────────

@api_bp.route('/auth/sso/providers', methods=['GET'])
@limited('auth_sso')
def sso_providers_public():
    """Sign-in buttons: enabled providers shown on the login page, plus
    whether the built-in GitHub OAuth app is configured."""
    from app.api.v1.endpoints.auth import _get_github_credentials
    rows = (SsoProvider.query.filter_by(is_enabled=True, show_on_login=True)
            .order_by(SsoProvider.display_name).all())
    gh_id, gh_secret = _get_github_credentials()
    return jsonify({
        'providers': [{'slug': p.slug, 'name': p.display_name, 'preset': p.preset,
                       'start_url': url_for('api_v1.sso_start', slug=p.slug)} for p in rows],
        'github': bool(gh_id and gh_secret),
    }), 200


@api_bp.route('/auth/sso/<string:slug>/start', methods=['GET'])
@limited('auth_sso')
def sso_start(slug):
    provider = sso.provider_by_slug(slug)
    if provider is None or not provider.is_enabled:
        _log_failure(slug, SsoError('provider_unavailable', 'unknown or disabled provider'))
        return _login_redirect('provider_unavailable')
    try:
        url, state = sso.start(provider, request.args.get('next'))
    except SsoError as err:
        _log_failure(slug, err)
        return _login_redirect(err.code)
    resp = redirect(url, code=302)
    resp.set_cookie(STATE_COOKIE, sso.state_cookie_value(state), max_age=STATE_TTL, httponly=True,
                    secure=_cookie_secure(), samesite='Lax', path='/')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api_bp.route('/auth/sso/<string:slug>/callback', methods=['GET'])
@limited('auth_sso')
def sso_callback(slug):
    from app.api.v1.endpoints.auth import _auth_cookies, issue_tokens
    from app.services.rbac_guard import emit_permissions_changed
    from app.services.user_lifecycle import register_successful_login

    provider = sso.provider_by_slug(slug)
    try:
        if provider is None or not provider.is_enabled:
            raise SsoError('provider_unavailable', 'unknown or disabled provider')
        pending = sso.consume_state(provider, request.args.get('state'), request.cookies.get(STATE_COOKIE))
        if request.args.get('error'):
            raise SsoError('access_denied', f"IdP returned {request.args.get('error', '')[:100]}: "
                                            f"{request.args.get('error_description', '')[:200]}")
        disc = sso.discovery(provider)
        tokens = sso.exchange_code(provider, disc, request.args.get('code'), pending['verifier'])
        claims = sso.verify_id_token(provider, disc, tokens['id_token'], pending['nonce'])
        claims = sso.merge_userinfo(provider, disc, claims, tokens.get('access_token'))
        outcome = sso.resolve_user(provider, sso.profile_from_claims(provider, claims))
    except SsoError as err:
        db.session.rollback()
        _log_failure(slug, err)
        return _clear_state(_login_redirect(err.code))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('SSO callback for %s failed', str(slug)[:40])
        _log_failure(slug, SsoError('server_error', 'unexpected error (see the server log)'))
        return _clear_state(_login_redirect('server_error'))

    user = outcome.user
    now = datetime.now(timezone.utc)
    outcome.identity.last_login_at = now
    provider.last_login_at = now
    details = {'provider': provider.slug, 'created': outcome.created, 'linked': outcome.linked,
               'roles_synced': outcome.roles_synced}

    if outcome.needs_totp:
        db.session.commit()
        pre_auth = create_access_token(identity=str(user.id), additional_claims={'pre_auth': True, 'auth_method': 'sso'},
                                       expires_delta=timedelta(minutes=5))
        log_auth_event('sso_login', user=user, success=False, details={**details, 'reason': 'mfa_required'})
        resp = redirect(sso.frontend_url(f"/login?sso=mfa&next={quote(pending['next'], safe='/')}"), code=302)
        resp.set_cookie(MFA_COOKIE, pre_auth, max_age=300, httponly=True, secure=_cookie_secure(),
                        samesite='Strict', path='/')
        return _clear_state(resp)

    register_successful_login(user)
    db.session.commit()
    if outcome.roles_synced:
        emit_permissions_changed([user.id])
    access_token, refresh_token = issue_tokens(user, auth_method='sso')
    log_auth_event('sso_login', user=user, success=True, details=details)
    resp = redirect(sso.frontend_url(pending['next']), code=302)
    resp.headers['Cache-Control'] = 'no-store'
    return _clear_state(_auth_cookies(resp, access_token, refresh_token))


# ── Admin ───────────────────────────────────────────────────────────

def _validation_error(exc):
    return jsonify({'error': 'validation_error', 'message': 'Invalid request',
                    'fields': validation_fields(exc)}), 400


def _bad(field, message):
    return jsonify({'error': 'validation_error', 'message': message, 'fields': {field: message}}), 400


def _provider_out(provider):
    data = provider.to_dict()
    data['redirect_uri'] = sso.redirect_uri(provider)
    data['start_url'] = url_for('api_v1.sso_start', slug=provider.slug)
    return data


def _own_provider(provider_id, user):
    return SsoProvider.query.filter_by(id=provider_id, organization_id=user.organization_id).first()


def _not_found():
    return jsonify({'error': 'not_found', 'message': 'SSO provider not found'}), 404


def _check_issuer(issuer):
    if issuer and not issuer.lower().startswith('https://') and not current_app.config.get('SSO_ALLOW_HTTP_ISSUERS'):
        return _bad('issuer', 'The issuer must be an https:// URL (SSO_ALLOW_HTTP_ISSUERS enables http for labs)')
    return None


def _check_roles(user, mappings, default_role_id):
    """Mapped/default roles must be visible to the org; handing them out
    needs roles:manage and every permission they carry."""
    from app.services.rbac_guard import GuardError, assert_can_grant_roles, guard_error_response
    ids = {m.role_id for m in mappings or []}
    if default_role_id:
        ids.add(default_role_id)
    if not ids:
        return None
    roles = Role.visible_to(user.organization_id).filter(Role.id.in_(list(ids))).all()
    if len(roles) != len(ids):
        found = {r.id for r in roles}
        return jsonify({'error': 'unknown_role', 'message': 'Unknown role(s)',
                        'unknown': [str(i) for i in ids if i not in found]}), 400
    if not user.has_permission('roles:manage'):
        return jsonify({'error': 'forbidden', 'message': 'roles:manage permission is required to map roles'}), 403
    try:
        assert_can_grant_roles(user, roles, resource_type='sso_provider')
    except GuardError as e:
        return guard_error_response(e)
    return None


def _slug_taken(slug, exclude_id=None):
    q = SsoProvider.query.filter_by(slug=slug)
    if exclude_id is not None:
        q = q.filter(SsoProvider.id != exclude_id)
    return db.session.query(q.exists()).scalar()


def _slug_conflict():
    return jsonify({'error': 'duplicate_slug', 'message': 'A provider with this slug already exists'}), 409


@api_bp.route('/admin/sso-providers', methods=['GET'])
@jwt_required()
@require_permission('users:manage')
def list_sso_providers():
    user = get_current_user()
    rows = (SsoProvider.query.filter_by(organization_id=user.organization_id)
            .order_by(SsoProvider.display_name).all())
    template = sso.redirect_uri_template()
    return jsonify({'items': [_provider_out(p) for p in rows],
                    'redirect_uri_template': template,
                    'allow_http_issuers': bool(current_app.config.get('SSO_ALLOW_HTTP_ISSUERS'))}), 200


@api_bp.route('/admin/sso-providers/<uuid:provider_id>', methods=['GET'])
@jwt_required()
@require_permission('users:manage')
def get_sso_provider(provider_id):
    provider = _own_provider(provider_id, get_current_user())
    return (jsonify(_provider_out(provider)), 200) if provider else _not_found()


@api_bp.route('/admin/sso-providers', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'create', 'sso_provider')
def create_sso_provider():
    user = get_current_user()
    try:
        body = SsoProviderWrite(**(request.get_json(silent=True) or {}))
    except (ValidationError, TypeError) as exc:
        return _validation_error(exc) if isinstance(exc, ValidationError) else _bad('body', 'Invalid request body')
    error = _check_issuer(body.issuer) or _check_roles(user, body.role_mappings, body.default_role_id)
    if error:
        return error
    if _slug_taken(body.slug):
        return _slug_conflict()
    data = body.model_dump(exclude={'client_secret'})
    data['role_mappings'] = [{'group': m.group, 'role_id': str(m.role_id)} for m in body.role_mappings]
    provider = SsoProvider(organization_id=user.organization_id, created_by=user.id, updated_by=user.id, **data)
    sso.set_client_secret(provider, body.client_secret)
    db.session.add(provider)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _slug_conflict()
    record_changes({}, snapshot(provider, AUDIT_FIELDS), client_secret_set=bool(body.client_secret))
    return jsonify(_provider_out(provider)), 201


@api_bp.route('/admin/sso-providers/<uuid:provider_id>', methods=['PUT'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'update', 'sso_provider')
def update_sso_provider(provider_id):
    user = get_current_user()
    provider = _own_provider(provider_id, user)
    if provider is None:
        return _not_found()
    try:
        body = SsoProviderUpdate(**(request.get_json(silent=True) or {}))
    except (ValidationError, TypeError) as exc:
        return _validation_error(exc) if isinstance(exc, ValidationError) else _bad('body', 'Invalid request body')
    sent = body.model_fields_set
    error = _check_issuer(body.issuer)
    if error:
        return error
    # Any edit makes the caller the provider's editor, whose grant ceiling
    # applies at sign-in: check the mapping as it will be after this change.
    if 'role_mappings' in sent and body.role_mappings is not None:
        mappings = body.role_mappings
    else:  # kept as is; mappings to roles deleted since then are ignored
        visible = {str(r.id) for r in Role.visible_to(user.organization_id).all()}
        mappings = [RoleMapping(**m) for m in provider.role_mappings or [] if m.get('role_id') in visible]
    default_id = body.default_role_id if 'default_role_id' in sent else provider.default_role_id
    error = _check_roles(user, mappings, default_id)
    if error:
        return error
    if body.slug and body.slug != provider.slug and _slug_taken(body.slug, provider.id):
        return _slug_conflict()

    before = snapshot(provider, AUDIT_FIELDS)
    issuer_before = provider.issuer
    for name in sent - {'client_secret', 'role_mappings'}:
        value = getattr(body, name)
        if value is None and name not in ('groups_claim', 'default_role_id'):
            continue  # null means "unchanged" for required fields
        setattr(provider, name, value)
    if 'role_mappings' in sent and body.role_mappings is not None:
        provider.role_mappings = [{'group': m.group, 'role_id': str(m.role_id)} for m in body.role_mappings]
    secret_changed = 'client_secret' in sent
    if secret_changed:
        sso.set_client_secret(provider, body.client_secret)
    provider.updated_by = user.id
    provider.updated_at = datetime.now(timezone.utc)
    record_changes(before, snapshot(provider, AUDIT_FIELDS), client_secret_changed=secret_changed)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _slug_conflict()
    if provider.issuer != issuer_before:
        sso.forget_cached(provider)
    return jsonify(_provider_out(provider)), 200


@api_bp.route('/admin/sso-providers/<uuid:provider_id>', methods=['DELETE'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'delete', 'sso_provider')
def delete_sso_provider(provider_id):
    provider = _own_provider(provider_id, get_current_user())
    if provider is None:
        return _not_found()
    linked = provider.identities.count()
    record_changes(snapshot(provider, AUDIT_FIELDS), {}, identities_removed=linked)
    sso.forget_cached(provider)
    db.session.delete(provider)
    db.session.commit()
    return jsonify({'deleted': True, 'identities_removed': linked}), 200


@api_bp.route('/admin/sso-providers/<uuid:provider_id>/test', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@limited('auth_sso')
def test_sso_provider(provider_id):
    provider = _own_provider(provider_id, get_current_user())
    if provider is None:
        return _not_found()
    return jsonify(sso.check_configuration(provider)), 200
