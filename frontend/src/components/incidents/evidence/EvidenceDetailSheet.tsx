"use client"

/**
 * Right-hand drawer for one evidence item: header (EV number, state, holder,
 * chain verdict, legal hold, actions), details, hashes, custody timeline,
 * stored files and derived items.
 *
 * Every action is permission-gated (cosmetic; the API decides):
 *   artifacts:upload   register derived, edit, record / verify hash, check out /
 *                      in, transfer, acknowledge, add file
 *   artifacts:delete   dispose, void, legal hold, delete a stored file
 *   artifacts:download download a stored file
 *   incidents:export   (in the export menu) the verifiable bundle
 * and by the custody state machine (`itemActions`).
 *
 * The drawer re-reads the item and its ledger whenever anything under the
 * incident's evidence prefix is invalidated (our own writes) or a live
 * `evidence_item` / `custody_entry` change for this item arrives.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowRightLeft,
  FilePlus2,
  Hash,
  LogIn,
  LogOut,
  MoreHorizontal,
  Pencil,
  ShieldCheck,
  Trash2,
  Upload,
  Ban,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { usePermission } from '@/components/auth/permission-gate'
import { isAbortError } from '@/lib/api'
import { evidenceApi, evidenceBase, evidenceFilesApi } from '@/lib/endpoints/evidence'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { invalidate, subscribe } from '@/lib/query-cache'
import { subscribeEntity } from '@/lib/realtime/live'
import type { ChainVerification, CustodyEntry, CustodyList, EvidenceArtifact, EvidenceItem, EvidenceItemDetail } from '@/types'
import { AcknowledgeDialog } from './AcknowledgeDialog'
import { AddHashDialog } from './AddHashDialog'
import { ChainStatusBadge, type ChainBadgeStatus } from './ChainStatusBadge'
import { CustodyActionDialog } from './CustodyActionDialog'
import { CustodyTimeline } from './CustodyTimeline'
import { DisposeVoidDialog, type DisposeVoidMode } from './DisposeVoidDialog'
import { DerivedSection, DetailsSection, FilesSection, HashesSection, Section } from './EvidenceDetailSections'
import { EvidenceExportMenu } from './EvidenceExportMenu'
import { EvidenceUploadDialog } from './EvidenceUploadDialog'
import { LegalHoldControl } from './LegalHoldControl'
import { RegisterEvidenceDialog } from './RegisterEvidenceDialog'
import { VerifyHashDialog } from './VerifyHashDialog'
import { custodyStateLabel, evidenceTypeLabel, itemActions, type CustodyMode } from './evidence-helpers'

export type EvidenceDialogState =
  | { type: 'custody'; mode: CustodyMode }
  | { type: 'edit' }
  | { type: 'addHash' }
  | { type: 'verify' }
  | { type: 'upload' }
  | { type: 'derive' }
  | { type: 'ack'; entry: CustodyEntry }
  | { type: 'disposeVoid'; mode: DisposeVoidMode }
  | null

const STATE_VARIANT = {
  in_storage: 'success',
  checked_out: 'warning',
  transferred: 'info',
  disposed: 'default',
} as const

export interface EvidenceDetailSheetProps {
  incidentId: string
  /** Item to show; null closes the drawer. */
  itemId: string | null
  /** The list row, shown while the detail loads. */
  row?: EvidenceItem | null
  onClose: () => void
  /** Open another item (parent / derived). */
  onOpenItem: (id: string) => void
  /** A dialog to open on top of the drawer right away (row actions). */
  initialAction?: EvidenceDialogState
}

export function EvidenceDetailSheet({ incidentId, itemId, row, onClose, onOpenItem, initialAction }: EvidenceDetailSheetProps) {
  return (
    <Sheet open={!!itemId} onOpenChange={(open) => !open && onClose()}>
      {itemId && (
        <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-2xl">
          <DrawerBody key={itemId} incidentId={incidentId} itemId={itemId} row={row} onOpenItem={onOpenItem} initialAction={initialAction} />
        </SheetContent>
      )}
    </Sheet>
  )
}

function DrawerBody({
  incidentId,
  itemId,
  row,
  onOpenItem,
  initialAction,
}: {
  incidentId: string
  itemId: string
  row?: EvidenceItem | null
  onOpenItem: (id: string) => void
  initialAction?: EvidenceDialogState
}) {
  const canWrite = usePermission('artifacts:upload')
  const canManage = usePermission('artifacts:delete')
  const canDownload = usePermission('artifacts:download')
  const confirm = useConfirm()

  const [detail, setDetail] = useState<EvidenceItemDetail | null>(null)
  const [custody, setCustody] = useState<CustodyList | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [dialog, setDialog] = useState<EvidenceDialogState>(initialAction ?? null)
  const [verification, setVerification] = useState<ChainVerification | null>(null)
  const [verifying, setVerifying] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    try {
      const [d, c] = await Promise.all([
        evidenceApi.get(incidentId, itemId, { signal: ctrl.signal }),
        evidenceApi.custody(incidentId, itemId, { signal: ctrl.signal }).catch((e) => {
          if (isAbortError(e)) throw e
          return null
        }),
      ])
      if (ctrl.signal.aborted) return
      setDetail(d)
      setCustody(c)
      setError(null)
    } catch (e) {
      if (isAbortError(e) || ctrl.signal.aborted) return
      setError(e)
    }
  }, [incidentId, itemId])

  useEffect(() => {
    void load()
    return () => ctrlRef.current?.abort()
  }, [load])

  useEffect(() => {
    const off = subscribe(evidenceBase(incidentId), (ev) => {
      if (ev.type === 'invalidate') {
        setVerification(null)
        void load()
      }
    })
    let timer: ReturnType<typeof setTimeout> | null = null
    const reloadSoon = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => void load(), 400)
    }
    const offItem = subscribeEntity('evidence_item', (c) => {
      if (c.id === itemId && c.incident_id === incidentId) reloadSoon()
    })
    const offEntry = subscribeEntity('custody_entry', (c) => {
      const owner = (c.data as { evidence_item_id?: string } | undefined)?.evidence_item_id
      if (c.incident_id === incidentId && owner === itemId) reloadSoon()
    })
    return () => {
      off()
      offItem()
      offEntry()
      if (timer) clearTimeout(timer)
    }
  }, [incidentId, itemId, load])

  const item: EvidenceItem | null = detail ?? row ?? null
  if (!item) {
    return (
      <div className="space-y-4 p-6">
        <SheetHeader>
          <SheetTitle>Evidence item</SheetTitle>
          <SheetDescription className="sr-only">Loading evidence details</SheetDescription>
        </SheetHeader>
        {error ? (
          <p role="alert" className="text-sm text-destructive">{describeError(error).description}</p>
        ) : (
          <>
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-40 w-full" />
          </>
        )}
      </div>
    )
  }

  const can = itemActions(item)
  const entries = custody?.entries ?? []
  const chainStatus: ChainBadgeStatus = verifying
    ? 'checking'
    : verification?.status ?? custody?.status ?? detail?.chain_summary.status ?? 'checking'

  const runVerify = async () => {
    setVerifying(true)
    try {
      setVerification(await evidenceApi.verifyItemChain(incidentId, itemId))
    } catch (e) {
      notifyError(e, 'verify the custody chain')
    } finally {
      setVerifying(false)
    }
  }

  const downloadFile = async (a: EvidenceArtifact) => {
    try {
      await evidenceFilesApi.download(incidentId, a.id, a.original_filename)
    } catch (e) {
      notifyError(e, 'download the file')
    }
  }

  const deleteFile = async (a: EvidenceArtifact) => {
    if (!(await confirmDelete(confirm, 'stored file', a.original_filename))) return
    try {
      await evidenceFilesApi.remove(incidentId, a.id)
      invalidate(evidenceBase(incidentId))
      invalidate(`/incidents/${incidentId}/artifacts`)
      notifySuccess('File deleted', 'The record and its hashes are kept; the stored content was purged.')
    } catch (e) {
      notifyError(e, 'delete the file')
    }
  }

  const close = () => setDialog(null)
  const holder = item.holder?.name

  return (
    <>
      <SheetHeader className="space-y-3 border-b border-border p-6 pr-12 text-left">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold">{item.evidence_number}</span>
          <Badge variant={STATE_VARIANT[item.custody_state] ?? 'default'}>{custodyStateLabel(item.custody_state)}</Badge>
          {item.voided_at && <Badge variant="destructive">Voided</Badge>}
          <ChainStatusBadge
            status={chainStatus}
            onClick={() => void runVerify()}
            detail={custody?.item_chain.head_seq != null ? `Head entry #${custody.item_chain.head_seq}` : undefined}
          />
        </div>
        <SheetTitle className="text-lg leading-snug">{item.title}</SheetTitle>
        <SheetDescription>
          {evidenceTypeLabel(item.evidence_type)}
          {holder ? ` · held by ${holder}` : ''}
          {item.holder?.type === 'storage' && !holder ? ' · in storage' : ''}
        </SheetDescription>
        <div className="flex flex-wrap items-center gap-2">
          <LegalHoldControl
            kind="evidence"
            incidentId={incidentId}
            id={item.id}
            item={item}
            label={item.evidence_number}
            onChanged={() => void load()}
          />
          <div className="ml-auto flex items-center gap-2">
            <EvidenceExportMenu incidentId={incidentId} item={item} />
            {(canWrite || canManage) && !item.voided_at && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" aria-label={`Actions for ${item.evidence_number}`}>
                    <MoreHorizontal className="h-4 w-4" />
                    Actions
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[14rem]">
                  {canWrite && (
                    <>
                      <DropdownMenuItem disabled={!can.checkOut} onSelect={() => setDialog({ type: 'custody', mode: 'check_out' })}>
                        <LogOut className="mr-2 h-4 w-4" /> Check out…
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={!can.checkIn} onSelect={() => setDialog({ type: 'custody', mode: 'check_in' })}>
                        <LogIn className="mr-2 h-4 w-4" /> Check in…
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={!can.transfer} onSelect={() => setDialog({ type: 'custody', mode: 'transfer' })}>
                        <ArrowRightLeft className="mr-2 h-4 w-4" /> Transfer…
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onSelect={() => setDialog({ type: 'addHash' })}>
                        <Hash className="mr-2 h-4 w-4" /> Record hash…
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setDialog({ type: 'verify' })}>
                        <ShieldCheck className="mr-2 h-4 w-4" /> Verify hash…
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setDialog({ type: 'upload' })}>
                        <Upload className="mr-2 h-4 w-4" /> Add file…
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setDialog({ type: 'derive' })}>
                        <FilePlus2 className="mr-2 h-4 w-4" /> Derive item…
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setDialog({ type: 'edit' })}>
                        <Pencil className="mr-2 h-4 w-4" /> Edit details…
                      </DropdownMenuItem>
                    </>
                  )}
                  {canManage && (
                    <>
                      {canWrite && <DropdownMenuSeparator />}
                      <DropdownMenuItem
                        disabled={!can.dispose}
                        className="text-destructive focus:text-destructive"
                        onSelect={() => setDialog({ type: 'disposeVoid', mode: 'dispose' })}
                      >
                        <Trash2 className="mr-2 h-4 w-4" /> Dispose…
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={!can.void}
                        className="text-destructive focus:text-destructive"
                        onSelect={() => setDialog({ type: 'disposeVoid', mode: 'void' })}
                      >
                        <Ban className="mr-2 h-4 w-4" /> Void…
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </SheetHeader>

      <div className="space-y-8 p-6">
        {item.voided_at && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
            Voided as entered in error{item.void_reason ? `: ${item.void_reason}` : '.'} The number {item.evidence_number} is
            not reused and the ledger is kept.
          </p>
        )}
        {error != null && !detail && (
          <p role="alert" className="text-sm text-destructive">{describeError(error).description}</p>
        )}

        {verification && (verification.status !== 'intact' || verification.breaks.length > 0 || verification.notes.length > 0) && (
          <div className="space-y-1 rounded-md border border-border bg-muted/30 p-3 text-sm" aria-label="Verification result">
            <p className="font-medium">Chain verification</p>
            {verification.breaks.map((b, i) => (
              <p key={i} className="text-destructive">
                Entry {b.seq ?? 'unknown'}: {b.reason.replace(/_/g, ' ')}
              </p>
            ))}
            {verification.notes.map((n, i) => (
              <p key={i} className="text-muted-foreground">{n}</p>
            ))}
          </div>
        )}

        <DetailsSection item={item} />

        <HashesSection
          item={item}
          canWrite={canWrite}
          onAdd={() => setDialog({ type: 'addHash' })}
          onVerify={() => setDialog({ type: 'verify' })}
        />

        <Section id="ev-custody" title="Chain of custody">
          <CustodyTimeline
            entries={entries}
            canAcknowledge={canWrite && !item.voided_at}
            onAcknowledge={(entry) => setDialog({ type: 'ack', entry })}
          />
        </Section>

        <FilesSection
          incidentId={incidentId}
          item={item}
          artifacts={detail?.artifacts ?? []}
          canDownload={canDownload}
          canWrite={canWrite}
          canManage={canManage}
          onDownload={(a) => void downloadFile(a)}
          onDelete={(a) => void deleteFile(a)}
          onAddFile={() => setDialog({ type: 'upload' })}
          onChanged={() => void load()}
        />

        <DerivedSection
          onOpen={onOpenItem}
          onDerive={canWrite && !item.voided_at ? () => setDialog({ type: 'derive' }) : undefined}
        >
          {detail?.children ?? []}
        </DerivedSection>
      </div>

      {dialog?.type === 'custody' && (
        <CustodyActionDialog
          open
          onOpenChange={(o) => !o && close()}
          incidentId={incidentId}
          item={item}
          mode={dialog.mode}
          onAcknowledge={(entry) => setDialog({ type: 'ack', entry })}
        />
      )}
      {dialog?.type === 'edit' && (
        <RegisterEvidenceDialog open onOpenChange={(o) => !o && close()} incidentId={incidentId} item={item} />
      )}
      {dialog?.type === 'derive' && (
        <RegisterEvidenceDialog
          open
          onOpenChange={(o) => !o && close()}
          incidentId={incidentId}
          parentId={item.id}
          onSaved={(created) => onOpenItem(created.id)}
        />
      )}
      {dialog?.type === 'addHash' && <AddHashDialog open onOpenChange={(o) => !o && close()} incidentId={incidentId} item={item} />}
      {dialog?.type === 'verify' && (
        <VerifyHashDialog
          open
          onOpenChange={(o) => !o && close()}
          incidentId={incidentId}
          item={item}
          artifacts={detail?.artifacts}
        />
      )}
      {dialog?.type === 'upload' && (
        <EvidenceUploadDialog open onOpenChange={(o) => !o && close()} incidentId={incidentId} attachTo={item} />
      )}
      {dialog?.type === 'ack' && (
        <AcknowledgeDialog open onOpenChange={(o) => !o && close()} incidentId={incidentId} item={item} entry={dialog.entry} />
      )}
      {dialog?.type === 'disposeVoid' && (
        <DisposeVoidDialog open onOpenChange={(o) => !o && close()} incidentId={incidentId} item={item} mode={dialog.mode} />
      )}
    </>
  )
}
