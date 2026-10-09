"use client"

/**
 * Edit a user: profile, roles, teams, account state and password reset.
 *
 * Mirrors the backend guardrails (cosmetic; `rbac_guard` enforces them):
 * - roles whose permissions exceed yours are disabled ("exceeds your permissions");
 * - a user holding permissions you lack can't be changed (403 insufficient_privilege);
 * - on yourself, the Active switch and password reset are hidden (400 self_action /
 *   use_change_password: change your own password from your profile);
 * - server refusals (`last_admin`, `self_lockout`, ...) are shown as returned.
 */

import { useState, useEffect, useCallback } from 'react'
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
import { Loader2, X, Plus, ShieldAlert } from 'lucide-react'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { GuardErrorAlert } from '@/components/auth/guard-error-alert'
import { usePermission } from '@/components/auth/permission-gate'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import { api } from '@/lib/api'
import { canGrant, isAdminCore, missingPermissions, rbac } from '@/lib/endpoints/rbac'
import { useAuthStore } from '@/lib/store'
import { User, Role, Team } from '@/types'

interface EditUserModalProps {
    user: User | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onSuccess: () => void
}

export function EditUserModal({ user, open, onOpenChange, onSuccess }: EditUserModalProps) {
    const confirm = useConfirm()
    const me = useAuthStore((s) => s.user)
    const granted = me?.permissions ?? []
    const isSelf = !!user && me?.id === user.id
    const canManageUsers = usePermission('users:manage')
    const canManageRoles = usePermission('roles:manage')
    const canEditTeams = usePermission('teams:update')
    const { lookup, labelOf } = usePermissionCatalog()

    const [isLoading, setIsLoading] = useState(false)
    const [formData, setFormData] = useState({
        name: '',
        is_active: true,
        organizational_role: '',
        password: ''
    })
    const [error, setError] = useState<unknown>(null)

    // Permissions of the target user (for the "outranks you" notice).
    const [targetPermissions, setTargetPermissions] = useState<string[] | null>(null)

    // Roles management
    const [availableRoles, setAvailableRoles] = useState<Role[]>([])
    const [userRoles, setUserRoles] = useState<{ id: string; name: string }[]>([])
    const [roleToAdd, setRoleToAdd] = useState('')

    // Teams management
    const [availableTeams, setAvailableTeams] = useState<Team[]>([])
    const [userTeams, setUserTeams] = useState<{ id: string; name: string }[]>([])
    const [teamToAdd, setTeamToAdd] = useState('')

    const loadUserRoles = useCallback(async () => {
        if (!user) return
        try {
            const res = await api.get<{ roles: { id: string; name: string }[] }>(`/users/${user.id}/roles`)
            setUserRoles(res.roles)
        } catch { /* ignore */ }
    }, [user])

    const loadTarget = useCallback(async () => {
        if (!user) return
        try {
            const res = await api.get<User>(`/users/${user.id}`)
            setTargetPermissions(res.permissions ?? [])
        } catch {
            setTargetPermissions(null)
        }
    }, [user])

    useEffect(() => {
        if (user && open) {
            setFormData({
                name: user.name,
                is_active: user.is_active,
                organizational_role: user.organizational_role || '',
                password: ''
            })
            setError(null)
            setTargetPermissions(null)
            setUserTeams(user.teams || [])
            rbac.listRoles().then((res) => setAvailableRoles(res.items)).catch(() => { /* ignore */ })
            api.get<{ items: Team[] }>('/teams').then((res) => setAvailableTeams(res.items)).catch(() => { /* ignore */ })
            void loadUserRoles()
            void loadTarget()
        }
    }, [user, open, loadUserRoles, loadTarget])

    // Acting on someone holding permissions you lack is refused server side.
    const outranksMe = isSelf ? [] : missingPermissions(targetPermissions ?? [], granted)
    const locked = outranksMe.length > 0

    const handleAddRole = async () => {
        if (!user || !roleToAdd) return
        const role = availableRoles.find(r => r.id === roleToAdd)
        if (!role) return
        const dangerous = role.permissions.filter((k) => lookup(k)?.dangerous)
        if (dangerous.length > 0) {
            const adminGrant = isAdminCore(role.permissions)
            const ok = await confirm({
                title: `Grant "${role.name}" to ${user.name}?`,
                description: (
                    <span className="block space-y-2">
                        <span className="block">
                            {adminGrant
                                ? 'This role makes the user an administrator (manage users and roles).'
                                : 'This role includes dangerous permissions:'}
                        </span>
                        <span className="block">
                            {dangerous.map((k) => (
                                <span key={k} className="block">{labelOf(k)}</span>
                            ))}
                        </span>
                    </span>
                ),
                confirmLabel: 'Grant role',
                variant: 'destructive',
                requireText: adminGrant ? role.name : undefined,
            })
            if (!ok) return
        }
        setError(null)
        try {
            await rbac.assignRole(user.id, roleToAdd)
            await loadUserRoles()
            void loadTarget()
            setRoleToAdd('')
        } catch (err) {
            setError(err)
        }
    }

    const handleRemoveRole = async (roleId: string) => {
        if (!user) return
        if (userRoles.length <= 1) {
            setError(new Error('A user must keep at least one role.'))
            return
        }
        setError(null)
        try {
            await rbac.revokeRole(user.id, roleId)
            await loadUserRoles()
            void loadTarget()
        } catch (err) {
            setError(err)
        }
    }

    const handleAddTeam = async () => {
        if (!user || !teamToAdd) return
        setError(null)
        try {
            await api.post(`/teams/${teamToAdd}/members`, { user_id: user.id })
            const team = availableTeams.find(t => t.id === teamToAdd)
            if (team) setUserTeams(prev => [...prev, { id: team.id, name: team.name }])
            setTeamToAdd('')
        } catch (err) {
            setError(err)
        }
    }

    const handleRemoveTeam = async (teamId: string) => {
        if (!user) return
        setError(null)
        try {
            await api.delete(`/teams/${teamId}/members/${user.id}`)
            setUserTeams(prev => prev.filter(t => t.id !== teamId))
        } catch (err) {
            setError(err)
        }
    }

    const showAccountControls = canManageUsers && !isSelf

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!user) return

        setError(null)
        setIsLoading(true)

        const payload: Record<string, unknown> = {
            name: formData.name,
            organizational_role: formData.organizational_role || null,
        }
        if (showAccountControls) {
            if (formData.is_active !== user.is_active) payload.is_active = formData.is_active
            if (formData.password) payload.password = formData.password
        }

        try {
            await api.put(`/users/${user.id}`, payload)
            onSuccess()
            onOpenChange(false)
        } catch (err) {
            setError(err)
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
                            {isSelf
                                ? 'Your own account. Change your password from your profile.'
                                : 'Update user details, roles, and team membership.'}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        {locked && (
                            <div className="flex gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400" role="status">
                                <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
                                <div>
                                    <p className="font-medium">This user holds permissions you don&apos;t have</p>
                                    <p className="mt-0.5 text-amber-400/80">
                                        You can&apos;t change their account or roles: {outranksMe.map(labelOf).join(', ')}.
                                    </p>
                                </div>
                            </div>
                        )}

                        <GuardErrorAlert error={error} labelOf={labelOf} />

                        <div className="grid gap-2">
                            <Label htmlFor="edit-name">Full Name</Label>
                            <Input
                                id="edit-name"
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                placeholder="John Doe"
                                required
                                disabled={locked}
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="edit-org-role">Organisational Role</Label>
                            <Input
                                id="edit-org-role"
                                value={formData.organizational_role}
                                onChange={(e) => setFormData({ ...formData, organizational_role: e.target.value })}
                                placeholder="e.g. Senior Analyst, Team Lead, SOC Manager"
                                disabled={locked}
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
                                        {canManageRoles && !locked && (
                                            <button
                                                type="button"
                                                onClick={() => handleRemoveRole(role.id)}
                                                className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                                aria-label={`Remove role ${role.name}`}
                                            >
                                                <X className="h-3 w-3" />
                                            </button>
                                        )}
                                    </Badge>
                                ))}
                            </div>
                            {canManageRoles && !locked && unassignedRoles.length > 0 && (
                                <div className="flex gap-2">
                                    <Select value={roleToAdd} onValueChange={setRoleToAdd}>
                                        <SelectTrigger className="flex-1" aria-label="Add role">
                                            <SelectValue placeholder="Add role..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {unassignedRoles.map(r => {
                                                const exceeds = !canGrant(granted, r.permissions)
                                                return (
                                                    <SelectItem key={r.id} value={r.id} disabled={exceeds}>
                                                        {r.name}{exceeds ? ' (exceeds your permissions)' : ''}
                                                    </SelectItem>
                                                )
                                            })}
                                        </SelectContent>
                                    </Select>
                                    <Button type="button" size="icon" variant="outline" onClick={handleAddRole} disabled={!roleToAdd} aria-label="Assign role">
                                        <Plus className="h-4 w-4" />
                                    </Button>
                                </div>
                            )}
                            {!canManageRoles && (
                                <p className="text-xs text-muted-foreground">Assigning roles requires the Manage roles permission.</p>
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
                                        {canEditTeams && (
                                            <button
                                                type="button"
                                                onClick={() => handleRemoveTeam(team.id)}
                                                className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                                aria-label={`Remove from team ${team.name}`}
                                            >
                                                <X className="h-3 w-3" />
                                            </button>
                                        )}
                                    </Badge>
                                ))}
                            </div>
                            {canEditTeams && unassignedTeams.length > 0 && (
                                <div className="flex gap-2">
                                    <Select value={teamToAdd} onValueChange={setTeamToAdd}>
                                        <SelectTrigger className="flex-1" aria-label="Add to team">
                                            <SelectValue placeholder="Add to team..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {unassignedTeams.map(t => (
                                                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button type="button" size="icon" variant="outline" onClick={handleAddTeam} disabled={!teamToAdd} aria-label="Add to team">
                                        <Plus className="h-4 w-4" />
                                    </Button>
                                </div>
                            )}
                        </div>

                        {showAccountControls && (
                            <>
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
                                        disabled={locked}
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
                                        disabled={locked}
                                        autoComplete="new-password"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Leave blank to keep current password. Resetting signs the user out everywhere.
                                    </p>
                                </div>
                            </>
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
                        <Button type="submit" disabled={isLoading || locked}>
                            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save Changes
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    )
}
