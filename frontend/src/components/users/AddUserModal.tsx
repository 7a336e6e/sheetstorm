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
import { Role, Team } from '@/types'

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
    const [selectedRoles, setSelectedRoles] = useState<string[]>(['Analyst'])
    const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])
    const [error, setError] = useState('')

    // Available roles and teams
    const [availableRoles, setAvailableRoles] = useState<Role[]>([])
    const [availableTeams, setAvailableTeams] = useState<Team[]>([])
    const [roleToAdd, setRoleToAdd] = useState('')
    const [teamToAdd, setTeamToAdd] = useState('')

    useEffect(() => {
        if (open) {
            loadRoles()
            loadTeams()
        }
    }, [open])

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

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setIsLoading(true)

        try {
            const res = await api.post<{ id: string }>('/users', {
                ...formData,
                roles: selectedRoles,
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
            setSelectedRoles(['Analyst'])
            setSelectedTeamIds([])
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create user')
        } finally {
            setIsLoading(false)
        }
    }

    const unassignedRoleNames = availableRoles
        .map(r => r.name)
        .filter(name => !selectedRoles.includes(name))

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
                        {error && (
                            <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 rounded-md border border-red-200 dark:border-red-900/20">
                                {error}
                            </div>
                        )}

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
                                minLength={8}
                            />
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
                            <div className="flex flex-wrap gap-1.5 min-h-[32px]">
                                {selectedRoles.map(role => (
                                    <Badge key={role} variant="default" className="gap-1 pr-1">
                                        {role}
                                        {selectedRoles.length > 1 && (
                                            <button
                                                type="button"
                                                onClick={() => setSelectedRoles(prev => prev.filter(r => r !== role))}
                                                className="ml-0.5 rounded-sm hover:bg-white/20 p-0.5"
                                            >
                                                <X className="h-3 w-3" />
                                            </button>
                                        )}
                                    </Badge>
                                ))}
                            </div>
                            {unassignedRoleNames.length > 0 && (
                                <div className="flex gap-2">
                                    <Select value={roleToAdd} onValueChange={setRoleToAdd}>
                                        <SelectTrigger className="flex-1">
                                            <SelectValue placeholder="Add role..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {unassignedRoleNames.map(name => (
                                                <SelectItem key={name} value={name}>{name}</SelectItem>
                                            ))}
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
                        </div>

                        {/* Teams */}
                        {availableTeams.length > 0 && (
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
