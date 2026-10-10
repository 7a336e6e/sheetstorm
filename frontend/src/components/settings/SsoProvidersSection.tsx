"use client"

/**
 * Single sign-on (OpenID Connect) providers of the organization: list, test
 * and edit. Needs `users:manage`; mapping roles also needs `roles:manage` and
 * every permission of the mapped roles (the server enforces both).
 *
 * The editor starts from a preset (Entra ID, Okta, Keycloak, ...) that builds
 * the issuer URL from a few fields and fills claim defaults; everything stays
 * editable. The client secret is write-only.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check, CheckCircle2, Copy, KeyRound, Loader2, Pencil, Plus, ShieldCheck, Trash2, TriangleAlert, XCircle, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { Field, NativeSelect } from '@/components/incidents/evidence/form-parts'
import { rbac } from '@/lib/endpoints/rbac'
import { ssoProviders } from '@/lib/endpoints/sso'
import { notifyError, notifySuccess } from '@/lib/errors'
import { SSO_PRESETS, buildIssuer, presetDef } from '@/lib/sso'
import type { Role, SsoMfaMode, SsoPreset, SsoProvider, SsoProviderInput, SsoProviderList, SsoTestReport } from '@/types'

const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$/

const MFA_MODES: { value: SsoMfaMode; label: string; hint: string }[] = [
  {
    value: 'sheetstorm',
    label: 'SheetStorm decides',
    hint: 'Users who enrolled SheetStorm TOTP enter a code after the identity provider; the MFA policy applies as usual.',
  },
  {
    value: 'idp',
    label: 'Trust the identity provider',
    hint: 'The identity provider enforces MFA. Users who only sign in through it are not asked for a SheetStorm code.',
  },
  {
    value: 'idp_amr',
    label: 'Trust it, but require proof',
    hint: 'As above, but a sign-in whose token does not report a second factor (amr claim) is refused.',
  },
]

const EMPTY: SsoProviderInput = {
  slug: '',
  display_name: '',
  preset: 'entra',
  issuer: '',
  client_id: '',
  token_auth_method: 'client_secret_basic',
  scopes: 'openid email profile',
  email_claims: ['email'],
  name_claim: 'name',
  groups_claim: null,
  role_mappings: [],
  default_role_id: null,
  allowed_groups: [],
  allowed_domains: [],
  is_enabled: true,
  show_on_login: true,
  auto_provision: false,
  link_existing: false,
  require_email_verified: true,
  role_sync: 'first_login',
  mfa_mode: 'sheetstorm',
}

/** Claim settings a preset may override; reset first so switching presets leaves nothing behind. */
const EMPTY_CLAIMS: Partial<SsoProviderInput> = {
  scopes: EMPTY.scopes,
  email_claims: EMPTY.email_claims,
  require_email_verified: EMPTY.require_email_verified,
  groups_claim: EMPTY.groups_claim,
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
}

const splitList = (value: string) => value.split(/[,\n]/).map((v) => v.trim()).filter(Boolean)

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      aria-label={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          setCopied(false)
        }
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </Button>
  )
}

function TestReport({ report }: { report: SsoTestReport }) {
  return (
    <ul className="mt-3 space-y-1 text-xs" aria-label="Configuration check">
      {report.checks.map((c) => (
        <li key={c.name} className="flex items-start gap-2">
          {!c.ok ? (
            <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-label="failed" />
          ) : c.warning ? (
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" aria-label="warning" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-400" aria-label="passed" />
          )}
          <span>
            <span className="font-medium">{c.name}</span>
            <span className="text-muted-foreground">: {c.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

export function SsoProvidersSection() {
  const confirm = useConfirm()
  const [data, setData] = useState<SsoProviderList | null>(null)
  const [roles, setRoles] = useState<Role[]>([])
  const [editing, setEditing] = useState<SsoProvider | 'new' | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [reports, setReports] = useState<Record<string, SsoTestReport>>({})

  // Bumped after a change to reload the list.
  const [version, setVersion] = useState(0)
  const reload = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    let alive = true
    Promise.all([ssoProviders.list(), rbac.listRoles().catch(() => ({ items: [] as Role[] }))])
      .then(([list, roleList]) => {
        if (!alive) return
        setData(list)
        setRoles(roleList.items)
      })
      .catch((err) => {
        if (!alive) return
        notifyError(err, 'load the single sign-on providers')
        setData({ items: [], redirect_uri_template: '', allow_http_issuers: false })
      })
    return () => {
      alive = false
    }
  }, [version])

  const runTest = async (provider: SsoProvider) => {
    setTesting(provider.id)
    try {
      const report = await ssoProviders.test(provider.id)
      setReports((r) => ({ ...r, [provider.id]: report }))
    } catch (err) {
      notifyError(err, 'test the provider')
    } finally {
      setTesting(null)
    }
  }

  const remove = async (provider: SsoProvider) => {
    const ok = await confirm({
      title: `Delete ${provider.display_name}?`,
      description:
        `${provider.identity_count} linked account(s) lose this sign-in method. Users created by this provider ` +
        'keep their data but cannot sign in until an administrator sets a password or links another provider.',
      confirmLabel: 'Delete provider',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await ssoProviders.remove(provider.id)
      notifySuccess('Provider deleted')
      reload()
    } catch (err) {
      notifyError(err, 'delete the provider')
    }
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <section className="space-y-4" aria-labelledby="sso-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 id="sso-heading" className="text-lg font-medium">Single sign-on (OpenID Connect)</h3>
          <p className="text-sm text-muted-foreground">
            Microsoft Entra ID, Okta, Keycloak, Google Workspace, authentik, Auth0 or any OpenID Connect provider.
          </p>
        </div>
        <Button onClick={() => setEditing('new')}>
          <Plus className="mr-2 h-4 w-4" /> Add identity provider
        </Button>
      </div>

      {data.items.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center p-8 text-center text-muted-foreground">
            <KeyRound className="mb-3 h-8 w-8 opacity-50" />
            <p className="font-medium">No identity provider yet</p>
            <p className="mt-1 text-sm">Add one to show a sign-in button for it on the login page.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {data.items.map((p) => (
            <Card key={p.id} data-testid={`sso-provider-${p.slug}`}>
              <CardContent className="p-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-primary" aria-hidden />
                      <span className="font-medium">{p.display_name}</span>
                      <Badge variant="outline" className="text-xs">{presetDef(p.preset).label}</Badge>
                      {p.is_enabled ? (
                        <Badge variant="outline" className="border-green-500/30 text-xs text-green-400">Enabled</Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs text-muted-foreground">Disabled</Badge>
                      )}
                      {p.is_enabled && !p.show_on_login && (
                        <Badge variant="outline" className="text-xs text-muted-foreground">Hidden on login page</Badge>
                      )}
                      {p.auto_provision && <Badge variant="outline" className="text-xs">Creates accounts</Badge>}
                      {p.mfa_mode !== 'sheetstorm' && <Badge variant="outline" className="text-xs">MFA by IdP</Badge>}
                    </div>
                    <p className="truncate font-mono text-xs text-muted-foreground" title={p.issuer}>{p.issuer}</p>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span className="truncate" title={p.redirect_uri}>Redirect URI: {p.redirect_uri}</span>
                      <CopyButton value={p.redirect_uri} label={`Copy the redirect URI of ${p.display_name}`} />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {p.identity_count} linked account{p.identity_count === 1 ? '' : 's'}
                      {p.last_login_at && (
                        <>
                          {' · last sign-in '}
                          <Timestamp value={p.last_login_at} seconds={false} />
                        </>
                      )}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => runTest(p)} disabled={testing === p.id}>
                      {testing === p.id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Zap className="mr-1.5 h-3.5 w-3.5" />}
                      Test
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setEditing(p)}>
                      <Pencil className="mr-1.5 h-3.5 w-3.5" /> Edit
                    </Button>
                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive/90"
                      aria-label={`Delete ${p.display_name}`} onClick={() => remove(p)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                {reports[p.id] && <TestReport report={reports[p.id]} />}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <SsoProviderDialog
          provider={editing === 'new' ? null : editing}
          roles={roles}
          redirectTemplate={data.redirect_uri_template}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            reload()
          }}
        />
      )}
    </section>
  )
}

function SsoProviderDialog({
  provider,
  roles,
  redirectTemplate,
  onClose,
  onSaved,
}: {
  provider: SsoProvider | null
  roles: Role[]
  redirectTemplate: string
  onClose: () => void
  onSaved: () => void | Promise<void>
}) {
  const creating = provider === null
  const [form, setForm] = useState<SsoProviderInput>(() => {
    if (provider) return { ...EMPTY, ...provider }
    const first = presetDef(EMPTY.preset)
    return { ...EMPTY, ...first.defaults, display_name: first.label, slug: slugify(first.label) }
  })
  const [presetValues, setPresetValues] = useState<Record<string, string>>({})
  // Existing providers show the issuer itself (the preset fields are not stored).
  const [manualIssuer, setManualIssuer] = useState(!creating)
  const [slugTouched, setSlugTouched] = useState(!creating)
  const [secret, setSecret] = useState('')
  const [clearSecret, setClearSecret] = useState(false)
  const [domains, setDomains] = useState(form.allowed_domains.join(', '))
  const [groups, setGroups] = useState(form.allowed_groups.join(', '))
  const [emailClaims, setEmailClaims] = useState(form.email_claims.join(', '))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const preset = presetDef(form.preset)
  const set = <K extends keyof SsoProviderInput>(key: K, value: SsoProviderInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const usesTemplate = !manualIssuer && preset.issuerTemplate !== ''
  const builtIssuer = usesTemplate ? buildIssuer(preset.issuerTemplate, presetValues) : null
  const issuer = usesTemplate ? builtIssuer ?? '' : form.issuer
  const redirectUri = redirectTemplate && SLUG_RE.test(form.slug) ? redirectTemplate.replace('{slug}', form.slug) : ''

  const choosePreset = (id: SsoPreset) => {
    const def = presetDef(id)
    setForm((f) => {
      const next = { ...f, ...EMPTY_CLAIMS, ...def.defaults, preset: id }
      // A new provider's label follows the preset until the admin types their own.
      if (creating && !isCustomName(f.display_name)) {
        next.display_name = def.id === 'generic' ? '' : def.label
        if (!slugTouched) next.slug = slugify(next.display_name)
      }
      return next
    })
    setEmailClaims((def.defaults.email_claims ?? EMPTY.email_claims).join(', '))
    setPresetValues({})
    if (creating) setManualIssuer(def.issuerTemplate === '')
  }

  const roleOptions = useMemo(() => roles.map((r) => ({ value: r.id, label: r.name })), [roles])

  const problems: string[] = []
  if (!form.display_name.trim()) problems.push('a display name')
  if (!SLUG_RE.test(form.slug)) problems.push('a valid slug')
  if (!issuer.trim()) problems.push(usesTemplate ? preset.fields.map((f) => f.label).join(' and ') : 'the issuer URL')
  if (!form.client_id.trim()) problems.push('the client ID')

  const save = async () => {
    setError(null)
    if (problems.length) {
      setError(`Enter ${problems.join(', ')}.`)
      return
    }
    const body: SsoProviderInput = {
      ...form,
      issuer: issuer.trim(),
      display_name: form.display_name.trim(),
      client_id: form.client_id.trim(),
      allowed_domains: splitList(domains),
      allowed_groups: splitList(groups),
      email_claims: splitList(emailClaims).length ? splitList(emailClaims) : ['email'],
      groups_claim: form.groups_claim?.trim() || null,
      role_mappings: form.role_mappings.filter((m) => m.group.trim() && m.role_id),
    }
    if (secret) body.client_secret = secret
    else if (clearSecret) body.client_secret = ''
    else delete body.client_secret
    setSaving(true)
    try {
      if (provider) await ssoProviders.update(provider.id, body)
      else await ssoProviders.create(body)
      notifySuccess(creating ? 'Identity provider added' : 'Identity provider updated')
      await onSaved()
    } catch (err) {
      notifyError(err, creating ? 'add the identity provider' : 'update the identity provider')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{provider ? `Edit ${provider.display_name}` : 'Add identity provider'}</DialogTitle>
          <DialogDescription>
            Users sign in at the identity provider and come back to SheetStorm through the redirect URI.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-6">
          {/* Provider */}
          <div className="space-y-4">
            <Field label="Identity provider">
              {({ id }) => (
                <NativeSelect id={id} value={form.preset} onValueChange={(v) => choosePreset(v as SsoPreset)}
                  options={SSO_PRESETS.map((p) => ({ value: p.id, label: p.label }))} />
              )}
            </Field>
            <p className="rounded-md bg-muted/30 p-3 text-xs text-muted-foreground">{preset.hint}</p>

            {usesTemplate ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {preset.fields.map((f) => (
                  <Field key={f.key} label={f.label} required>
                    {({ id }) => (
                      <Input id={id} value={presetValues[f.key] ?? ''} placeholder={f.placeholder}
                        onChange={(e) => setPresetValues((v) => ({ ...v, [f.key]: e.target.value }))} />
                    )}
                  </Field>
                ))}
                <p className="text-xs text-muted-foreground sm:col-span-2">
                  Issuer: <span className="font-mono">{builtIssuer ?? '…'}</span>{' '}
                  <button type="button" className="underline" onClick={() => { set('issuer', builtIssuer ?? ''); setManualIssuer(true) }}>
                    Enter the issuer URL instead
                  </button>
                </p>
              </div>
            ) : (
              <Field label="Issuer URL" required hint="The URL that serves /.well-known/openid-configuration.">
                {({ id, describedBy }) => (
                  <Input id={id} aria-describedby={describedBy} value={form.issuer} placeholder="https://idp.example.com/realms/ir"
                    onChange={(e) => set('issuer', e.target.value)} className="font-mono text-xs" />
                )}
              </Field>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Button label" required hint='Shown as the sign-in button ("Sign in with …").'>
                {({ id, describedBy }) => (
                  <Input id={id} aria-describedby={describedBy} value={form.display_name} maxLength={80}
                    onChange={(e) => {
                      const name = e.target.value
                      setForm((f) => ({ ...f, display_name: name, slug: slugTouched ? f.slug : slugify(name) }))
                    }} />
                )}
              </Field>
              <Field label="Slug" required
                hint={creating ? 'Part of the redirect URI.' : 'Changing it changes the redirect URI: update it at the identity provider too.'}>
                {({ id, describedBy }) => (
                  <Input id={id} aria-describedby={describedBy} value={form.slug} maxLength={40} className="font-mono text-xs"
                    onChange={(e) => { setSlugTouched(true); set('slug', e.target.value.toLowerCase()) }} />
                )}
              </Field>
            </div>
            <div className="space-y-1.5">
              <Label>Redirect URI</Label>
              <div className="flex items-center gap-2 rounded-md border border-border bg-muted/20 px-3 py-2">
                <span className="flex-1 truncate font-mono text-xs" data-testid="sso-redirect-uri">
                  {redirectUri || 'Enter a slug first'}
                </span>
                {redirectUri && <CopyButton value={redirectUri} label="Copy the redirect URI" />}
              </div>
              <p className="text-xs text-muted-foreground">Register this exact URL at the identity provider.</p>
            </div>
          </div>

          {/* Client */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Client ID" required>
              {({ id }) => <Input id={id} value={form.client_id} onChange={(e) => set('client_id', e.target.value)} />}
            </Field>
            <Field label="Client secret"
              hint={provider?.has_client_secret ? 'Leave empty to keep the stored secret.' : 'Stored encrypted; never shown again.'}>
              {({ id, describedBy }) => (
                <Input id={id} type="password" autoComplete="new-password" aria-describedby={describedBy} value={secret}
                  placeholder={provider?.has_client_secret ? '(unchanged)' : ''}
                  onChange={(e) => { setSecret(e.target.value); setClearSecret(false) }} />
              )}
            </Field>
            {provider?.has_client_secret && (
              <label className="flex items-center gap-2 text-xs text-muted-foreground sm:col-span-2">
                <input type="checkbox" checked={clearSecret} disabled={!!secret} onChange={(e) => setClearSecret(e.target.checked)} />
                Remove the stored secret (public client with PKCE only)
              </label>
            )}
          </div>

          {/* Accounts */}
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Accounts</p>
            {([
              ['auto_provision', 'Create accounts on first sign-in', 'New users join this organization with the roles below.'],
              ['link_existing', 'Link existing accounts by email', 'An existing SheetStorm account with the same (verified) email signs in through this provider.'],
              ['require_email_verified', 'Require a verified email', 'For linking and new accounts. Entra ID does not send this flag.'],
            ] as const).map(([key, label, hint]) => (
              <div key={key} className="flex items-start justify-between gap-4">
                <div>
                  <Label htmlFor={`sso-${key}`}>{label}</Label>
                  <p className="text-xs text-muted-foreground">{hint}</p>
                </div>
                <Switch id={`sso-${key}`} checked={form[key]} onCheckedChange={(c) => set(key, c)} />
              </div>
            ))}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Allowed email domains" hint="Comma-separated; empty allows any.">
                {({ id, describedBy }) => (
                  <Input id={id} aria-describedby={describedBy} value={domains} placeholder="example.com"
                    onChange={(e) => setDomains(e.target.value)} />
                )}
              </Field>
              <Field label="Allowed groups" hint="Only members of these groups may sign in; empty allows everyone.">
                {({ id, describedBy }) => (
                  <Input id={id} aria-describedby={describedBy} value={groups} placeholder="IR-Team"
                    onChange={(e) => setGroups(e.target.value)} />
                )}
              </Field>
            </div>
          </div>

          {/* Roles */}
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Roles</p>
            <Field label="Groups claim" hint='Where the token lists groups or roles, e.g. "groups", "roles", "realm_access.roles".'>
              {({ id, describedBy }) => (
                <Input id={id} aria-describedby={describedBy} value={form.groups_claim ?? ''} className="font-mono text-xs"
                  onChange={(e) => set('groups_claim', e.target.value)} />
              )}
            </Field>
            <div className="space-y-2" role="group" aria-label="Group to role mappings">
              {form.role_mappings.map((m, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input aria-label={`Group ${i + 1}`} value={m.group} placeholder="Group name or ID"
                    onChange={(e) => set('role_mappings', form.role_mappings.map((x, j) => (j === i ? { ...x, group: e.target.value } : x)))} />
                  <NativeSelect aria-label={`Role for group ${i + 1}`} value={m.role_id} placeholder="Role…" options={roleOptions}
                    onValueChange={(v) => set('role_mappings', form.role_mappings.map((x, j) => (j === i ? { ...x, role_id: v } : x)))} />
                  <Button type="button" variant="ghost" size="icon" aria-label={`Remove mapping ${i + 1}`}
                    onClick={() => set('role_mappings', form.role_mappings.filter((_, j) => j !== i))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm"
                onClick={() => set('role_mappings', [...form.role_mappings, { group: '', role_id: '' }])}>
                <Plus className="mr-1.5 h-3.5 w-3.5" /> Map a group to a role
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Default role" hint="When no mapped group matches.">
                {({ id, describedBy }) => (
                  <NativeSelect id={id} aria-describedby={describedBy} value={form.default_role_id ?? ''}
                    placeholder="Organization default" options={roleOptions}
                    onValueChange={(v) => set('default_role_id', v || null)} />
                )}
              </Field>
              <Field label="Apply roles" hint="Every sign-in replaces the user's roles with the mapped ones (never removing the last administrator).">
                {({ id, describedBy }) => (
                  <NativeSelect id={id} aria-describedby={describedBy} value={form.role_sync}
                    onValueChange={(v) => set('role_sync', v as SsoProviderInput['role_sync'])}
                    options={[
                      { value: 'first_login', label: 'When the account is created' },
                      { value: 'every_login', label: 'On every sign-in' },
                    ]} />
                )}
              </Field>
            </div>
          </div>

          {/* MFA */}
          <Field label="Multi-factor authentication" hint={MFA_MODES.find((m) => m.value === form.mfa_mode)?.hint}>
            {({ id, describedBy }) => (
              <NativeSelect id={id} aria-describedby={describedBy} value={form.mfa_mode}
                onValueChange={(v) => set('mfa_mode', v as SsoMfaMode)}
                options={MFA_MODES.map((m) => ({ value: m.value, label: m.label }))} />
            )}
          </Field>

          {/* Advanced */}
          <details className="rounded-md border border-border p-3">
            <summary className="cursor-pointer text-sm font-medium">Advanced</summary>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Field label="Scopes">
                {({ id }) => <Input id={id} value={form.scopes} className="font-mono text-xs" onChange={(e) => set('scopes', e.target.value)} />}
              </Field>
              <Field label="Client authentication">
                {({ id }) => (
                  <NativeSelect id={id} value={form.token_auth_method}
                    onValueChange={(v) => set('token_auth_method', v as SsoProviderInput['token_auth_method'])}
                    options={[
                      { value: 'client_secret_basic', label: 'Secret in the Authorization header' },
                      { value: 'client_secret_post', label: 'Secret in the request body' },
                      { value: 'none', label: 'None (public client, PKCE only)' },
                    ]} />
                )}
              </Field>
              <Field label="Email claims" hint="Tried in order. Only the standard email claim counts as verified.">
                {({ id, describedBy }) => (
                  <Input id={id} aria-describedby={describedBy} value={emailClaims} className="font-mono text-xs"
                    onChange={(e) => setEmailClaims(e.target.value)} />
                )}
              </Field>
              <Field label="Name claim">
                {({ id }) => <Input id={id} value={form.name_claim} className="font-mono text-xs" onChange={(e) => set('name_claim', e.target.value)} />}
              </Field>
            </div>
          </details>

          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={form.is_enabled} onCheckedChange={(c) => set('is_enabled', c)} aria-label="Enabled" />
              Enabled
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={form.show_on_login} onCheckedChange={(c) => set('show_on_login', c)} aria-label="Show on the login page" />
              Show on the login page
            </label>
          </div>

          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {creating ? 'Add provider' : 'Save changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Whether the admin typed their own button label (presets only replace an empty or preset-named one). */
function isCustomName(name: string): boolean {
  const trimmed = name.trim()
  return !!trimmed && !SSO_PRESETS.some((p) => p.label === trimmed)
}
