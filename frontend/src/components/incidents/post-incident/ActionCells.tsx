"use client"

/** Cells shared by the two improvement-action tables (incident tab, org page). */
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Timestamp } from '@/components/ui/timestamp'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { postIncident, IMPROVEMENT_ACTIONS_ENDPOINT, incidentActionsEndpoint } from '@/lib/endpoints/post-incident'
import { isOverdue, labelOf, PRIORITY_OPTIONS, STATUS_OPTIONS } from '@/lib/post-incident'
import type { ActionStatus, ImprovementAction } from '@/types'

export function PriorityBadge({ priority }: { priority: ImprovementAction['priority'] }) {
  return <Badge variant={priority}>{labelOf(PRIORITY_OPTIONS, priority)}</Badge>
}

export function DueCell({ action }: { action: Pick<ImprovementAction, 'due_date' | 'status'> }) {
  if (!action.due_date) return <span className="text-muted-foreground">No due date</span>
  const overdue = isOverdue(action)
  return (
    <span className={overdue ? 'text-red-400' : undefined}>
      <Timestamp value={action.due_date} seconds={false} />
      {overdue && <span className="ml-1 text-xs font-medium">overdue</span>}
    </span>
  )
}

/**
 * The status as a select when `canChange`, else a badge. Saves immediately
 * with If-Match; a stale row opens the conflict dialog.
 */
export function ActionStatusSelect({
  action,
  canChange,
  onChanged,
}: {
  action: ImprovementAction
  canChange: boolean
  onChanged?: () => void
}) {
  const [saving, setSaving] = useState(false)
  if (!canChange) return <Badge variant="outline">{labelOf(STATUS_OPTIONS, action.status)}</Badge>

  const change = async (next: string) => {
    if (next === action.status) return
    setSaving(true)
    try {
      await postIncident.updateAction(action.id, { status: next as ActionStatus }, action.version)
      if (action.incident_id) invalidate(incidentActionsEndpoint(action.incident_id))
      invalidate(IMPROVEMENT_ACTIONS_ENDPOINT)
      onChanged?.()
    } catch (err) {
      notifyError(err, 'change the status')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Select value={action.status} onValueChange={(v) => void change(v)} disabled={saving}>
      <SelectTrigger aria-label={`Status of ${action.title}`} className="h-8 w-[140px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {STATUS_OPTIONS.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Short control label: `NIST CSF 2.0 RS.MA-01`. */
export function controlText(action: Pick<ImprovementAction, 'control_framework' | 'control_ref'>): string {
  if (!action.control_framework) return ''
  const names: Record<string, string> = {
    nist_csf: 'NIST CSF',
    d3fend: 'D3FEND',
    cis: 'CIS',
    iso27001: 'ISO 27001',
    other: 'Other',
  }
  return `${names[action.control_framework] ?? action.control_framework} ${action.control_ref ?? ''}`.trim()
}
