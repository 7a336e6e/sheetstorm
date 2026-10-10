# Single sign-on (OpenID Connect)

SheetStorm signs users in through any identity provider that speaks OpenID
Connect. That includes Microsoft Entra ID, Okta, Keycloak, Google Workspace,
authentik, Auth0, ADFS, PingFederate, JumpCloud, Zitadel and Dex. Each
provider gets its own button on the login page. Password sign-in stays
available for accounts that have a password.

Configure providers under **Admin → Settings → Authentication → Single sign-on**.
You need `users:manage`. Mapping groups to roles also needs `roles:manage`,
plus every permission of the roles you map.

## How it works

SheetStorm uses the authorization code flow with PKCE, run entirely by the
backend:

1. **The login button.** It opens `/api/v1/auth/sso/<slug>/start`. The
   backend stores a random `state`, `nonce` and PKCE verifier for ten
   minutes, single use. It ties the sign-in to the browser with a short-lived
   httpOnly cookie, then redirects to the identity provider.
2. **The callback.** The provider sends the browser back to
   `/api/v1/auth/sso/<slug>/callback`. The backend first checks that the
   `state` matches the cookie, then exchanges the code (client secret plus
   PKCE verifier). It then verifies the ID token:
   - the signature, against the provider's published keys. Only RS, PS and ES
     algorithms are accepted: never `none` or HMAC;
   - the exact issuer;
   - the audience and `azp`;
   - expiry, with 60 seconds of clock leeway;
   - the `nonce`.

   Claims missing from the ID token are filled from the userinfo endpoint,
   which must report the same subject.
3. **Finding the user.** The user is found by identity (provider plus
   subject). Failing that, by email, with linking switched on (see below).
   Failing that, they're created when automatic provisioning is on. Group
   rules, account status and the MFA mode then decide whether they get in.
4. **The session.** The user gets the same session cookies as a password
   sign-in and lands on the page they started from.

A provider belongs to the organization of the admin who created it. It can
only sign in, link or create users of that organization. An email address that
belongs to another organization is always refused.

## Adding a provider

1. **Pick a preset.** It builds the issuer URL from a few fields (tenant ID,
   domain, realm) and fills sensible claim defaults. "Other OpenID Connect
   provider" takes any issuer URL.
2. **Register the redirect URI at the provider.** The editor shows it, for
   example `https://sheetstorm.example.com/api/v1/auth/sso/entra/callback`. It
   is built from `SSO_REDIRECT_BASE_URL`, else `FRONTEND_URL`, else the
   address you opened the admin page on. Set `FRONTEND_URL` in production so
   it never depends on how you reached the page.
3. **Enter the client ID and secret.** The secret is stored encrypted
   (`FERNET_KEY`) and never shown again.
4. **Press Test.** It fetches the provider's discovery document and keys and
   checks:
   - that the issuer matches;
   - the token algorithms;
   - PKCE support;
   - the client authentication method;
   - the scopes.

The issuer must be `https://`. A self-hosted provider on a private address
(Keycloak, authentik, ADFS) must also be listed in `OUTBOUND_URL_ALLOWLIST`,
the same rule as other self-hosted integrations. For a lab without TLS, set
`SSO_ALLOW_HTTP_ISSUERS=true`. Never do that in production.

### Microsoft Entra ID

1. Entra admin center → **App registrations → New registration**, single
   tenant. Under **Authentication**, add the redirect URI as a **Web**
   redirect.
2. **Certificates & secrets → New client secret.** Copy the value, not the ID.
3. Preset **Microsoft Entra ID**: enter the Directory (tenant) ID and the
   Application (client) ID.
4. **Roles:** define **App roles** on the app registration (for example
   `SheetStorm.Responder`) and assign users or groups to them in Enterprise
   applications. They arrive in the `roles` claim, which the preset maps. The
   `groups` claim instead lists object IDs, and Entra drops it entirely above
   200 groups ("overage"). SheetStorm logs a warning when that happens.
5. Entra sends no `email_verified`, so the preset turns **Require a verified
   email** off. It reads `email`, then `preferred_username`. Leave **Link
   existing accounts** off unless you trust every UPN in the tenant.
6. Enforce MFA with Conditional Access and choose **Trust the identity
   provider**, or **Trust it, but require proof** (Entra reports `mfa` in
   `amr`).

Only single-tenant issuers are supported (no `common` or `organizations`).

### Okta

1. Admin console → **Applications → Create App Integration → OIDC → Web
   Application**. Use the redirect URI as the sign-in redirect URI.
2. Preset **Okta**: enter your Okta domain. It uses the `default`
   authorization server; edit the issuer for a custom one.
3. **Groups:** under **Security → API → Authorization servers → default →
   Claims**, add a `groups` claim of type Groups with a filter (for example
   *Starts with* `IR-`), included in the ID token for the `groups` scope. The
   preset requests that scope.

### Keycloak

Verified against Keycloak 26.7.

1. **Clients → Create client**: OpenID Connect, **Client authentication** on,
   **Standard flow** on. Add the redirect URI to **Valid redirect URIs**.
   Under **Advanced**, set **PKCE method** to `S256`.
2. **Groups:** on the client's dedicated scope, add a **Group Membership**
   mapper. Token claim name `groups`, **Full group path** off, **Add to ID
   token** on. For realm roles instead, set the groups claim to
   `realm_access.roles` and add the realm roles mapper to the ID token.
3. Preset **Keycloak**: enter the host and realm. The client secret is under
   **Credentials**.

### Google Workspace

1. Google Cloud console → **APIs & Services → Credentials → Create
   credentials → OAuth client ID** (Web application) with the redirect URI.
2. Preset **Google Workspace**. Google sends no groups, so restrict sign-in
   with **Allowed email domains** (your Workspace domain) and choose a
   **Default role**.

### authentik, Auth0 and others

- **authentik:**
  1. Create an **OAuth2/OpenID Provider** (confidential) with the redirect
     URI, and an Application that uses it.
  2. The issuer is `https://<host>/application/o/<app-slug>/`.
  3. Groups come in the `groups` claim.
- **Auth0:**
  1. Create a **Regular Web Application** and add the redirect URI to Allowed
     Callback URLs.
  2. Roles need a post-login Action that sets a namespaced claim, for example
     `api.idToken.setCustomClaim('https://sheetstorm/roles', event.authorization.roles)`.
  3. The preset reads `https://sheetstorm/roles`.
- **ADFS, PingFederate, JumpCloud, Zitadel, Dex:** use **Other OpenID Connect
  provider** with the issuer URL. The provider must publish
  `/.well-known/openid-configuration` and sign ID tokens with RS, PS or ES
  keys.

## Accounts

| Setting | Effect |
|---|---|
| **Create accounts on first sign-in** | A user with no SheetStorm account is created in the provider's organization, with the roles below. Off: such users are refused ("no account"). |
| **Link existing accounts by email** | An existing account with the same email signs in through the provider from then on (the link is by subject). Off: refused with "account exists". |
| **Require a verified email** | Linking and creating need `email_verified: true`. Only the standard `email` claim can be verified; addresses taken from other claims never count as verified. |
| **Allowed email domains** | Only these domains may link or be created. The organization's security policy domain list applies as well. |
| **Allowed groups** | Only members of at least one of these groups may sign in at all (matched case-insensitively). |

Accounts created through SSO have no password: they can only sign in through
their provider. Deleting a provider removes its links but never the users. An
administrator can then set a password or link them to another provider.

## Roles

- **Groups claim:** where the token lists groups or roles. Use a plain name
  (`groups`, `roles`), a dotted path (`realm_access.roles`) or a URL-style
  name (`https://sheetstorm/roles`).
- **Group to role mappings:** each matching group adds its role. With no
  match, the user gets the **Default role**, else the organization's default
  role (Viewer unless changed).
- **Apply roles:**
  - *When the account is created* (default): later role changes in SheetStorm
    are kept.
  - *On every sign-in*: the identity provider is the source of truth, and the
    user's roles are replaced with the mapped ones each time. A sync that
    would leave the organization without an administrator is skipped and
    logged (`sso_role_sync_blocked`).
- **Grant ceiling:** a provider only hands out roles that its last editor may
  grant. If that admin later loses the permission or is disabled, the mapping
  stops applying and users get the default role (`sso_role_mapping_ignored`
  in the audit log).

## Multi-factor authentication

| Mode | Behavior |
|---|---|
| **SheetStorm decides** (default) | Users who enrolled SheetStorm TOTP enter their code after the identity provider. The organization's MFA policy applies to SSO users as to everyone else. |
| **Trust the identity provider** | The provider enforces MFA. Users who only sign in through it (no password) are neither asked for a SheetStorm code nor required to enroll in TOTP. |
| **Trust it, but require proof** | As above, but a sign-in is refused unless the ID token's `amr` claim reports a second factor (`mfa`, `otp`, `hwk`, `swk`, `sms`, `tel`, `sc`, biometrics). |

During the TOTP step, the short-lived pre-authentication token sits in an
httpOnly cookie, never in the URL.

## Troubleshooting

A refused sign-in returns to `/login?sso_error=<code>` with a short message.
The details go to the audit log only: **Activity**, action `sso_login`, with
`reason` and `detail`.

| Code | Usual cause |
|---|---|
| `provider_unavailable` | Provider disabled, unreachable, or the issuer doesn't match the discovery document. Not `https`, or a private address missing from `OUTBOUND_URL_ALLOWLIST`. |
| `state_invalid` | The sign-in took more than ten minutes, or the callback arrived in another browser. |
| `access_denied` | The user cancelled, or the provider refused (the `detail` has the provider's error). |
| `token_invalid` | Wrong client secret (`invalid_client`), a redirect URI mismatch, or an ID token that fails verification. |
| `email_missing` / `email_unverified` | No email in the configured claims, or not verified. See the Entra note above. |
| `domain_not_allowed` / `group_not_allowed` | Outside the allowed domains or groups (the `detail` lists the groups received). |
| `account_exists` / `no_account` | Linking or automatic provisioning is off. |
| `account_conflict` | The email belongs to another organization, or the account is already linked to another subject. |
| `account_disabled` | Disabled, locked or a service account. |
| `mfa_required` | **Trust it, but require proof**, and the token reported no second factor. |

Endpoints and rate limits are listed in the
[API reference](api-reference.md#single-sign-on-openid-connect). The
`auth_sso` rate-limit group covers the sign-in routes (30 per minute per
client address).

## Limits

- **No SAML.** Every provider above speaks OpenID Connect.
- **Signing out of SheetStorm doesn't sign the user out of the identity
  provider.**
- **Entra multi-tenant (`common`) issuers aren't supported.**

## Testing

- **Backend:** `backend/tests/test_sso.py` runs the whole flow against an
  in-process fake provider with real RSA and EC keys, including tampered,
  expired and wrongly signed tokens. It also uses Entra, Okta and
  Keycloak-shaped claims.
- **End to end:** `frontend/e2e/sso.spec.ts` drives a browser through
  `ci/mock-oidc`, a small standard-library provider that runs in the CI e2e
  stack.
