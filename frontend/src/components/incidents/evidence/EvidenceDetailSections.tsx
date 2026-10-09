"use client"

/**
 * Read-only sections of the evidence drawer: details, hashes, stored files and
 * derived items. Actions are passed in as callbacks so the permission checks
 * live in one place (the drawer).
 */
import { useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, Check, Copy, Download, FileText, GitBranch, HardDrive, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Timestamp } from '@/components/ui/timestamp'
import api from '@/lib/api'
import { notifyError } from '@/lib/errors'
import { cn, formatBytes } from '@/lib/utils'
import type { EvidenceArtifact, EvidenceItem, EvidenceItemSummary } from '@/types'
import {
  HASH_LABELS,
  HASH_SOURCE_LABELS,
  activeHashes,
  evidenceTypeLabel,
} from './evidence-helpers'
import { LegalHoldControl } from './LegalHoldControl'

export function Section({
  title,
  action,
  children,
  id,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  id: string
}) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 id={id} className="text-sm font-semibold">
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  if (children === null || children === undefined || children === '') return null
  return (
    <div className="grid grid-cols-[130px_1fr] gap-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

/** Name of a user id, when the viewer is allowed to look it up (else null). */
function useUserName(userId: string | null | undefined, known?: string | null): string | null {
  const [name, setName] = useState<string | null>(null)
  useEffect(() => {
    if (!userId || known) return
    let alive = true
    api
      .get<{ name?: string; email?: string }>(`/users/${userId}`)
      .then((u) => alive && setName(u.name || u.email || null))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [userId, known])
  return known || name
}

export function DetailsSection({ item }: { item: EvidenceItem }) {
  const acquirer = useUserName(item.acquired_by_user_id, item.acquired_by_name)
  const make = [item.make, item.model].filter(Boolean).join(' ')
  return (
    <Section id="ev-details" title="Details">
      <dl className="space-y-1.5">
        <Row label="Type">{evidenceTypeLabel(item.evidence_type)}</Row>
        <Row label="Description">{item.description}</Row>
        <Row label="Make / model">{make}</Row>
        <Row label="Media">{item.media_type}</Row>
        <Row label="Serial number">{item.serial_number && <span className="font-mono text-xs">{item.serial_number}</span>}</Row>
        <Row label="Capacity">{item.capacity_bytes != null ? formatBytes(item.capacity_bytes) : null}</Row>
        <Row label="Seal / bag">
          {[item.seal_number && `Seal ${item.seal_number}`, item.bag_number && `Bag ${item.bag_number}`].filter(Boolean).join(' · ')}
        </Row>
        <Row label="Storage">{item.storage_location}</Row>
        <Row label="Condition">{item.condition_notes}</Row>
        <Row label="Source host">{item.source_host_label}</Row>
        <Row label="Acquired">{item.acquired_at && <Timestamp value={item.acquired_at} />}</Row>
        <Row label="Acquired by">{acquirer}</Row>
        <Row label="Acquired from">{item.acquired_from}</Row>
        <Row label="Method">
          {[item.acquisition_method, [item.acquisition_tool, item.acquisition_tool_version].filter(Boolean).join(' ')]
            .filter(Boolean)
            .join(' · ')}
        </Row>
        <Row label="Derived from">
          {item.parent && (
            <span>
              {item.parent.evidence_number} {item.parent.title}
              {item.derivation_note ? ` (${item.derivation_note})` : ''}
            </span>
          )}
        </Row>
        <Row label="Registered">
          {item.creator ? `${item.creator.name}, ` : ''}
          <Timestamp value={item.created_at} />
        </Row>
      </dl>
    </Section>
  )
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false)
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className="h-6 w-6"
      aria-label={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setDone(true)
          setTimeout(() => setDone(false), 1500)
        } catch (e) {
          notifyError(e, 'copy the hash')
        }
      }}
    >
      {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </Button>
  )
}

export function HashesSection({
  item,
  canWrite,
  onAdd,
  onVerify,
}: {
  item: EvidenceItem
  canWrite: boolean
  onAdd: () => void
  onVerify: () => void
}) {
  const all = item.acquisition_hashes ?? []
  const active = activeHashes(item)
  const voided = !!item.voided_at
  return (
    <Section
      id="ev-hashes"
      title="Hashes"
      action={
        canWrite && !voided ? (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onAdd}>
              Record hash
            </Button>
            <Button variant="outline" size="sm" onClick={onVerify} disabled={active.length === 0}>
              Verify…
            </Button>
          </div>
        ) : undefined
      }
    >
      {all.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hash recorded for this item.</p>
      ) : (
        <ul className="space-y-2">
          {all.map((h, i) => (
            <li
              key={`${h.algorithm}-${h.value}-${i}`}
              className={cn('rounded-md border border-border p-2', h.superseded && 'opacity-60')}
            >
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="default">{HASH_LABELS[h.algorithm] ?? h.algorithm}</Badge>
                <span className="text-muted-foreground">{HASH_SOURCE_LABELS[h.source] ?? h.source}</span>
                {h.recorded_at && (
                  <span className="text-muted-foreground">
                    <Timestamp value={h.recorded_at} />
                  </span>
                )}
                {h.superseded && <Badge variant="warning">Superseded</Badge>}
              </div>
              <div className="mt-1 flex items-start gap-1">
                <code className="min-w-0 flex-1 break-all font-mono text-xs">{h.value}</code>
                <CopyButton value={h.value} label={`Copy ${HASH_LABELS[h.algorithm] ?? h.algorithm} hash`} />
              </div>
            </li>
          ))}
        </ul>
      )}
      {item.weak_hashes_only && (
        <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          Only MD5 / SHA-1 are recorded. Record a SHA-256 for evidence that may be challenged.
        </p>
      )}
      {item.last_verified_at && (
        <p className="text-xs text-muted-foreground">
          Last verified <Timestamp value={item.last_verified_at} />:{' '}
          <span className={item.last_verification_result === 'match' ? 'text-emerald-600 dark:text-emerald-400' : 'font-medium text-destructive'}>
            {item.last_verification_result === 'match' ? 'match' : 'mismatch'}
          </span>
        </p>
      )}
    </Section>
  )
}

export function FilesSection({
  incidentId,
  item,
  artifacts,
  canDownload,
  canWrite,
  canManage,
  onDownload,
  onDelete,
  onAddFile,
  onChanged,
}: {
  incidentId: string
  item: EvidenceItem
  artifacts: EvidenceArtifact[]
  canDownload: boolean
  canWrite: boolean
  canManage: boolean
  onDownload: (a: EvidenceArtifact) => void
  onDelete: (a: EvidenceArtifact) => void
  onAddFile: () => void
  onChanged: () => void
}) {
  return (
    <Section
      id="ev-files"
      title="Stored files"
      action={
        canWrite && !item.voided_at ? (
          <Button variant="outline" size="sm" onClick={onAddFile}>
            Add file
          </Button>
        ) : undefined
      }
    >
      {artifacts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Metadata only. No file is stored in SheetStorm for this item.
        </p>
      ) : (
        <ul className="space-y-2">
          {artifacts.map((a) => {
            const gone = !!a.deleted_at
            return (
              <li key={a.id} className={cn('rounded-md border border-border p-2', gone && 'opacity-60')}>
                <div className="flex items-start gap-2">
                  {a.storage_type === 'google_drive' ? (
                    <HardDrive className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  ) : (
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className={cn('truncate text-sm font-medium', gone && 'line-through')} title={a.original_filename}>
                      {a.original_filename}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(a.file_size)} · {a.purpose === 'custody_receipt' ? 'Signed receipt' : a.storage_type.replace('_', ' ')} ·{' '}
                      <Timestamp value={a.created_at} />
                    </p>
                    <p className="break-all font-mono text-[11px] text-muted-foreground">SHA-256 {a.sha256}</p>
                    {gone && (
                      <p className="text-xs text-muted-foreground">
                        Deleted <Timestamp value={a.deleted_at} />
                        {a.deletion_reason ? `: ${a.deletion_reason}` : ''}. The record and its hashes are kept
                        {a.content_purged ? '; the stored content was purged.' : '.'}
                      </p>
                    )}
                  </div>
                  {!gone && (
                    <div className="flex shrink-0 items-center">
                      {canDownload && (
                        <Button variant="ghost" size="icon-sm" aria-label={`Download ${a.original_filename}`} onClick={() => onDownload(a)}>
                          <Download className="h-4 w-4" />
                        </Button>
                      )}
                      {canManage && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Delete ${a.original_filename}`}
                          className="hover:text-destructive"
                          onClick={() => onDelete(a)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  )}
                </div>
                {!gone && (canManage || a.under_legal_hold) && (
                  <LegalHoldControl
                    kind="artifact"
                    incidentId={incidentId}
                    id={a.id}
                    item={a}
                    label={a.original_filename}
                    compact
                    className="mt-2"
                    onChanged={onChanged}
                  />
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Section>
  )
}

export function DerivedSection({
  children,
  onOpen,
  onDerive,
}: {
  children: EvidenceItemSummary[]
  onOpen: (id: string) => void
  /** Register a new item derived from this one (needs artifacts:upload). */
  onDerive?: () => void
}) {
  if (children.length === 0 && !onDerive) return null
  return (
    <Section
      id="ev-derived"
      title="Derived items"
      action={
        onDerive ? (
          <Button variant="outline" size="sm" onClick={onDerive}>
            <GitBranch className="h-4 w-4" />
            Derive item
          </Button>
        ) : undefined
      }
    >
      {children.length === 0 ? (
        <p className="text-sm text-muted-foreground">No items derived from this one.</p>
      ) : (
        <ul className="space-y-1">
          {children.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={cn('text-left text-sm text-primary underline-offset-2 hover:underline', c.voided && 'line-through opacity-60')}
                onClick={() => onOpen(c.id)}
              >
                {c.evidence_number} {c.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
