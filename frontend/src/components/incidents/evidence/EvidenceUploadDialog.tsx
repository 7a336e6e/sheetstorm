"use client"

/**
 * Upload files into the evidence register.
 *
 * Each uploaded file is registered as its own evidence item (EV number,
 * `register` + `upload` ledger entries, one server transaction), unless it is
 * attached to an existing item as another stored copy. The upload route is
 * `POST /incidents/<id>/artifacts` (artifacts.py); this dialog is where the
 * old Artifacts tab's dropzone and Google Drive status/setup now live.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, FolderOpen, HardDrive, Loader2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EntityPicker } from '@/components/ui/entity-picker'
import { Input, Textarea } from '@/components/ui/input'
import api from '@/lib/api'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { evidenceBase, evidenceFilesApi } from '@/lib/endpoints/evidence'
import { invalidate } from '@/lib/query-cache'
import { cn, formatBytes } from '@/lib/utils'
import type { EvidenceItem, EvidenceType } from '@/types'
import { EVIDENCE_TYPES } from '@/types'
import { EVIDENCE_TYPE_LABELS, evidenceTypeLabel } from './evidence-helpers'
import { Field, NativeSelect, optionsFrom } from './form-parts'

type FileStatus = 'queued' | 'uploading' | 'done' | 'error'
interface Row {
  file: File
  status: FileStatus
  error?: string
}

interface DriveStatus {
  configured: boolean
  connected: boolean
  email?: string
  message?: string
}

export interface EvidenceUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  /** Files dropped on the tab before the dialog opened. */
  initialFiles?: File[]
  /** Attach to this item instead of registering new ones. */
  attachTo?: Pick<EvidenceItem, 'id' | 'evidence_number' | 'title'> | null
  onUploaded?: () => void
}

export function EvidenceUploadDialog(props: EvidenceUploadDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      {props.open && <UploadForm {...props} />}
    </Dialog>
  )
}

function UploadForm({ onOpenChange, incidentId, initialFiles, attachTo, onUploaded }: EvidenceUploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [rows, setRows] = useState<Row[]>(() => (initialFiles ?? []).map((file) => ({ file, status: 'queued' })))
  const [evidenceType, setEvidenceType] = useState<EvidenceType>('digital_file')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [target, setTarget] = useState<string | null>(attachTo?.id ?? null)
  const [dragOver, setDragOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [attempted, setAttempted] = useState(false)

  // Google Drive (optional storage backend).
  const [drive, setDrive] = useState<DriveStatus | null>(null)
  const [settingUp, setSettingUp] = useState(false)
  const [caseReady, setCaseReady] = useState(false)
  useEffect(() => {
    let alive = true
    api
      .get<DriveStatus>('/google-drive/status')
      .then((s) => alive && setDrive(s))
      .catch(() => alive && setDrive({ configured: false, connected: false }))
    return () => {
      alive = false
    }
  }, [])

  const addFiles = useCallback((list: FileList | File[] | null) => {
    if (!list || list.length === 0) return
    setRows((prev) => [...prev, ...Array.from(list).map((file) => ({ file, status: 'queued' as const }))])
  }, [])

  const setupCaseFolder = async () => {
    setSettingUp(true)
    try {
      await api.post(`/incidents/${incidentId}/google-drive/setup`)
      setCaseReady(true)
      notifySuccess('Case folder created', 'The Google Drive case folder structure is ready.')
    } catch (e) {
      notifyError(e, 'create the Google Drive case folder')
    } finally {
      setSettingUp(false)
    }
  }

  const pending = rows.filter((r) => r.status === 'queued' || r.status === 'error')
  const single = rows.length === 1

  const upload = async () => {
    setAttempted(true)
    if (pending.length === 0) return
    setBusy(true)
    let failed = 0
    let done = 0
    for (const row of pending) {
      setRows((rs) => rs.map((r) => (r === row ? { ...r, status: 'uploading', error: undefined } : r)))
      try {
        const form = new FormData()
        form.append('file', row.file)
        if (target) {
          form.append('evidence_item_id', target)
        } else {
          form.append('evidence_type', evidenceType)
          if (single && title.trim()) form.append('title', title.trim())
        }
        if (description.trim()) form.append('description', description.trim())
        await evidenceFilesApi.upload(incidentId, form)
        done += 1
        setRows((rs) => rs.map((r) => (r.file === row.file ? { ...r, status: 'done' } : r)))
      } catch (e) {
        failed += 1
        setRows((rs) =>
          rs.map((r) => (r.file === row.file ? { ...r, status: 'error', error: describeError(e).description } : r))
        )
      }
    }
    setBusy(false)
    if (done > 0) {
      invalidate(evidenceBase(incidentId))
      invalidate(`/incidents/${incidentId}/artifacts`)
      onUploaded?.()
    }
    if (failed === 0) {
      notifySuccess('Upload complete', `${done} file${done === 1 ? '' : 's'} added to the evidence register`)
      onOpenChange(false)
    }
  }

  return (
    <DialogContent className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{attachTo ? `Add a stored copy to ${attachTo.evidence_number}` : 'Upload files'}</DialogTitle>
        <DialogDescription>
          {attachTo
            ? 'The file is kept as another stored copy of this item; its hashes are computed on upload.'
            : 'Each file becomes its own evidence item with a hash computed on upload and a signed custody entry.'}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto px-1">
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            addFiles(e.dataTransfer.files)
          }}
          className={cn(
            'rounded-lg border-2 border-dashed p-6 text-center transition-colors',
            dragOver ? 'border-primary bg-primary/5' : 'border-border hover:border-muted-foreground/40'
          )}
        >
          <Upload className="mx-auto mb-2 h-7 w-7 text-muted-foreground" aria-hidden />
          <p className="text-sm text-muted-foreground">Drag and drop files here, or</p>
          <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => inputRef.current?.click()} disabled={busy}>
            Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="sr-only"
            aria-label="Files to upload"
            onChange={(e) => {
              addFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </div>

        {rows.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-border" aria-label="Files to upload">
            {rows.map((r, i) => (
              <li key={`${r.file.name}-${i}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate" title={r.file.name}>{r.file.name}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{formatBytes(r.file.size)}</span>
                <span className="w-24 shrink-0 text-right text-xs" aria-live="polite">
                  {r.status === 'uploading' && <Loader2 className="ml-auto h-4 w-4 animate-spin" aria-label="Uploading" />}
                  {r.status === 'done' && (
                    <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="h-4 w-4" aria-hidden /> Added
                    </span>
                  )}
                  {r.status === 'error' && (
                    <span className="inline-flex items-center gap-1 text-destructive" title={r.error}>
                      <AlertTriangle className="h-4 w-4" aria-hidden /> Failed
                    </span>
                  )}
                  {r.status === 'queued' && !busy && (
                    <button
                      type="button"
                      className="text-muted-foreground underline-offset-2 hover:underline"
                      onClick={() => setRows((rs) => rs.filter((x) => x !== r))}
                    >
                      Remove
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {rows.some((r) => r.status === 'error') && (
          <ul role="alert" className="space-y-1 text-sm text-destructive">
            {rows
              .filter((r) => r.status === 'error')
              .map((r, i) => (
                <li key={i}>
                  {r.file.name}: {r.error}
                </li>
              ))}
          </ul>
        )}
        {attempted && rows.length === 0 && <p role="alert" className="text-sm text-destructive">Choose at least one file</p>}

        {!attachTo && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Attach to an existing item" hint="Leave empty to register each file as a new item." className="sm:col-span-2">
              {() => (
                <EntityPicker<EvidenceItem>
                  value={target}
                  onChange={(id) => setTarget(id)}
                  endpoint={evidenceBase(incidentId)}
                  params={{ sort: 'sequence_number' }}
                  getId={(p) => p.id}
                  getLabel={(p) => `${p.evidence_number} ${p.title}`}
                  getDescription={(p) => evidenceTypeLabel(p.evidence_type)}
                  ariaLabel="Attach to existing evidence item"
                  placeholder="Search registered items…"
                />
              )}
            </Field>
            {!target && (
              <>
                <Field label="Type">
                  {({ id }) => (
                    <NativeSelect
                      id={id}
                      value={evidenceType}
                      onValueChange={(v) => setEvidenceType(v as EvidenceType)}
                      options={optionsFrom(EVIDENCE_TYPE_LABELS).filter((o) => EVIDENCE_TYPES.includes(o.value))}
                    />
                  )}
                </Field>
                <Field label="Title" hint={single ? 'Defaults to the file name.' : 'Used only for a single file; each file is titled by its name.'}>
                  {({ id, describedBy }) => (
                    <Input id={id} aria-describedby={describedBy} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} disabled={!single} />
                  )}
                </Field>
              </>
            )}
            <Field label="Description" className="sm:col-span-2">
              {({ id }) => <Textarea id={id} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={20000} />}
            </Field>
          </div>
        )}

        {drive?.configured && (
          <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/30 p-3">
            <div className="flex items-center gap-3">
              <HardDrive className={cn('h-5 w-5', drive.connected ? 'text-emerald-500' : 'text-muted-foreground')} aria-hidden />
              <div>
                <p className="text-sm font-medium">Google Drive {drive.connected && <span className="text-xs font-normal text-emerald-600 dark:text-emerald-400">connected</span>}</p>
                {!drive.connected && <p className="text-xs text-muted-foreground">{drive.message || 'Not connected'}</p>}
              </div>
            </div>
            {drive.connected ? (
              <Button variant="outline" size="sm" onClick={() => void setupCaseFolder()} loading={settingUp}>
                <FolderOpen className="h-4 w-4" />
                {caseReady ? 'Case folder ready' : 'Set up case folder'}
              </Button>
            ) : (
              <Button variant="outline" size="sm" asChild>
                <a href="/dashboard/admin">
                  Connect <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </Button>
            )}
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          {rows.some((r) => r.status === 'done') ? 'Close' : 'Cancel'}
        </Button>
        <Button onClick={() => void upload()} loading={busy} disabled={pending.length === 0 && rows.length > 0}>
          Upload{pending.length > 0 ? ` ${pending.length} file${pending.length === 1 ? '' : 's'}` : ''}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
