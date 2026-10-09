'use client'

/**
 * Security tab in Settings (organizations:manage): the organization's
 * security policy (`/organization/security-policy`).
 *
 * - Password: length, character classes, reuse history, maximum age.
 * - Lockout: failed attempts and lock duration.
 * - MFA: not required / admins (privileged roles) / everyone, grace period,
 *   adoption counts.
 * - Sessions: token lifetimes (apply to newly issued tokens) and, with
 *   users:manage, any user's active sessions.
 * - Provisioning: allowed email domains, default role (never a privileged
 *   role), self-registration (platform organization only).
 *
 * Saving sends the loaded `version`; a concurrent change answers 409 and the
 * tab reloads. Every change is audited with before/after values. Rate limits
 * are configured separately.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, KeyRound, Loader2, Lock, ShieldCheck, Timer, UserPlus, X } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { RateLimitingSection } from './RateLimitingSection'
import { api, isApiError } from '@/lib/api'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { rbac } from '@/lib/endpoints/rbac'
import { securityPolicy as policyApi } from '@/lib/endpoints/security'
import { clearPasswordRulesCache } from '@/hooks/use-password-policy'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import { useAuthStore } from '@/lib/store'
import { SessionsCard } from './SessionsCard'
import type {
  MfaScope,
  Role,
  SecurityPolicy,
  SecurityPolicyBound,
  SecurityPolicyResponse,
  SecurityPolicyUpdate,
  User,
} from '@/types'

export const MFA_SCOPE_LABELS: Record<MfaScope, string> = {
  none: 'Not required',
  privileged: 'Admins (privileged roles)',
  all: 'Everyone',
}

const DOMAIN_RE = /^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$/

/** Normalise a typed domain the way the server does (lowercase, no leading @). */
export function normalizeDomain(raw: string): string | null {
  const d = raw.trim().toLowerCase().replace(/^@/, '')
  return DOMAIN_RE.test(d) ? d : null
}

/** The PUT body: every section, without the server-managed `enforced_since`. */
export function policyUpdate(form: SecurityPolicy): SecurityPolicyUpdate {
  return {
    password: { ...form.password },
    lockout: { ...form.lockout },
    mfa: { required_for: form.mfa.required_for, grace_days: form.mfa.grace_days },
    session: { ...form.session },
    provisioning: { ...form.provisioning, allowed_email_domains: [...form.provisioning.allowed_email_domains] },
  }
}

function clonePolicy(p: SecurityPolicy): SecurityPolicy {
  return JSON.parse(JSON.stringify(p)) as SecurityPolicy
}

function fieldErrorsFrom(err: unknown): Record<string, string> {
  if (!isApiError(err) || err.code !== 'validation_error') return {}
  const fields = err.details?.fields
  if (!fields || typeof fields !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(fields as Record<string, unknown>)) {
    if (typeof v === 'string') out[k] = v
  }
  return out
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="text-xs text-destructive">{message}</p>
}

function NumberField({
  id,
  label,
  value,
  onChange,
  bound,
  error,
  hint,
}: {
  id: string
  label: string
  value: number
  onChange: (v: number) => void
  bound?: SecurityPolicyBound
  error?: string
  hint?: string
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        value={Number.isFinite(value) ? String(value) : ''}
        min={bound?.off ?? bound?.min}
        max={bound?.max}
        onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))}
        aria-invalid={!!error}
        className="max-w-[10rem]"
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      <FieldError message={error} />
    </div>
  )
}

function SwitchField({
  id,
  label,
  checked,
  onChange,
  disabled,
}: {
  id: string
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="flex items-center gap-3">
      <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  )
}

function range(bound?: SecurityPolicyBound): string | undefined {
  if (!bound || bound.min === undefined || bound.max === undefined) return undefined
  return bound.off !== undefined ? `${bound.off} = off, or ${bound.min}–${bound.max}` : `${bound.min}–${bound.max}`
}

/** Any user's sessions (users:manage): pick a user, see and revoke their sessions. */
function OrgSessionsCard() {
  const [users, setUsers] = useState<User[] | null>(null)
  const [selected, setSelected] = useState<string>('')

  useEffect(() => {
    let active = true
    api
      .get<{ items: User[] }>('/users?per_page=200&sort=name')
      .then((page) => {
        if (active) setUsers(page.items)
      })
      .catch(() => {
        if (active) setUsers([])
      })
    return () => {
      active = false
    }
  }, [])

  const chosen = users?.find((u) => u.id === selected)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Timer className="h-5 w-5" />
          User sessions
        </CardTitle>
        <CardDescription>Review and revoke the active sign-ins of anyone in your organization.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-1.5 max-w-sm">
          <Label htmlFor="sessions-user">User</Label>
          <Select value={selected} onValueChange={setSelected} disabled={!users || users.length === 0}>
            <SelectTrigger id="sessions-user">
              <SelectValue placeholder={users === null ? 'Loading users…' : 'Choose a user'} />
            </SelectTrigger>
            <SelectContent>
              {(users ?? []).map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.name} ({u.email})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {chosen && <SessionsCard key={chosen.id} userId={chosen.id} userLabel={chosen.name} />}
      </CardContent>
    </Card>
  )
}

export function SecurityTab() {
  const me = useAuthStore((s) => s.user)
  const canManageUsers = usePermission('users:manage')
  const { lookup } = usePermissionCatalog()
  const [data, setData] = useState<SecurityPolicyResponse | null>(null)
  const [form, setForm] = useState<SecurityPolicy | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [domainInput, setDomainInput] = useState('')
  const [domainError, setDomainError] = useState<string | null>(null)
  const [roles, setRoles] = useState<Role[] | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const res = await policyApi.get()
      setData(res)
      setForm(clonePolicy(res.policy))
      setFieldErrors({})
    } catch (err) {
      setLoadError(err)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    let active = true
    rbac
      .listRoles()
      .then((res) => {
        if (active) setRoles(res.items)
      })
      .catch(() => {
        if (active) setRoles([])
      })
    return () => {
      active = false
    }
  }, [])

  // Only non-privileged roles can be the default role (the server enforces it).
  const roleOptions = useMemo(() => {
    const names = (roles ?? [])
      .filter((r) => !r.permissions.some((p) => lookup(p)?.privileged))
      .map((r) => r.name)
    const current = form?.provisioning.default_role
    return current && !names.includes(current) ? [current, ...names] : names
  }, [roles, lookup, form?.provisioning.default_role])

  const dirty = useMemo(
    () => !!data && !!form && JSON.stringify(policyUpdate(form)) !== JSON.stringify(policyUpdate(data.policy)),
    [data, form]
  )

  if (loadError) {
    const { title, description } = describeError(loadError)
    return (
      <Card>
        <CardContent className="flex flex-col items-start gap-3 p-6">
          <p className="text-sm font-medium">{title}</p>
          <p className="text-sm text-muted-foreground">{description}</p>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }
  if (!data || !form) {
    return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="Loading security policy" />
  }

  const b = data.bounds
  const err = (key: string) => fieldErrors[key]

  function set<S extends keyof SecurityPolicy, K extends keyof SecurityPolicy[S]>(
    section: S,
    key: K,
    value: SecurityPolicy[S][K]
  ) {
    setForm((f) => (f ? { ...f, [section]: { ...f[section], [key]: value } } : f))
  }

  const addDomain = () => {
    const d = normalizeDomain(domainInput)
    if (!d) {
      setDomainError('Enter a domain such as example.com')
      return
    }
    const list = form.provisioning.allowed_email_domains
    if (!list.includes(d)) set('provisioning', 'allowed_email_domains', [...list, d])
    setDomainInput('')
    setDomainError(null)
  }

  const save = async () => {
    setSaving(true)
    setFieldErrors({})
    try {
      const res = await policyApi.update(policyUpdate(form), data.version)
      setData(res)
      setForm(clonePolicy(res.policy))
      clearPasswordRulesCache()
      notifySuccess('Security policy saved')
    } catch (e) {
      if (isApiError(e) && e.code === 'conflict') {
        notifyError(e, 'save the security policy (it was changed by someone else; reloaded)')
        await load()
      } else {
        const fields = fieldErrorsFrom(e)
        setFieldErrors(fields)
        notifyError(e, 'save the security policy')
      }
    } finally {
      setSaving(false)
    }
  }

  const stats = data.stats
  const mfaPct = stats.users_total ? Math.round((stats.users_mfa / stats.users_total) * 100) : 0
  const selfAtRisk = form.mfa.required_for !== 'none' && !me?.mfa_enabled

  return (
    <div className="space-y-6 max-w-4xl">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-5 w-5" />
            Password
          </CardTitle>
          <CardDescription>
            Applies to every new password (sign-up, change, admin create and reset, invites). At most 72 bytes.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <NumberField
            id="pw-min-length"
            label="Minimum length"
            value={form.password.min_length}
            onChange={(v) => set('password', 'min_length', v)}
            bound={b['password.min_length']}
            hint={range(b['password.min_length'])}
            error={err('password.min_length')}
          />
          <div className="grid gap-3 content-start pt-1">
            <SwitchField id="pw-upper" label="Require an uppercase letter" checked={form.password.require_upper}
              onChange={(v) => set('password', 'require_upper', v)} />
            <SwitchField id="pw-lower" label="Require a lowercase letter" checked={form.password.require_lower}
              onChange={(v) => set('password', 'require_lower', v)} />
            <SwitchField id="pw-digit" label="Require a number" checked={form.password.require_digit}
              onChange={(v) => set('password', 'require_digit', v)} />
            <SwitchField id="pw-symbol" label="Require a symbol" checked={form.password.require_symbol}
              onChange={(v) => set('password', 'require_symbol', v)} />
          </div>
          <NumberField
            id="pw-history"
            label="Block reuse of the last N passwords"
            value={form.password.history_count}
            onChange={(v) => set('password', 'history_count', v)}
            bound={b['password.history_count']}
            hint={`${range(b['password.history_count']) ?? ''} (0 = off; values above 10 slow down password changes)`}
            error={err('password.history_count')}
          />
          <NumberField
            id="pw-max-age"
            label="Maximum password age (days)"
            value={form.password.max_age_days}
            onChange={(v) => set('password', 'max_age_days', v)}
            bound={b['password.max_age_days']}
            hint={`${range(b['password.max_age_days']) ?? ''}. Expired passwords must be changed at next sign-in.`}
            error={err('password.max_age_days')}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Lock className="h-5 w-5" />
            Lockout
          </CardTitle>
          <CardDescription>Failed sign-in attempts (password or MFA code) before an account is locked.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <NumberField
            id="lockout-threshold"
            label="Failed attempts"
            value={form.lockout.threshold}
            onChange={(v) => set('lockout', 'threshold', v)}
            bound={b['lockout.threshold']}
            hint={range(b['lockout.threshold'])}
            error={err('lockout.threshold')}
          />
          <NumberField
            id="lockout-duration"
            label="Lock duration (minutes)"
            value={form.lockout.duration_minutes}
            onChange={(v) => set('lockout', 'duration_minutes', v)}
            bound={b['lockout.duration_minutes']}
            hint={range(b['lockout.duration_minutes'])}
            error={err('lockout.duration_minutes')}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-5 w-5" />
            Multi-factor authentication
          </CardTitle>
          <CardDescription>
            After the grace period, users who must use MFA can only enroll until they do. API keys are not affected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="mfa-scope">Required for</Label>
              <Select
                value={form.mfa.required_for}
                onValueChange={(v) => set('mfa', 'required_for', v as MfaScope)}
              >
                <SelectTrigger id="mfa-scope" aria-invalid={!!err('mfa.required_for')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(MFA_SCOPE_LABELS) as MfaScope[]).map((scope) => (
                    <SelectItem key={scope} value={scope}>
                      {MFA_SCOPE_LABELS[scope]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError message={err('mfa.required_for')} />
            </div>
            <NumberField
              id="mfa-grace"
              label="Grace period (days)"
              value={form.mfa.grace_days}
              onChange={(v) => set('mfa', 'grace_days', v)}
              bound={b['mfa.grace_days']}
              hint={`${range(b['mfa.grace_days']) ?? ''}. Counted from when the requirement started or the account was created.`}
              error={err('mfa.grace_days')}
            />
          </div>
          {data.policy.mfa.enforced_since && (
            <p className="text-xs text-muted-foreground">
              Required since <Timestamp value={data.policy.mfa.enforced_since} seconds={false} />.
            </p>
          )}
          <div className="space-y-1.5" aria-label="MFA adoption">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                MFA adoption: {stats.users_mfa} of {stats.users_total} users ({mfaPct}%), {stats.privileged_mfa} of{' '}
                {stats.privileged_total} admins
              </span>
              {stats.users_without_mfa_past_grace > 0 && (
                <Badge variant="outline" className="text-[10px]">
                  {stats.users_without_mfa_past_grace} past the grace period
                </Badge>
              )}
            </div>
            <div className="h-1.5 w-full rounded bg-white/10">
              <div className="h-1.5 rounded bg-cyan-500" style={{ width: `${mfaPct}%` }} />
            </div>
          </div>
          {selfAtRisk && (
            <p role="alert" className="flex items-center gap-2 text-xs text-amber-400">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              You have not set up MFA yet. Enroll from your profile before the grace period ends.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Timer className="h-5 w-5" />
            Sessions
          </CardTitle>
          <CardDescription>Token lifetimes apply to newly issued tokens; current sessions are not cut short.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <NumberField
            id="session-access"
            label="Access token lifetime (minutes)"
            value={form.session.access_token_minutes}
            onChange={(v) => set('session', 'access_token_minutes', v)}
            bound={b['session.access_token_minutes']}
            hint={range(b['session.access_token_minutes'])}
            error={err('session.access_token_minutes')}
          />
          <NumberField
            id="session-refresh"
            label="Session lifetime without activity (days)"
            value={form.session.refresh_token_days}
            onChange={(v) => set('session', 'refresh_token_days', v)}
            bound={b['session.refresh_token_days']}
            hint={range(b['session.refresh_token_days'])}
            error={err('session.refresh_token_days')}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserPlus className="h-5 w-5" />
            Account provisioning
          </CardTitle>
          <CardDescription>
            New accounts (admin-created, invited{data.is_platform_org ? ', self-registered or first SSO sign-in' : ''}).
            Existing accounts are not affected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-1.5">
            <Label htmlFor="domain-input">Allowed email domains</Label>
            <div className="flex max-w-md gap-2">
              <Input
                id="domain-input"
                value={domainInput}
                placeholder="example.com"
                onChange={(e) => setDomainInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addDomain()
                  }
                }}
              />
              <Button type="button" variant="outline" onClick={addDomain} disabled={!domainInput.trim()}>
                Add
              </Button>
            </div>
            {domainError && <FieldError message={domainError} />}
            <div className="flex flex-wrap gap-1.5" aria-label="Allowed domains">
              {form.provisioning.allowed_email_domains.length === 0 ? (
                <p className="text-xs text-muted-foreground">Any domain is allowed.</p>
              ) : (
                form.provisioning.allowed_email_domains.map((d) => (
                  <Badge key={d} variant="outline" className="gap-1">
                    {d}
                    <button
                      type="button"
                      aria-label={`Remove ${d}`}
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() =>
                        set(
                          'provisioning',
                          'allowed_email_domains',
                          form.provisioning.allowed_email_domains.filter((x) => x !== d)
                        )
                      }
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))
              )}
            </div>
            <FieldError message={err('provisioning.allowed_email_domains')} />
          </div>

          <div className="grid gap-1.5 max-w-sm">
            <Label htmlFor="default-role">Default role</Label>
            <Select
              value={form.provisioning.default_role}
              onValueChange={(v) => set('provisioning', 'default_role', v)}
            >
              <SelectTrigger id="default-role" aria-invalid={!!err('provisioning.default_role')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roleOptions.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Given to new accounts without an explicit role. Roles with privileged permissions are not allowed.
            </p>
            <FieldError message={err('provisioning.default_role')} />
          </div>

          {data.is_platform_org && (
            <div className="grid gap-1">
              <SwitchField
                id="registration-enabled"
                label="Allow self-registration"
                checked={form.provisioning.registration_enabled}
                onChange={(v) => set('provisioning', 'registration_enabled', v)}
              />
              <p className="pl-12 text-xs text-muted-foreground">
                Sign-ups and first SSO sign-ins join this organization with the default role.
              </p>
              <FieldError message={err('provisioning.registration_enabled')} />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {data.updated_at ? (
            <>
              Last changed <Timestamp value={data.updated_at} seconds={false} />
              {data.updated_by?.name ? ` by ${data.updated_by.name}` : ''}.
            </>
          ) : (
            'Using the default policy.'
          )}
        </p>
        <div className="flex gap-2">
          <Button variant="outline" disabled={!dirty || saving} onClick={() => setForm(clonePolicy(data.policy))}>
            Discard
          </Button>
          <Button disabled={!dirty || saving} onClick={() => void save()}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </div>
      </div>

      {canManageUsers && <OrgSessionsCard />}

      <RateLimitingSection />
    </div>
  )
}
