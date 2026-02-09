"use client"

import { useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
    DialogBody,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    GlassTable,
    TableEmpty,
} from '@/components/ui/table'
import { SkeletonTableRow } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { CompromisedAccount, CompromisedHost } from '@/types'
import {
    Plus,
    User,
    Key,
    Eye,
    EyeOff,
    Shield,
    Search,
    Filter,
    MoreHorizontal,
    Copy,
    Check,
    Crown,
    Trash2,
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'

interface CompromisedAccountsTabProps {
    incidentId: string
}

export function CompromisedAccountsTab({ incidentId }: CompromisedAccountsTabProps) {
    const confirm = useConfirm()
    const [accounts, setAccounts] = useState<CompromisedAccount[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [typeFilter, setTypeFilter] = useState<string>('all')
    const [showModal, setShowModal] = useState(false)
    const [editingAccount, setEditingAccount] = useState<CompromisedAccount | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
    const [revealedPasswords, setRevealedPasswords] = useState<Record<string, string>>({})
    const [revealingId, setRevealingId] = useState<string | null>(null)
    const [copiedId, setCopiedId] = useState<string | null>(null)

    const [form, setForm] = useState({
        datetime_seen: '',
        account_name: '',
        password: '',
        host_id: '',
        host_system: '',
        sid: '',
        account_type: 'domain',
        domain: '',
        is_privileged: false,
        status: 'active',
        notes: '',
    })
    const [hosts, setHosts] = useState<CompromisedHost[]>([])

    useEffect(() => {
        if (incidentId) {
            loadAccounts()
        }
    }, [incidentId])

    const loadAccounts = async () => {
        setIsLoading(true)
        try {
            const [accountsRes, hostsRes] = await Promise.all([
                api.get<{ items: CompromisedAccount[] }>(`/incidents/${incidentId}/accounts`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
            ])
            setAccounts(accountsRes.items)
            setHosts(hostsRes.items)
        } catch (error) {
            console.error('Failed to load accounts:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const resetForm = () => {
        setForm({
            datetime_seen: '',
            account_name: '',
            password: '',
            host_id: '',
            host_system: '',
            sid: '',
            account_type: 'domain',
            domain: '',
            is_privileged: false,
            status: 'active',
            notes: '',
        })
        setEditingAccount(null)
    }

    const handleOpenModal = (account?: CompromisedAccount) => {
        if (account) {
            setEditingAccount(account)
            setForm({
                datetime_seen: account.datetime_seen?.slice(0, 16) || '', // Format for datetime-local
                account_name: account.account_name,
                password: account.password || '',
                host_id: account.host_id || '',
                host_system: account.host_system || '',
                sid: account.sid || '',
                account_type: account.account_type || 'domain',
                domain: account.domain || '',
                is_privileged: account.is_privileged,
                status: account.status || 'active',
                notes: account.notes || '',
            })
        } else {
            resetForm()
        }
        setShowModal(true)
    }

    const handleSubmit = async () => {
        if (!form.account_name) return
        // datetime_seen is required for creation, but for editing we might keep existing

        setIsSubmitting(true)
        try {
            const payload = {
                datetime_seen: form.datetime_seen || undefined,
                account_name: form.account_name,
                password: form.password || null,
                host_id: form.host_id || null,
                host_system: form.host_system || null,
                sid: form.sid || null,
                account_type: form.account_type,
                domain: form.domain || null,
                is_privileged: form.is_privileged,
                status: form.status,
                notes: form.notes || null,
            }
            // Ensure datetime_seen is present for new accounts
            if (!editingAccount && !payload.datetime_seen) {
                // Fallback or validation error - simplified for now
            }

            if (editingAccount) {
                await api.put(`/incidents/${incidentId}/accounts/${editingAccount.id}`, payload)
            } else {
                await api.post(`/incidents/${incidentId}/accounts`, payload)
            }

            setShowModal(false)
            resetForm()
            loadAccounts()
        } catch (error) {
            console.error('Failed to save account:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Account',
            description: 'Are you sure you want to delete this compromised account?',
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        try {
            await api.delete(`/incidents/${incidentId}/accounts/${id}`)
            loadAccounts()
        } catch (error) {
            console.error('Failed to delete:', error)
        }
    }

    const togglePassword = async (id: string) => {
        if (showPasswords[id]) {
            // Hide password
            setShowPasswords((prev) => ({ ...prev, [id]: false }))
            return
        }
        // If already revealed from API, just show it
        if (revealedPasswords[id]) {
            setShowPasswords((prev) => ({ ...prev, [id]: true }))
            return
        }
        // Fetch the decrypted password from the API
        setRevealingId(id)
        try {
            const res = await api.get<{ items: CompromisedAccount[] }>(
                `/incidents/${incidentId}/accounts?reveal=true`
            )
            const account = res.items.find((a) => a.id === id)
            if (account?.password && account.password !== '********') {
                setRevealedPasswords((prev) => ({ ...prev, [id]: account.password! }))
                setShowPasswords((prev) => ({ ...prev, [id]: true }))
            } else {
                // User may not have permission to reveal
                setShowPasswords((prev) => ({ ...prev, [id]: true }))
            }
        } catch (error) {
            console.error('Failed to reveal password:', error)
        } finally {
            setRevealingId(null)
        }
    }

    const copyToClipboard = (text: string, id: string) => {
        navigator.clipboard.writeText(text)
        setCopiedId(id)
        setTimeout(() => setCopiedId(null), 2000)
    }

    const filteredAccounts = accounts.filter((account) => {
        const matchesSearch =
            account.account_name.toLowerCase().includes(search.toLowerCase()) ||
            account.host_system?.toLowerCase().includes(search.toLowerCase()) ||
            account.domain?.toLowerCase().includes(search.toLowerCase())
        const matchesType = typeFilter === 'all' || account.account_type === typeFilter
        return matchesSearch && matchesType
    })

    return (
        <div className="space-y-4">
            {/* Filters & Action */}
            <Card>
                <CardContent className="p-4">
                    <div className="flex flex-col lg:flex-row gap-4 justify-between">
                        <div className="flex flex-col lg:flex-row gap-4 flex-1">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Search accounts, hosts, domains..."
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    className="pl-10"
                                    variant="glass"
                                />
                            </div>
                            <Select value={typeFilter} onValueChange={setTypeFilter}>
                                <SelectTrigger className="w-[180px]">
                                    <Filter className="mr-2 h-4 w-4" />
                                    <SelectValue placeholder="All Types" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Types</SelectItem>
                                    <SelectItem value="domain">Domain</SelectItem>
                                    <SelectItem value="local">Local</SelectItem>
                                    <SelectItem value="service">Service</SelectItem>
                                    <SelectItem value="admin">Admin</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button onClick={() => handleOpenModal()}>
                            <Plus className="mr-2 h-4 w-4" />
                            Add Account
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Accounts Table */}
            <Card>
                <CardContent className="p-0">
                    <GlassTable className="border-0">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Account Name</TableHead>
                                    <TableHead>Type</TableHead>
                                    <TableHead>Host System</TableHead>
                                    <TableHead>Password</TableHead>
                                    <TableHead>Date Seen</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead className="w-[80px]">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {isLoading ? (
                                    <>
                                        <SkeletonTableRow columns={7} />
                                        <SkeletonTableRow columns={7} />
                                        <SkeletonTableRow columns={7} />
                                    </>
                                ) : filteredAccounts.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={7} className="h-[300px]">
                                            <TableEmpty
                                                icon={<User className="h-10 w-10" />}
                                                title={search || typeFilter !== 'all' ? 'No matching accounts' : 'No compromised accounts'}
                                                description={
                                                    search || typeFilter !== 'all'
                                                        ? 'Try adjusting your filters'
                                                        : 'Record any compromised accounts discovered during the investigation'
                                                }
                                                action={
                                                    !search && typeFilter === 'all' && (
                                                        <Button size="sm" onClick={() => handleOpenModal()}>
                                                            <Plus className="mr-2 h-4 w-4" />
                                                            Add Account
                                                        </Button>
                                                    )
                                                }
                                            />
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    filteredAccounts.map((account) => (
                                        <TableRow key={account.id} className="group">
                                            <TableCell>
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${account.is_privileged
                                                        ? 'bg-red-500/20 text-red-500'
                                                        : 'bg-white/5 text-muted-foreground'
                                                        }`}>
                                                        {account.is_privileged ? <Crown className="h-4 w-4" /> : <User className="h-4 w-4" />}
                                                    </div>
                                                    <div>
                                                        <div className="font-medium text-foreground flex items-center gap-2">
                                                            {account.domain && <span className="text-muted-foreground">{account.domain}\</span>}
                                                            {account.account_name}
                                                        </div>
                                                        {account.sid && <div className="text-xs text-muted-foreground">{account.sid}</div>}
                                                    </div>
                                                </div>
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant="outline" className="capitalize">
                                                    {account.account_type}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                {account.host_id ? (
                                                    // If correlated with a host object, display nicely
                                                    hosts.find(h => h.id === account.host_id)?.hostname || account.host_system || '-'
                                                ) : (
                                                    account.host_system || '-'
                                                )}
                                            </TableCell>
                                            <TableCell>
                                                {account.has_password ? (
                                                    <div className="flex items-center gap-2">
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="h-6 w-6 p-0"
                                                            onClick={() => togglePassword(account.id)}
                                                            disabled={revealingId === account.id}
                                                        >
                                                            {revealingId === account.id ? (
                                                                <span className="h-3 w-3 border border-current border-t-transparent rounded-full animate-spin inline-block" />
                                                            ) : showPasswords[account.id] ? (
                                                                <EyeOff className="h-3 w-3" />
                                                            ) : (
                                                                <Eye className="h-3 w-3" />
                                                            )}
                                                        </Button>
                                                        <span className="font-mono text-xs">
                                                            {showPasswords[account.id]
                                                                ? (revealedPasswords[account.id] || account.password || '********')
                                                                : '••••••••'}
                                                        </span>
                                                        {showPasswords[account.id] && revealedPasswords[account.id] && (
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                                                onClick={() => copyToClipboard(revealedPasswords[account.id], account.id)}
                                                            >
                                                                {copiedId === account.id ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                                                            </Button>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span className="text-muted-foreground text-xs italic">No password</span>
                                                )}
                                            </TableCell>
                                            <TableCell className="text-muted-foreground text-sm whitespace-nowrap">
                                                {formatDateTime(account.datetime_seen)}
                                            </TableCell>
                                            <TableCell>
                                                <Badge
                                                    className={
                                                        account.status === 'active'
                                                            ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border-red-500/30'
                                                            : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                                                    }
                                                >
                                                    {account.status}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => handleOpenModal(account)}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 p-0"
                                                    >
                                                        <MoreHorizontal className="h-4 w-4" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => handleDelete(account.id)}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 p-0 text-destructive hover:text-destructive"
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </GlassTable>
                </CardContent>
            </Card>

            {/* Add/Edit Account Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>{editingAccount ? 'Edit' : 'Add'} Compromised Account</DialogTitle>
                        <DialogDescription>
                            {editingAccount ? 'Update details of the compromised account' : 'Record details of a compromised user or service account'}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogBody className="space-y-4 max-h-[60vh] overflow-y-auto">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="datetime">Date Seen *</Label>
                                <Input
                                    id="datetime"
                                    type="datetime-local"
                                    value={form.datetime_seen}
                                    onChange={(e) => setForm({ ...form, datetime_seen: e.target.value })}
                                    variant="glass"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="type">Account Type</Label>
                                <Select
                                    value={form.account_type}
                                    onValueChange={(value) => setForm({ ...form, account_type: value })}
                                >
                                    <SelectTrigger variant="glass">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="domain">Domain User</SelectItem>
                                        <SelectItem value="local">Local User</SelectItem>
                                        <SelectItem value="admin">Administrator</SelectItem>
                                        <SelectItem value="service">Service Account</SelectItem>
                                        <SelectItem value="ftp">FTP/Web</SelectItem>
                                        <SelectItem value="other">Other</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="domain">Domain (Optional)</Label>
                                <Input
                                    id="domain"
                                    placeholder="CORP"
                                    value={form.domain}
                                    onChange={(e) => setForm({ ...form, domain: e.target.value })}
                                    variant="glass"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="name">Account Name *</Label>
                                <Input
                                    id="name"
                                    placeholder="jdoe"
                                    value={form.account_name}
                                    onChange={(e) => setForm({ ...form, account_name: e.target.value })}
                                    variant="glass"
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="sid">SID (Optional)</Label>
                            <Input
                                id="sid"
                                placeholder="S-1-5-21-..."
                                value={form.sid}
                                onChange={(e) => setForm({ ...form, sid: e.target.value })}
                                variant="glass"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="password">Password (if compromised)</Label>
                            <div className="relative">
                                <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    id="password"
                                    type="text"
                                    placeholder="Enter compromised password or hash..."
                                    value={form.password}
                                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                                    className="pl-10"
                                    variant="glass"
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="host_id">Observed on Host (Correlation)</Label>
                            <Select
                                value={form.host_id}
                                onValueChange={(value) => {
                                    const host = hosts.find(h => h.id === value)
                                    setForm({ ...form, host_id: value, host_system: host?.hostname || '' })
                                }}
                            >
                                <SelectTrigger variant="glass">
                                    <SelectValue placeholder="Select Host..." />
                                </SelectTrigger>
                                <SelectContent>
                                    {hosts.map(host => (
                                        <SelectItem key={host.id} value={host.id}>{host.hostname} ({host.ip_address})</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="notes">Notes</Label>
                            <Textarea
                                id="notes"
                                placeholder="Additional details..."
                                value={form.notes}
                                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                                variant="glass"
                            />
                        </div>

                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="privileged"
                                    checked={form.is_privileged}
                                    onChange={(e) => setForm({ ...form, is_privileged: e.target.checked })}
                                    className="w-4 h-4 rounded border-white/20 bg-white/5"
                                />
                                <Label htmlFor="privileged" className="text-sm font-normal cursor-pointer">
                                    Privileged / Admin Account
                                </Label>
                            </div>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowModal(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSubmit} loading={isSubmitting}>
                            {editingAccount ? 'Save Changes' : 'Add Account'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
