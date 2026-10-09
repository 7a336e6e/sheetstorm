"use client"

import { useState } from 'react'
import { Edit2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UserPicker } from '@/components/ui/entity-picker'
import { usePermission } from '@/components/auth/permission-gate'
import { assignmentsEndpoint } from '@/components/incidents/AssignmentsPanel'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'

// ─── Lead Responder Selector (inline in Details card) ────────────────────

interface LeadResponderSelectorProps {
  incidentId: string
  /** Incident version for If-Match (optimistic concurrency). */
  incidentVersion?: number
  currentLead?: { id: string; name: string } | null
  onUpdated: () => void
}

export function LeadResponderSelector({
  incidentId,
  incidentVersion,
  currentLead,
  onUpdated,
}: LeadResponderSelectorProps) {
  const canEdit = usePermission('incidents:update')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleChange = async (userId: string | null) => {
    if (!userId || userId === currentLead?.id) return
    setSaving(true)
    try {
      await api.put(`/incidents/${incidentId}`, { lead_responder_id: userId }, { ifMatch: incidentVersion })
      // The server syncs the "Lead Responder" assignment as well.
      invalidate(assignmentsEndpoint(incidentId))
      onUpdated()
      setEditing(false)
    } catch (err) {
      notifyError(err, 'change the lead responder')
    } finally {
      setSaving(false)
    }
  }

  if (editing && canEdit) {
    return (
      <div className="space-y-2">
        <UserPicker
          value={currentLead?.id ?? null}
          valueLabel={currentLead?.name}
          onChange={(id) => void handleChange(id)}
          ariaLabel="Lead responder"
          placeholder={saving ? 'Saving…' : 'Search users…'}
          disabled={saving}
          clearable={false}
        />
        <Button variant="ghost" size="sm" className="text-xs h-6" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
    )
  }

  const avatar = (
    <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-xs font-medium">
      {currentLead?.name?.charAt(0) || '?'}
    </div>
  )

  if (!canEdit) {
    return (
      <div className="flex items-center gap-2">
        {avatar}
        <span className="font-medium text-foreground">{currentLead?.name || 'Unassigned'}</span>
      </div>
    )
  }

  return (
    <button
      type="button"
      className="flex items-center gap-2 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={() => setEditing(true)}
      title="Change lead responder"
      aria-label={`Lead responder: ${currentLead?.name || 'Unassigned'}. Change`}
    >
      {avatar}
      <span className="font-medium text-foreground">{currentLead?.name || 'Unassigned'}</span>
      <Edit2 className="h-3 w-3 text-muted-foreground" />
    </button>
  )
}
