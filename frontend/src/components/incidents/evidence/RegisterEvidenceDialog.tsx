"use client"

/**
 * Register a new evidence item, or edit the descriptive fields of one.
 *
 * Register: identification, media, acquisition, hashes (validated per
 * algorithm length) and derivation (parent). The `register` ledger entry
 * snapshots all of it.
 * Edit (PATCH with `If-Match: version`): only changed fields are sent. Hashes
 * (add or supersede, never edit), parent, holder, state and storage location
 * are not editable here; those have their own ledger actions.
 */
import { useState } from 'react'
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
import { DateTimeInput } from '@/components/ui/datetime-input'
import { EntityPicker, UserPicker } from '@/components/ui/entity-picker'
import { Input, Textarea } from '@/components/ui/input'
import { evidenceApi, evidenceBase } from '@/lib/endpoints/evidence'
import { invalidate } from '@/lib/query-cache'
import type {
  CompromisedHost,
  EvidenceItem,
  EvidenceType,
  RegisterEvidenceInput,
  UpdateEvidenceInput,
} from '@/types'
import { EVIDENCE_TYPES } from '@/types'
import { EVIDENCE_TYPE_LABELS, evidenceTypeLabel } from './evidence-helpers'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError, NativeSelect, optionsFrom } from './form-parts'
import { HashEntry, hashRowsInvalid, hashRowsToInput, newHashRow, type HashRow } from './HashEntry'

/** `acquired_at` may not be in the future (5 minutes of clock slack, like the server). */
export const FUTURE_SLACK_MS = 5 * 60 * 1000

interface FormState {
  title: string
  evidence_type: EvidenceType
  description: string
  media_type: string
  make: string
  model: string
  serial_number: string
  capacity_bytes: string
  seal_number: string
  bag_number: string
  storage_location: string
  condition_notes: string
  acquired_at: string | null
  acquired_by_user_id: string | null
  acquired_by_name: string
  acquired_from: string
  acquisition_method: string
  acquisition_tool: string
  acquisition_tool_version: string
  source_host_id: string | null
  parent_id: string | null
  derivation_note: string
}

const TEXT_KEYS = [
  'description',
  'media_type',
  'make',
  'model',
  'serial_number',
  'seal_number',
  'bag_number',
  'condition_notes',
  'acquired_by_name',
  'acquired_from',
  'acquisition_method',
  'acquisition_tool',
  'acquisition_tool_version',
  'derivation_note',
] as const

function initialState(item?: EvidenceItem | null): FormState {
  const s = (v: string | null | undefined) => v ?? ''
  return {
    title: s(item?.title),
    evidence_type: item?.evidence_type ?? 'digital_file',
    description: s(item?.description),
    media_type: s(item?.media_type),
    make: s(item?.make),
    model: s(item?.model),
    serial_number: s(item?.serial_number),
    capacity_bytes: item?.capacity_bytes != null ? String(item.capacity_bytes) : '',
    seal_number: s(item?.seal_number),
    bag_number: s(item?.bag_number),
    storage_location: s(item?.storage_location),
    condition_notes: s(item?.condition_notes),
    acquired_at: item?.acquired_at ?? null,
    acquired_by_user_id: item?.acquired_by_user_id ?? null,
    acquired_by_name: s(item?.acquired_by_name),
    acquired_from: s(item?.acquired_from),
    acquisition_method: s(item?.acquisition_method),
    acquisition_tool: s(item?.acquisition_tool),
    acquisition_tool_version: s(item?.acquisition_tool_version),
    source_host_id: item?.source_host_id ?? null,
    parent_id: item?.parent_id ?? null,
    derivation_note: s(item?.derivation_note),
  }
}

const orNull = (v: string) => (v.trim() ? v.trim() : null)

/** Why the form cannot be sent (field -> message). */
export function evidenceFormProblems(f: FormState, now = Date.now()): Partial<Record<keyof FormState, string>> {
  const out: Partial<Record<keyof FormState, string>> = {}
  if (!f.title.trim()) out.title = 'A title is required'
  if (f.capacity_bytes.trim() && !/^\d{1,18}$/.test(f.capacity_bytes.trim())) {
    out.capacity_bytes = 'Whole number of bytes'
  }
  if (f.acquired_at && new Date(f.acquired_at).getTime() > now + FUTURE_SLACK_MS) {
    out.acquired_at = 'Acquisition time cannot be in the future'
  }
  return out
}

export interface RegisterEvidenceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  /** Set to edit that item; omit to register a new one. */
  item?: EvidenceItem | null
  /** Register mode: preselect the parent (derive from this item). */
  parentId?: string | null
  onSaved?: (item: EvidenceItem) => void
}

export function RegisterEvidenceDialog(props: RegisterEvidenceDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      {props.open && <EvidenceForm key={props.item?.id ?? 'new'} {...props} />}
    </Dialog>
  )
}

function EvidenceForm({ onOpenChange, incidentId, item, parentId, onSaved }: RegisterEvidenceDialogProps) {
  const editing = !!item
  const [form, setForm] = useState<FormState>(() => ({ ...initialState(item), parent_id: item?.parent_id ?? parentId ?? null }))
  const [hashes, setHashes] = useState<HashRow[]>(() => (editing ? [] : [newHashRow('sha256')]))
  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }))
  const problems = evidenceFormProblems(form)
  const err = <K extends keyof FormState>(key: K) => (attempted ? problems[key] ?? null : null)
  const blocked = Object.keys(problems).length > 0 || hashRowsInvalid(hashes)

  const buildBody = (): RegisterEvidenceInput => {
    const body: RegisterEvidenceInput = { title: form.title.trim(), evidence_type: form.evidence_type }
    const rec = body as unknown as Record<string, unknown>
    for (const key of TEXT_KEYS) {
      const v = orNull(form[key])
      if (v !== null) rec[key] = v
    }
    if (form.storage_location.trim()) body.storage_location = form.storage_location.trim()
    if (form.capacity_bytes.trim()) body.capacity_bytes = Number(form.capacity_bytes.trim())
    if (form.acquired_at) body.acquired_at = form.acquired_at
    if (form.acquired_by_user_id) body.acquired_by_user_id = form.acquired_by_user_id
    if (form.source_host_id) body.source_host_id = form.source_host_id
    if (form.parent_id) body.parent_id = form.parent_id
    const hs = hashRowsToInput(hashes)
    if (hs.length) body.acquisition_hashes = hs
    return body
  }

  /** PATCH body: only the descriptive fields that differ from the item. */
  const buildPatch = (): UpdateEvidenceInput => {
    const initial = initialState(item)
    const patch: Record<string, unknown> = {}
    if (form.title.trim() !== initial.title) patch.title = form.title.trim()
    if (form.evidence_type !== initial.evidence_type) patch.evidence_type = form.evidence_type
    for (const key of TEXT_KEYS) {
      if (key === 'derivation_note') continue // derivation is fixed at registration
      if (form[key].trim() !== initial[key].trim()) patch[key] = orNull(form[key])
    }
    if (form.capacity_bytes.trim() !== initial.capacity_bytes) {
      patch.capacity_bytes = form.capacity_bytes.trim() ? Number(form.capacity_bytes.trim()) : null
    }
    if (form.acquired_at !== initial.acquired_at) patch.acquired_at = form.acquired_at
    if (form.acquired_by_user_id !== initial.acquired_by_user_id) patch.acquired_by_user_id = form.acquired_by_user_id
    if (form.source_host_id !== initial.source_host_id) patch.source_host_id = form.source_host_id
    return patch as UpdateEvidenceInput
  }

  const submit = async () => {
    setAttempted(true)
    setServerError(null)
    if (blocked) return
    setBusy(true)
    try {
      let saved: EvidenceItem
      if (editing && item) {
        const patch = buildPatch()
        if (Object.keys(patch).length === 0) {
          onOpenChange(false)
          return
        }
        saved = await evidenceApi.update(incidentId, item.id, patch, item.version)
      } else {
        saved = await evidenceApi.register(incidentId, buildBody())
      }
      invalidate(evidenceBase(incidentId))
      onSaved?.(saved)
      onOpenChange(false)
    } catch (e) {
      reportEvidenceError(e, editing ? 'save the evidence item' : 'register the evidence item', setServerError)
    } finally {
      setBusy(false)
    }
  }

  const textField = (key: (typeof TEXT_KEYS)[number], label: string, opts: { max?: number; placeholder?: string; className?: string } = {}) => (
    <Field label={label} className={opts.className}>
      {({ id }) => (
        <Input
          id={id}
          value={form[key]}
          onChange={(e) => set(key, e.target.value)}
          maxLength={opts.max ?? 255}
          placeholder={opts.placeholder}
        />
      )}
    </Field>
  )

  return (
    <DialogContent className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>{editing ? `Edit ${item?.evidence_number}` : 'Register evidence'}</DialogTitle>
        <DialogDescription>
          {editing
            ? 'Changes are written to the custody ledger with the old and new values. Hashes, holder and storage location are changed through their own actions.'
            : 'Record a physical or digital item. An EV number is assigned automatically and the registration is written to the signed custody ledger.'}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="max-h-[68vh] space-y-6 overflow-y-auto px-1">
        <section aria-labelledby="ev-sec-id" className="space-y-3">
          <h3 id="ev-sec-id" className="text-sm font-semibold">Identification</h3>
          <div className="grid gap-4 sm:grid-cols-[1fr_220px]">
            <Field label="Title" required error={err('title')}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  value={form.title}
                  onChange={(e) => set('title', e.target.value)}
                  maxLength={255}
                  placeholder="e.g. CFO laptop, internal SSD"
                />
              )}
            </Field>
            <Field label="Type" required>
              {({ id }) => (
                <NativeSelect
                  id={id}
                  value={form.evidence_type}
                  onValueChange={(v) => set('evidence_type', v as EvidenceType)}
                  options={optionsFrom(EVIDENCE_TYPE_LABELS).filter((o) => EVIDENCE_TYPES.includes(o.value))}
                />
              )}
            </Field>
          </div>
          <Field label="Description">
            {({ id }) => (
              <Textarea id={id} rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} maxLength={20000} />
            )}
          </Field>
        </section>

        <section aria-labelledby="ev-sec-media" className="space-y-3">
          <h3 id="ev-sec-media" className="text-sm font-semibold">Media</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            {textField('media_type', 'Media type', { max: 120, placeholder: 'e.g. NVMe SSD' })}
            {textField('make', 'Make', { max: 120 })}
            {textField('model', 'Model', { max: 120 })}
            {textField('serial_number', 'Serial number', { max: 120 })}
            <Field label="Capacity (bytes)" error={err('capacity_bytes')}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  inputMode="numeric"
                  value={form.capacity_bytes}
                  onChange={(e) => set('capacity_bytes', e.target.value)}
                />
              )}
            </Field>
            {textField('bag_number', 'Bag number', { max: 120 })}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {textField('seal_number', 'Seal number', { max: 120 })}
            <Field label="Storage location" hint={editing ? 'Changed by checking the item in.' : undefined}>
              {({ id, describedBy }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  value={form.storage_location}
                  onChange={(e) => set('storage_location', e.target.value)}
                  maxLength={500}
                  disabled={editing}
                  placeholder="e.g. Evidence locker 3"
                />
              )}
            </Field>
          </div>
          {textField('condition_notes', 'Condition notes', { max: 20000 })}
        </section>

        <section aria-labelledby="ev-sec-acq" className="space-y-3">
          <h3 id="ev-sec-acq" className="text-sm font-semibold">Acquisition</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Acquired at" error={err('acquired_at')}>
              {({ id, describedBy, invalid }) => (
                <DateTimeInput
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  value={form.acquired_at}
                  onChange={(iso) => set('acquired_at', iso)}
                />
              )}
            </Field>
            <Field label="Source host">
              {() => (
                <EntityPicker<CompromisedHost>
                  value={form.source_host_id}
                  onChange={(id) => set('source_host_id', id)}
                  endpoint={`/incidents/${incidentId}/hosts`}
                  params={{ sort: 'hostname' }}
                  getId={(h) => h.id}
                  getLabel={(h) => h.hostname}
                  getDescription={(h) => h.ip_address || undefined}
                  valueLabel={item?.source_host_label ?? undefined}
                  ariaLabel="Source host"
                  placeholder="Search hosts…"
                />
              )}
            </Field>
            <Field label="Acquired by (colleague)">
              {() => (
                <UserPicker
                  value={form.acquired_by_user_id}
                  onChange={(id) => set('acquired_by_user_id', id)}
                  ariaLabel="Acquired by colleague"
                  valueLabel={item?.acquired_by_name ?? undefined}
                />
              )}
            </Field>
            {textField('acquired_by_name', 'Or external examiner', { placeholder: 'Name, if not a user' })}
            {textField('acquired_from', 'Acquired from', { max: 500, placeholder: 'Person, location or system' })}
            {textField('acquisition_method', 'Method', { max: 100, placeholder: 'e.g. Write-blocked image' })}
            {textField('acquisition_tool', 'Tool', { max: 150 })}
            {textField('acquisition_tool_version', 'Tool version', { max: 60 })}
          </div>
        </section>

        {!editing && (
          <section aria-labelledby="ev-sec-hash" className="space-y-3">
            <h3 id="ev-sec-hash" className="text-sm font-semibold">Hashes</h3>
            <p className="text-xs text-muted-foreground">
              Optional at registration (a phone may have none). A recorded hash is never edited: later corrections
              supersede it with a reason.
            </p>
            <HashEntry rows={hashes} onChange={setHashes} showErrors />
          </section>
        )}

        <section aria-labelledby="ev-sec-parent" className="space-y-3">
          <h3 id="ev-sec-parent" className="text-sm font-semibold">Derivation</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Derived from" hint={editing ? 'Fixed at registration.' : 'E.g. a forensic image of a registered drive.'}>
              {() =>
                editing ? (
                  <p className="text-sm">{item?.parent ? `${item.parent.evidence_number} ${item.parent.title}` : 'None'}</p>
                ) : (
                  <EntityPicker<EvidenceItem>
                    value={form.parent_id}
                    onChange={(id) => set('parent_id', id)}
                    endpoint={evidenceBase(incidentId)}
                    params={{ sort: 'sequence_number' }}
                    getId={(p) => p.id}
                    getLabel={(p) => `${p.evidence_number} ${p.title}`}
                    getDescription={(p) => evidenceTypeLabel(p.evidence_type)}
                    ariaLabel="Parent evidence item"
                    placeholder="Search registered items…"
                  />
                )
              }
            </Field>
            {!editing && textField('derivation_note', 'Derivation note', { max: 20000, placeholder: 'How it was derived' })}
          </div>
        </section>

        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={busy}>
          {editing ? 'Save changes' : 'Register'}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
