"use client"

/** Review participants: user chips plus a user search to add more. */
import { X } from 'lucide-react'
import { UserPicker } from '@/components/ui/entity-picker'

export const MAX_PARTICIPANTS = 50

interface Props {
  /** User ids. */
  value: string[]
  /** Names for ids we already know (from the server or the picker). */
  names: Record<string, string>
  onChange(ids: string[], names: Record<string, string>): void
  disabled?: boolean
}

export function ParticipantsEditor({ value, names, onChange, disabled }: Props) {
  return (
    <div className="space-y-3">
      {value.length === 0 ? (
        <p className="text-sm text-muted-foreground">No participants recorded.</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label="Participants">
          {value.map((id) => (
            <li
              key={id}
              className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-2 py-1 text-sm"
            >
              <span>{names[id] ?? 'Unknown user'}</span>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => onChange(value.filter((v) => v !== id), names)}
                  aria-label={`Remove participant ${names[id] ?? id}`}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!disabled && value.length < MAX_PARTICIPANTS && (
        <UserPicker
          value={null}
          ariaLabel="Add participant"
          placeholder="Add a participant…"
          clearable={false}
          onChange={(id, user) => {
            if (!id || value.includes(id)) return
            onChange([...value, id], { ...names, [id]: user?.name || user?.email || id })
          }}
        />
      )}
    </div>
  )
}
