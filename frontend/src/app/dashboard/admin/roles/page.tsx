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
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Shield, Plus, Pencil, Trash2, MoreVertical, Loader2, Lock, Eye, Check } from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { useToast } from '@/components/ui/use-toast'
import { api } from '@/lib/api'
import { Role } from '@/types'

// ---------------------------------------------------------------------------
// Permission definitions organised by entity
// ---------------------------------------------------------------------------

interface PermissionGroup {
    entity: string
    label: string
    permissions: { value: string; label: string }[]
}

const PERMISSION_GROUPS: PermissionGroup[] = [
    {
        entity: 'incidents',
        label: 'Incidents',
        permissions: [
            { value: 'incidents:create', label: 'Create' },
            { value: 'incidents:read', label: 'Read' },
            { value: 'incidents:update', label: 'Update' },
            { value: 'incidents:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'timeline',
        label: 'Timeline',
        permissions: [
            { value: 'timeline:create', label: 'Create' },
            { value: 'timeline:read', label: 'Read' },
            { value: 'timeline:update', label: 'Update' },
            { value: 'timeline:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'hosts',
        label: 'Hosts',
        permissions: [
            { value: 'hosts:create', label: 'Create' },
            { value: 'hosts:read', label: 'Read' },
            { value: 'hosts:update', label: 'Update' },
            { value: 'hosts:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'accounts',
        label: 'Accounts',
        permissions: [
            { value: 'accounts:create', label: 'Create' },
            { value: 'accounts:read', label: 'Read' },
            { value: 'accounts:update', label: 'Update' },
            { value: 'accounts:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'compromised_accounts',
        label: 'Compromised Accounts',
        permissions: [
            { value: 'compromised_accounts:reveal', label: 'Reveal' },
        ],
    },
    {
        entity: 'network_iocs',
        label: 'Network IOCs',
        permissions: [
            { value: 'network_iocs:create', label: 'Create' },
            { value: 'network_iocs:read', label: 'Read' },
            { value: 'network_iocs:update', label: 'Update' },
            { value: 'network_iocs:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'host_iocs',
        label: 'Host IOCs',
        permissions: [
            { value: 'host_iocs:create', label: 'Create' },
            { value: 'host_iocs:read', label: 'Read' },
            { value: 'host_iocs:update', label: 'Update' },
            { value: 'host_iocs:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'malware',
        label: 'Malware',
        permissions: [
            { value: 'malware:create', label: 'Create' },
            { value: 'malware:read', label: 'Read' },
            { value: 'malware:update', label: 'Update' },
            { value: 'malware:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'artifacts',
        label: 'Artifacts',
        permissions: [
            { value: 'artifacts:upload', label: 'Upload' },
            { value: 'artifacts:read', label: 'Read' },
            { value: 'artifacts:download', label: 'Download' },
            { value: 'artifacts:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'tasks',
        label: 'Tasks',
        permissions: [
            { value: 'tasks:create', label: 'Create' },
            { value: 'tasks:read', label: 'Read' },
            { value: 'tasks:update', label: 'Update' },
            { value: 'tasks:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'attack_graph',
        label: 'Attack Graph',
        permissions: [
            { value: 'attack_graph:create', label: 'Create' },
            { value: 'attack_graph:read', label: 'Read' },
            { value: 'attack_graph:update', label: 'Update' },
            { value: 'attack_graph:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'reports',
        label: 'Reports',
        permissions: [
            { value: 'reports:generate', label: 'Generate' },
            { value: 'reports:read', label: 'Read' },
        ],
    },
    {
        entity: 'users',
        label: 'Users',
        permissions: [
            { value: 'users:create', label: 'Create' },
            { value: 'users:read', label: 'Read' },
            { value: 'users:update', label: 'Update' },
            { value: 'users:delete', label: 'Delete' },
            { value: 'users:manage', label: 'Manage' },
        ],
    },
    {
        entity: 'roles',
        label: 'Roles',
        permissions: [
            { value: 'roles:manage', label: 'Manage' },
        ],
    },
    {
        entity: 'integrations',
        label: 'Integrations',
        permissions: [
            { value: 'integrations:create', label: 'Create' },
            { value: 'integrations:read', label: 'Read' },
            { value: 'integrations:update', label: 'Update' },
            { value: 'integrations:delete', label: 'Delete' },
        ],
    },
    {
        entity: 'audit_logs',
        label: 'Audit Logs',
        permissions: [
            { value: 'audit_logs:read', label: 'Read' },
        ],
    },
    {
        entity: 'organizations',
        label: 'Organizations',
        permissions: [
            { value: 'organizations:manage', label: 'Manage' },
        ],
    },
    {
        entity: 'teams',
        label: 'Teams',
        permissions: [
            { value: 'teams:create', label: 'Create' },
            { value: 'teams:read', label: 'Read' },
            { value: 'teams:update', label: 'Update' },
            { value: 'teams:delete', label: 'Delete' },
        ],
    },
]

const ALL_PERMISSIONS = PERMISSION_GROUPS.flatMap(g => g.permissions.map(p => p.value))

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function RolesPage() {
    const [roles, setRoles] = useState<Role[]>([])
    const [loading, setLoading] = useState(true)
    const confirm = useConfirm()
    const { toast } = useToast()

    // Dialog state
    const [isDialogOpen, setIsDialogOpen] = useState(false)
    const [editingRole, setEditingRole] = useState<Role | null>(null)
    const [viewingRole, setViewingRole] = useState<Role | null>(null)
    const [formName, setFormName] = useState('')
    const [formDescription, setFormDescription] = useState('')
    const [formPermissions, setFormPermissions] = useState<Set<string>>(new Set())
    const [formLoading, setFormLoading] = useState(false)
    const [formError, setFormError] = useState('')

    // View permissions dialog
    const [isViewOpen, setIsViewOpen] = useState(false)

    const loadRoles = useCallback(async () => {
        setLoading(true)
        try {
            const response = await api.get<{ items: Role[] }>('/roles')
            setRoles(response.items)
        } catch (error) {
            console.error('Failed to load roles:', error)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        loadRoles()
    }, [loadRoles])

    // --- CRUD handlers ---

    const handleOpenCreate = () => {
        setEditingRole(null)
        setFormName('')
        setFormDescription('')
        setFormPermissions(new Set())
        setFormError('')
        setIsDialogOpen(true)
    }

    const handleOpenEdit = (role: Role) => {
        setEditingRole(role)
        setFormName(role.name)
        setFormDescription(role.description || '')
        setFormPermissions(new Set(role.permissions))
        setFormError('')
        setIsDialogOpen(true)
    }

    const handleViewPermissions = (role: Role) => {
        setViewingRole(role)
        setIsViewOpen(true)
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setFormError('')

        if (!formName.trim()) {
            setFormError('Role name is required')
            return
        }

        setFormLoading(true)
        try {
            const payload = {
                name: formName.trim(),
                description: formDescription.trim() || undefined,
                permissions: Array.from(formPermissions),
            }

            if (editingRole) {
                await api.put(`/roles/${editingRole.id}`, payload)
                toast({ title: 'Role updated', description: `"${formName}" has been updated.` })
            } else {
                await api.post('/roles', payload)
                toast({ title: 'Role created', description: `"${formName}" has been created.` })
            }

            setIsDialogOpen(false)
            await loadRoles()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Failed to save role')
        } finally {
            setFormLoading(false)
        }
    }

    const handleDelete = async (role: Role) => {
        const confirmed = await confirm({
            title: 'Delete Role',
            description: `Are you sure you want to delete "${role.name}"? Users with this role will lose the associated permissions. This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return

        try {
            await api.delete(`/roles/${role.id}`)
            toast({ title: 'Role deleted', description: `"${role.name}" has been deleted.` })
            await loadRoles()
        } catch (error) {
            console.error('Failed to delete role:', error)
            toast({ title: 'Error', description: 'Failed to delete role', variant: 'destructive' })
        }
    }

    // --- Permission helpers ---

    const togglePermission = (perm: string) => {
        setFormPermissions(prev => {
            const next = new Set(prev)
            if (next.has(perm)) {
                next.delete(perm)
            } else {
                next.add(perm)
            }
            return next
        })
    }

    const toggleGroup = (group: PermissionGroup) => {
        const groupPerms = group.permissions.map(p => p.value)
        const allSelected = groupPerms.every(p => formPermissions.has(p))

        setFormPermissions(prev => {
            const next = new Set(prev)
            if (allSelected) {
                groupPerms.forEach(p => next.delete(p))
            } else {
                groupPerms.forEach(p => next.add(p))
            }
            return next
        })
    }

    const toggleAll = () => {
        const allSelected = ALL_PERMISSIONS.every(p => formPermissions.has(p))
        setFormPermissions(allSelected ? new Set() : new Set(ALL_PERMISSIONS))
    }

    // --- Computed ---

    const systemRoles = roles.filter(r => r.is_system)
    const customRoles = roles.filter(r => !r.is_system)

    return (
        <div className="p-6 space-y-6">
            {/* Create / Edit Role Dialog */}
            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
                    <form onSubmit={handleSubmit}>
                        <DialogHeader>
                            <DialogTitle>
                                {editingRole
                                    ? editingRole.is_system
                                        ? `Edit System Role: ${editingRole.name}`
                                        : 'Edit Role'
                                    : 'Create Role'}
                            </DialogTitle>
                            <DialogDescription>
                                {editingRole?.is_system
                                    ? 'System roles cannot be renamed or deleted. You may add additional permissions.'
                                    : editingRole
                                        ? 'Update role details and permissions.'
                                        : 'Create a new custom role with specific permissions.'}
                            </DialogDescription>
                        </DialogHeader>

                        <div className="grid gap-4 py-4">
                            {formError && (
                                <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 rounded-md border border-red-200 dark:border-red-900/20">
                                    {formError}
                                </div>
                            )}

                            <div className="grid gap-2">
                                <Label htmlFor="role-name">Name</Label>
                                <Input
                                    id="role-name"
                                    value={formName}
                                    onChange={(e) => setFormName(e.target.value)}
                                    placeholder="e.g. Incident Lead"
                                    required
                                    disabled={editingRole?.is_system}
                                />
                            </div>

                            <div className="grid gap-2">
                                <Label htmlFor="role-description">Description</Label>
                                <Textarea
                                    id="role-description"
                                    value={formDescription}
                                    onChange={(e) => setFormDescription(e.target.value)}
                                    placeholder="Brief description of this role's purpose"
                                    rows={2}
                                    disabled={editingRole?.is_system}
                                />
                            </div>

                            {/* Permissions */}
                            <div className="grid gap-2">
                                <div className="flex items-center justify-between">
                                    <Label>Permissions</Label>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs h-7"
                                        onClick={toggleAll}
                                    >
                                        {ALL_PERMISSIONS.every(p => formPermissions.has(p))
                                            ? 'Deselect All'
                                            : 'Select All'}
                                    </Button>
                                </div>

                                <div className="border rounded-md divide-y max-h-[40vh] overflow-y-auto">
                                    {PERMISSION_GROUPS.map((group) => {
                                        const groupPerms = group.permissions.map(p => p.value)
                                        const selectedCount = groupPerms.filter(p => formPermissions.has(p)).length
                                        const allSelected = selectedCount === groupPerms.length
                                        const someSelected = selectedCount > 0 && !allSelected

                                        return (
                                            <div key={group.entity} className="p-3">
                                                <div className="flex items-center gap-2 mb-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => toggleGroup(group)}
                                                        className="flex items-center justify-center h-4 w-4 rounded border border-input shrink-0 transition-colors hover:border-primary"
                                                        style={{
                                                            backgroundColor: allSelected
                                                                ? 'hsl(var(--primary))'
                                                                : someSelected
                                                                    ? 'hsl(var(--primary) / 0.3)'
                                                                    : 'transparent',
                                                            borderColor: allSelected || someSelected
                                                                ? 'hsl(var(--primary))'
                                                                : undefined,
                                                        }}
                                                    >
                                                        {allSelected && (
                                                            <Check className="h-3 w-3 text-primary-foreground" />
                                                        )}
                                                        {someSelected && (
                                                            <div className="h-1.5 w-1.5 rounded-sm bg-primary-foreground" />
                                                        )}
                                                    </button>
                                                    <span className="text-sm font-medium">{group.label}</span>
                                                    <Badge variant="outline" className="text-xs ml-auto">
                                                        {selectedCount}/{groupPerms.length}
                                                    </Badge>
                                                </div>
                                                <div className="flex flex-wrap gap-x-4 gap-y-1.5 pl-6">
                                                    {group.permissions.map((perm) => (
                                                        <label
                                                            key={perm.value}
                                                            className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer hover:text-foreground transition-colors"
                                                        >
                                                            <input
                                                                type="checkbox"
                                                                checked={formPermissions.has(perm.value)}
                                                                onChange={() => togglePermission(perm.value)}
                                                                className="rounded border-input h-3.5 w-3.5 accent-primary"
                                                            />
                                                            {perm.label}
                                                        </label>
                                                    ))}
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>

                                <p className="text-xs text-muted-foreground">
                                    {formPermissions.size} of {ALL_PERMISSIONS.length} permissions selected
                                </p>
                            </div>
                        </div>

                        <DialogFooter>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setIsDialogOpen(false)}
                                disabled={formLoading}
                            >
                                Cancel
                            </Button>
                            <Button type="submit" disabled={formLoading}>
                                {formLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                {editingRole ? 'Save Changes' : 'Create Role'}
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>

            {/* View Permissions Dialog (read-only) */}
            <Dialog open={isViewOpen} onOpenChange={setIsViewOpen}>
                <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Shield className="h-5 w-5" />
                            {viewingRole?.name} — Permissions
                        </DialogTitle>
                        <DialogDescription>
                            {viewingRole?.description || 'No description provided.'}
                            {viewingRole?.is_system && ' This is a system role.'}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="border rounded-md divide-y max-h-[50vh] overflow-y-auto">
                        {PERMISSION_GROUPS.map((group) => {
                            const groupPerms = group.permissions.map(p => p.value)
                            const granted = groupPerms.filter(p => viewingRole?.permissions.includes(p))
                            if (granted.length === 0) return null

                            return (
                                <div key={group.entity} className="p-3">
                                    <div className="flex items-center gap-2 mb-1.5">
                                        <span className="text-sm font-medium">{group.label}</span>
                                        <Badge variant="outline" className="text-xs">
                                            {granted.length}/{groupPerms.length}
                                        </Badge>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5 pl-0">
                                        {group.permissions.map((perm) => {
                                            const has = viewingRole?.permissions.includes(perm.value)
                                            return (
                                                <Badge
                                                    key={perm.value}
                                                    variant={has ? 'default' : 'outline'}
                                                    className={`text-xs ${!has ? 'opacity-30' : ''}`}
                                                >
                                                    {perm.label}
                                                </Badge>
                                            )
                                        })}
                                    </div>
                                </div>
                            )
                        })}
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setIsViewOpen(false)}>
                            Close
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-semibold">Roles</h1>
                    <p className="text-sm text-muted-foreground mt-1">Manage roles and permissions</p>
                </div>
                <Button onClick={handleOpenCreate}>
                    <Plus className="mr-2 h-4 w-4" />
                    Create Role
                </Button>
            </div>

            {/* Stats */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Roles</CardDescription>
                        <CardTitle className="text-2xl">{roles.length}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>System Roles</CardDescription>
                        <CardTitle className="text-2xl">{systemRoles.length}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Custom Roles</CardDescription>
                        <CardTitle className="text-2xl">{customRoles.length}</CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Roles Table */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Shield className="h-5 w-5" />
                                All Roles
                            </CardTitle>
                            <CardDescription>System roles are built-in and cannot be deleted</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : roles.length > 0 ? (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Description</TableHead>
                                    <TableHead>Permissions</TableHead>
                                    <TableHead>Type</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {roles.map((role) => (
                                    <TableRow key={role.id}>
                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                {role.is_system && (
                                                    <Lock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                                )}
                                                <span className="font-medium">{role.name}</span>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground max-w-[300px] truncate">
                                            {role.description || '\u2014'}
                                        </TableCell>
                                        <TableCell>
                                            <button
                                                onClick={() => handleViewPermissions(role)}
                                                className="inline-flex items-center gap-1 hover:underline"
                                            >
                                                <Badge variant="outline">
                                                    {role.permissions.length}
                                                </Badge>
                                            </button>
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant={role.is_system ? 'default' : 'outline'}>
                                                {role.is_system ? 'System' : 'Custom'}
                                            </Badge>
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
                                                    <DropdownMenuItem onClick={() => handleViewPermissions(role)}>
                                                        <Eye className="mr-2 h-4 w-4" />
                                                        View Permissions
                                                    </DropdownMenuItem>
                                                    {role.is_system ? (
                                                        <DropdownMenuItem onClick={() => handleOpenEdit(role)}>
                                                            <Pencil className="mr-2 h-4 w-4" />
                                                            Edit Permissions
                                                        </DropdownMenuItem>
                                                    ) : (
                                                        <>
                                                            <DropdownMenuItem onClick={() => handleOpenEdit(role)}>
                                                                <Pencil className="mr-2 h-4 w-4" />
                                                                Edit Role
                                                            </DropdownMenuItem>
                                                            <DropdownMenuSeparator />
                                                            <DropdownMenuItem
                                                                onClick={() => handleDelete(role)}
                                                                className="text-red-600 focus:text-red-600 focus:bg-red-50 dark:focus:bg-red-900/10"
                                                            >
                                                                <Trash2 className="mr-2 h-4 w-4" />
                                                                Delete Role
                                                            </DropdownMenuItem>
                                                        </>
                                                    )}
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
                                <Shield className="h-6 w-6 text-muted-foreground" />
                            </div>
                            <p className="font-medium mb-1">No roles found</p>
                            <p className="text-sm text-muted-foreground">
                                Create your first custom role to get started.
                            </p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
