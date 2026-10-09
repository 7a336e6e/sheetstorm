"use client"

/**
 * Audit log filter controls, bound to the activity page's
 * `usePaginatedQuery` (so every filter lives in the URL as `audit.f.<name>`).
 * Free-text fields commit on Enter / blur, not per keystroke.
 */
import * as React from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { FilterSelect } from '@/components/ui/data-table'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { IncidentPicker, UserPicker } from '@/components/ui/entity-picker'
import { usePermission } from '@/components/auth/permission-gate'
import type { ListState } from '@/hooks/use-paginated-query'
import { cn } from '@/lib/utils'
import type { AuditFacets } from '@/types'
import {
  EVENT_TYPES,
  STATUS_OPTIONS,
  countActiveFilters,
  parseEventTypes,
  toggleEventType,
} from './audit-filters'

export interface AuditFilterControls {
  state: ListState
  setFilter(k: string, v?: string): void
  resetFilters(): void
}

/** Text input that reports its value on Enter or blur (Escape reverts). */
export function CommitInput({
  value,
  onCommit,
  ...rest
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> & {
  value: string | undefined
  onCommit(v: string | undefined): void
}) {
  const [draft, setDraft] = React.useState(value ?? '')
  const [synced, setSynced] = React.useState(value)
  if (synced !== value) {
    setSynced(value)
    setDraft(value ?? '')
  }
  const commit = () => {
    const next = draft.trim() || undefined
    if (next !== (value || undefined)) onCommit(next)
  }
  return (
    <Input
      {...rest}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          commit()
        } else if (e.key === 'Escape') {
          setDraft(value ?? '')
        }
      }}
    />
  )
}

function Field({ label, htmlFor, children, className }: { label: string; htmlFor?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  )
}

export function AuditFilterBar({
  query,
  facets,
}: {
  query: AuditFilterControls
  facets?: AuditFacets | null
}) {
  const { state, setFilter } = query
  const f = state.filters
  const canPickUsers = usePermission('users:read')
  const selectedTypes = parseEventTypes(f.event_type)
  const active = countActiveFilters(state)
  const ids = {
    action: React.useId(),
    actionList: React.useId(),
    resourceId: React.useId(),
    ip: React.useId(),
    email: React.useId(),
    start: React.useId(),
    end: React.useId(),
    changes: React.useId(),
  }

  return (
    <div className="space-y-4" data-testid="audit-filter-bar">
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Event types">
        {EVENT_TYPES.map((t) => {
          const on = selectedTypes.includes(t.value)
          return (
            <button
              key={t.value}
              type="button"
              aria-pressed={on}
              onClick={() => setFilter('event_type', toggleEventType(f.event_type, t.value))}
              className={cn(
                'rounded-md border px-2.5 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                on
                  ? 'border-primary/40 bg-primary/15 text-foreground'
                  : 'border-white/10 bg-slate-900/40 text-muted-foreground hover:text-foreground'
              )}
            >
              {t.label}
            </button>
          )
        })}
        <div className="ml-auto flex items-center gap-2">
          <Switch
            id={ids.changes}
            checked={f.has_changes === 'true'}
            onCheckedChange={(v) => setFilter('has_changes', v ? 'true' : undefined)}
          />
          <Label htmlFor={ids.changes} className="text-xs">
            Admin changes only
          </Label>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="From" htmlFor={ids.start}>
          <DateTimeInput
            id={ids.start}
            value={f.start_date ?? null}
            onChange={(iso) => setFilter('start_date', iso ?? undefined)}
            className="h-9"
          />
        </Field>
        <Field label="To" htmlFor={ids.end}>
          <DateTimeInput
            id={ids.end}
            value={f.end_date ?? null}
            onChange={(iso) => setFilter('end_date', iso ?? undefined)}
            className="h-9"
          />
        </Field>
        <Field label="Action contains" htmlFor={ids.action}>
          <CommitInput
            id={ids.action}
            list={ids.actionList}
            value={f.action_contains}
            onCommit={(v) => setFilter('action_contains', v)}
            placeholder="e.g. update_role"
            className="h-9"
            maxLength={100}
          />
          <datalist id={ids.actionList}>
            {(facets?.actions ?? []).map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>
        </Field>
        <Field label="Status">
          <FilterSelect
            label="Status"
            allLabel="Any status"
            value={f.status}
            onChange={(v) => setFilter('status', v)}
            options={STATUS_OPTIONS}
            className="w-full"
          />
        </Field>
        <Field label="Resource type">
          <FilterSelect
            label="Resource type"
            allLabel="Any resource"
            value={f.resource_type}
            onChange={(v) => setFilter('resource_type', v)}
            options={(facets?.resource_types ?? []).map((r) => ({ value: r, label: r.replace(/_/g, ' ') }))}
            className="w-full"
          />
        </Field>
        <Field label="Resource ID" htmlFor={ids.resourceId}>
          <CommitInput
            id={ids.resourceId}
            value={f.resource_id}
            onCommit={(v) => setFilter('resource_id', v)}
            placeholder="UUID"
            className="h-9 font-mono text-xs"
            spellCheck={false}
          />
        </Field>
        <Field label="IP / CIDR" htmlFor={ids.ip}>
          <CommitInput
            id={ids.ip}
            value={f.ip}
            onCommit={(v) => setFilter('ip', v)}
            placeholder="10.0.0.0/8"
            className="h-9 font-mono text-xs"
            spellCheck={false}
          />
        </Field>
        <Field label="Incident">
          <IncidentPicker
            ariaLabel="Incident"
            value={f.incident_id ?? null}
            onChange={(id) => setFilter('incident_id', id ?? undefined)}
          />
        </Field>
        {canPickUsers && (
          <Field label="User">
            <UserPicker
              ariaLabel="User"
              value={f.user_id ?? null}
              params={{ is_active: undefined }}
              onChange={(id) => setFilter('user_id', id ?? undefined)}
            />
          </Field>
        )}
        <Field label="User email (incl. deleted users)" htmlFor={ids.email}>
          <CommitInput
            id={ids.email}
            type="email"
            value={f.user_email}
            onCommit={(v) => setFilter('user_email', v)}
            placeholder="name@example.com"
            className="h-9"
          />
        </Field>
      </div>

      {active > 0 && (
        <div className="flex items-center justify-end">
          <Button variant="ghost" size="sm" onClick={query.resetFilters}>
            <X className="h-3.5 w-3.5" />
            Clear all filters
          </Button>
        </div>
      )}
    </div>
  )
}
