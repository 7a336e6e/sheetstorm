"""API keys, the key exchange and service accounts (services/api_key_service.py).

``POST /auth/token`` exchanges a key for a short-lived access JWT (JSON only:
no cookies, no refresh token). Every management route requires an
interactive session (``require_interactive_session``): a key can never mint,
rotate or manage keys. All queries are org-scoped; a key or account of
another org, or another user's key without ``api_keys:manage``, is 404.

Secrets appear only in the 201 bodies of create / rotate, once, with
``Cache-Control: no-store``; they are never part of an audit row.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError

from app.services.rate_limit_settings import limited
from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log, log_auth_event
from app.middleware.rbac import (
    get_current_user, require_any_permission, require_interactive_session, require_permission,
)
from app.models import User
from app.models.api_key import ApiKey
from app.schemas.api_keys import (
    ApiKeyCreate, ApiKeyRevoke, ApiKeyRotate, ServiceAccountCreate, ServiceAccountUpdate, validation_fields,
)
from app.services import api_key_service as svc
from app.services.api_key_service import ApiKeyError, ExchangeError
from app.services.rbac_guard import GuardError, guard_error_response
from app.services.token_revocation import SessionRevocationError, revocation_failed_response
from app.utils.audit_diff import record_changes
from app.utils.pagination import list_response

KEY_STATUSES = ('active', 'expired', 'revoked', 'all')


def _no_store(resp, status=200):
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Pragma'] = 'no-cache'
    return resp, status


def _not_found(what='API key'):
    return jsonify({'error': 'not_found', 'message': f'{what} not found'}), 404


def _validation_error(exc):
    return jsonify({'error': 'validation_error', 'message': 'Invalid request',
                    'fields': validation_fields(exc)}), 400


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _run(fn):
    """Run a service call; map its errors to responses (with rollback)."""
    try:
        return fn(), None
    except ApiKeyError as e:
        return None, e.response()
    except GuardError as e:
        return None, guard_error_response(e)
    except SessionRevocationError:
        db.session.rollback()
        return None, revocation_failed_response()


def _can_manage(user) -> bool:
    return user.has_permission('api_keys:manage')


def _visible_key(user, api_key_id):
    """The org's key if `user` owns it or may manage keys, else None (404)."""
    key = svc.get_org_key(user.organization_id, api_key_id)
    if key is None or (key.owner_user_id != user.id and not _can_manage(user)):
        return None
    return key


def _key_payload(key, owner=None):
    owner = owner or db.session.get(User, key.owner_user_id)
    return key.to_dict(owner=owner)


def _audit_key(key, **extra):
    record_changes({}, {}, api_key_id=str(key.id), prefix=key.prefix, owner_id=str(key.owner_user_id), **extra)


# ── Exchange ────────────────────────────────────────────────────────

def _raw_key_from_request():
    """The key from `Authorization: ApiKey <key>` or the JSON body `api_key`."""
    header = request.headers.get('Authorization', '')
    if header[:7].lower() == 'apikey ':
        return header[7:].strip()
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        return body.get('api_key')
    return None


def _exchange_ip_key():
    return f'apikey_exchange_ip:{request.remote_addr}'


def _exchange_prefix_key():
    prefix = svc.prefix_of(_raw_key_from_request())
    return f'apikey_exchange_prefix:{prefix}' if prefix else _exchange_ip_key()


@api_bp.route('/auth/token', methods=['POST'])
@limited('api_key_exchange', key_func=_exchange_ip_key)
@limited('api_key_exchange_prefix', key_func=_exchange_prefix_key)
def api_key_exchange():
    """Exchange an API key for a short-lived access token (Bearer only).

    Every failure is the same 401 `invalid_api_key`; the precise reason is
    recorded in the audit log with the key prefix (never the key)."""
    raw = _raw_key_from_request()
    try:
        token, key, owner, expires_in = svc.exchange(raw, request.remote_addr)
    except ExchangeError as e:
        db.session.rollback()
        details = {'reason': e.reason, 'prefix': e.prefix}
        if e.key is not None:
            details['api_key_id'] = str(e.key.id)
        log_auth_event('api_key_exchange', user=e.owner, success=False, details=details)
        return _no_store(jsonify({'error': 'invalid_api_key', 'message': 'Invalid API key'}), 401)

    log_auth_event('api_key_exchange', user=owner, success=True,
                   details={'api_key_id': str(key.id), 'prefix': key.prefix})
    return _no_store(jsonify({
        'access_token': token,
        'token_type': 'Bearer',
        'expires_in': expires_in,
        'scopes': sorted(key.scopes or []),
        'api_key': {'id': str(key.id), 'prefix': key.prefix, 'name': key.name,
                    'expires_at': key.expires_at.isoformat()},
        'user': {'id': str(owner.id), 'email': owner.email, 'name': owner.name},
    }))


# ── Keys ────────────────────────────────────────────────────────────

@api_bp.route('/api-keys/scopes', methods=['GET'])
@jwt_required()
@require_interactive_session
@require_any_permission(['api_keys:own', 'api_keys:manage'])
def list_api_key_scopes():
    """Grantable scopes for a key of `owner_id` (default: me), grouped."""
    user = get_current_user()
    owner = user
    owner_id = request.args.get('owner_id')
    if owner_id and owner_id != str(user.id):
        if not _can_manage(user):
            return _not_found('User')
        try:
            owner = User.query.filter_by(id=owner_id, organization_id=user.organization_id).first()
        except Exception:
            db.session.rollback()
            owner = None
        if owner is None or not owner.is_service_account:
            return _not_found('Service account')
    elif not user.has_permission('api_keys:own'):
        return jsonify({'error': 'forbidden', 'message': 'Permission denied. Required: api_keys:own'}), 403
    return jsonify({
        'owner_id': str(owner.id),
        'groups': svc.scope_groups(owner, user),
        'max_lifetime_days': svc.max_lifetime_days(user.organization_id),
        'api_keys_enabled': svc.api_keys_enabled(user.organization_id),
    }), 200


@api_bp.route('/api-keys', methods=['GET'])
@jwt_required()
@require_interactive_session
@require_any_permission(['api_keys:own', 'api_keys:manage'])
def list_api_keys():
    """My keys; with api_keys:manage (and no `mine`), every key of the org.

    Query: status (active|expired|revoked|all, default all), owner_id, mine,
    q (name/prefix), sort (created_at|name|expires_at|last_used_at), page."""
    user = get_current_user()
    query = ApiKey.query.filter(ApiKey.organization_id == user.organization_id)
    mine = request.args.get('mine', '').lower() in ('1', 'true', 'yes')
    filters = {}
    if mine or not _can_manage(user):
        query = query.filter(ApiKey.owner_user_id == user.id)
    else:
        filters['owner_id'] = (ApiKey.owner_user_id, 'uuid')
    status = request.args.get('status', 'all')
    if status not in KEY_STATUSES:
        return jsonify({'error': 'validation_error', 'message': 'Invalid status',
                        'fields': {'status': f'One of {list(KEY_STATUSES)}'}}), 400
    if status != 'all':
        query = query.filter(svc.status_filter(status))

    owners = {}

    def serialize(key):
        if key.owner_user_id not in owners:
            owners[key.owner_user_id] = db.session.get(User, key.owner_user_id)
        return _key_payload(key, owners[key.owner_user_id])

    sortable = {
        'created_at': ApiKey.created_at,
        'name': db.func.lower(ApiKey.name),
        'expires_at': ApiKey.expires_at,
        'last_used_at': ApiKey.last_used_at,
    }
    body = list_response(query, sortable=sortable, default_sort='-created_at', id_col=ApiKey.id,
                         serialize=serialize, search_columns=(ApiKey.name, ApiKey.prefix), filters=filters)
    return _no_store(jsonify(body))


@api_bp.route('/api-keys', methods=['POST'])
@limited('api_keys_write')
@jwt_required()
@require_interactive_session
@require_any_permission(['api_keys:own', 'api_keys:manage'])
@audit_log('admin_action', 'create', 'api_key')
def create_api_key():
    """Create a key for myself (api_keys:own) or for a service account of my
    org (api_keys:manage). Admins never mint keys for other humans.
    201 -> key + `secret` (the full key; shown only this once)."""
    user = get_current_user()
    try:
        data = ApiKeyCreate.model_validate(_body())
    except ValidationError as e:
        return _validation_error(e)

    if data.owner_id is None or data.owner_id == user.id:
        if not user.has_permission('api_keys:own'):
            return jsonify({'error': 'forbidden', 'message': 'Permission denied. Required: api_keys:own'}), 403
        owner = user
    else:
        if not _can_manage(user):
            return jsonify({'error': 'forbidden',
                            'message': 'Only API key managers can create keys for service accounts'}), 403
        owner = User.query.filter_by(id=data.owner_id, organization_id=user.organization_id).first()
        if owner is None:
            return _not_found('User')
        if not owner.is_service_account:
            return jsonify({'error': 'not_service_account',
                            'message': 'Keys can only be created for yourself or a service account'}), 403

    result, error = _run(lambda: svc.create_key(
        owner, user, name=data.name, scopes=data.scopes, expires_in_days=data.expires_in_days,
        description=data.description))
    if error:
        return error
    key, full_key = result
    db.session.commit()
    _audit_key(key, scopes=list(key.scopes), expires_at=key.expires_at.isoformat())
    return _no_store(jsonify({**_key_payload(key, owner), 'secret': full_key}), 201)


@api_bp.route('/api-keys/<uuid:api_key_id>', methods=['GET'])
@jwt_required()
@require_interactive_session
@require_any_permission(['api_keys:own', 'api_keys:manage'])
def get_api_key(api_key_id):
    user = get_current_user()
    key = _visible_key(user, api_key_id)
    if key is None:
        return _not_found()
    return _no_store(jsonify(_key_payload(key)))


@api_bp.route('/api-keys/<uuid:api_key_id>/rotate', methods=['POST'])
@limited('api_keys_write')
@jwt_required()
@require_interactive_session
@require_any_permission(['api_keys:own', 'api_keys:manage'])
@audit_log('admin_action', 'rotate', 'api_key')
def rotate_api_key(api_key_id):
    """Replace a key: same owner, name and scopes, new secret. The old key is
    revoked at once, or after `grace_minutes` (0-1440).
    201 -> new key + `secret`."""
    user = get_current_user()
    key = _visible_key(user, api_key_id)
    if key is None:
        return _not_found()
    try:
        data = ApiKeyRotate.model_validate(_body())
    except ValidationError as e:
        return _validation_error(e)
    if key.owner_user_id != user.id:
        owner = db.session.get(User, key.owner_user_id)
        if owner is None or not owner.is_service_account:
            return jsonify({'error': 'forbidden',
                            'message': "Only the owner can rotate a personal key; revoke it instead"}), 403
    elif not user.has_permission('api_keys:own') and not _can_manage(user):
        return jsonify({'error': 'forbidden', 'message': 'Permission denied. Required: api_keys:own'}), 403

    result, error = _run(lambda: svc.rotate_key(key, user, expires_in_days=data.expires_in_days,
                                                grace_minutes=data.grace_minutes))
    if error:
        return error
    new_key, full_key = result
    old_id, old_revoked_at = key.id, key.revoked_at
    db.session.commit()
    if not data.grace_minutes:
        svc.mark_revoked([old_id])
    _audit_key(key, new_api_key_id=str(new_key.id), new_prefix=new_key.prefix,
               grace_minutes=data.grace_minutes, old_key_revoked_at=old_revoked_at.isoformat())
    return _no_store(jsonify({**_key_payload(new_key), 'secret': full_key}), 201)


@api_bp.route('/api-keys/<uuid:api_key_id>', methods=['DELETE'])
@jwt_required()
@require_interactive_session
@require_any_permission(['api_keys:own', 'api_keys:manage'])
@audit_log('admin_action', 'revoke', 'api_key')
def revoke_api_key(api_key_id):
    """Revoke (soft: the row stays for audit). Idempotent."""
    user = get_current_user()
    key = _visible_key(user, api_key_id)
    if key is None:
        return _not_found()
    try:
        data = ApiKeyRevoke.model_validate(_body())
    except ValidationError as e:
        return _validation_error(e)
    changed = svc.revoke_key(key, user, 'manual')
    db.session.commit()
    if changed:
        svc.mark_revoked([key.id])
    _audit_key(key, revoked=changed, reason=data.reason)
    return _no_store(jsonify(_key_payload(key)))


# ── Service accounts ────────────────────────────────────────────────

def _service_account_payload(sa):
    return {
        'id': str(sa.id),
        'name': sa.name,
        'email': sa.email,
        'is_active': bool(sa.is_active),
        'is_service_account': True,
        'roles': [{'id': str(ur.role_id), 'name': ur.role.name} for ur in sa.user_roles if ur.role],
        'active_key_count': svc.active_key_count(sa.id),
        'created_at': sa.created_at.isoformat() if sa.created_at else None,
        'deactivated_at': sa.deactivated_at.isoformat() if sa.deactivated_at else None,
    }


def _service_account_view(sa):
    """Flat snapshot for the audit diff."""
    return {'name': sa.name, 'is_active': bool(sa.is_active),
            'roles': sorted(str(ur.role_id) for ur in sa.user_roles)}


def _org_service_account(user, service_account_id):
    return User.query.filter_by(id=service_account_id, organization_id=user.organization_id,
                                is_service_account=True).first()


@api_bp.route('/service-accounts', methods=['GET'])
@jwt_required()
@require_interactive_session
@require_permission('api_keys:manage')
def list_service_accounts():
    """Service accounts of my org with their active key count.
    Query: q (name), is_active, sort (name|created_at), page."""
    user = get_current_user()
    query = User.query.filter(User.organization_id == user.organization_id, User.is_service_account.is_(True))
    body = list_response(
        query, sortable={'name': db.func.lower(User.name), 'created_at': User.created_at},
        default_sort='name', id_col=User.id, serialize=_service_account_payload,
        search_columns=(User.name,), filters={'is_active': (User.is_active, 'bool')})
    return jsonify(body), 200


@api_bp.route('/service-accounts', methods=['POST'])
@limited('api_keys_write')
@jwt_required()
@require_interactive_session
@require_permission('api_keys:manage')
@audit_log('admin_action', 'create', 'service_account')
def create_service_account():
    """Create a service account: `{name, role_ids[]}`. Roles go through the
    anti-escalation guard. It cannot sign in; it only owns API keys."""
    user = get_current_user()
    try:
        data = ServiceAccountCreate.model_validate(_body())
    except ValidationError as e:
        return _validation_error(e)
    sa, error = _run(lambda: svc.create_service_account(user, name=data.name, role_ids=data.role_ids))
    if error:
        return error
    db.session.commit()
    record_changes({}, {}, service_account_id=str(sa.id), name=sa.name,
                   role_ids=sorted(str(r) for r in data.role_ids))
    return jsonify(_service_account_payload(sa)), 201


@api_bp.route('/service-accounts/<uuid:service_account_id>', methods=['PATCH'])
@jwt_required()
@require_interactive_session
@require_permission('api_keys:manage')
@audit_log('admin_action', 'update', 'service_account')
def update_service_account(service_account_id):
    """`{name?, is_active?, role_ids?}`. Deactivation revokes every key."""
    user = get_current_user()
    sa = _org_service_account(user, service_account_id)
    if sa is None:
        return _not_found('Service account')
    try:
        data = ServiceAccountUpdate.model_validate(_body())
    except ValidationError as e:
        return _validation_error(e)
    before = _service_account_view(sa)
    _, error = _run(lambda: svc.update_service_account(
        user, sa, name=data.name, is_active=data.is_active, role_ids=data.role_ids))
    if error:
        return error
    db.session.commit()
    record_changes(before, _service_account_view(sa), service_account_id=str(sa.id))
    return jsonify(_service_account_payload(sa)), 200


@api_bp.route('/service-accounts/<uuid:service_account_id>', methods=['DELETE'])
@jwt_required()
@require_interactive_session
@require_permission('api_keys:manage')
@audit_log('admin_action', 'delete', 'service_account')
def delete_service_account(service_account_id):
    """Revoke every key, then soft-disable (the row stays for attribution)."""
    user = get_current_user()
    sa = _org_service_account(user, service_account_id)
    if sa is None:
        return _not_found('Service account')
    _, error = _run(lambda: svc.delete_service_account(user, sa))
    if error:
        return error
    db.session.commit()
    record_changes({}, {}, service_account_id=str(sa.id), name=sa.name)
    return jsonify(_service_account_payload(sa)), 200
