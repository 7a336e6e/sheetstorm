"use client"

/**
 * Before/after table for an audit row's `details.changes`
 * (backend `utils/audit_diff.py`):
 *
 *   {field: {from, to}}        value change          → before | after
 *   {field: {added, removed}}  list of scalars       → removed chips | added chips
 *   {field: {changed: true}}   sensitive (redacted)  → "changed (redacted)" badge
 *   `_truncated: true`         diff hit the key cap  → footnote
 *
 * Nested settings arrive flattened with dotted keys
 * (`settings.ai_tlp_policy.red`); the path is shown as segments.
 */
import * as React from 'react'
import { EyeOff, Minus, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

export type DiffRow =
  | { field: string; path: string[]; kind: 'value'; from: unknown; to: unknown }
  | { field: string; path: string[]; kind: 'list'; added: unknown[]; removed: unknown[] }
  | { field: string; path: string[]; kind: 'redacted' }

export interface NormalizedDiff {
  rows: DiffRow[]
  truncated: boolean
}

const TRUNCATED_KEY = '_truncated'

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

/** Parse `details.changes` defensively (it is user-influenced JSON). */
export function normalizeChanges(changes: unknown): NormalizedDiff {
  if (!isRecord(changes)) return { rows: [], truncated: false }
  const rows: DiffRow[] = []
  let truncated = false
  for (const [field, entry] of Object.entries(changes)) {
    if (field === TRUNCATED_KEY) {
      truncated = entry === true
      continue
    }
    const path = field.split('.').filter(Boolean)
    if (!isRecord(entry)) {
      // Unknown shape: show it as the new value rather than dropping it.
      rows.push({ field, path, kind: 'value', from: undefined, to: entry })
      continue
    }
    if (entry.changed === true && !('from' in entry) && !('to' in entry)) {
      rows.push({ field, path, kind: 'redacted' })
    } else if (Array.isArray(entry.added) || Array.isArray(entry.removed)) {
      rows.push({
        field,
        path,
        kind: 'list',
        added: Array.isArray(entry.added) ? entry.added : [],
        removed: Array.isArray(entry.removed) ? entry.removed : [],
      })
    } else {
      rows.push({ field, path, kind: 'value', from: entry.from, to: entry.to })
    }
  }
  return { rows, truncated }
}

/** Whether `details` carries a non-empty `changes` diff. */
export function hasChanges(details: unknown): boolean {
  return isRecord(details) && normalizeChanges(details.changes).rows.length > 0
}

/** Display text of one diff value. */
export function formatDiffValue(v: unknown): string {
  if (v === undefined || v === null) return '—'
  if (typeof v === 'string') return v === '' ? '""' : v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function FieldPath({ path, field }: { path: string[]; field: string }) {
  if (path.length <= 1) return <span className="font-mono text-xs text-foreground">{field}</span>
  return (
    <span className="font-mono text-xs" title={field}>
      {path.map((seg, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span className="px-0.5 text-muted-foreground/60">›</span>}
          <span className={i === path.length - 1 ? 'text-foreground' : 'text-muted-foreground'}>{seg}</span>
        </React.Fragment>
      ))}
    </span>
  )
}

function Value({ value, tone }: { value: unknown; tone: 'from' | 'to' }) {
  const empty = value === undefined || value === null
  return (
    <span
      className={cn(
        'break-all font-mono text-xs',
        empty ? 'text-muted-foreground' : tone === 'from' ? 'text-red-300/90' : 'text-emerald-300'
      )}
    >
      {formatDiffValue(value)}
    </span>
  )
}

function Chips({ items, kind }: { items: unknown[]; kind: 'added' | 'removed' }) {
  if (items.length === 0) return <span className="text-xs text-muted-foreground">—</span>
  const Icon = kind === 'added' ? Plus : Minus
  return (
    <ul className="flex flex-wrap gap-1" aria-label={kind}>
      {items.map((item, i) => (
        <li
          key={`${formatDiffValue(item)}-${i}`}
          className={cn(
            'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px]',
            kind === 'added'
              ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
              : 'border-red-500/25 bg-red-500/10 text-red-300'
          )}
        >
          <Icon className="h-3 w-3" aria-hidden />
          {formatDiffValue(item)}
        </li>
      ))}
    </ul>
  )
}

export function AuditDiffViewer({ changes, className }: { changes: unknown; className?: string }) {
  const { rows, truncated } = React.useMemo(() => normalizeChanges(changes), [changes])

  if (rows.length === 0) {
    return <p className={cn('text-xs text-muted-foreground', className)}>No field changes recorded.</p>
  }

  return (
    <div className={cn('overflow-hidden rounded-md border border-white/10', className)}>
      <table className="w-full text-left text-sm" aria-label="Changes">
        <thead className="border-b border-white/10 bg-slate-900/60">
          <tr>
            <th scope="col" className="w-1/4 px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Field
            </th>
            <th scope="col" className="px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Before
            </th>
            <th scope="col" className="px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              After
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field} className="border-b border-white/5 align-top last:border-0" data-field={row.field}>
              <th scope="row" className="px-3 py-2 font-normal">
                <FieldPath path={row.path} field={row.field} />
              </th>
              {row.kind === 'redacted' ? (
                <td colSpan={2} className="px-3 py-2">
                  <span className="inline-flex items-center gap-1 rounded border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300">
                    <EyeOff className="h-3 w-3" aria-hidden />
                    changed (redacted)
                  </span>
                </td>
              ) : row.kind === 'list' ? (
                <>
                  <td className="px-3 py-2">
                    <Chips items={row.removed} kind="removed" />
                  </td>
                  <td className="px-3 py-2">
                    <Chips items={row.added} kind="added" />
                  </td>
                </>
              ) : (
                <>
                  <td className="px-3 py-2">
                    <Value value={row.from} tone="from" />
                  </td>
                  <td className="px-3 py-2">
                    <Value value={row.to} tone="to" />
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="border-t border-white/10 px-3 py-2 text-xs text-muted-foreground">
          The diff was truncated: only the first 100 changed fields were recorded.
        </p>
      )}
    </div>
  )
}
