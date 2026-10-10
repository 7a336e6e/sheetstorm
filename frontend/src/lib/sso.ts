/**
 * Single sign-on helpers shared by the login page and the admin editor:
 * identity-provider presets (issuer template + sensible claim defaults +
 * setup hints) and the messages for `/login?sso_error=<code>`.
 */
import type { SsoPreset, SsoProviderInput } from '@/types'

export interface SsoPresetField {
  key: string
  label: string
  placeholder: string
}

export interface SsoPresetDef {
  id: SsoPreset
  label: string
  /** Issuer with `{field}` placeholders filled from `fields`. */
  issuerTemplate: string
  fields: SsoPresetField[]
  defaults: Partial<SsoProviderInput>
  hint: string
}

export const SSO_PRESETS: SsoPresetDef[] = [
  {
    id: 'entra',
    label: 'Microsoft Entra ID',
    issuerTemplate: 'https://login.microsoftonline.com/{tenant}/v2.0',
    fields: [{ key: 'tenant', label: 'Directory (tenant) ID', placeholder: '00000000-0000-0000-0000-000000000000' }],
    defaults: {
      scopes: 'openid email profile',
      email_claims: ['email', 'preferred_username'],
      require_email_verified: false,
      groups_claim: 'roles',
    },
    hint:
      'Entra admin center → App registrations → New registration (single tenant). Add the redirect URI below as a ' +
      'Web platform redirect, create a client secret, and define App roles: they arrive in the "roles" claim, which ' +
      'is the recommended way to map roles (the groups claim lists object IDs and is dropped above 200 groups). ' +
      'Entra does not send email_verified, so "Require a verified email" is off for this preset.',
  },
  {
    id: 'okta',
    label: 'Okta',
    issuerTemplate: 'https://{domain}/oauth2/default',
    fields: [{ key: 'domain', label: 'Okta domain', placeholder: 'your-org.okta.com' }],
    defaults: { scopes: 'openid email profile groups', groups_claim: 'groups' },
    hint:
      'Admin console → Applications → Create App Integration → OIDC, Web Application. Use the redirect URI below as ' +
      'the sign-in redirect URI. For groups, add a "groups" claim (filter e.g. starts with "IR-") to the ' +
      'authorization server and keep the groups scope.',
  },
  {
    id: 'keycloak',
    label: 'Keycloak',
    issuerTemplate: 'https://{host}/realms/{realm}',
    fields: [
      { key: 'host', label: 'Keycloak host', placeholder: 'sso.example.com' },
      { key: 'realm', label: 'Realm', placeholder: 'incident-response' },
    ],
    defaults: { scopes: 'openid email profile', groups_claim: 'groups' },
    hint:
      'Clients → Create client (OpenID Connect, client authentication on, standard flow). Add the redirect URI below ' +
      'as a valid redirect URI. For groups, add a "Group Membership" mapper to the client (token claim name ' +
      '"groups", full group path off, add to ID token).',
  },
  {
    id: 'google',
    label: 'Google Workspace',
    issuerTemplate: 'https://accounts.google.com',
    fields: [],
    defaults: { scopes: 'openid email profile', groups_claim: null },
    hint:
      'Google Cloud console → APIs & Services → Credentials → OAuth client ID (Web application) with the redirect ' +
      'URI below. Google sends no groups: restrict sign-in with Allowed email domains and use a default role.',
  },
  {
    id: 'authentik',
    label: 'authentik',
    issuerTemplate: 'https://{host}/application/o/{app}/',
    fields: [
      { key: 'host', label: 'authentik host', placeholder: 'auth.example.com' },
      { key: 'app', label: 'Application slug', placeholder: 'sheetstorm' },
    ],
    defaults: { scopes: 'openid email profile', groups_claim: 'groups' },
    hint:
      'Applications → Providers → OAuth2/OpenID Provider (confidential) with the redirect URI below, then an ' +
      'Application using it. The default profile scope includes "groups".',
  },
  {
    id: 'auth0',
    label: 'Auth0',
    issuerTemplate: 'https://{domain}/',
    fields: [{ key: 'domain', label: 'Auth0 domain', placeholder: 'your-tenant.eu.auth0.com' }],
    defaults: { scopes: 'openid email profile', groups_claim: 'https://sheetstorm/roles' },
    hint:
      'Applications → Create Application → Regular Web Application; add the redirect URI below to Allowed Callback ' +
      'URLs. Roles need a post-login Action that adds a namespaced claim (e.g. https://sheetstorm/roles).',
  },
  {
    id: 'generic',
    label: 'Other OpenID Connect provider',
    issuerTemplate: '',
    fields: [],
    defaults: {},
    hint:
      'Any provider with OpenID Connect discovery (/.well-known/openid-configuration), the authorization code flow ' +
      'and RS/PS/ES-signed ID tokens: ADFS, PingFederate, JumpCloud, Zitadel, Dex, ...',
  },
]

export function presetDef(id: SsoPreset): SsoPresetDef {
  return SSO_PRESETS.find((p) => p.id === id) ?? SSO_PRESETS[SSO_PRESETS.length - 1]
}

/** Fill an issuer template; null while a field is still empty. */
export function buildIssuer(template: string, values: Record<string, string>): string | null {
  let missing = false
  const url = template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const v = (values[key] || '').trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')
    if (!v) missing = true
    return v
  })
  return missing ? null : url
}

export const SSO_ERROR_MESSAGES: Record<string, string> = {
  provider_unavailable:
    'Single sign-on is unavailable right now. Try again, or ask an administrator to check the provider.',
  state_invalid: 'The sign-in expired or was started in another browser tab. Please try again.',
  access_denied: 'The identity provider did not complete the sign-in.',
  token_invalid:
    "The identity provider's response could not be verified. Ask an administrator to check the configuration.",
  email_missing: 'Your identity provider did not share an email address.',
  email_unverified: 'Your email address is not verified at the identity provider.',
  domain_not_allowed: 'Accounts with this email domain cannot sign in here.',
  group_not_allowed: 'You are not in a group that may sign in to SheetStorm.',
  account_exists:
    'An account with your email already exists. Sign in with your password, or ask an administrator to enable ' +
    'account linking for this provider.',
  account_conflict: 'This identity cannot be used with that SheetStorm account. Contact an administrator.',
  no_account:
    'You do not have a SheetStorm account yet. Ask an administrator to create one or to enable automatic ' +
    'provisioning for this provider.',
  account_disabled: 'Your account is disabled or temporarily locked.',
  mfa_required:
    'Your identity provider did not report multi-factor authentication. Sign in again using your second factor.',
  server_error: 'Something went wrong during sign-in. Please try again.',
}

export function ssoErrorMessage(code: string | null | undefined): string | null {
  if (!code) return null
  return SSO_ERROR_MESSAGES[code] ?? SSO_ERROR_MESSAGES.server_error
}

/** A same-site path to continue to after sign-in (never an absolute URL). */
export function safeNextPath(value: string | null | undefined, fallback = '/dashboard'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return fallback
  return value
}
