"use client"

/**
 * Evidence tab: the incident's evidence register and chain of custody
 * (replaces the old Artifacts tab; `?tab=artifacts` aliases here).
 *
 * - Server-paged DataTable on `usePaginatedQuery` (`live: 'evidence_item'`,
 *   filters and search in the URL under `evidence.*`).
 * - Uploading a file registers an item; "Register evidence" records physical
 *   or metadata-only items. Both need `artifacts:upload`.
 * - The toolbar badge is the incident-wide chain verdict, verified lazily.
 * - Clicking a row opens the item drawer (details, hashes, custody timeline,
 *   files, actions).
 * - Register exports need `incidents:export`.
 */
import { useState, type DragEvent } from 'react'
import { Check, Copy, GitBranch, Lock, Shield, ShieldAlert, ShieldCheck, ShieldX, Upload } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Switch } from '@/components/ui/switch'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { evidenceBase } from '@/lib/endpoints/evidence'
import { notifyError } from '@/lib/errors'
import { useAuthStore } from '@/lib/store'
import { cn } from '@/lib/utils'
import type { EvidenceItem } from '@/types'
import { FocusNotice, type IncidentTabBaseProps } from '../table-helpers'
import { ChainStatusBadge } from './ChainStatusBadge'
import { EvidenceDetailSheet, type EvidenceDialogState } from './EvidenceDetailSheet'
import { EvidenceExportMenu } from './EvidenceExportMenu'
import { EvidenceUploadDialog } from './EvidenceUploadDialog'
import { RegisterEvidenceDialog } from './RegisterEvidenceDialog'
import { useChainVerification } from './use-chain-verification'
import {
  CUSTODY_STATE_LABELS,
  EVIDENCE_TYPE_LABELS,
  custodyStateLabel,
  evidenceTypeLabel,
  itemActions,
  primaryHash,
  shortHash,
} from './evidence-helpers'
import { optionsFrom } from './form-parts'

const TYPE_OPTIONS = optionsFrom(EVIDENCE_TYPE_LABELS)
const STATE_OPTIONS = optionsFrom(CUSTODY_STATE_LABELS)
const HOLD_OPTIONS = [
  { value: 'true', label: 'Under legal hold' },
  { value: 'false', label: 'No hold' },
]
const VERIFICATION_OPTIONS = [
  { value: 'match', label: 'Hash verified' },
  { value: 'mismatch', label: 'Hash mismatch' },
  { value: 'none', label: 'Never verified' },
]

const STATE_VARIANT = {
  in_storage: 'success',
  checked_out: 'warning',
  transferred: 'info',
  disposed: 'default',
} as const

function HashCell({ item }: { item: EvidenceItem }) {
  const [copied, setCopied] = useState(false)
  const h = primaryHash(item)
  if (!h) return <span className="text-muted-foreground">No hash</span>
  return (
    <div className="flex items-center gap-1 font-mono text-xs">
      <span title={`${h.algorithm.toUpperCase()} ${h.value}`}>{shortHash(h.value, 8, 4)}</span>
      <Button
        variant="ghost"
        size="icon-sm"
        className="h-5 w-5"
        aria-label={`Copy ${h.algorithm.toUpperCase()} of ${item.evidence_number}`}
        onClick={async (e) => {
          e.stopPropagation()
          try {
            await navigator.clipboard.writeText(h.value)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          } catch (err) {
            notifyError(err, 'copy the hash')
          }
        }}
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      </Button>
    </div>
  )
}

export function EvidenceTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
  const endpoint = evidenceBase(incidentId)
  const canWrite = usePermission('artifacts:upload')
  const myId = useAuthStore((s) => s.user?.id)
  const query = usePaginatedQuery<EvidenceItem>({
    endpoint,
    urlKey: 'evidence',
    focus: focusRowId,
    live: 'evidence_item',
    defaults: { sort: 'sequence_number' },
  })
  const chain = useChainVerification(incidentId)

  const [openId, setOpenId] = useState<string | null>(focusRowId ?? null)
  const [prevFocus, setPrevFocus] = useState(focusRowId ?? null)
  if ((focusRowId ?? null) !== prevFocus) {
    setPrevFocus(focusRowId ?? null)
    if (focusRowId) setOpenId(focusRowId)
  }
  const [initialAction, setInitialAction] = useState<EvidenceDialogState>(null)
  const [registering, setRegistering] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [dropped, setDropped] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)

  const open = (item: EvidenceItem, action: EvidenceDialogState = null) => {
    setInitialAction(action)
    setOpenId(item.id)
  }

  const brokenIds = new Set(
    Object.entries(chain.data?.items ?? {})
      .filter(([, v]) => v.breaks.length > 0)
      .map(([id]) => id)
  )
  const chainBad = chain.data && chain.data.status !== 'intact' && chain.data.status !== 'intact_with_unsigned_legacy'

  const onDragOver = (e: DragEvent) => {
    if (!canWrite || !Array.from(e.dataTransfer.types).includes('Files')) return
    e.preventDefault()
    setDragging(true)
  }
  const onDrop = (e: DragEvent) => {
    if (!canWrite) return
    setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length === 0) return
    e.preventDefault()
    setDropped(files)
    setUploadOpen(true)
  }

  const columns: DataTableColumn<EvidenceItem>[] = [
    {
      id: 'number',
      header: 'EV #',
      sortKey: 'sequence_number',
      cell: (i) => <span className="font-mono text-xs font-semibold">{i.evidence_number}</span>,
    },
    {
      id: 'title',
      header: 'Item',
      sortKey: 'title',
      cell: (i) => (
        <div className="min-w-0">
          <div className={cn('flex items-center gap-2 font-medium', i.voided_at && 'line-through opacity-60')}>
            <span className="truncate" title={i.title}>{i.title}</span>
            {i.voided_at && <Badge variant="destructive">Voided</Badge>}
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            {evidenceTypeLabel(i.evidence_type)}
            {i.parent && (
              <span className="inline-flex items-center gap-0.5" title={`Derived from ${i.parent.evidence_number} ${i.parent.title}`}>
                · <GitBranch className="h-3 w-3" aria-hidden /> from {i.parent.evidence_number}
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      id: 'identifiers',
      header: 'Serial / seal',
      hideBelow: 'lg',
      cell: (i) => (
        <div className="text-xs">
          <div className="font-mono">{i.serial_number || '—'}</div>
          {i.seal_number && <div className="text-muted-foreground">Seal {i.seal_number}</div>}
        </div>
      ),
    },
    {
      id: 'state',
      header: 'Custody',
      cell: (i) => <Badge variant={STATE_VARIANT[i.custody_state] ?? 'default'}>{custodyStateLabel(i.custody_state)}</Badge>,
    },
    {
      id: 'holder',
      header: 'Holder / location',
      hideBelow: 'md',
      cell: (i) => (
        <div className="min-w-0 text-xs">
          <div className="truncate">{i.holder?.type === 'storage' ? 'In storage' : i.holder?.name || '—'}</div>
          {i.storage_location && i.holder?.type === 'storage' && (
            <div className="truncate text-muted-foreground" title={i.storage_location}>{i.storage_location}</div>
          )}
        </div>
      ),
    },
    { id: 'hash', header: 'Hash', hideBelow: 'lg', cell: (i) => <HashCell item={i} /> },
    {
      id: 'acquired',
      header: 'Acquired',
      sortKey: 'acquired_at',
      hideBelow: 'lg',
      cell: (i) => (i.acquired_at ? <Timestamp value={i.acquired_at} seconds={false} className="text-xs" /> : <span className="text-muted-foreground">—</span>),
    },
    {
      id: 'flags',
      header: 'Status',
      cell: (i) => (
        <div className="flex items-center gap-1.5">
          {i.under_legal_hold && (
            <span title="Under legal hold" className="inline-flex text-amber-600 dark:text-amber-400">
              <Lock className="h-4 w-4" aria-hidden />
              <span className="sr-only">Under legal hold</span>
            </span>
          )}
          {i.last_verification_result === 'match' && (
            <span title="Hash verified" className="inline-flex text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="h-4 w-4" aria-hidden />
              <span className="sr-only">Hash verified</span>
            </span>
          )}
          {i.last_verification_result === 'mismatch' && (
            <span title="Hash mismatch" className="inline-flex text-destructive">
              <ShieldX className="h-4 w-4" aria-hidden />
              <span className="sr-only">Hash mismatch</span>
            </span>
          )}
          {!i.last_verification_result && (
            <span title="Hash never verified" className="inline-flex text-muted-foreground">
              <Shield className="h-4 w-4" aria-hidden />
              <span className="sr-only">Hash never verified</span>
            </span>
          )}
          {brokenIds.has(i.id) && (
            <span title="Custody chain broken" className="inline-flex text-destructive">
              <ShieldAlert className="h-4 w-4" aria-hidden />
              <span className="sr-only">Custody chain broken</span>
            </span>
          )}
        </div>
      ),
    },
  ]

  const rowActions = (i: EvidenceItem): RowAction[] => {
    const can = itemActions(i)
    return [
      { label: 'Open details', onSelect: () => open(i) },
      { label: 'Check out', onSelect: () => open(i, { type: 'custody', mode: 'check_out' }), permission: 'artifacts:upload', disabled: !can.checkOut },
      { label: 'Check in', onSelect: () => open(i, { type: 'custody', mode: 'check_in' }), permission: 'artifacts:upload', disabled: !can.checkIn },
      { label: 'Transfer', onSelect: () => open(i, { type: 'custody', mode: 'transfer' }), permission: 'artifacts:upload', disabled: !can.transfer },
      { label: 'Dispose', onSelect: () => open(i, { type: 'disposeVoid', mode: 'dispose' }), permission: 'artifacts:delete', destructive: true, disabled: !can.dispose },
      { label: 'Void', onSelect: () => open(i, { type: 'disposeVoid', mode: 'void' }), permission: 'artifacts:delete', destructive: true, disabled: !can.void },
    ]
  }

  return (
    <div
      className={cn('space-y-4 rounded-lg', dragging && 'ring-2 ring-primary/50')}
      onDragOver={onDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="evidence item" />
      {chainBad && (
        <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
          <span>
            {chain.data!.status === 'unverifiable'
              ? 'The custody signing key changed, so entries signed before cannot be verified here.'
              : `The custody ledger failed verification (${chain.data!.breaks.length} problem${chain.data!.breaks.length === 1 ? '' : 's'}). Treat affected evidence as unverified and open the item for details.`}
          </span>
        </div>
      )}
      <DataTable
        query={query}
        columns={columns}
        getRowId={(i) => i.id}
        ariaLabel="Evidence register"
        searchPlaceholder="Search EV number, title, serial, seal or hash…"
        onRowClick={(i) => open(i)}
        focusedRowId={focusRowId}
        toolbar={
          <>
            <FilterSelect label="Types" allLabel="All types" value={query.state.filters.type} onChange={(v) => query.setFilter('type', v)} options={TYPE_OPTIONS} />
            <FilterSelect label="Custody" allLabel="Any custody state" value={query.state.filters.custody_state} onChange={(v) => query.setFilter('custody_state', v)} options={STATE_OPTIONS} />
            <FilterSelect label="Legal hold" allLabel="Any hold status" value={query.state.filters.legal_hold} onChange={(v) => query.setFilter('legal_hold', v)} options={HOLD_OPTIONS} />
            <FilterSelect label="Verification" allLabel="Any verification" value={query.state.filters.verification} onChange={(v) => query.setFilter('verification', v)} options={VERIFICATION_OPTIONS} />
            <FilterSelect
              label="Holder"
              allLabel="Any holder"
              value={query.state.filters.holder_user_id}
              onChange={(v) => query.setFilter('holder_user_id', v)}
              options={myId ? [{ value: myId, label: 'Held by me' }] : []}
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Switch
                checked={query.state.filters.include_voided === 'true'}
                onCheckedChange={(on) => query.setFilter('include_voided', on ? 'true' : undefined)}
                aria-label="Include voided items"
              />
              Voided
            </label>
            <ChainStatusBadge
              status={chain.status}
              onClick={() => void chain.verify()}
              detail={chain.data?.incident_chain?.head_seq != null ? `Incident ledger head #${chain.data.incident_chain.head_seq}` : undefined}
            />
            {canWrite && (
              <Button variant="outline" size="sm" onClick={() => { setDropped([]); setUploadOpen(true) }}>
                <Upload className="h-4 w-4" />
                Upload file
              </Button>
            )}
            <EvidenceExportMenu incidentId={incidentId} />
          </>
        }
        primaryAction={{ label: 'Register evidence', onSelect: () => setRegistering(true), permission: 'artifacts:upload' }}
        rowActions={rowActions}
        empty={{
          title: 'No evidence registered',
          description:
            'Register physical or digital evidence, or upload files, to keep a hash-verified, tamper-evident chain of custody for this incident.',
        }}
      />

      <EvidenceDetailSheet
        incidentId={incidentId}
        itemId={openId}
        row={query.items.find((i) => i.id === openId) ?? null}
        initialAction={initialAction}
        onClose={() => {
          setOpenId(null)
          setInitialAction(null)
        }}
        onOpenItem={(id) => {
          setInitialAction(null)
          setOpenId(id)
        }}
      />
      <RegisterEvidenceDialog
        open={registering}
        onOpenChange={setRegistering}
        incidentId={incidentId}
        onSaved={(item) => setOpenId(item.id)}
      />
      <EvidenceUploadDialog open={uploadOpen} onOpenChange={setUploadOpen} incidentId={incidentId} initialFiles={dropped} />
    </div>
  )
}
