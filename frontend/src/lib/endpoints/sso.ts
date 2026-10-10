/**
 * OpenID Connect single sign-on.
 *
 * Admin (`users:manage`; mapping roles also needs `roles:manage`):
 * `/admin/sso-providers`. Public: `/auth/sso/providers` lists the sign-in
 * buttons; the sign-in itself is a full-page navigation to
 * `/auth/sso/<slug>/start` (never a fetch), see `ssoStartHref`.
 */
import { api } from '@/lib/api'
import type { SsoLoginProviders, SsoProvider, SsoProviderInput, SsoProviderList, SsoTestReport } from '@/types'

export const SSO_PROVIDERS_ENDPOINT = '/admin/sso-providers'

export const ssoProviders = {
  list: () => api.get<SsoProviderList>(SSO_PROVIDERS_ENDPOINT),
  create: (body: SsoProviderInput) => api.post<SsoProvider>(SSO_PROVIDERS_ENDPOINT, body),
  update: (id: string, body: Partial<SsoProviderInput>) =>
    api.put<SsoProvider>(`${SSO_PROVIDERS_ENDPOINT}/${id}`, body),
  remove: (id: string) =>
    api.delete<{ deleted: boolean; identities_removed: number }>(`${SSO_PROVIDERS_ENDPOINT}/${id}`),
  test: (id: string) => api.post<SsoTestReport>(`${SSO_PROVIDERS_ENDPOINT}/${id}/test`),
  loginOptions: () => api.get<SsoLoginProviders>('/auth/sso/providers'),
}

/** Where a sign-in button navigates: the API's start URL plus the page to land on. */
export function ssoStartHref(startUrl: string, next?: string | null): string {
  const base = (process.env.NEXT_PUBLIC_API_URL || '/api/v1').replace(/\/api\/v1\/?$/, '')
  const href = startUrl.startsWith('http') ? startUrl : `${base}${startUrl}`
  return next && next.startsWith('/') && !next.startsWith('//') ? `${href}?next=${encodeURIComponent(next)}` : href
}
