"use client"

import { useState, useEffect, useCallback } from 'react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
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
import { Input } from '@/components/ui/input'
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

export function AssignmentsPanel({ incidentId }: AssignmentsPanelProps) {
  const { hasPermission } = useAuthStore()
  const canEdit = hasPermission('incidents:update')

  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [orgUsers, setOrgUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [selectedRole, setSelectedRole] = useState('')
  const [adding, setAdding] = useState(false)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const fetchAssignments = useCallback(async () => {
    try {
      const data = await api.get<{ items: Assignment[] }>(`/incidents/${incidentId}/assignments`)
      setAssignments(data.items)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [incidentId])

  const fetchUsers = useCallback(async () => {
    try {
      const data = await api.get<{ items: User[] }>('/users?per_page=200')
      setOrgUsers(data.items)
    } catch {
      // silently fail
    }
  }, [])

  useEffect(() => {
    fetchAssignments()
  }, [fetchAssignments])

  useEffect(() => {
    if (showAddForm && orgUsers.length === 0) {
      fetchUsers()
    }
  }, [showAddForm, orgUsers.length, fetchUsers])

  const handleAssign = async () => {
    if (!selectedUserId) return
    setAdding(true)
    try {
      await api.post(`/incidents/${incidentId}/assignments`, {
        user_id: selectedUserId,
        role: selectedRole || null,
      })
      await fetchAssignments()
      setSelectedUserId('')
      setSelectedRole('')
      setShowAddForm(false)
    } catch {
      // error handled by api client
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (assignmentId: string) => {
    setRemovingId(assignmentId)
    try {
      await api.delete(`/incidents/${incidentId}/assignments/${assignmentId}`)
      setAssignments((prev) => prev.filter((a) => a.id !== assignmentId))
    } catch {
      // error handled by api client
    } finally {
      setRemovingId(null)
    }
  }

  // Filter out already-assigned users from the dropdown
  const assignedUserIds = new Set(assignments.map(a => a.user?.id).filter(Boolean))
  const availableUsers = orgUsers
    .filter(u => !assignedUserIds.has(u.id))
    .filter(u =>
      !searchQuery ||
      u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase())
    )

  if (loading) {
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
        {assignments.length === 0 && !showAddForm && (
          <div className="text-center py-4 text-sm text-muted-foreground">
            <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
            No personnel assigned
          </div>
        )}

        {assignments.map((assignment) => (
          <div
            key={assignment.id}
            className="flex items-center gap-3 p-2 rounded-md hover:bg-muted/50 group"
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
                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive shrink-0"
                onClick={() => handleRemove(assignment.id)}
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

        {showAddForm && (
          <div className="border rounded-md p-3 space-y-3 bg-muted/30">
            <Input
              placeholder="Search users..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 text-sm"
            />
            <Select value={selectedUserId} onValueChange={setSelectedUserId}>
              <SelectTrigger className="h-8 text-sm">
                <SelectValue placeholder="Select user" />
              </SelectTrigger>
              <SelectContent>
                {availableUsers.length === 0 ? (
                  <div className="text-xs text-muted-foreground p-2 text-center">
                    {orgUsers.length === 0 ? 'Loading users...' : 'No users available'}
                  </div>
                ) : (
                  availableUsers.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      <span>{u.name}</span>
                      <span className="text-muted-foreground ml-2 text-xs">{u.email}</span>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            <Select value={selectedRole} onValueChange={setSelectedRole}>
              <SelectTrigger className="h-8 text-sm">
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
                onClick={handleAssign}
                className="flex-1"
              >
                {adding ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                Assign
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setShowAddForm(false)
                  setSelectedUserId('')
                  setSelectedRole('')
                  setSearchQuery('')
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
