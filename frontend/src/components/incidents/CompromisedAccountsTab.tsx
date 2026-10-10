"use client"

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
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
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { useAllPages, usePaginatedQuery } from '@/hooks/use-paginated-query'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { usePermission } from '@/components/auth/permission-gate'
import type { CompromisedAccount, CompromisedHost, VersionedRow } from '@/types'
import {
    User,
    Key,
    Eye,
    EyeOff,
    Copy,
    Check,
    Crown,
    Pencil,
    Trash2,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Timestamp } from '@/components/ui/timestamp'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'

type AccountRow = VersionedRow<CompromisedAccount>

const ACCOUNT_TYPES = [
    { value: 'domain', label: 'Domain' },
    { value: 'local', label: 'Local' },
    { value: 'admin', label: 'Admin' },
    { value: 'service', label: 'Service' },
    { value: 'ftp', label: 'FTP/Web' },
    { value: 'application', label: 'Application' },
    { value: 'other', label: 'Other' },
]

const ACCOUNT_STATUSES = [
    { value: 'active', label: 'Active' },
    { value: 'disabled', label: 'Disabled' },
    { value: 'reset', label: 'Reset' },
    { value: 'deleted', label: 'Deleted' },
]

const EMPTY_FORM = {
    datetime_seen: '',
    account_name: '',
    password: '',
    clear_password: false,
    host_id: '',
    host_system: '',
    sid: '',
    account_type: 'domain',
    domain: '',
    is_privileged: false,
    status: 'active',
    notes: '',
}

export function CompromisedAccountsTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
    const confirm = useConfirm()
    const canReveal = usePermission('compromised_accounts:reveal')
    const endpoint = `/incidents/${incidentId}/accounts`
    const query = usePaginatedQuery<AccountRow>({
        endpoint,
        urlKey: 'accounts',
        focus: focusRowId,
        live: 'account',
    })
    const [showModal, setShowModal] = useState(false)
    const [editingAccount, setEditingAccount] = useState<AccountRow | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
    const [revealedPasswords, setRevealedPasswords] = useState<Record<string, string>>({})
    const [revealingId, setRevealingId] = useState<string | null>(null)
    const [copiedId, setCopiedId] = useState<string | null>(null)
    const [form, setForm] = useState(EMPTY_FORM)

    // Host correlation picker: every host, loaded only while the modal is open.
    const hostsQuery = useAllPages<CompromisedHost>(`/incidents/${incidentId}/hosts`, {
        live: 'host',
        enabled: showModal,
    })
    const hosts = hostsQuery.items

    const resetForm = () => {
        setForm(EMPTY_FORM)
        setEditingAccount(null)
    }

    const handleOpenModal = (account?: AccountRow) => {
        if (account) {
            setEditingAccount(account)
            setForm({
                datetime_seen: account.datetime_seen || '',
                account_name: account.account_name,
                // Never pre-fill: the API only returns the masked value
                password: '',
                clear_password: false,
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
        setIsSubmitting(true)
        try {
            const payload: Record<string, unknown> = {
                datetime_seen: form.datetime_seen || undefined,
                account_name: form.account_name,
                host_id: form.host_id || null,
                host_system: form.host_system || null,
                sid: form.sid || null,
                account_type: form.account_type,
                domain: form.domain || null,
                is_privileged: form.is_privileged,
                status: form.status,
                notes: form.notes || null,
            }
            // Only send a password the user actually typed; an empty field leaves
            // the stored password unchanged. Clearing needs the explicit checkbox.
            if (form.password) {
                payload.password = form.password
            }
            if (editingAccount && form.clear_password) {
                payload.clear_password = true
            }

            if (editingAccount) {
                await api.put(`${endpoint}/${editingAccount.id}`, payload, { ifMatch: editingAccount.version })
                // A changed password must be revealed again.
                setRevealedPasswords((prev) => {
                    const next = { ...prev }
                    delete next[editingAccount.id]
                    return next
                })
                setShowPasswords((prev) => ({ ...prev, [editingAccount.id]: false }))
            } else {
                await api.post(endpoint, payload)
            }

            setShowModal(false)
            resetForm()
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, editingAccount ? 'save the account' : 'add the account')
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (account: AccountRow) => {
        if (!(await confirmDelete(confirm, 'account', account.account_name))) return
        try {
            await api.delete(`${endpoint}/${account.id}`, undefined, { ifMatch: account.version })
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, 'delete the account')
        }
    }

    /** Reveal ONE account's password (single-account endpoint, one audit event). */
    const togglePassword = async (id: string) => {
        if (showPasswords[id]) {
            setShowPasswords((prev) => ({ ...prev, [id]: false }))
            return
        }
        if (revealedPasswords[id] !== undefined) {
            setShowPasswords((prev) => ({ ...prev, [id]: true }))
            return
        }
        setRevealingId(id)
        try {
            const account = await api.get<CompromisedAccount>(`${endpoint}/${id}?reveal=true`)
            const password = account.password && account.password !== '********' ? account.password : ''
            setRevealedPasswords((prev) => ({ ...prev, [id]: password }))
            setShowPasswords((prev) => ({ ...prev, [id]: true }))
        } catch (error) {
            notifyError(error, 'reveal the password')
        } finally {
            setRevealingId(null)
        }
    }

    const copyToClipboard = async (text: string, id: string) => {
        try {
            await navigator.clipboard.writeText(text)
            setCopiedId(id)
            setTimeout(() => setCopiedId(null), 2000)
        } catch (error) {
            notifyError(error, 'copy the password')
        }
    }

    const renderPassword = (account: AccountRow) => {
        if (!account.has_password) {
            return <span className="text-muted-foreground text-xs italic">No password</span>
        }
        const shown = !!showPasswords[account.id]
        const revealed = revealedPasswords[account.id]
        return (
            <div className="flex items-center gap-2">
                {canReveal && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        aria-label={shown ? 'Hide password' : 'Reveal password'}
                        onClick={() => void togglePassword(account.id)}
                        disabled={revealingId === account.id}
                    >
                        {revealingId === account.id ? (
                            <span className="h-3 w-3 border border-current border-t-transparent rounded-full animate-spin inline-block" />
                        ) : shown ? (
                            <EyeOff className="h-3 w-3" />
                        ) : (
                            <Eye className="h-3 w-3" />
                        )}
                    </Button>
                )}
                <span className="font-mono text-xs">
                    {shown ? (revealed || '********') : '••••••••'}
                </span>
                {shown && !!revealed && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        aria-label="Copy password"
                        onClick={() => void copyToClipboard(revealed, account.id)}
                    >
                        {copiedId === account.id ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                    </Button>
                )}
            </div>
        )
    }

    const columns: DataTableColumn<AccountRow>[] = [
        {
            id: 'account_name', header: 'Account Name', sortKey: 'account_name', cell: (account) => (
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
            ),
        },
        {
            id: 'type', header: 'Type', hideBelow: 'md', cell: (account) => (
                <Badge variant="outline" className="capitalize">{account.account_type}</Badge>
            ),
        },
        {
            id: 'host', header: 'Host System', hideBelow: 'md',
            cell: (account) => account.host?.hostname || account.host_system || '-',
        },
        { id: 'password', header: 'Password', cell: renderPassword },
        {
            id: 'datetime_seen', header: 'Date Seen', sortKey: 'datetime_seen', hideBelow: 'sm',
            className: 'text-muted-foreground text-sm whitespace-nowrap',
            cell: (account) => <Timestamp value={account.datetime_seen} />,
        },
        {
            id: 'status', header: 'Status', sortKey: 'status', cell: (account) => (
                <Badge
                    className={
                        account.status === 'active'
                            ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border-red-500/30'
                            : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                    }
                >
                    {account.status}
                </Badge>
            ),
        },
    ]

    return (
        <div className="space-y-4">
            <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="account" />
            <DataTable
                query={query}
                columns={columns}
                getRowId={(a) => a.id}
                rowLabel={(a) => a.account_name}
                ariaLabel="Compromised accounts"
                searchPlaceholder="Search accounts, hosts, domains..."
                toolbar={
                    <>
                        <FilterSelect
                            label="Type"
                            allLabel="All types"
                            value={query.state.filters.account_type}
                            onChange={(v) => query.setFilter('account_type', v)}
                            options={ACCOUNT_TYPES}
                        />
                        <FilterSelect
                            label="Status"
                            allLabel="All statuses"
                            value={query.state.filters.status}
                            onChange={(v) => query.setFilter('status', v)}
                            options={ACCOUNT_STATUSES}
                        />
                    </>
                }
                primaryAction={{ label: 'Add Account', onSelect: () => handleOpenModal(), permission: 'accounts:create' }}
                rowActions={(a) => [
                    { label: 'Edit', icon: Pencil, onSelect: () => handleOpenModal(a), permission: 'accounts:update' },
                    { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDelete(a), permission: 'accounts:delete' },
                ]}
                focusedRowId={focusRowId}
                empty={{
                    title: 'No compromised accounts',
                    description: 'Record user and service accounts that have been compromised or are under investigation.',
                }}
            />

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
                                <DateTimeInput
                                    id="datetime"
                                    value={form.datetime_seen}
                                    onChange={(iso) => setForm({ ...form, datetime_seen: iso ?? '' })}
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
                                    placeholder={editingAccount?.has_password
                                        ? 'Leave blank to keep current password'
                                        : 'Enter compromised password or hash...'}
                                    value={form.password}
                                    onChange={(e) => setForm({ ...form, password: e.target.value, clear_password: false })}
                                    className="pl-10"
                                    variant="glass"
                                />
                            </div>
                            {!!editingAccount?.has_password && (
                                <div className="flex items-center gap-2">
                                    <Checkbox
                                        id="clear_password"
                                        checked={form.clear_password}
                                        disabled={!!form.password}
                                        onCheckedChange={(checked) => setForm({ ...form, clear_password: checked === true })}
                                    />
                                    <Label htmlFor="clear_password" className="text-xs text-muted-foreground font-normal">
                                        Clear stored password
                                    </Label>
                                </div>
                            )}
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
                                    <SelectValue placeholder={hostsQuery.isLoading ? 'Loading hosts...' : 'Select Host...'} />
                                </SelectTrigger>
                                <SelectContent>
                                    {hosts.map(host => (
                                        <SelectItem key={host.id} value={host.id}>
                                            {host.hostname}{host.ip_address ? ` (${host.ip_address})` : ''}
                                        </SelectItem>
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
