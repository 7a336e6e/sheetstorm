"use client"

import { useEffect, useState } from 'react'
import { Edit2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import type { User as UserType } from '@/types'

// ─── Lead Responder Selector (inline in Details card) ────────────────────

interface LeadResponderSelectorProps {
  incidentId: string
  currentLead?: { id: string; name: string } | null
  onUpdated: () => void
}

export function LeadResponderSelector({
  incidentId,
  currentLead,
  onUpdated,
}: LeadResponderSelectorProps) {
  const { hasPermission } = useAuthStore()
  const canEdit = hasPermission('incidents:update')
  const [editing, setEditing] = useState(false)
  const [users, setUsers] = useState<UserType[]>([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (editing && users.length === 0) {
      api.get<{ items: UserType[] }>('/users?per_page=200').then((data) => setUsers(data.items)).catch(() => {})
    }
  }, [editing, users.length])

  const handleChange = async (userId: string) => {
    setSaving(true)
    try {
      await api.put(`/incidents/${incidentId}`, { lead_responder_id: userId })
      onUpdated()
      setEditing(false)
    } catch {
      // handled by api client
    } finally {
      setSaving(false)
    }
  }

  if (editing && canEdit) {
    return (
      <div className="space-y-2">
        <Select onValueChange={handleChange} disabled={saving}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue placeholder={saving ? 'Saving...' : 'Select lead responder'} />
          </SelectTrigger>
          <SelectContent>
            {users.map((u) => (
              <SelectItem key={u.id} value={u.id}>
                {u.name} <span className="text-muted-foreground ml-1 text-xs">{u.email}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" className="text-xs h-6" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
    )
  }

  return (
    <div
      className={`flex items-center gap-2 ${canEdit ? 'cursor-pointer group' : ''}`}
      onClick={() => canEdit && setEditing(true)}
      title={canEdit ? 'Click to change lead responder' : undefined}
    >
      <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-xs font-medium">
        {currentLead?.name?.charAt(0) || '?'}
      </div>
      <span className="font-medium text-foreground">{currentLead?.name || 'Unassigned'}</span>
      {canEdit && (
        <Edit2 className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      )}
    </div>
  )
}
