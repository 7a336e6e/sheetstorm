"use client"

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
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Loader2, X, Plus } from 'lucide-react'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { api } from '@/lib/api'
import { User, Role, Team } from '@/types'

interface EditUserModalProps {
    user: User | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onSuccess: () => void
}

export function EditUserModal({ user, open, onOpenChange, onSuccess }: EditUserModalProps) {
    const [isLoading, setIsLoading] = useState(false)
    const [formData, setFormData] = useState({
        name: '',
        is_active: true,
        organizational_role: '',
        password: ''
    })
    const [error, setError] = useState('')

    // Roles management
    const [availableRoles, setAvailableRoles] = useState<Role[]>([])
    const [userRoles, setUserRoles] = useState<{ id: string; name: string }[]>([])
    const [roleToAdd, setRoleToAdd] = useState('')

    // Teams management
    const [availableTeams, setAvailableTeams] = useState<Team[]>([])
    const [userTeams, setUserTeams] = useState<{ id: string; name: string }[]>([])
    const [teamToAdd, setTeamToAdd] = useState('')

    useEffect(() => {
        if (user && open) {
            setFormData({
                name: user.name,
                is_active: user.is_active,
                organizational_role: user.organizational_role || '',
                password: ''
            })
            setUserTeams(user.teams || [])
            loadRoles()
            loadTeams()
            loadUserRoles()
        }
    }, [user, open])

    const loadRoles = async () => {
        try {
            const res = await api.get<{ items: Role[] }>('/roles')
            setAvailableRoles(res.items)
        } catch { /* ignore */ }
    }

    const loadTeams = async () => {
        try {
            const res = await api.get<{ items: Team[] }>('/teams')
            setAvailableTeams(res.items)
        } catch { /* ignore */ }
    }

    const loadUserRoles = async () => {
        if (!user) return
        try {
            const res = await api.get<{ roles: { id: string; name: string }[] }>(`/users/${user.id}/roles`)
            setUserRoles(res.roles)
        } catch { /* ignore */ }
    }

    const handleAddRole = async () => {
        if (!user || !roleToAdd) return
        try {
            await api.post(`/users/${user.id}/roles`, { role_id: roleToAdd })
            await loadUserRoles()
            setRoleToAdd('')
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to add role')
        }
    }

    const handleRemoveRole = async (roleId: string) => {
        if (!user) return
        if (userRoles.length <= 1) {
            setError('User must have at least one role')
            return
        }
        try {
            await api.delete(`/users/${user.id}/roles/${roleId}`)
            await loadUserRoles()
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to remove role')
        }
    }

    const handleAddTeam = async () => {
        if (!user || !teamToAdd) return
        try {
            await api.post(`/teams/${teamToAdd}/members`, { user_id: user.id })
            const team = availableTeams.find(t => t.id === teamToAdd)
            if (team) setUserTeams(prev => [...prev, { id: team.id, name: team.name }])
            setTeamToAdd('')
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to add to team')
        }
    }

    const handleRemoveTeam = async (teamId: string) => {
        if (!user) return
        try {
            await api.delete(`/teams/${teamId}/members/${user.id}`)
            setUserTeams(prev => prev.filter(t => t.id !== teamId))
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to remove from team')
        }
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!user) return

        setError('')
        setIsLoading(true)

        const payload: Record<string, unknown> = {
            name: formData.name,
            is_active: formData.is_active,
            organizational_role: formData.organizational_role || null,
        }

        if (formData.password) {
            payload.password = formData.password
        }

        try {
            await api.put(`/users/${user.id}`, payload)
            onSuccess()
            onOpenChange(false)
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update user')
        } finally {
            setIsLoading(false)
        }
    }

    const unassignedRoles = availableRoles.filter(
        r => !userRoles.some(ur => ur.id === r.id)
    )
    const unassignedTeams = availableTeams.filter(
        t => !userTeams.some(ut => ut.id === t.id)
    )

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <form onSubmit={handleSubmit}>
                    <DialogHeader>
                        <DialogTitle>Edit User</DialogTitle>
                        <DialogDescription>
                            Update user details, roles, and team membership.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        {error && (
                            <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 rounded-md border border-red-200 dark:border-red-900/20">
                                {error}
                            </div>
                        )}

                        <div className="grid gap-2">
                            <Label htmlFor="edit-name">Full Name</Label>
                            <Input
                                id="edit-name"
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                placeholder="John Doe"
                                required
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="edit-org-role">Organisational Role</Label>
                            <Input
                                id="edit-org-role"
                                value={formData.organizational_role}
                                onChange={(e) => setFormData({ ...formData, organizational_role: e.target.value })}
                                placeholder="e.g. Senior Analyst, Team Lead, SOC Manager"
                            />
                            <p className="text-xs text-muted-foreground">Job title or organisational position</p>
                        </div>

                        {/* Roles Section */}
                        <div className="grid gap-2 border-t pt-4 mt-1">
                            <Label>Roles</Label>
                            <div className="flex flex-wrap gap-1.5 min-h-[32px]">
                                {userRoles.map(role => (
                                    <Badge key={role.id} variant="default" className="gap-1 pr-1">
                                        {role.name}
                                        <button
                                            type="button"
                                            onClick={() => handleRemoveRole(role.id)}
                                            className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </Badge>
                                ))}
                            </div>
                            {unassignedRoles.length > 0 && (
                                <div className="flex gap-2">
                                    <Select value={roleToAdd} onValueChange={setRoleToAdd}>
                                        <SelectTrigger className="flex-1">
                                            <SelectValue placeholder="Add role..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {unassignedRoles.map(r => (
                                                <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button type="button" size="icon" variant="outline" onClick={handleAddRole} disabled={!roleToAdd}>
                                        <Plus className="h-4 w-4" />
                                    </Button>
                                </div>
                            )}
                        </div>

                        {/* Teams Section */}
                        <div className="grid gap-2 border-t pt-4 mt-1">
                            <Label>Teams</Label>
                            <div className="flex flex-wrap gap-1.5 min-h-[32px]">
                                {userTeams.length === 0 && (
                                    <span className="text-xs text-muted-foreground">No team assignments</span>
                                )}
                                {userTeams.map(team => (
                                    <Badge key={team.id} variant="outline" className="gap-1 pr-1">
                                        {team.name}
                                        <button
                                            type="button"
                                            onClick={() => handleRemoveTeam(team.id)}
                                            className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </Badge>
                                ))}
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
                                    <Button type="button" size="icon" variant="outline" onClick={handleAddTeam} disabled={!teamToAdd}>
                                        <Plus className="h-4 w-4" />
                                    </Button>
                                </div>
                            )}
                        </div>

                        <div className="flex items-center justify-between space-x-2 border-t pt-4 mt-1 p-3 rounded-md border">
                            <Label htmlFor="active-mode" className="flex flex-col space-y-1">
                                <span>Active Account</span>
                                <span className="font-normal text-xs text-muted-foreground">
                                    Disable to prevent login
                                </span>
                            </Label>
                            <Switch
                                id="active-mode"
                                checked={formData.is_active}
                                onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
                            />
                        </div>

                        <div className="grid gap-2 border-t pt-4 mt-1">
                            <Label htmlFor="reset-password">Reset Password (Optional)</Label>
                            <Input
                                id="reset-password"
                                type="password"
                                value={formData.password}
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                placeholder="New password"
                                minLength={8}
                            />
                            <p className="text-xs text-muted-foreground">
                                Leave blank to keep current password.
                            </p>
                        </div>
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
                            Save Changes
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    )
}
