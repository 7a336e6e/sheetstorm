"use client"

import { useState } from 'react'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { useAllPages } from '@/hooks/use-paginated-query'
import { usePermission } from '@/components/auth/permission-gate'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { UserPicker } from '@/components/ui/entity-picker'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  UserPlus,
  X,
  Users,
  Loader2,
} from 'lucide-react'
import type { User } from '@/types'

interface Assignment {
  id: string
  incident_id: string
  user: User | null
  role: string | null
  assigned_by: string | null
  assigned_at: string | null
}

interface AssignmentsPanelProps {
  incidentId: string
}

const ASSIGNMENT_ROLES = [
  'Lead Responder',
  'Analyst',
  'Forensic Investigator',
  'Communications',
  'Legal',
  'Observer',
]

/** Cache path of the assignments list; invalidate it after lead/status changes. */
export const assignmentsEndpoint = (incidentId: string) => `/incidents/${incidentId}/assignments`

export function AssignmentsPanel({ incidentId }: AssignmentsPanelProps) {
  const canEdit = usePermission('incidents:update')
  const confirm = useConfirm()
  const endpoint = assignmentsEndpoint(incidentId)
  const { items: assignments, isLoading, error, refetch } = useAllPages<Assignment>(endpoint, { live: 'assignment' })

  const [showAddForm, setShowAddForm] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [selectedRole, setSelectedRole] = useState('')
  const [adding, setAdding] = useState(false)
  const [removingId, setRemovingId] = useState<string | null>(null)

  const closeForm = () => {
    setShowAddForm(false)
    setSelectedUserId(null)
    setSelectedRole('')
  }

  const handleAssign = async () => {
    if (!selectedUserId) return
    const role = selectedRole || null
    if (assignments.some((a) => a.user?.id === selectedUserId && (a.role ?? null) === role)) {
      notifyError(new Error('That user is already assigned with this role.'), 'assign the user')
      return
    }
    setAdding(true)
    try {
      await api.post(endpoint, { user_id: selectedUserId, role })
      invalidate(endpoint)
      closeForm()
    } catch (err) {
      notifyError(err, 'assign the user')
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (assignment: Assignment) => {
    const name = assignment.user?.name || 'This user'
    const ok = await confirm({
      title: 'Remove assignment?',
      description: `${name} will be removed from this incident's personnel.`,
      confirmLabel: 'Remove',
      variant: 'destructive',
    })
    if (!ok) return
    setRemovingId(assignment.id)
    try {
      await api.delete(`${endpoint}/${assignment.id}`)
      invalidate(endpoint)
    } catch (err) {
      notifyError(err, 'remove the assignment')
    } finally {
      setRemovingId(null)
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader><CardTitle className="text-lg">Assigned Personnel</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">Assigned Personnel</CardTitle>
        {canEdit && !showAddForm && (
          <Button variant="ghost" size="sm" onClick={() => setShowAddForm(true)}>
            <UserPlus className="h-4 w-4 mr-1" /> Assign
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {error && assignments.length === 0 && (
          <div role="alert" className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
            <span>Couldn&apos;t load assignments.</span>
            <Button variant="ghost" size="sm" onClick={() => void refetch()}>Retry</Button>
          </div>
        )}

        {!error && assignments.length === 0 && !showAddForm && (
          <div className="text-center py-4 text-sm text-muted-foreground">
            <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
            No personnel assigned
          </div>
        )}

        {assignments.map((assignment) => (
          <div
            key={assignment.id}
            className="flex items-center gap-3 p-2 rounded-md hover:bg-muted/50"
          >
            <div className="h-8 w-8 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 flex items-center justify-center text-white text-xs font-medium shrink-0">
              {assignment.user?.name?.charAt(0).toUpperCase() || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{assignment.user?.name || 'Unknown'}</p>
              <p className="text-xs text-muted-foreground truncate">{assignment.user?.email}</p>
            </div>
            {assignment.role && (
              <Badge variant="outline" className="text-xs shrink-0">
                {assignment.role}
              </Badge>
            )}
            {canEdit && (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${assignment.user?.name || 'assignment'}`}
                className="text-muted-foreground hover:text-destructive shrink-0"
                onClick={() => void handleRemove(assignment)}
                disabled={removingId === assignment.id}
              >
                {removingId === assignment.id ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <X className="h-3 w-3" />
                )}
              </Button>
            )}
          </div>
        ))}

        {canEdit && showAddForm && (
          <div className="border border-border rounded-md p-3 space-y-3 bg-muted/30">
            <UserPicker
              value={selectedUserId}
              onChange={(id) => setSelectedUserId(id)}
              ariaLabel="User to assign"
              placeholder="Search users…"
            />
            <Select value={selectedRole} onValueChange={setSelectedRole}>
              <SelectTrigger className="h-8 text-sm" aria-label="Assignment role">
                <SelectValue placeholder="Select role (optional)" />
              </SelectTrigger>
              <SelectContent>
                {ASSIGNMENT_ROLES.map((role) => (
                  <SelectItem key={role} value={role}>{role}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!selectedUserId || adding}
                onClick={() => void handleAssign()}
                className="flex-1"
              >
                {adding ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                Assign
              </Button>
              <Button size="sm" variant="outline" onClick={closeForm}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
