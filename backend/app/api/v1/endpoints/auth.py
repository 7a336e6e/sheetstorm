"""Authentication endpoints"""
import re
from datetime import datetime, timezone, timedelta
from flask import jsonify, request, g, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt,
    set_access_cookies, set_refresh_cookies, unset_jwt_cookies
)
from app.api.v1 import api_bp
from app import db, limiter
from app.models import User, Role, UserRole, Session, Organization
from app.middleware.audit import log_auth_event


def validate_password(password: str) -> tuple:
    """Validate password meets requirements."""
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain an uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain a lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain a number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain a special character"
    return True, None


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _redis():
    """Current Redis client (resolved at call time, set up by create_app)."""
    from app import redis_client
    return redis_client


def _current_token_epoch(user_id: str) -> int:
    """Return the user's current token epoch (advanced on password change)."""
    redis_client = _redis()
    if redis_client is None:
        return 0
    try:
        val = redis_client.get(f'token_epoch:{user_id}')
        return int(val) if val is not None else 0
    except Exception:
        return 0


def _bump_token_epoch(user_id: str) -> None:
    """Invalidate all existing tokens for a user by advancing their epoch."""
    redis_client = _redis()
    if redis_client is None:
        return
    try:
        redis_client.incr(f'token_epoch:{user_id}')
    except Exception:
        pass


def _revoke_jti(jti, exp) -> None:
    """Blocklist a token's jti in Redis until it would naturally expire."""
    redis_client = _redis()
    if not jti or redis_client is None:
        return
    try:
        ttl = int((exp or 0) - datetime.now(timezone.utc).timestamp())
        redis_client.setex(f'revoked_token:{jti}', ttl if ttl > 0 else 60, 'true')
    except Exception:
        pass


def issue_tokens(user):
    """Mint an access + refresh token pair stamped with the user's token epoch.

    Centralised so session-invalidation (token epoch) and, later, cookie
    delivery are applied consistently everywhere tokens are issued.
    """
    claims = {'token_epoch': _current_token_epoch(str(user.id))}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims)
    return access, refresh


def _auth_cookies(resp, access_token=None, refresh_token=None):
    """Attach httpOnly JWT cookies to a response for browser auth.

    Tokens are also returned in the JSON body for non-browser clients during
    the migration; browsers should rely on the httpOnly cookies.
    """
    if access_token:
        set_access_cookies(resp, access_token)
    if refresh_token:
        set_refresh_cookies(resp, refresh_token)
    return resp


def _is_registration_enabled() -> bool:
    """Whether self-registration / first SSO sign-in may create accounts.

    Closed unless the default organization explicitly enables it (fresh
    installs are closed; the admin_guardrails_rbac migration kept existing
    installs open)."""
    org = Organization.query.filter_by(slug='default').first()
    if not org or not org.settings:
        return False
    return org.settings.get('registration_enabled', False) is True


@api_bp.route('/auth/registration-status', methods=['GET'])
def registration_status():
    """Public endpoint to check whether registration is enabled."""
    return jsonify({'registration_enabled': _is_registration_enabled()}), 200


@api_bp.route('/auth/register', methods=['POST'])
@limiter.limit("3 per hour")
def register():
    """Register a new user account."""
    if not _is_registration_enabled():
        return jsonify({'error': 'registration_disabled', 'message': 'Registration is currently disabled by the administrator'}), 403

    try:
        from app.schemas.auth import UserRegister
        data = UserRegister(**request.get_json())
    except ValueError:
        return jsonify({'error': 'bad_request', 'message': 'Invalid request data'}), 400

    email = data.email.lower().strip()
    
    # Check if user exists
    if User.query.filter_by(email=email).first():
        log_auth_event('register', success=False, details={'email': email, 'reason': 'email_exists'})
        return jsonify({'error': 'conflict', 'message': 'Email already registered'}), 409

    # Get or create default organization
    org = Organization.query.filter_by(slug='default').first()
    if not org:
        org = Organization(name='Default Organization', slug='default')
        db.session.add(org)
        db.session.flush()

    # Create user
    user = User(
        email=email,
        name=data.name.strip(),
        organization_id=org.id,
        auth_provider='local'
    )
    user.set_password(data.password)
    db.session.add(user)
    db.session.flush()

    # Assign default Viewer role
    viewer_role = Role.resolve('Viewer', org.id)
    if viewer_role:
        user_role = UserRole(user_id=user.id, role_id=viewer_role.id, organization_id=org.id)
        db.session.add(user_role)

    db.session.commit()

    # Generate tokens
    access_token, refresh_token = issue_tokens(user)

    log_auth_event('register', user=user, success=True)

    resp = jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict(include_permissions=True)
    })
    return _auth_cookies(resp, access_token, refresh_token), 201


@api_bp.route('/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """Authenticate user and return tokens."""
    try:
        from app.schemas.auth import UserLogin
        data = UserLogin(**request.get_json())
    except ValueError:
        return jsonify({'error': 'bad_request', 'message': 'Invalid request data'}), 400

    email = data.email.lower().strip()
    
    # Find user
    user = User.query.filter_by(email=email).first()

    if not user:
        log_auth_event('login', success=False, details={'email': email, 'reason': 'user_not_found'})
        # Use generic message for security
        return jsonify({'error': 'unauthorized', 'message': 'Invalid email or password'}), 401

    if not user.is_active:
        log_auth_event('login', user=user, success=False, details={'reason': 'account_disabled'})
        return jsonify({'error': 'unauthorized', 'message': 'Account is disabled'}), 401

    # Only reject non-local providers if the user has NO password hash
    # (i.e. they were created purely via OAuth and never set a password)
    if user.auth_provider != 'local' and not user.password_hash:
        log_auth_event('login', user=user, success=False, details={'reason': 'wrong_provider'})
        return jsonify({
            'error': 'unauthorized',
            'message': f'Please login with {user.auth_provider}'
        }), 401

    if not user.check_password(data.password):
        log_auth_event('login', user=user, success=False, details={'reason': 'invalid_password'})
        return jsonify({'error': 'unauthorized', 'message': 'Invalid email or password'}), 401

    # MFA check: if user has MFA enabled, require code
    if user.mfa_enabled and user.mfa_secret:
        mfa_code = request.get_json().get('mfa_code')
        if not mfa_code:
            log_auth_event('login', user=user, success=False, details={'reason': 'mfa_required'})
            return jsonify({
                'error': 'mfa_required',
                'message': 'MFA code is required',
                'mfa_required': True
            }), 403

        import pyotp
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(str(mfa_code), valid_window=1):
            log_auth_event('login', user=user, success=False, details={'reason': 'invalid_mfa_code'})
            return jsonify({'error': 'unauthorized', 'message': 'Invalid MFA code'}), 401

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    # Generate tokens
    access_token, refresh_token = issue_tokens(user)

    log_auth_event('login', user=user, success=True)

    resp = jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict(include_permissions=True)
    })
    return _auth_cookies(resp, access_token, refresh_token), 200


@api_bp.route('/auth/refresh', methods=['POST'])
@limiter.limit("30 per hour")
@jwt_required(refresh=True)
def refresh():
    """Refresh access token, rotating the refresh token."""
    identity = get_jwt_identity()
    user = User.query.get(identity)

    if not user or not user.is_active:
        return jsonify({'error': 'unauthorized', 'message': 'Invalid user'}), 401

    # Rotate: revoke the presented refresh token and issue a fresh pair, so a
    # leaked refresh token has a bounded lifetime. The first rotation of a
    # token also opens a short grace window in which that same token is
    # accepted once more (consumed in the blocklist loader), so concurrent
    # refreshes from several tabs / the MCP server don't log the user out.
    current = get_jwt()
    jti, exp = current.get('jti'), current.get('exp')
    redis_client = _redis()
    if jti and redis_client is not None:
        try:
            ttl = max(int((exp or 0) - datetime.now(timezone.utc).timestamp()), 60)
            first_rotation = redis_client.set(f'revoked_token:{jti}', 'true', ex=ttl, nx=True)
            grace = int(current_app.config.get('JWT_REFRESH_GRACE_SECONDS', 30))
            if first_rotation and grace > 0:
                redis_client.setex(f'refresh_grace:{jti}', grace, '1')
        except Exception:
            current_app.logger.error('Failed to revoke rotated refresh token')
            return jsonify({'error': 'server_error', 'message': 'Token rotation failed'}), 503
    access_token, refresh_token = issue_tokens(user)

    resp = jsonify({'access_token': access_token, 'refresh_token': refresh_token})
    return _auth_cookies(resp, access_token, refresh_token), 200


@api_bp.route('/auth/logout', methods=['POST'])
@limiter.limit("30 per minute")
@jwt_required()
def logout():
    """Logout and revoke the current access token (and refresh token if given)."""
    jwt_data = get_jwt()
    _revoke_jti(jwt_data['jti'], jwt_data['exp'])

    # Also revoke the refresh token when supplied (request body or cookie) so a
    # stolen refresh token cannot mint new access tokens after logout.
    body = request.get_json(silent=True) or {}
    refresh_tok = body.get('refresh_token') or request.cookies.get('refresh_token_cookie')
    if refresh_tok:
        try:
            from flask_jwt_extended import decode_token
            decoded = decode_token(refresh_tok)
            _revoke_jti(decoded.get('jti'), decoded.get('exp'))
        except Exception:
            pass

    identity = get_jwt_identity()
    user = User.query.get(identity)
    if user:
        log_auth_event('logout', user=user, success=True)

    resp = jsonify({'message': 'Successfully logged out'})
    unset_jwt_cookies(resp)
    return resp, 200


@api_bp.route('/auth/me', methods=['GET'])
@limiter.limit("60 per minute")
@jwt_required()
def get_current_user():
    """Get current authenticated user."""
    identity = get_jwt_identity()
    user = User.query.get(identity)

    if not user or not user.is_active:
        return jsonify({'error': 'unauthorized', 'message': 'Account not found or disabled'}), 401

    return jsonify(user.to_dict(include_permissions=True)), 200


@api_bp.route('/auth/change-password', methods=['POST'])
@limiter.limit("5 per hour")
@jwt_required()
def change_password():
    """Change user password."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'error': 'bad_request', 'message': 'Current and new password are required'}), 400

    identity = get_jwt_identity()
    user = User.query.get(identity)

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    if not user.check_password(current_password):
        log_auth_event('change_password', user=user, success=False, details={'reason': 'invalid_current'})
        return jsonify({'error': 'unauthorized', 'message': 'Current password is incorrect'}), 401

    # Validate new password
    valid, message = validate_password(new_password)
    if not valid:
        return jsonify({'error': 'bad_request', 'message': message}), 400

    user.set_password(new_password)
    # Invalidate every existing session for this user (revokes all outstanding
    # access + refresh tokens via the token epoch).
    _bump_token_epoch(identity)
    db.session.commit()

    log_auth_event('change_password', user=user, success=True)

    # Re-issue tokens for the current session so the user stays logged in here.
    access_token, refresh_token = issue_tokens(user)

    resp = jsonify({
        'message': 'Password changed successfully',
        'access_token': access_token,
        'refresh_token': refresh_token,
    })
    return _auth_cookies(resp, access_token, refresh_token), 200


@api_bp.route('/auth/supabase', methods=['POST'])
@limiter.limit("10 per minute")
def supabase_auth():
    """Authenticate with Supabase JWT."""
    data = request.get_json(silent=True) or {}
    supabase_token = data.get('access_token')

    if not supabase_token:
        return jsonify({'error': 'bad_request', 'message': 'Supabase access token required'}), 400

    supabase_url = current_app.config.get('SUPABASE_URL')
    if not supabase_url:
        return jsonify({'error': 'not_configured', 'message': 'Supabase not configured'}), 501

    try:
        import jwt as pyjwt
        import requests as http_requests

        # Verify the Supabase JWT using the project's JWT secret
        # Supabase JWTs can be verified with the SUPABASE_JWT_SECRET or by
        # fetching the JWKS. For simplicity, we call Supabase's user endpoint.
        supabase_user_resp = http_requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                'Authorization': f'Bearer {supabase_token}',
                'apikey': current_app.config.get('SUPABASE_ANON_KEY'),
            },
            timeout=10,
        )

        if supabase_user_resp.status_code != 200:
            return jsonify({'error': 'unauthorized', 'message': 'Invalid Supabase token'}), 401

        sb_user = supabase_user_resp.json()
        email = sb_user.get('email')
        if not email:
            return jsonify({'error': 'unauthorized', 'message': 'No email in Supabase token'}), 401

        user_metadata = sb_user.get('user_metadata', {})
        sb_id = sb_user.get('id', '')

        user = User.query.filter_by(email=email).first()

        if not user:
            # Check if registration is enabled before creating new user
            if not _is_registration_enabled():
                return jsonify({'error': 'registration_disabled', 'message': 'Registration is currently disabled by the administrator'}), 403

            # Get or create default organization
            org = Organization.query.filter_by(slug='default').first()
            if not org:
                org = Organization(name='Default Organization', slug='default')
                db.session.add(org)
                db.session.flush()

            user = User(
                email=email,
                name=user_metadata.get('name') or user_metadata.get('full_name') or email.split('@')[0],
                organization_id=org.id,
                auth_provider='supabase',
                supabase_id=sb_id,
                is_verified=True
            )
            db.session.add(user)
            db.session.flush()

            # Restore roles from Supabase app_metadata, fall back to Viewer
            from app.services.supabase_role_sync import roles_from_supabase_metadata, assign_roles_from_list
            sb_roles = roles_from_supabase_metadata(sb_user)
            if sb_roles:
                assign_roles_from_list(user, sb_roles, organization_id=org.id)
            else:
                viewer_role = Role.resolve('Viewer', org.id)
                if viewer_role:
                    user_role = UserRole(user_id=user.id, role_id=viewer_role.id, organization_id=org.id)
                    db.session.add(user_role)

            db.session.commit()

        if not user.is_active:
            log_auth_event('supabase_login', user=user, success=False, details={'reason': 'account_disabled'})
            return jsonify({'error': 'unauthorized', 'message': 'Account is disabled'}), 401

        # MFA check: if user has MFA enabled, require code before issuing tokens
        if user.mfa_enabled and user.mfa_secret:
            mfa_code = data.get('mfa_code')
            if not mfa_code:
                # Generate a short-lived pre-auth token so frontend can retry with MFA code
                pre_auth_token = create_access_token(
                    identity=str(user.id),
                    additional_claims={'pre_auth': True, 'auth_method': 'supabase'},
                    expires_delta=timedelta(minutes=5)
                )
                log_auth_event('supabase_login', user=user, success=False, details={'reason': 'mfa_required'})
                return jsonify({
                    'error': 'mfa_required',
                    'message': 'MFA code is required',
                    'mfa_required': True,
                    'pre_auth_token': pre_auth_token,
                }), 403

            import pyotp
            totp = pyotp.TOTP(user.mfa_secret)
            if not totp.verify(str(mfa_code), valid_window=1):
                # Check backup codes
                backup_valid = False
                if user.mfa_backup_codes:
                    codes = user.mfa_backup_codes.split(',')
                    if str(mfa_code).upper() in codes:
                        codes.remove(str(mfa_code).upper())
                        user.mfa_backup_codes = ','.join(codes)
                        backup_valid = True
                if not backup_valid:
                    log_auth_event('supabase_login', user=user, success=False, details={'reason': 'invalid_mfa_code'})
                    return jsonify({'error': 'unauthorized', 'message': 'Invalid MFA code'}), 401

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # Generate our tokens
        access_token, refresh_token = issue_tokens(user)

        log_auth_event('supabase_login', user=user, success=True)

        resp = jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(include_permissions=True)
        })
        return _auth_cookies(resp, access_token, refresh_token), 200

    except Exception as e:
        current_app.logger.error(f"Supabase auth error: {e}")
        return jsonify({'error': 'server_error', 'message': 'Authentication failed'}), 500


# ── GitHub OAuth Endpoints ─────────────────────────────────────────

def _get_github_credentials():
    """Resolve GitHub OAuth credentials from DB integration or env config."""
    from app.models.integration import Integration
    from app.services.encryption_service import encryption_service
    import json

    # Login happens before any organization context exists, so only the
    # platform (default) organization's OAuth app may drive the login flow —
    # never an arbitrary tenant's integration.
    default_org = Organization.query.filter_by(slug='default').first()
    integration = Integration.query.filter_by(
        organization_id=default_org.id, type='oauth_github', is_enabled=True
    ).first() if default_org else None
    if integration and integration.credentials_encrypted:
        try:
            creds_json = encryption_service.decrypt(integration.credentials_encrypted)
            creds = json.loads(creds_json)
            client_id = creds.get('client_id', '')
            client_secret = creds.get('client_secret', '')
            if client_id and client_secret:
                return client_id, client_secret
        except Exception:
            pass
    # Fallback to env-based config
    return (
        current_app.config.get('GITHUB_CLIENT_ID', ''),
        current_app.config.get('GITHUB_CLIENT_SECRET', ''),
    )


@api_bp.route('/auth/github', methods=['GET'])
@limiter.limit("20 per minute")
def github_auth_redirect():
    """Return the GitHub OAuth authorization URL for the frontend to redirect to."""
    client_id, _ = _get_github_credentials()

    if not client_id:
        return jsonify({'error': 'not_configured', 'message': 'GitHub OAuth is not configured'}), 501

    redirect_uri = current_app.config.get('GITHUB_OAUTH_REDIRECT_URI')
    scope = 'read:user user:email'

    # Generate a random state for CSRF protection
    import secrets
    state = secrets.token_urlsafe(32)

    # Store state in Redis with 10-minute expiry
    _redis().setex(f'github_oauth_state:{state}', 600, '1')

    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&state={state}"
    )

    return jsonify({'url': github_url, 'state': state}), 200


@api_bp.route('/auth/github/callback', methods=['POST'])
@limiter.limit("20 per minute")
def github_auth_callback():
    """Exchange GitHub OAuth code for user tokens."""
    import requests as http_requests

    data = request.get_json(silent=True) or {}
    code = data.get('code')
    state = data.get('state')

    if not code:
        return jsonify({'error': 'bad_request', 'message': 'Authorization code is required'}), 400

    # Validate CSRF state (required; single use).
    if not state or not _redis().delete(f'github_oauth_state:{state}'):
        return jsonify({'error': 'bad_request', 'message': 'Invalid or expired OAuth state'}), 400

    client_id, client_secret = _get_github_credentials()

    if not client_id or not client_secret:
        return jsonify({'error': 'not_configured', 'message': 'GitHub OAuth is not configured'}), 501

    redirect_uri = current_app.config.get('GITHUB_OAUTH_REDIRECT_URI')

    # Exchange code for access token
    try:
        token_resp = http_requests.post(
            'https://github.com/login/oauth/access_token',
            json={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'redirect_uri': redirect_uri,
            },
            headers={'Accept': 'application/json'},
            timeout=10,
        )
        token_data = token_resp.json()

        if 'error' in token_data:
            current_app.logger.error(f"GitHub token exchange failed: {token_data.get('error')}")
            return jsonify({'error': 'oauth_error', 'message': token_data.get('error_description', 'OAuth token exchange failed')}), 400

        gh_access_token = token_data.get('access_token')
        if not gh_access_token:
            return jsonify({'error': 'oauth_error', 'message': 'No access token received from GitHub'}), 400

    except Exception as e:
        current_app.logger.error(f"GitHub token exchange error: {e}")
        return jsonify({'error': 'server_error', 'message': 'Failed to exchange authorization code'}), 500

    # Fetch GitHub user profile
    try:
        user_resp = http_requests.get(
            'https://api.github.com/user',
            headers={'Authorization': f'Bearer {gh_access_token}', 'Accept': 'application/json'},
            timeout=10,
        )
        gh_user = user_resp.json()

        # Fetch verified primary email
        emails_resp = http_requests.get(
            'https://api.github.com/user/emails',
            headers={'Authorization': f'Bearer {gh_access_token}', 'Accept': 'application/json'},
            timeout=10,
        )
        emails = emails_resp.json()
        primary_email = next((e['email'] for e in emails if e.get('primary') and e.get('verified')), None)

        if not primary_email:
            return jsonify({'error': 'oauth_error', 'message': 'No verified primary email on your GitHub account'}), 400

    except Exception as e:
        current_app.logger.error(f"GitHub user fetch error: {e}")
        return jsonify({'error': 'server_error', 'message': 'Failed to fetch GitHub user profile'}), 500

    # Find or create user
    try:
        user = User.query.filter_by(email=primary_email.lower()).first()
        github_id = str(gh_user.get('id', ''))

        if user:
            # Existing user — update provider info if needed
            if user.auth_provider == 'local':
                # Allow linking: local users can also sign in via GitHub
                user.auth_provider_id = github_id
            elif user.auth_provider == 'github' and user.auth_provider_id != github_id:
                return jsonify({'error': 'conflict', 'message': 'Email is associated with a different GitHub account'}), 409
        else:
            # Check if registration is enabled before creating new user
            if not _is_registration_enabled():
                return jsonify({'error': 'registration_disabled', 'message': 'Registration is currently disabled by the administrator'}), 403

            # Create new user
            org = Organization.query.filter_by(slug='default').first()
            if not org:
                org = Organization(name='Default Organization', slug='default')
                db.session.add(org)
                db.session.flush()

            display_name = gh_user.get('name') or gh_user.get('login') or primary_email.split('@')[0]

            user = User(
                email=primary_email.lower(),
                name=display_name,
                organization_id=org.id,
                auth_provider='github',
                auth_provider_id=github_id,
                is_verified=True,
            )
            db.session.add(user)
            db.session.flush()

            # Assign default Viewer role
            viewer_role = Role.resolve('Viewer', org.id)
            if viewer_role:
                user_role = UserRole(user_id=user.id, role_id=viewer_role.id, organization_id=org.id)
                db.session.add(user_role)

        if not user.is_active:
            db.session.rollback()
            log_auth_event('github_login', user=user, success=False, details={'reason': 'account_disabled'})
            return jsonify({'error': 'unauthorized', 'message': 'Account is disabled'}), 401

        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # MFA check: if user has MFA enabled, require code
        if user.mfa_enabled and user.mfa_secret:
            mfa_code = data.get('mfa_code')
            if not mfa_code:
                pre_auth_token = create_access_token(
                    identity=str(user.id),
                    additional_claims={'pre_auth': True, 'auth_method': 'github'},
                    expires_delta=timedelta(minutes=5)
                )
                log_auth_event('github_login', user=user, success=False, details={'reason': 'mfa_required'})
                return jsonify({
                    'error': 'mfa_required',
                    'message': 'MFA code is required',
                    'mfa_required': True,
                    'pre_auth_token': pre_auth_token,
                    'user': {'name': user.name, 'email': user.email},
                }), 403

            import pyotp
            totp = pyotp.TOTP(user.mfa_secret)
            if not totp.verify(str(mfa_code), valid_window=1):
                backup_valid = False
                if user.mfa_backup_codes:
                    codes = user.mfa_backup_codes.split(',')
                    if str(mfa_code).upper() in codes:
                        codes.remove(str(mfa_code).upper())
                        user.mfa_backup_codes = ','.join(codes)
                        db.session.commit()
                        backup_valid = True
                if not backup_valid:
                    log_auth_event('github_login', user=user, success=False, details={'reason': 'invalid_mfa_code'})
                    return jsonify({'error': 'unauthorized', 'message': 'Invalid MFA code'}), 401

        # Generate JWT tokens
        access_token, refresh_token = issue_tokens(user)

        log_auth_event('github_login', user=user, success=True)

        resp = jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(include_permissions=True),
        })
        return _auth_cookies(resp, access_token, refresh_token), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"GitHub auth user creation error: {e}")
        return jsonify({'error': 'server_error', 'message': 'Authentication failed'}), 500


# ── MFA Endpoints ──────────────────────────────────────────────────

@api_bp.route('/auth/mfa/setup', methods=['POST'])
@limiter.limit("5 per hour")
@jwt_required()
def mfa_setup():
    """
    Generate a TOTP secret and provisioning URI for QR code.
    Does NOT enable MFA yet — user must verify a code first.
    """
    import pyotp

    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    if user.mfa_enabled:
        return jsonify({'error': 'conflict', 'message': 'MFA is already enabled'}), 409

    # Generate new secret
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.email,
        issuer_name='SheetStorm'
    )

    # Generate backup codes (8 random 8-char codes)
    import secrets
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]

    # Store secret temporarily (not enabled yet until verification)
    user.mfa_secret = secret
    user.mfa_backup_codes = ','.join(backup_codes)
    db.session.commit()

    log_auth_event('mfa_setup_initiated', user=user, success=True)

    return jsonify({
        'secret': secret,
        'provisioning_uri': provisioning_uri,
        'backup_codes': backup_codes,
    }), 200


@api_bp.route('/auth/mfa/verify', methods=['POST'])
@limiter.limit("10 per hour")
@jwt_required()
def mfa_verify():
    """
    Verify a TOTP code to confirm MFA setup and enable it.
    """
    import pyotp

    data = request.get_json() or {}
    code = data.get('code', '')

    if not code:
        return jsonify({'error': 'bad_request', 'message': 'Verification code is required'}), 400

    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    if user.mfa_enabled:
        return jsonify({'error': 'conflict', 'message': 'MFA is already enabled'}), 409

    if not user.mfa_secret:
        return jsonify({'error': 'bad_request', 'message': 'Run MFA setup first'}), 400

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(str(code), valid_window=1):
        log_auth_event('mfa_verify', user=user, success=False, details={'reason': 'invalid_code'})
        return jsonify({'error': 'unauthorized', 'message': 'Invalid verification code'}), 401

    # Enable MFA
    user.mfa_enabled = True
    db.session.commit()

    log_auth_event('mfa_verify', user=user, success=True)

    return jsonify({'message': 'MFA enabled successfully'}), 200


@api_bp.route('/auth/mfa/complete', methods=['POST'])
@limiter.limit("10 per minute")
def mfa_complete_oauth():
    """Complete OAuth login by verifying MFA code using a pre-auth token.

    This is called after GitHub/Supabase OAuth returns mfa_required.
    The frontend sends the pre_auth_token + mfa_code to get full access tokens.
    """
    import pyotp

    data = request.get_json() or {}
    pre_auth_token = data.get('pre_auth_token', '')
    mfa_code = data.get('mfa_code', '')

    if not pre_auth_token or not mfa_code:
        return jsonify({'error': 'bad_request', 'message': 'pre_auth_token and mfa_code are required'}), 400

    # Decode the pre-auth token to get user identity
    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(pre_auth_token)
        if not decoded.get('pre_auth'):
            return jsonify({'error': 'bad_request', 'message': 'Invalid pre-auth token'}), 400
        user_id = decoded.get('sub')
    except Exception:
        return jsonify({'error': 'unauthorized', 'message': 'Invalid or expired pre-auth token'}), 401

    user = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({'error': 'unauthorized', 'message': 'Account not found or disabled'}), 401

    if not user.mfa_enabled or not user.mfa_secret:
        return jsonify({'error': 'bad_request', 'message': 'MFA is not enabled for this user'}), 400

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(str(mfa_code), valid_window=1):
        # Check backup codes
        backup_valid = False
        if user.mfa_backup_codes:
            codes = user.mfa_backup_codes.split(',')
            if str(mfa_code).upper() in codes:
                codes.remove(str(mfa_code).upper())
                user.mfa_backup_codes = ','.join(codes)
                backup_valid = True
        if not backup_valid:
            log_auth_event('mfa_complete_oauth', user=user, success=False, details={'reason': 'invalid_mfa_code'})
            return jsonify({'error': 'unauthorized', 'message': 'Invalid MFA code'}), 401

    # MFA verified — issue full tokens
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token, refresh_token = issue_tokens(user)

    auth_method = decoded.get('auth_method', 'oauth')
    log_auth_event(f'{auth_method}_login_mfa', user=user, success=True)

    resp = jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict(include_permissions=True),
    })
    return _auth_cookies(resp, access_token, refresh_token), 200


@api_bp.route('/auth/mfa/disable', methods=['POST'])
@limiter.limit("5 per hour")
@jwt_required()
def mfa_disable():
    """Disable MFA for the current user. Requires password confirmation."""
    data = request.get_json() or {}
    password = data.get('password', '')

    if not password:
        return jsonify({'error': 'bad_request', 'message': 'Password is required to disable MFA'}), 400

    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    if not user.mfa_enabled:
        return jsonify({'error': 'bad_request', 'message': 'MFA is not enabled'}), 400

    if not user.check_password(password):
        log_auth_event('mfa_disable', user=user, success=False, details={'reason': 'invalid_password'})
        return jsonify({'error': 'unauthorized', 'message': 'Invalid password'}), 401

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    db.session.commit()

    log_auth_event('mfa_disable', user=user, success=True)

    return jsonify({'message': 'MFA disabled successfully'}), 200
