"use client"

/**
 * Create a user. Picking roles needs roles:manage; roles whose permissions
 * exceed yours are disabled (backend 403 privilege_escalation). Without an
 * explicit role the server assigns the org's default role (security policy,
 * Viewer unless changed). Password hints follow the org's password policy.
 */

import { useState, useEffect } from 'react'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Loader2, X, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { canGrant, rbac } from '@/lib/endpoints/rbac'
import { useAuthStore } from '@/lib/store'
import { usePermission } from '@/components/auth/permission-gate'
import { GuardErrorAlert } from '@/components/auth/guard-error-alert'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import { usePasswordPolicy } from '@/hooks/use-password-policy'
import { PasswordChecklist, PasswordRulesHint } from '@/components/settings/PasswordChecklist'
import { Role, Team } from '@/types'

const DEFAULT_ROLE = 'Analyst'

interface AddUserModalProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onSuccess: () => void
}

export function AddUserModal({ open, onOpenChange, onSuccess }: AddUserModalProps) {
    const [isLoading, setIsLoading] = useState(false)
    const [formData, setFormData] = useState({
        email: '',
        name: '',
        password: '',
        organizational_role: '',
    })
    const granted = useAuthStore((s) => s.user?.permissions) ?? []
    const canAssignRoles = usePermission('roles:manage')
    const canEditTeams = usePermission('teams:update')
    const { labelOf } = usePermissionCatalog()
    const [selectedRoles, setSelectedRoles] = useState<string[]>([])
    const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])
    const [error, setError] = useState<unknown>(null)
    // The org's password policy (hints; the server validates the password).
    const passwordRules = usePasswordPolicy(open)

    // Available roles and teams
    const [availableRoles, setAvailableRoles] = useState<Role[]>([])
    const [availableTeams, setAvailableTeams] = useState<Team[]>([])
    const [roleToAdd, setRoleToAdd] = useState('')
    const [teamToAdd, setTeamToAdd] = useState('')

    useEffect(() => {
        if (open) {
            setError(null)
            loadRoles()
            loadTeams()
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open])

    const loadRoles = async () => {
        try {
            const res = await rbac.listRoles()
            setAvailableRoles(res.items)
            // Preselect the default role only when you may grant it.
            const fallback = res.items.find(r => r.name === DEFAULT_ROLE)
            setSelectedRoles(prev =>
                prev.length === 0 && fallback && canGrant(granted, fallback.permissions) ? [fallback.name] : prev
            )
        } catch { /* ignore */ }
    }

    const loadTeams = async () => {
        try {
            const res = await api.get<{ items: Team[] }>('/teams')
            setAvailableTeams(res.items)
        } catch { /* ignore */ }
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError(null)
        setIsLoading(true)

        try {
            const res = await api.post<{ id: string }>('/users', {
                ...formData,
                // Without roles:manage the server assigns Viewer; sending roles would be refused.
                ...(canAssignRoles && selectedRoles.length > 0 ? { roles: selectedRoles } : {}),
                organizational_role: formData.organizational_role || undefined,
            })

            // Add user to selected teams
            for (const teamId of selectedTeamIds) {
                try {
                    await api.post(`/teams/${teamId}/members`, { user_id: res.id })
                } catch { /* best effort */ }
            }

            onSuccess()
            onOpenChange(false)
            setFormData({ email: '', name: '', password: '', organizational_role: '' })
            setSelectedRoles([])
            setSelectedTeamIds([])
        } catch (err) {
            setError(err)
        } finally {
            setIsLoading(false)
        }
    }

    const unassignedRoles = availableRoles.filter(r => !selectedRoles.includes(r.name))

    const unassignedTeams = availableTeams.filter(t => !selectedTeamIds.includes(t.id))

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <form onSubmit={handleSubmit}>
                    <DialogHeader>
                        <DialogTitle>Add New User</DialogTitle>
                        <DialogDescription>
                            Create a new user account. They will be able to log in immediately.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        <GuardErrorAlert error={error} labelOf={labelOf} />

                        <div className="grid gap-2">
                            <Label htmlFor="name">Full Name</Label>
                            <Input
                                id="name"
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                placeholder="John Doe"
                                required
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="email">Email Address</Label>
                            <Input
                                id="email"
                                type="email"
                                value={formData.email}
                                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                placeholder="john@example.com"
                                required
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="password">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                value={formData.password}
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                placeholder="••••••••"
                                required
                                minLength={passwordRules.min_length}
                            />
                            {formData.password.length > 0 ? (
                                <PasswordChecklist password={formData.password} rules={passwordRules} />
                            ) : (
                                <PasswordRulesHint rules={passwordRules} />
                            )}
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="org-role">Organisational Role</Label>
                            <Input
                                id="org-role"
                                value={formData.organizational_role}
                                onChange={(e) => setFormData({ ...formData, organizational_role: e.target.value })}
                                placeholder="e.g. Senior Analyst, Team Lead"
                            />
                        </div>

                        {/* Roles */}
                        <div className="grid gap-2 border-t pt-4 mt-1">
                            <Label>Roles</Label>
                            {!canAssignRoles ? (
                                <p className="text-xs text-muted-foreground">
                                    New users get the Viewer role. Assigning other roles requires the Manage roles permission.
                                </p>
                            ) : (
                            <>
                            <div className="flex flex-wrap gap-1.5 min-h-[32px]">
                                {selectedRoles.length === 0 && (
                                    <span className="text-xs text-muted-foreground">No role selected: the user gets Viewer</span>
                                )}
                                {selectedRoles.map(role => (
                                    <Badge key={role} variant="default" className="gap-1 pr-1">
                                        {role}
                                        <button
                                            type="button"
                                            onClick={() => setSelectedRoles(prev => prev.filter(r => r !== role))}
                                            className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                            aria-label={`Remove role ${role}`}
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </Badge>
                                ))}
                            </div>
                            {unassignedRoles.length > 0 && (
                                <div className="flex gap-2">
                                    <Select value={roleToAdd} onValueChange={setRoleToAdd}>
                                        <SelectTrigger className="flex-1" aria-label="Add role">
                                            <SelectValue placeholder="Add role..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {unassignedRoles.map(r => {
                                                const exceeds = !canGrant(granted, r.permissions)
                                                return (
                                                    <SelectItem key={r.id} value={r.name} disabled={exceeds}>
                                                        {r.name}{exceeds ? ' (exceeds your permissions)' : ''}
                                                    </SelectItem>
                                                )
                                            })}
                                        </SelectContent>
                                    </Select>
                                    <Button
                                        type="button"
                                        size="icon"
                                        variant="outline"
                                        onClick={() => {
                                            if (roleToAdd) {
                                                setSelectedRoles(prev => [...prev, roleToAdd])
                                                setRoleToAdd('')
                                            }
                                        }}
                                        disabled={!roleToAdd}
                                    >
                                        <Plus className="h-4 w-4" />
                                    </Button>
                                </div>
                            )}
                            </>
                            )}
                        </div>

                        {/* Teams */}
                        {canEditTeams && availableTeams.length > 0 && (
                            <div className="grid gap-2 border-t pt-4 mt-1">
                                <Label>Teams</Label>
                                <div className="flex flex-wrap gap-1.5 min-h-[32px]">
                                    {selectedTeamIds.length === 0 && (
                                        <span className="text-xs text-muted-foreground">No teams selected</span>
                                    )}
                                    {selectedTeamIds.map(id => {
                                        const team = availableTeams.find(t => t.id === id)
                                        return team ? (
                                            <Badge key={id} variant="outline" className="gap-1 pr-1">
                                                {team.name}
                                                <button
                                                    type="button"
                                                    onClick={() => setSelectedTeamIds(prev => prev.filter(tid => tid !== id))}
                                                    className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                                >
                                                    <X className="h-3 w-3" />
                                                </button>
                                            </Badge>
                                        ) : null
                                    })}
                                </div>
                                {unassignedTeams.length > 0 && (
                                    <div className="flex gap-2">
                                        <Select value={teamToAdd} onValueChange={setTeamToAdd}>
                                            <SelectTrigger className="flex-1">
                                                <SelectValue placeholder="Add to team..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {unassignedTeams.map(t => (
                                                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                        <Button
                                            type="button"
                                            size="icon"
                                            variant="outline"
                                            onClick={() => {
                                                if (teamToAdd) {
                                                    setSelectedTeamIds(prev => [...prev, teamToAdd])
                                                    setTeamToAdd('')
                                                }
                                            }}
                                            disabled={!teamToAdd}
                                        >
                                            <Plus className="h-4 w-4" />
                                        </Button>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => onOpenChange(false)}
                            disabled={isLoading}
                        >
                            Cancel
                        </Button>
                        <Button type="submit" disabled={isLoading}>
                            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Create User
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    )
}
