"use client"

/**
 * Scope picker for a new API key: the grantable permissions of the key's
 * owner (`GET /api-keys/scopes`), grouped like the permission catalog.
 *
 * - Per-group select-all (indeterminate when partly selected).
 * - Sensitive (dangerous) scopes carry a warning marker; scopes the server
 *   says are not grantable to keys are hidden (`visibleGroups`).
 * - Presets only ever select scopes that are in the list: "Read-only" is
 *   every `*:read`, "MCP analyst" adds create / update of the investigation
 *   data groups.
 *
 * Controlled: `value` is the selected scope keys. Cosmetic; the server
 * validates the scopes against the owner's permissions on create.
 */
import { useMemo } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { visibleGroups } from '@/lib/endpoints/api-keys'
import type { ApiKeyScopeGroup } from '@/types'

/** Investigation-data groups an assistant may write to (preset "MCP analyst"). */
const MCP_WRITE_GROUPS = ['timeline', 'network_iocs', 'host_iocs', 'hosts', 'accounts', 'malware', 'tasks']

export type ScopePreset = 'read-only' | 'mcp-analyst'

export const SCOPE_PRESETS: { id: ScopePreset; label: string; description: string }[] = [
  { id: 'read-only', label: 'Read-only', description: 'Every view (:read) scope' },
  {
    id: 'mcp-analyst',
    label: 'MCP analyst',
    description: 'Read, plus create and edit timeline, IOCs, hosts, accounts, malware and tasks',
  },
]

/** Scope keys a preset selects out of the available groups (never invents keys). */
export function presetScopes(preset: ScopePreset, groups: ApiKeyScopeGroup[]): string[] {
  const keys = groups.flatMap((g) => g.scopes.map((s) => ({ key: s.value, group: g.group })))
  if (preset === 'read-only') return keys.filter((k) => k.key.endsWith(':read')).map((k) => k.key)
  return keys
    .filter(
      (k) =>
        k.key.endsWith(':read') ||
        (MCP_WRITE_GROUPS.includes(k.group) && (k.key.endsWith(':create') || k.key.endsWith(':update')))
    )
    .map((k) => k.key)
}

export function ScopePicker({
  groups,
  value,
  onChange,
  disabled = false,
}: {
  groups: ApiKeyScopeGroup[]
  value: string[]
  onChange: (scopes: string[]) => void
  disabled?: boolean
}) {
  const shown = useMemo(() => visibleGroups(groups), [groups])
  const selected = useMemo(() => new Set(value), [value])
  const sensitiveSelected = useMemo(
    () => shown.flatMap((g) => g.scopes).filter((s) => s.sensitive && selected.has(s.value)).length,
    [shown, selected]
  )

  const setMany = (keys: string[], on: boolean) => {
    const next = new Set(selected)
    keys.forEach((k) => (on ? next.add(k) : next.delete(k)))
    onChange(Array.from(next).sort())
  }

  if (shown.length === 0) {
    return <p className="text-sm text-muted-foreground">No scopes can be granted to this owner.</p>
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Presets</span>
        {SCOPE_PRESETS.map((p) => (
          <Button
            key={p.id}
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            title={p.description}
            onClick={() => onChange(presetScopes(p.id, shown).sort())}
          >
            {p.label}
          </Button>
        ))}
        <Button type="button" variant="ghost" size="sm" disabled={disabled || value.length === 0} onClick={() => onChange([])}>
          Clear
        </Button>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground" aria-live="polite">
          {value.length} selected
        </span>
      </div>

      {sensitiveSelected > 0 && (
        <p role="status" className="flex items-center gap-1.5 text-xs text-amber-500">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
          {sensitiveSelected} sensitive {sensitiveSelected === 1 ? 'scope' : 'scopes'} selected. Anyone holding the key
          can use {sensitiveSelected === 1 ? 'it' : 'them'}.
        </p>
      )}

      <div className="max-h-72 space-y-4 overflow-y-auto rounded-md border border-border p-3" role="group" aria-label="Scopes">
        {shown.map((g) => {
          const keys = g.scopes.map((s) => s.value)
          const count = keys.filter((k) => selected.has(k)).length
          const all = count === keys.length
          return (
            <fieldset key={g.group} className="space-y-1.5" data-group={g.group}>
              <legend className="sr-only">{g.label}</legend>
              <div className="flex items-center gap-2 border-b border-border pb-1">
                <Checkbox
                  id={`scope-group-${g.group}`}
                  aria-label={`Select all ${g.label}`}
                  checked={all ? true : count > 0 ? 'indeterminate' : false}
                  disabled={disabled}
                  onCheckedChange={(v) => setMany(keys, v === true)}
                />
                <span className="text-sm font-medium">{g.label}</span>
                <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                  {count}/{keys.length}
                </span>
              </div>
              <ul className="space-y-1 pl-6">
                {g.scopes.map((s) => (
                  <li key={s.value} className="flex items-start gap-2">
                    <Checkbox
                      id={`scope-${s.value}`}
                      className="mt-0.5"
                      checked={selected.has(s.value)}
                      disabled={disabled}
                      onCheckedChange={(v) => setMany([s.value], v === true)}
                    />
                    <div className="min-w-0 text-sm">
                      <Label htmlFor={`scope-${s.value}`} className="font-normal">
                        {s.label}
                      </Label>
                      <span className="ml-2 font-mono text-xs text-muted-foreground">{s.value}</span>
                      {s.sensitive && (
                        <span className="ml-2 inline-flex items-center gap-1 text-xs text-amber-500">
                          <AlertTriangle className="h-3 w-3" aria-hidden />
                          Sensitive
                        </span>
                      )}
                      {s.description && <p className="text-xs text-muted-foreground">{s.description}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            </fieldset>
          )
        })}
      </div>
    </div>
  )
}
