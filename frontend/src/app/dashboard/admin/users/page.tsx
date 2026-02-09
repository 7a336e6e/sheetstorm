/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, useEffect } from 'react'
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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Users, UserPlus, Shield, Loader2, Pencil, Trash2, MoreVertical, UsersRound, Cloud, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { User, Team } from '@/types'
import { AddUserModal } from '@/components/users/AddUserModal'
import { EditUserModal } from '@/components/users/EditUserModal'
import { RoleBadge } from '@/components/ui/badge'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'

export default function UsersPage() {
    const [users, setUsers] = useState<User[]>([])
    const [teams, setTeams] = useState<Team[]>([])
    const [loading, setLoading] = useState(true)
    const [syncing, setSyncing] = useState(false)
    const [isAddOpen, setIsAddOpen] = useState(false)
    const [isEditOpen, setIsEditOpen] = useState(false)
    const [selectedUser, setSelectedUser] = useState<User | null>(null)
    const [teamFilter, setTeamFilter] = useState<string>('all')
    const { toast } = useToast()
    const confirm = useConfirm()

    useEffect(() => {
        loadUsers()
        loadTeams()
    }, [])

    const loadUsers = async () => {
        setLoading(true)
        try {
            const response = await api.get<{ items: User[] }>('/users')
            setUsers(response.items)
        } catch (error) {
            console.error('Failed to load users:', error)
        } finally {
            setLoading(false)
        }
    }

    const loadTeams = async () => {
        try {
            const response = await api.get<{ items: Team[] }>('/teams')
            setTeams(response.items)
        } catch { /* ignore */ }
    }

    const handleEdit = (user: User) => {
        setSelectedUser(user)
        setIsEditOpen(true)
    }

    const handleDelete = async (user: User) => {
        const confirmed = await confirm({
            title: 'Delete User',
            description: `Are you sure you want to delete ${user.name}? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return

        try {
            await api.delete(`/users/${user.id}`)
            await loadUsers()
        } catch (error) {
            console.error('Failed to delete user:', error)
            toast({ title: 'Error', description: 'Failed to delete user', variant: 'destructive' })
        }
    }

    const handleSuccess = () => {
        loadUsers()
        loadTeams()
    }

    const syncSupabaseUsers = async () => {
        setSyncing(true)
        try {
            const result = await api.post<{ message: string; created: number; skipped: number }>('/users/sync-supabase')
            toast({
                title: 'Supabase Sync Complete',
                description: result.message,
            })
            await loadUsers()
        } catch (error: any) {
            toast({
                title: 'Sync Failed',
                description: error?.message || 'Could not sync Supabase users',
                variant: 'destructive',
            })
        } finally {
            setSyncing(false)
        }
    }

    const filteredUsers = teamFilter === 'all'
        ? users
        : users.filter(u => u.teams?.some(t => t.id === teamFilter))

    return (
        <div className="p-6 space-y-6">
            <AddUserModal
                open={isAddOpen}
                onOpenChange={setIsAddOpen}
                onSuccess={handleSuccess}
            />

            <EditUserModal
                user={selectedUser}
                open={isEditOpen}
                onOpenChange={setIsEditOpen}
                onSuccess={handleSuccess}
            />

            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-semibold">Users</h1>
                    <p className="text-sm text-muted-foreground mt-1">Manage users, roles, and team membership</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={syncSupabaseUsers} disabled={syncing}>
                        {syncing ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <Cloud className="mr-2 h-4 w-4" />
                        )}
                        Sync Supabase
                    </Button>
                    <Button onClick={() => setIsAddOpen(true)}>
                        <UserPlus className="mr-2 h-4 w-4" />
                        Add User
                    </Button>
                </div>
            </div>

            {/* Stats */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Users</CardDescription>
                        <CardTitle className="text-2xl">{users.length}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Administrators</CardDescription>
                        <CardTitle className="text-2xl">
                            {users.filter(u => u.roles.includes('Administrator')).length}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Analysts</CardDescription>
                        <CardTitle className="text-2xl">
                            {users.filter(u => u.roles.includes('Analyst')).length}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Teams</CardDescription>
                        <CardTitle className="text-2xl">{teams.length}</CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Users Table */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Users className="h-5 w-5" />
                                All Users
                            </CardTitle>
                            <CardDescription>Manage user accounts, roles, and teams</CardDescription>
                        </div>
                        {teams.length > 0 && (
                            <Select value={teamFilter} onValueChange={setTeamFilter}>
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue placeholder="Filter by team" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Teams</SelectItem>
                                    {teams.map(team => (
                                        <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : filteredUsers.length > 0 ? (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>User</TableHead>
                                    <TableHead>Email</TableHead>
                                    <TableHead>Provider</TableHead>
                                    <TableHead>Roles</TableHead>
                                    <TableHead>Org Role</TableHead>
                                    <TableHead>Teams</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Joined</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredUsers.map((user) => (
                                    <TableRow key={user.id}>
                                        <TableCell>
                                            <div className="flex items-center gap-3">
                                                <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-sm font-medium">
                                                    {user.name?.charAt(0).toUpperCase() || user.email.charAt(0).toUpperCase()}
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="font-medium">{user.name || 'No name'}</span>
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">{user.email}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={`text-xs capitalize ${
                                                user.auth_provider === 'supabase' ? 'border-green-500/50 text-green-400' :
                                                user.auth_provider === 'github' ? 'border-purple-500/50 text-purple-400' :
                                                'border-blue-500/50 text-blue-400'
                                            }`}>
                                                {user.auth_provider || 'local'}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex gap-1 flex-wrap">
                                                {user.roles.map((role) => (
                                                    <RoleBadge key={role} role={role} />
                                                ))}
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground text-sm">
                                            {user.organizational_role || '—'}
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex gap-1 flex-wrap">
                                                {user.teams && user.teams.length > 0 ? (
                                                    user.teams.map(team => (
                                                        <Badge key={team.id} variant="outline" className="text-xs">
                                                            {team.name}
                                                        </Badge>
                                                    ))
                                                ) : (
                                                    <span className="text-muted-foreground text-sm">—</span>
                                                )}
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant={user.is_active ? "default" : "outline"}>
                                                {user.is_active ? "Active" : "Disabled"}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {new Date(user.created_at).toLocaleDateString()}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" className="h-8 w-8 p-0">
                                                        <span className="sr-only">Open menu</span>
                                                        <MoreVertical className="h-4 w-4" />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                    <DropdownMenuItem onClick={() => handleEdit(user)}>
                                                        <Pencil className="mr-2 h-4 w-4" />
                                                        Edit Details
                                                    </DropdownMenuItem>
                                                    <DropdownMenuSeparator />
                                                    <DropdownMenuItem
                                                        onClick={() => handleDelete(user)}
                                                        className="text-red-600 focus:text-red-600 focus:bg-red-50 dark:focus:bg-red-900/10"
                                                    >
                                                        <Trash2 className="mr-2 h-4 w-4" />
                                                        Delete User
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    ) : (
                        <div className="text-center py-8">
                            <div className="mx-auto w-12 h-12 rounded-md bg-muted flex items-center justify-center mb-4">
                                <Users className="h-6 w-6 text-muted-foreground" />
                            </div>
                            <p className="font-medium mb-1">No users found</p>
                            <p className="text-sm text-muted-foreground">
                                {teamFilter !== 'all' ? 'No users in this team' : 'Add your first team member to get started'}
                            </p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
