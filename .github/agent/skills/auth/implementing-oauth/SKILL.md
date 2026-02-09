---
name: implementing-oauth
description: GitHub and Google OAuth 2.0 integration using Authlib for Flask applications.
---

# Implementing OAuth

## Goal

Integrate OAuth 2.0 Authorization Code flow for GitHub and Google using Authlib. Support first-time login (account creation) and account linking for users who already have a local account with a matching email.

## When to Use

- Adding "Sign in with GitHub" or "Sign in with Google" to an application.
- Supplementing local auth with social login options.
- Building a developer-focused tool where GitHub login is expected.
- Any scenario where reducing registration friction is a priority.

## Instructions

### OAuth 2.0 Authorization Code Flow Overview

1. User clicks "Sign in with GitHub" in the frontend.
2. Backend redirects user to the provider's authorization URL with a `state` parameter.
3. User authenticates with the provider and grants consent.
4. Provider redirects back to the callback URL with an authorization `code` and `state`.
5. Backend validates the `state`, exchanges the `code` for an access token.
6. Backend fetches the user profile from the provider's API.
7. Backend links or creates the user account and issues a JWT.

### Authlib Setup for Flask

```python
from authlib.integrations.flask_client import OAuth
from flask import Flask

app = Flask(__name__)
app.config.from_prefixed_env()

oauth = OAuth(app)

oauth.register(
    name="github",
    client_id=app.config["GITHUB_CLIENT_ID"],
    client_secret=app.config["GITHUB_CLIENT_SECRET"],
    authorize_url="https://github.com/login/oauth/authorize",
    access_token_url="https://github.com/login/oauth/access_token",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)

oauth.register(
    name="google",
    client_id=app.config["GOOGLE_CLIENT_ID"],
    client_secret=app.config["GOOGLE_CLIENT_SECRET"],
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    access_token_url="https://oauth2.googleapis.com/token",
    api_base_url="https://www.googleapis.com/",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
```

### GitHub OAuth Flow

```python
from flask import Blueprint, redirect, url_for, session, jsonify

oauth_bp = Blueprint("oauth", __name__, url_prefix="/api/v1/auth")


@oauth_bp.route("/github/login")
def github_login():
    redirect_uri = url_for("oauth.github_callback", _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@oauth_bp.route("/github/callback")
def github_callback():
    token = oauth.github.authorize_access_token()

    resp = oauth.github.get("user", token=token)
    profile = resp.json()

    # Fetch email separately if not public
    if not profile.get("email"):
        emails_resp = oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
        primary = next((e for e in emails if e["primary"] and e["verified"]), None)
        if primary:
            profile["email"] = primary["email"]

    user = link_or_create_user(
        provider="github",
        provider_id=str(profile["id"]),
        email=profile.get("email"),
        name=profile.get("name") or profile.get("login"),
    )

    access_token = generate_access_token(user)
    return jsonify({"access_token": access_token}), 200
```

### Account Linking

When an OAuth user logs in, attempt to match their verified email to an existing local account. If a match is found, link the OAuth identity to that account rather than creating a duplicate.

```python
def link_or_create_user(provider: str, provider_id: str, email: str, name: str):
    # Check for existing OAuth link
    oauth_account = OAuthAccount.query.filter_by(
        provider=provider, provider_id=provider_id
    ).first()
    if oauth_account:
        return oauth_account.user

    # Check for existing user by email
    user = User.query.filter_by(email=email).first() if email else None

    if not user:
        user = User(email=email, name=name)
        db.session.add(user)

    # Link OAuth identity
    oauth_account = OAuthAccount(
        user=user, provider=provider, provider_id=provider_id
    )
    db.session.add(oauth_account)
    db.session.commit()

    return user
```

### Google OAuth Flow

The Google flow follows the same pattern as GitHub. The key difference is that Google returns the email directly in the user info response and supports OpenID Connect.

```python
@oauth_bp.route("/google/login")
def google_login():
    redirect_uri = url_for("oauth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@oauth_bp.route("/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()

    resp = oauth.google.get("oauth2/v3/userinfo", token=token)
    profile = resp.json()

    user = link_or_create_user(
        provider="google",
        provider_id=profile["sub"],
        email=profile.get("email"),
        name=profile.get("name"),
    )

    access_token = generate_access_token(user)
    return jsonify({"access_token": access_token}), 200
```

## Constraints

### ✅ Do
- Validate the `state` parameter on every callback to prevent CSRF attacks.
- Store OAuth tokens securely on the server side, never in frontend storage.
- Handle account linking by matching verified email addresses.
- Use HTTPS for all callback URLs in both development and production.
- Fetch the email separately for GitHub if the profile email is null.
- Support multiple OAuth providers linked to a single user account.


### ❌ Don&#x27;t
- Skip state parameter validation on the callback endpoint.
- Store access tokens or refresh tokens in the frontend (localStorage or sessionStorage).
- Trust an email address from an OAuth provider without checking its verification status.
- Hard-code client IDs or secrets in source code; use environment variables.
- Assume the provider will always return an email in the profile response.


## Output Format

**OAuth login redirect** (302):
Redirect to the provider's authorization page.

**Callback success** (200):
```json
{ "access_token": "<jwt>" }
```

**Callback failure** (401):
```json
{ "error": "OAuth authentication failed" }
```

## Dependencies

- [Scaffolding Flask](../../backend/scaffolding-flask/SKILL.md) -- Flask application setup and configuration.
- [Environment Config](../../shared/environment-config/SKILL.md) -- managing client IDs and secrets via environment variables.
- [Provider Configs](references/provider-configs.md) -- OAuth provider URLs, scopes, and environment variable names.
