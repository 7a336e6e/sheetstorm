"use client"

/**
 * Settings → Security → Rate limiting (W4-RL, owner requirement).
 *
 * Every rate-limited route belongs to a group; platform administrators can
 * change a group's limit, disable a group (it then falls back to the global
 * `api_default` limit) or switch rate limiting off entirely. Changes that
 * weaken protection need an explicit confirmation (409
 * `confirmation_required` → warnings dialog → resend with
 * `confirm_weakening`). Read-only for everyone else, and when the
 * environment locks the settings.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Gauge, Loader2, RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { isApiError } from '@/lib/api'
import { notifyError, notifySuccess } from '@/lib/errors'
import { CATEGORY_LABELS, isValidLimit, overridesFrom, rateLimitsApi } from '@/lib/endpoints/rate-limits'
import type { RateLimitGroup, RateLimitSettings } from '@/types'

type Draft = Record<string, { limit: string; enabled: boolean }>

function draftFrom(groups: RateLimitGroup[]): Draft {
  const out: Draft = {}
  for (const g of groups) out[g.key] = { limit: g.limit, enabled: g.enabled }
  return out
}

const SOURCE_LABEL: Record<string, string> = { code: 'Default', env: 'Environment', override: 'Custom' }

export function RateLimitingSection() {
  const confirm = useConfirm()
  const [data, setData] = useState<RateLimitSettings | null>(null)
  const [draft, setDraft] = useState<Draft>({})
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  const [unavailable, setUnavailable] = useState(false)

  const apply = useCallback((d: RateLimitSettings) => {
    if (!d || !Array.isArray(d.groups)) {
      setUnavailable(true)
      return
    }
    setData(d)
    setDraft(draftFrom(d.groups))
    setEnabled(d.enabled)
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    rateLimitsApi
      .get({ signal: ctrl.signal })
      .then(apply)
      .catch((err) => {
        if ((err as Error)?.name === 'AbortError') return
        setUnavailable(true)
        notifyError(err, 'load the rate limits')
      })
    return () => ctrl.abort()
  }, [apply])

  const editable = !!data?.can_edit
  const invalid = useMemo(
    () => Object.entries(draft).filter(([, d]) => d.enabled && !isValidLimit(d.limit)).map(([k]) => k),
    [draft]
  )
  const dirty = useMemo(() => {
    if (!data) return false
    if (enabled !== data.enabled) return true
    return data.groups.some((g) => draft[g.key]?.limit !== g.limit || draft[g.key]?.enabled !== g.enabled)
  }, [data, draft, enabled])

  if (unavailable) return null
  if (!data) {
    return (
      <Card>
        <CardContent className="flex justify-center p-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  const save = async (confirmWeakening = false) => {
    setSaving(true)
    try {
      const next = await rateLimitsApi.update({
        enabled,
        groups: overridesFrom(data.groups, draft),
        version: data.version,
        ...(confirmWeakening ? { confirm_weakening: true } : {}),
      })
      apply(next)
      notifySuccess('Rate limits saved', `Applied within ${data.cache_ttl_seconds} seconds, no restart needed.`)
    } catch (err) {
      if (!confirmWeakening && isApiError(err) && err.code === 'confirmation_required') {
        const warnings = (err.details?.warnings as string[] | undefined) ?? []
        const ok = await confirm({
          title: 'Weaken rate limiting?',
          description: (
            <div className="space-y-2">
              <p>This change lowers the protection against brute force and abuse:</p>
              <ul className="list-disc space-y-1 pl-5">
                {warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
              <p>The change is recorded in the audit log as a security event.</p>
            </div>
          ),
          confirmLabel: 'Apply anyway',
          variant: 'destructive',
        })
        setSaving(false)
        if (ok) await save(true)
        return
      }
      notifyError(err, 'save the rate limits')
    } finally {
      setSaving(false)
    }
  }

  const reset = async (groups?: string[]) => {
    const ok = await confirm({
      title: groups ? `Reset ${groups[0]}?` : 'Reset all rate limits?',
      description: 'Custom values are removed; environment and built-in defaults apply again.',
      confirmLabel: 'Reset',
    })
    if (!ok) return
    try {
      apply(await rateLimitsApi.reset(groups))
      notifySuccess('Rate limits reset')
    } catch (err) {
      notifyError(err, 'reset the rate limits')
    }
  }

  const categories = Array.from(new Set(data.groups.map((g) => g.category)))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge className="h-4 w-4" /> Rate limiting
        </CardTitle>
        <CardDescription>
          Requests allowed per user, API key or client IP. Format: <code>5 per minute</code>, several limits separated by{' '}
          <code>;</code>. A disabled group falls back to the global default limit.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.hard_disabled && (
          <p role="status" className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
            <AlertTriangle className="h-4 w-4 text-amber-500" /> Rate limiting is disabled by the server configuration (RATELIMIT_ENABLED).
          </p>
        )}
        {data.locked ? (
          <p role="status" className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
            Managed by the environment (RATE_LIMIT_SETTINGS_LOCKED): limits can only be changed through environment variables.
          </p>
        ) : !editable ? (
          <p role="status" className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
            Only platform administrators can change rate limits, because they protect every organization.
          </p>
        ) : null}

        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <p className="text-sm font-medium">Rate limiting enabled</p>
            <p className="text-xs text-muted-foreground">Turning it off removes every limit, including on sign-in.</p>
          </div>
          <Switch
            checked={enabled}
            disabled={!editable}
            onCheckedChange={setEnabled}
            aria-label="Rate limiting enabled"
          />
        </div>

        <div className="overflow-x-auto">
          <Table aria-label="Rate-limit groups">
            <TableHeader>
              <TableRow>
                <TableHead>Group</TableHead>
                <TableHead className="w-56">Limit</TableHead>
                <TableHead className="hidden md:table-cell">Source</TableHead>
                <TableHead className="w-20">On</TableHead>
                {editable && <TableHead className="w-12"><span className="sr-only">Reset</span></TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {categories.map((cat) => [
                <TableRow key={`cat-${cat}`} className="bg-muted/30 hover:bg-muted/30">
                  <TableCell colSpan={editable ? 5 : 4} className="py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {CATEGORY_LABELS[cat] ?? cat}
                  </TableCell>
                </TableRow>,
                ...data.groups
                  .filter((g) => g.category === cat)
                  .map((g) => {
                    const d = draft[g.key] ?? { limit: g.limit, enabled: g.enabled }
                    const bad = invalid.includes(g.key)
                    return (
                      <TableRow key={g.key}>
                        <TableCell>
                          <div className="flex items-center gap-2 font-mono text-xs">
                            {g.key}
                            {g.auth_sensitive && <Badge variant="outline" className="text-[10px]">auth</Badge>}
                          </div>
                          <p className="text-xs text-muted-foreground" title={g.routes.join('\n')}>{g.description}</p>
                        </TableCell>
                        <TableCell>
                          <Input
                            value={d.limit}
                            disabled={!editable || !d.enabled}
                            aria-label={`${g.key} limit`}
                            aria-invalid={bad}
                            placeholder={g.default}
                            className={`h-8 font-mono text-xs ${bad ? 'border-destructive' : ''}`}
                            onChange={(e) => setDraft({ ...draft, [g.key]: { ...d, limit: e.target.value } })}
                          />
                          {g.limit !== g.default && (
                            <p className="mt-0.5 text-[11px] text-muted-foreground">default {g.default}</p>
                          )}
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          <Badge variant="outline" className="text-[10px]">{SOURCE_LABEL[g.source] ?? g.source}</Badge>
                        </TableCell>
                        <TableCell>
                          <Switch
                            checked={d.enabled}
                            disabled={!editable}
                            aria-label={`${g.key} enabled`}
                            onCheckedChange={(v) => setDraft({ ...draft, [g.key]: { ...d, enabled: v } })}
                          />
                        </TableCell>
                        {editable && (
                          <TableCell>
                            {g.source === 'override' && (
                              <Button variant="ghost" size="sm" aria-label={`Reset ${g.key}`} onClick={() => void reset([g.key])}>
                                <RotateCcw className="h-3.5 w-3.5" />
                              </Button>
                            )}
                          </TableCell>
                        )}
                      </TableRow>
                    )
                  }),
              ])}
            </TableBody>
          </Table>
        </div>

        {editable && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            {invalid.length > 0 ? (
              <p className="text-xs text-destructive">Invalid limit for {invalid.join(', ')}.</p>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => void reset()} disabled={saving}>Reset all</Button>
              <Button variant="outline" onClick={() => apply(data)} disabled={!dirty || saving}>Discard</Button>
              <Button onClick={() => void save()} disabled={!dirty || saving || invalid.length > 0}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save rate limits
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
