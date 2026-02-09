/** UI must follow DESIGN_CONSTRAINTS.md strictly. Goal: production-quality, restrained, non-AI-looking UI. */

"use client"

import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Users, Plus, Pencil, Trash2, MoreVertical, UserPlus, UserMinus, Loader2 } from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { useToast } from '@/components/ui/use-toast'
import { api } from '@/lib/api'
import { Team, TeamMemberEntry, User } from '@/types'

export default function TeamsPage() {
    const [teams, setTeams] = useState<Team[]>([])
    const [loading, setLoading] = useState(true)
    const confirm = useConfirm()
    const { toast } = useToast()

    // Create/Edit team dialog
    const [isTeamDialogOpen, setIsTeamDialogOpen] = useState(false)
    const [editingTeam, setEditingTeam] = useState<Team | null>(null)
    const [teamForm, setTeamForm] = useState({ name: '', description: '' })
    const [teamFormLoading, setTeamFormLoading] = useState(false)
    const [teamFormError, setTeamFormError] = useState('')

    // Team detail / expanded row
    const [expandedTeamId, setExpandedTeamId] = useState<string | null>(null)
    const [expandedTeam, setExpandedTeam] = useState<Team | null>(null)
    const [expandedLoading, setExpandedLoading] = useState(false)

    // Add member dialog
    const [isAddMemberOpen, setIsAddMemberOpen] = useState(false)
    const [allUsers, setAllUsers] = useState<User[]>([])
    const [selectedUserId, setSelectedUserId] = useState('')
    const [addMemberLoading, setAddMemberLoading] = useState(false)

    const loadTeams = useCallback(async () => {
        setLoading(true)
        try {
            const response = await api.get<{ items: Team[] }>('/teams')
            setTeams(response.items)
        } catch (error) {
            console.error('Failed to load teams:', error)
        } finally {
            setLoading(false)
        }
    }, [])

    const loadTeamDetail = useCallback(async (teamId: string) => {
        setExpandedLoading(true)
        try {
            const team = await api.get<Team>(`/teams/${teamId}`)
            setExpandedTeam(team)
        } catch (error) {
            console.error('Failed to load team detail:', error)
        } finally {
            setExpandedLoading(false)
        }
    }, [])

    const loadUsers = useCallback(async () => {
        try {
            const response = await api.get<{ items: User[] }>('/users')
            setAllUsers(response.items)
        } catch { /* ignore */ }
    }, [])

    useEffect(() => {
        loadTeams()
    }, [loadTeams])

    // --- Team CRUD ---

    const handleOpenCreate = () => {
        setEditingTeam(null)
        setTeamForm({ name: '', description: '' })
        setTeamFormError('')
        setIsTeamDialogOpen(true)
    }

    const handleOpenEdit = (team: Team) => {
        setEditingTeam(team)
        setTeamForm({ name: team.name, description: team.description || '' })
        setTeamFormError('')
        setIsTeamDialogOpen(true)
    }

    const handleTeamSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setTeamFormError('')
        setTeamFormLoading(true)

        try {
            if (editingTeam) {
                await api.put(`/teams/${editingTeam.id}`, {
                    name: teamForm.name,
                    description: teamForm.description || undefined,
                })
            } else {
                await api.post('/teams', {
                    name: teamForm.name,
                    description: teamForm.description || undefined,
                })
            }
            setIsTeamDialogOpen(false)
            await loadTeams()
            // Refresh detail if the edited team is currently expanded
            if (editingTeam && expandedTeamId === editingTeam.id) {
                loadTeamDetail(editingTeam.id)
            }
        } catch (err) {
            setTeamFormError(err instanceof Error ? err.message : 'Failed to save team')
        } finally {
            setTeamFormLoading(false)
        }
    }

    const handleDelete = async (team: Team) => {
        const confirmed = await confirm({
            title: 'Delete Team',
            description: `Are you sure you want to delete "${team.name}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return

        try {
            await api.delete(`/teams/${team.id}`)
            if (expandedTeamId === team.id) {
                setExpandedTeamId(null)
                setExpandedTeam(null)
            }
            await loadTeams()
        } catch (error) {
            console.error('Failed to delete team:', error)
            toast({ title: 'Error', description: 'Failed to delete team', variant: 'destructive' })
        }
    }

    // --- Row expand ---

    const handleRowClick = (teamId: string) => {
        if (expandedTeamId === teamId) {
            setExpandedTeamId(null)
            setExpandedTeam(null)
        } else {
            setExpandedTeamId(teamId)
            loadTeamDetail(teamId)
        }
    }

    // --- Members ---

    const handleOpenAddMember = () => {
        setSelectedUserId('')
        loadUsers()
        setIsAddMemberOpen(true)
    }

    const handleAddMember = async () => {
        if (!selectedUserId || !expandedTeamId) return
        setAddMemberLoading(true)

        try {
            await api.post(`/teams/${expandedTeamId}/members`, { user_id: selectedUserId })
            setIsAddMemberOpen(false)
            setSelectedUserId('')
            await loadTeamDetail(expandedTeamId)
            await loadTeams()
        } catch (error) {
            console.error('Failed to add member:', error)
            toast({ title: 'Error', description: 'Failed to add member', variant: 'destructive' })
        } finally {
            setAddMemberLoading(false)
        }
    }

    const handleRemoveMember = async (userId: string, userName: string) => {
        if (!expandedTeamId) return
        const confirmed = await confirm({
            title: 'Remove Member',
            description: `Remove ${userName} from this team?`,
            confirmLabel: 'Remove',
            variant: 'destructive',
        })
        if (!confirmed) return

        try {
            await api.delete(`/teams/${expandedTeamId}/members/${userId}`)
            await loadTeamDetail(expandedTeamId)
            await loadTeams()
        } catch (error) {
            console.error('Failed to remove member:', error)
            toast({ title: 'Error', description: 'Failed to remove member', variant: 'destructive' })
        }
    }

    // --- Computed ---

    const totalMembers = teams.reduce((sum, t) => sum + (t.member_count || 0), 0)

    const existingMemberIds = new Set(
        (expandedTeam?.members || []).map(m => m.user_id)
    )
    const availableUsers = allUsers.filter(u => !existingMemberIds.has(u.id))

    return (
        <div className="p-6 space-y-6">
            {/* Create/Edit Team Dialog */}
            <Dialog open={isTeamDialogOpen} onOpenChange={setIsTeamDialogOpen}>
                <DialogContent className="max-w-lg">
                    <form onSubmit={handleTeamSubmit}>
                        <DialogHeader>
                            <DialogTitle>{editingTeam ? 'Edit Team' : 'Create Team'}</DialogTitle>
                            <DialogDescription>
                                {editingTeam
                                    ? 'Update the team name and description.'
                                    : 'Create a new team to organise members.'}
                            </DialogDescription>
                        </DialogHeader>

                        <div className="grid gap-4 py-4">
                            {teamFormError && (
                                <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 rounded-md border border-red-200 dark:border-red-900/20">
                                    {teamFormError}
                                </div>
                            )}

                            <div className="grid gap-2">
                                <Label htmlFor="team-name">Team Name</Label>
                                <Input
                                    id="team-name"
                                    value={teamForm.name}
                                    onChange={(e) => setTeamForm({ ...teamForm, name: e.target.value })}
                                    placeholder="e.g. Incident Response"
                                    required
                                />
                            </div>

                            <div className="grid gap-2">
                                <Label htmlFor="team-description">Description</Label>
                                <Textarea
                                    id="team-description"
                                    value={teamForm.description}
                                    onChange={(e) => setTeamForm({ ...teamForm, description: e.target.value })}
                                    placeholder="Brief description of the team's purpose"
                                    rows={3}
                                />
                            </div>
                        </div>

                        <DialogFooter>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setIsTeamDialogOpen(false)}
                                disabled={teamFormLoading}
                            >
                                Cancel
                            </Button>
                            <Button type="submit" disabled={teamFormLoading}>
                                {teamFormLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                {editingTeam ? 'Save Changes' : 'Create Team'}
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>

            {/* Add Member Dialog */}
            <Dialog open={isAddMemberOpen} onOpenChange={setIsAddMemberOpen}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle>Add Member</DialogTitle>
                        <DialogDescription>
                            Select a user to add to this team.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        <div className="grid gap-2">
                            <Label>User</Label>
                            {availableUsers.length > 0 ? (
                                <Select value={selectedUserId} onValueChange={setSelectedUserId}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select a user..." />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {availableUsers.map(user => (
                                            <SelectItem key={user.id} value={user.id}>
                                                {user.name} ({user.email})
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            ) : (
                                <p className="text-sm text-muted-foreground py-2">
                                    All users are already members of this team.
                                </p>
                            )}
                        </div>
                    </div>

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setIsAddMemberOpen(false)}
                            disabled={addMemberLoading}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            onClick={handleAddMember}
                            disabled={addMemberLoading || !selectedUserId}
                        >
                            {addMemberLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Add Member
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-semibold">Teams</h1>
                    <p className="text-sm text-muted-foreground mt-1">Manage teams and team membership</p>
                </div>
                <Button onClick={handleOpenCreate}>
                    <Plus className="mr-2 h-4 w-4" />
                    Create Team
                </Button>
            </div>

            {/* Stats */}
            <div className="grid gap-4 md:grid-cols-2">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Teams</CardDescription>
                        <CardTitle className="text-2xl">{teams.length}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Members</CardDescription>
                        <CardTitle className="text-2xl">{totalMembers}</CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Teams Table */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Users className="h-5 w-5" />
                                All Teams
                            </CardTitle>
                            <CardDescription>Click a team row to view and manage its members</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : teams.length > 0 ? (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Team Name</TableHead>
                                    <TableHead>Description</TableHead>
                                    <TableHead>Members</TableHead>
                                    <TableHead>Created</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {teams.map((team) => (
                                    <>
                                        <TableRow
                                            key={team.id}
                                            className="cursor-pointer"
                                            onClick={() => handleRowClick(team.id)}
                                        >
                                            <TableCell>
                                                <span className="font-medium">{team.name}</span>
                                            </TableCell>
                                            <TableCell className="text-muted-foreground max-w-[300px] truncate">
                                                {team.description || '\u2014'}
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant="outline">
                                                    {team.member_count || 0}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-muted-foreground">
                                                {new Date(team.created_at).toLocaleDateString()}
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger asChild>
                                                        <Button
                                                            variant="ghost"
                                                            className="h-8 w-8 p-0"
                                                            onClick={(e) => e.stopPropagation()}
                                                        >
                                                            <span className="sr-only">Open menu</span>
                                                            <MoreVertical className="h-4 w-4" />
                                                        </Button>
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent align="end">
                                                        <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                        <DropdownMenuItem onClick={() => handleOpenEdit(team)}>
                                                            <Pencil className="mr-2 h-4 w-4" />
                                                            Edit Team
                                                        </DropdownMenuItem>
                                                        <DropdownMenuSeparator />
                                                        <DropdownMenuItem
                                                            onClick={() => handleDelete(team)}
                                                            className="text-red-600 focus:text-red-600 focus:bg-red-50 dark:focus:bg-red-900/10"
                                                        >
                                                            <Trash2 className="mr-2 h-4 w-4" />
                                                            Delete Team
                                                        </DropdownMenuItem>
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            </TableCell>
                                        </TableRow>

                                        {/* Expanded detail panel */}
                                        {expandedTeamId === team.id && (
                                            <TableRow key={`${team.id}-detail`}>
                                                <TableCell colSpan={5} className="bg-muted/30 p-0">
                                                    <div className="p-4 space-y-4">
                                                        <div className="flex items-center justify-between">
                                                            <h3 className="text-sm font-medium">
                                                                Members
                                                            </h3>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={(e) => {
                                                                    e.stopPropagation()
                                                                    handleOpenAddMember()
                                                                }}
                                                            >
                                                                <UserPlus className="mr-2 h-3.5 w-3.5" />
                                                                Add Member
                                                            </Button>
                                                        </div>

                                                        {expandedLoading ? (
                                                            <div className="flex items-center justify-center py-6">
                                                                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                                            </div>
                                                        ) : (expandedTeam?.members && expandedTeam.members.length > 0) ? (
                                                            <Table>
                                                                <TableHeader>
                                                                    <TableRow>
                                                                        <TableHead>User</TableHead>
                                                                        <TableHead>Email</TableHead>
                                                                        <TableHead>Status</TableHead>
                                                                        <TableHead>Joined</TableHead>
                                                                        <TableHead className="text-right">Remove</TableHead>
                                                                    </TableRow>
                                                                </TableHeader>
                                                                <TableBody>
                                                                    {expandedTeam.members.map((member: TeamMemberEntry) => (
                                                                        <TableRow key={member.id}>
                                                                            <TableCell>
                                                                                <div className="flex items-center gap-3">
                                                                                    <div className="h-7 w-7 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-xs font-medium">
                                                                                        {member.user?.name?.charAt(0).toUpperCase() || member.user?.email?.charAt(0).toUpperCase() || '?'}
                                                                                    </div>
                                                                                    <span className="font-medium text-sm">
                                                                                        {member.user?.name || 'Unknown'}
                                                                                    </span>
                                                                                </div>
                                                                            </TableCell>
                                                                            <TableCell className="text-muted-foreground text-sm">
                                                                                {member.user?.email || '\u2014'}
                                                                            </TableCell>
                                                                            <TableCell>
                                                                                <Badge variant={member.user?.is_active ? "default" : "outline"}>
                                                                                    {member.user?.is_active ? "Active" : "Disabled"}
                                                                                </Badge>
                                                                            </TableCell>
                                                                            <TableCell className="text-muted-foreground text-sm">
                                                                                {new Date(member.joined_at).toLocaleDateString()}
                                                                            </TableCell>
                                                                            <TableCell className="text-right">
                                                                                <Button
                                                                                    variant="ghost"
                                                                                    size="sm"
                                                                                    className="text-red-600 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/10"
                                                                                    onClick={(e) => {
                                                                                        e.stopPropagation()
                                                                                        handleRemoveMember(
                                                                                            member.user_id,
                                                                                            member.user?.name || member.user?.email || 'this user'
                                                                                        )
                                                                                    }}
                                                                                >
                                                                                    <UserMinus className="mr-1.5 h-3.5 w-3.5" />
                                                                                    Remove
                                                                                </Button>
                                                                            </TableCell>
                                                                        </TableRow>
                                                                    ))}
                                                                </TableBody>
                                                            </Table>
                                                        ) : (
                                                            <div className="text-center py-6">
                                                                <p className="text-sm text-muted-foreground">
                                                                    No members in this team yet.
                                                                </p>
                                                            </div>
                                                        )}
                                                    </div>
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </>
                                ))}
                            </TableBody>
                        </Table>
                    ) : (
                        <div className="text-center py-8">
                            <div className="mx-auto w-12 h-12 rounded-md bg-muted flex items-center justify-center mb-4">
                                <Users className="h-6 w-6 text-muted-foreground" />
                            </div>
                            <p className="font-medium mb-1">No teams found</p>
                            <p className="text-sm text-muted-foreground">
                                Create your first team to get started.
                            </p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
