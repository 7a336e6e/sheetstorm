"use client"

/**
 * Who receives the evidence: a colleague (internal user), a saved external
 * custody party (counsel, lab, law enforcement, ...), or a new party typed in
 * place. Exactly one of the three is sent (`to_user_id` / `to_party_id` /
 * `new_party`), which is what the API requires.
 */
import { EntityPicker, UserPicker } from '@/components/ui/entity-picker'
import { Input } from '@/components/ui/input'
import type { CustodyParty, NewPartyInput, PartyRole, RecipientInput } from '@/types'
import { PARTY_ROLES } from '@/types'
import { PARTY_ROLE_LABELS, partyRoleLabel } from './evidence-helpers'
import { Field, NativeSelect, optionsFrom } from './form-parts'

export type RecipientKind = 'user' | 'party' | 'new'

export interface RecipientState {
  kind: RecipientKind
  userId: string | null
  partyId: string | null
  party: { name: string; role: PartyRole; organization_name: string; email: string; phone: string }
}

export function emptyRecipient(kind: RecipientKind = 'party'): RecipientState {
  return {
    kind,
    userId: null,
    partyId: null,
    party: { name: '', role: 'other', organization_name: '', email: '', phone: '' },
  }
}

/** Why the recipient is incomplete, or null when it can be sent. */
export function recipientProblem(r: RecipientState): string | null {
  if (r.kind === 'user') return r.userId ? null : 'Choose the colleague who receives the evidence'
  if (r.kind === 'party') return r.partyId ? null : 'Choose the receiving party, or add a new one'
  if (!r.party.name.trim()) return 'Enter the new party’s name'
  const email = r.party.email.trim()
  if (email && !/^\S+@\S+\.\S+$/.test(email)) return 'Enter a valid email address'
  return null
}

/** The API body part. Call only when `recipientProblem` is null. */
export function recipientInput(r: RecipientState): RecipientInput {
  if (r.kind === 'user') return { to_user_id: r.userId ?? undefined }
  if (r.kind === 'party') return { to_party_id: r.partyId ?? undefined }
  const p = r.party
  const party: NewPartyInput = { name: p.name.trim(), role: p.role }
  if (p.organization_name.trim()) party.organization_name = p.organization_name.trim()
  if (p.email.trim()) party.email = p.email.trim()
  if (p.phone.trim()) party.phone = p.phone.trim()
  return { new_party: party }
}

const KIND_LABELS: Record<RecipientKind, string> = {
  user: 'Colleague',
  party: 'External party',
  new: 'New party',
}

export function RecipientPicker({
  value,
  onChange,
  kinds = ['user', 'party', 'new'],
  disabled,
}: {
  value: RecipientState
  onChange: (next: RecipientState) => void
  kinds?: RecipientKind[]
  disabled?: boolean
}) {
  const set = (patch: Partial<RecipientState>) => onChange({ ...value, ...patch })
  const setParty = (patch: Partial<RecipientState['party']>) => set({ party: { ...value.party, ...patch } })

  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="mb-1.5 text-sm font-medium">
        Recipient<span aria-hidden className="ml-0.5 text-destructive">*</span>
      </legend>
      <div role="radiogroup" aria-label="Recipient type" className="inline-flex rounded-md border border-border p-0.5">
        {kinds.map((k) => (
          <label
            key={k}
            className={`cursor-pointer rounded px-3 py-1 text-sm transition-colors ${
              value.kind === k ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <input
              type="radio"
              name="recipient-kind"
              className="sr-only"
              checked={value.kind === k}
              onChange={() => set({ kind: k })}
            />
            {KIND_LABELS[k]}
          </label>
        ))}
      </div>

      {value.kind === 'user' && (
        <UserPicker
          value={value.userId}
          onChange={(id) => set({ userId: id })}
          ariaLabel="Recipient colleague"
          placeholder="Search colleagues…"
          disabled={disabled}
        />
      )}

      {value.kind === 'party' && (
        <EntityPicker<CustodyParty>
          value={value.partyId}
          onChange={(id) => set({ partyId: id })}
          endpoint="/custody-parties"
          params={{ sort: 'name' }}
          getId={(p) => p.id}
          getLabel={(p) => p.name}
          getDescription={(p) =>
            [p.organization_name, partyRoleLabel(p.role)].filter(Boolean).join(' · ') || undefined
          }
          itemEndpoint={(id) => `/custody-parties/${id}`}
          ariaLabel="Recipient party"
          placeholder="Search saved parties…"
          emptyMessage="No saved party matches. Use New party to add one."
          disabled={disabled}
        />
      )}

      {value.kind === 'new' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Party name" required>
            {({ id }) => (
              <Input id={id} value={value.party.name} onChange={(e) => setParty({ name: e.target.value })} maxLength={255} />
            )}
          </Field>
          <Field label="Role">
            {({ id }) => (
              <NativeSelect
                id={id}
                value={value.party.role}
                onValueChange={(v) => setParty({ role: v as PartyRole })}
                options={optionsFrom(PARTY_ROLE_LABELS).filter((o) => PARTY_ROLES.includes(o.value))}
              />
            )}
          </Field>
          <Field label="Organization">
            {({ id }) => (
              <Input
                id={id}
                value={value.party.organization_name}
                onChange={(e) => setParty({ organization_name: e.target.value })}
                maxLength={255}
              />
            )}
          </Field>
          <Field label="Email">
            {({ id }) => (
              <Input id={id} type="email" value={value.party.email} onChange={(e) => setParty({ email: e.target.value })} maxLength={255} />
            )}
          </Field>
          <Field label="Phone" className="sm:col-span-2">
            {({ id }) => (
              <Input id={id} value={value.party.phone} onChange={(e) => setParty({ phone: e.target.value })} maxLength={60} />
            )}
          </Field>
          <p className="text-xs text-muted-foreground sm:col-span-2">
            The party is saved to your organization&apos;s address book. Its details are copied into the signed
            custody entry, so later edits never change history.
          </p>
        </div>
      )}
    </fieldset>
  )
}
