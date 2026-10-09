/**
 * General tab in Settings: organization name, timezone, IOC auto-enrichment
 * and the Data egress card (per-TLP AI policy + third-party enrichment
 * limits). Self-registration lives in the Security tab (security policy).
 *
 * `PUT /organization` validates every key (extra keys are rejected) and
 * merges them over the stored settings; loosening the AI policy is audited
 * and raises a security event server side.
 */

"use client"

import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { TLPBadge } from '@/components/ui/badge'
import { Loader2, Lock, Settings, ShieldAlert } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { PermissionGate } from '@/components/auth/permission-gate'
import { isApiError } from '@/lib/api'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { organization as orgApi } from '@/lib/endpoints/rbac'
import type { AiPolicyMode, AiTlpPolicy, Organization, OrganizationUpdate, TLPLevel } from '@/types'

/** Display order, least to most restricted. */
export const TLP_LEVELS: TLPLevel[] = ['white', 'green', 'amber', 'amber_strict', 'red']

/** Mirror of backend AI_TLP_POLICY_DEFAULTS (the server always returns the effective policy). */
export const AI_TLP_POLICY_DEFAULTS: AiTlpPolicy = {
  white: 'allow',
  green: 'allow',
  amber: 'allow',
  amber_strict: 'local_only',
  red: 'local_only',
}

export const AI_MODE_LABELS: Record<AiPolicyMode, string> = {
  allow: 'Any provider',
  local_only: 'Local providers only',
  block: 'Blocked',
}

const AI_MODE_RANK: Record<AiPolicyMode, number> = { block: 0, local_only: 1, allow: 2 }

const TLP_TEXT: Record<TLPLevel, string> = {
  white: 'TLP:WHITE',
  green: 'TLP:GREEN',
  amber: 'TLP:AMBER',
  amber_strict: 'TLP:AMBER+STRICT',
  red: 'TLP:RED',
}

const TIMEZONES: { value: string; label: string }[] = [
  { value: 'UTC', label: 'UTC' },
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'Europe/London', label: 'London (GMT)' },
  { value: 'Europe/Paris', label: 'Central European (CET)' },
  { value: 'Europe/Helsinki', label: 'Eastern European (EET)' },
  { value: 'Asia/Tokyo', label: 'Japan (JST)' },
  { value: 'Asia/Shanghai', label: 'China (CST)' },
  { value: 'Australia/Sydney', label: 'Sydney (AEDT)' },
]

export interface GeneralForm {
  name: string
  timezone: string
  auto_enrich_iocs: boolean
  enrichment_allow_amber_strict: boolean
  ai_tlp_policy: AiTlpPolicy
}

export function formFromOrganization(org: Organization): GeneralForm {
  return {
    name: org.name,
    timezone: org.settings?.timezone || 'UTC',
    auto_enrich_iocs: org.settings?.auto_enrich_iocs ?? false,
    enrichment_allow_amber_strict: org.settings?.enrichment_allow_amber_strict ?? false,
    ai_tlp_policy: { ...AI_TLP_POLICY_DEFAULTS, ...(org.settings?.ai_tlp_policy ?? {}) },
  }
}

/** The `PUT /organization` body: every writable key. */
export function buildOrganizationUpdate(_org: Organization, form: GeneralForm): OrganizationUpdate {
  return {
    name: form.name.trim(),
    settings: {
      timezone: form.timezone,
      auto_enrich_iocs: form.auto_enrich_iocs,
      enrichment_allow_amber_strict: form.enrichment_allow_amber_strict,
      ai_tlp_policy: { ...form.ai_tlp_policy },
    },
  }
}

/** TLP levels whose AI mode becomes more permissive. */
export function loosenedLevels(before: AiTlpPolicy, after: AiTlpPolicy): TLPLevel[] {
  return TLP_LEVELS.filter((lvl) => AI_MODE_RANK[after[lvl]] > AI_MODE_RANK[before[lvl]])
}

function fieldErrorsFrom(err: unknown): Record<string, string> {
  if (!isApiError(err) || (err.code !== 'validation_error' && err.code !== 'not_applicable')) return {}
  const fields = err.details?.fields
  if (!fields || typeof fields !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(fields as Record<string, unknown>)) {
    if (typeof v === 'string') out[k] = v
  }
  return out
}

function FieldError({ message, id }: { message?: string; id?: string }) {
  if (!message) return null
  return (
    <p id={id} className="text-xs text-red-400" role="alert">
      {message}
    </p>
  )
}

export function GeneralTab() {
  const confirm = useConfirm()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [org, setOrg] = useState<Organization | null>(null)
  const [form, setForm] = useState<GeneralForm | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await orgApi.get()
      setOrg(res)
      setForm(formFromOrganization(res))
    } catch (err) {
      setLoadError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const update = <K extends keyof GeneralForm>(key: K, value: GeneralForm[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f))

  const setAiMode = (level: TLPLevel, mode: AiPolicyMode) =>
    setForm((f) => (f ? { ...f, ai_tlp_policy: { ...f.ai_tlp_policy, [level]: mode } } : f))

  const handleSave = async () => {
    if (!org || !form) return
    const before = formFromOrganization(org)
    const loosened = loosenedLevels(before.ai_tlp_policy, form.ai_tlp_policy)
    const enablesStrictEnrichment = form.enrichment_allow_amber_strict && !before.enrichment_allow_amber_strict
    if (loosened.length > 0 || enablesStrictEnrichment) {
      const lines: string[] = loosened.map(
        (lvl) => `${TLP_TEXT[lvl]}: ${AI_MODE_LABELS[before.ai_tlp_policy[lvl]]} → ${AI_MODE_LABELS[form.ai_tlp_policy[lvl]]}`
      )
      if (enablesStrictEnrichment) lines.push('TLP:AMBER+STRICT indicators may be sent to third-party enrichment providers')
      const ok = await confirm({
        title: 'Loosen data egress policy?',
        description: (
          <span className="block space-y-2">
            <span className="block">More incident data may leave your environment:</span>
            <span className="block font-mono text-xs">
              {lines.map((l) => (
                <span key={l} className="block">{l}</span>
              ))}
            </span>
            <span className="block">The change is audited and raises a security event.</span>
          </span>
        ),
        confirmLabel: 'Save and loosen',
        variant: 'destructive',
      })
      if (!ok) return
    }

    setSaving(true)
    setFieldErrors({})
    try {
      const res = await orgApi.update(buildOrganizationUpdate(org, form))
      setOrg(res)
      setForm(formFromOrganization(res))
      notifySuccess('Settings saved', 'Organization settings updated.')
    } catch (err) {
      setFieldErrors(fieldErrorsFrom(err))
      notifyError(err, 'save the organization settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (loadError || !org || !form) {
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

  const tzOptions = TIMEZONES.some((t) => t.value === form.timezone)
    ? TIMEZONES
    : [{ value: form.timezone, label: form.timezone }, ...TIMEZONES]
  const unmatchedErrors = Object.entries(fieldErrors).filter(
    ([k]) => !['name', 'settings.timezone'].includes(k)
  )

  return (
    <div className="space-y-6 max-w-4xl">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings className="h-5 w-5" />
            Organization
          </CardTitle>
          <CardDescription>Name and timezone of {org.slug}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="org-name">Organization name</Label>
            <Input
              id="org-name"
              value={form.name}
              maxLength={255}
              onChange={(e) => update('name', e.target.value)}
              aria-invalid={!!fieldErrors.name}
            />
            <FieldError message={fieldErrors.name} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="timezone">Timezone</Label>
            <Select value={form.timezone} onValueChange={(v) => update('timezone', v)}>
              <SelectTrigger id="timezone" aria-invalid={!!fieldErrors['settings.timezone']}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {tzOptions.map((tz) => (
                  <SelectItem key={tz.value} value={tz.value}>
                    {tz.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError message={fieldErrors['settings.timezone']} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="h-5 w-5" />
            Data egress
          </CardTitle>
          <CardDescription>
            What incident data may leave your environment, per TLP level of the incident.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-1">
            <div className="flex items-center space-x-3">
              <Switch
                id="auto-enrich"
                checked={form.auto_enrich_iocs}
                onCheckedChange={(c) => update('auto_enrich_iocs', c)}
              />
              <Label htmlFor="auto-enrich">Auto-enrich new indicators</Label>
            </div>
            <p className="pl-12 text-xs text-amber-400">
              Sends indicator values to third-party providers when they are added.
            </p>
          </div>

          <div className="overflow-x-auto rounded-md border border-white/10">
            <table className="w-full text-sm" aria-label="Data egress by TLP level">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th scope="col" className="px-3 py-2 font-medium">Incident TLP</th>
                  <th scope="col" className="px-3 py-2 font-medium">AI processing</th>
                  <th scope="col" className="px-3 py-2 font-medium">Third-party enrichment</th>
                </tr>
              </thead>
              <tbody>
                {TLP_LEVELS.map((level) => (
                  <tr key={level} className="border-b border-white/10 last:border-0">
                    <td className="px-3 py-2">
                      <TLPBadge tlp={level} />
                    </td>
                    <td className="px-3 py-2">
                      <Select
                        value={form.ai_tlp_policy[level]}
                        onValueChange={(v) => setAiMode(level, v as AiPolicyMode)}
                      >
                        <SelectTrigger className="h-8 w-[200px]" aria-label={`AI processing for ${TLP_TEXT[level]}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(Object.keys(AI_MODE_LABELS) as AiPolicyMode[]).map((mode) => (
                            <SelectItem key={mode} value={mode}>
                              {AI_MODE_LABELS[mode]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-3 py-2">
                      {level === 'red' ? (
                        <span
                          className="inline-flex items-center gap-1.5 text-muted-foreground"
                          title="TLP:RED values are never sent to enrichment providers"
                          data-testid="enrichment-red-locked"
                        >
                          <Lock className="h-3.5 w-3.5" aria-hidden />
                          Always blocked
                        </span>
                      ) : level === 'amber_strict' ? (
                        <span className="inline-flex items-center gap-2">
                          <Switch
                            id="enrich-amber-strict"
                            checked={form.enrichment_allow_amber_strict}
                            onCheckedChange={(c) => update('enrichment_allow_amber_strict', c)}
                            aria-label="Allow enrichment of TLP:AMBER+STRICT indicators"
                          />
                          <span className="text-muted-foreground">
                            {form.enrichment_allow_amber_strict ? 'Allowed' : 'Blocked'}
                          </span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">Allowed</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>
              <span className="text-foreground">Local providers only</span>: Ollama or an OpenAI-compatible server
              on a private address listed in OUTBOUND_URL_ALLOWLIST. Cloud providers are refused.
            </li>
            <li>
              <span className="text-foreground">Blocked</span>: AI features are disabled for incidents of that level.
            </li>
            <li>
              A value is never sent for enrichment if it appears in any TLP:RED incident of the organization.
            </li>
          </ul>
        </CardContent>
      </Card>

      {unmatchedErrors.length > 0 && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400" role="alert">
          {unmatchedErrors.map(([k, v]) => (
            <p key={k}>
              <span className="font-mono">{k}</span>: {v}
            </p>
          ))}
        </div>
      )}

      <PermissionGate permission="organizations:manage">
        <Button onClick={() => void handleSave()} disabled={saving || !form.name.trim()}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save changes
        </Button>
      </PermissionGate>
    </div>
  )
}
