"use client"

/**
 * Small pieces shared by the incident detail tabs (W1-TBL).
 *
 * Tabs receive `focusRowId` from the page (`?tab=<id>&row=<uuid>`, e.g. from
 * global search) and pass it to `usePaginatedQuery({ focus })`, which lands on
 * the page containing that row. When the server reports `focus_found: false`
 * (deleted, filtered out, or not visible), this notice says so instead of
 * silently showing page 1.
 */
import { Info } from 'lucide-react'

export interface IncidentTabBaseProps {
  incidentId: string
  /** Row to land on and highlight (`?row=`), only set while this tab is active. */
  focusRowId?: string | null
}

export function FocusNotice({
  focusRowId,
  focusFound,
  noun = 'item',
}: {
  focusRowId?: string | null
  focusFound?: boolean
  noun?: string
}) {
  if (!focusRowId || focusFound !== false) return null
  return (
    <div
      role="status"
      className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
    >
      <Info className="h-4 w-4 shrink-0" />
      The linked {noun} was not found. It may have been deleted or hidden by the current filters.
    </div>
  )
}
