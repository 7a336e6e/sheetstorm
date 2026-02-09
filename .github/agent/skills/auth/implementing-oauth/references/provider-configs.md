---
name: provider-configs
description: OAuth provider endpoint URLs, scopes, and environment variable configuration for GitHub and Google.
---

# OAuth Provider Configurations

This reference documents the OAuth 2.0 endpoints, scopes, and environment variables for each supported provider.

## GitHub

| Setting           | Value                                                  |
|-------------------|--------------------------------------------------------|
| Authorization URL | `https://github.com/login/oauth/authorize`             |
| Token URL         | `https://github.com/login/oauth/access_token`          |
| User Info URL     | `https://api.github.com/user`                          |
| User Emails URL   | `https://api.github.com/user/emails`                   |
| Scopes            | `read:user`, `user:email`                              |

### Environment Variables

```
GITHUB_CLIENT_ID=<your-github-client-id>
GITHUB_CLIENT_SECRET=<your-github-client-secret>
```

### Authlib Registration

```python
oauth.register(
    name="github",
    client_id=app.config["GITHUB_CLIENT_ID"],
    client_secret=app.config["GITHUB_CLIENT_SECRET"],
    authorize_url="https://github.com/login/oauth/authorize",
    access_token_url="https://github.com/login/oauth/access_token",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)
```

### Notes

- GitHub does not always include the email in the `/user` response. If the email is null, fetch it from `/user/emails` and select the primary, verified address.
- Register your OAuth app at: `https://github.com/settings/applications/new`.
- The "Authorization callback URL" in the GitHub app settings must match your callback route exactly.

---

## Google

| Setting           | Value                                                     |
|-------------------|-----------------------------------------------------------|
| Authorization URL | `https://accounts.google.com/o/oauth2/v2/auth`           |
| Token URL         | `https://oauth2.googleapis.com/token`                     |
| User Info URL     | `https://www.googleapis.com/oauth2/v3/userinfo`           |
| Discovery Doc     | `https://accounts.google.com/.well-known/openid-configuration` |
| Scopes            | `openid`, `email`, `profile`                              |

### Environment Variables

```
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
```

### Authlib Registration

```python
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

### Notes

- Google supports OpenID Connect. The `server_metadata_url` allows Authlib to auto-discover endpoints.
- Register your OAuth app in the Google Cloud Console under **APIs & Services > Credentials**.
- The `email` field in the user info response is the user's primary Google account email.

---

## Common Settings

### Callback URL Pattern

All OAuth providers use the following callback URL pattern:

```
/api/v1/auth/{provider}/callback
```

Examples:
- GitHub: `/api/v1/auth/github/callback`
- Google: `/api/v1/auth/google/callback`

In production, the full URL must use HTTPS:

```
https://yourdomain.com/api/v1/auth/github/callback
```

### Required Environment Variables Per Provider

Every provider requires exactly two environment variables:

| Provider | Client ID Var          | Client Secret Var          |
|----------|------------------------|----------------------------|
| GitHub   | `GITHUB_CLIENT_ID`     | `GITHUB_CLIENT_SECRET`     |
| Google   | `GOOGLE_CLIENT_ID`     | `GOOGLE_CLIENT_SECRET`     |

These must be set in the `.env` file and loaded via the application's environment configuration. Never commit these values to source control.

### Adding a New Provider

To add a new OAuth provider:

1. Add the provider's environment variables to `.env.example`.
2. Register the provider with Authlib in the OAuth setup module.
3. Create login and callback routes following the existing pattern.
4. Add an entry to this reference document with URLs, scopes, and notes.
5. Test the full flow in a staging environment before deploying.
