'use client'

import * as React from 'react'
import { Input, type InputProps } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useTimePrefStore } from '@/lib/store'
import { formatOffset, fromInputValue, parseTs, toInputValue, type TimeMode } from '@/lib/time'

export interface DateTimeInputProps
  extends Omit<InputProps, 'type' | 'value' | 'defaultValue' | 'onChange' | 'step'> {
  /** ISO 8601 string (any offset) or null/'' for empty. */
  value: string | null | undefined
  /** Receives an ISO string in UTC (`…Z`), or null when cleared/incomplete. */
  onChange: (iso: string | null) => void
  /** Override the user's preference (default: the UTC/Local toggle). */
  mode?: TimeMode
  /** Seconds granularity of the picker (default 1; ≥60 hides seconds). */
  step?: number
  /** Show the "UTC" / "Local (UTC±hh:mm)" suffix (default true). */
  showZone?: boolean
}

const isoOrNull = (v: string | null | undefined) => parseTs(v)?.toISOString() ?? null

/**
 * `datetime-local` that speaks ISO: it shows `value` in the current mode
 * and emits UTC ISO strings, so forms never hold or send naive wall-clock
 * strings. Use it for every timestamp input.
 */
export const DateTimeInput = React.forwardRef<HTMLInputElement, DateTimeInputProps>(
  function DateTimeInput(
    { value, onChange, mode: modeProp, step = 1, showZone = true, className, ...rest },
    ref,
  ) {
    const prefMode = useTimePrefStore((s) => s.mode)
    const mode = modeProp ?? prefMode
    const seconds = step < 60
    const zoneId = React.useId()

    // The draft holds what the user is typing (possibly incomplete, which the
    // browser reports as ''). It is re-derived from `value` only when
    // `value`/`mode` change from outside, never mid-edit.
    const [draft, setDraft] = React.useState(() => toInputValue(value, mode, { seconds }))
    const [synced, setSynced] = React.useState({ value, mode })
    if (synced.value !== value || synced.mode !== mode) {
      setSynced({ value, mode })
      if (synced.mode !== mode || fromInputValue(draft, mode) !== isoOrNull(value)) {
        setDraft(toInputValue(value, mode, { seconds }))
      }
    }

    const zone = mode === 'utc' ? 'UTC' : `Local (${formatOffset(parseTs(value) ?? new Date())})`
    const describedBy = [rest['aria-describedby'], showZone ? zoneId : undefined].filter(Boolean).join(' ') || undefined

    return (
      <div className="flex w-full items-center gap-2">
        <Input
          {...rest}
          ref={ref}
          type="datetime-local"
          step={step}
          value={draft}
          aria-describedby={describedBy}
          className={cn('min-w-0 flex-1', className)}
          onChange={(e) => {
            setDraft(e.target.value)
            onChange(fromInputValue(e.target.value, mode))
          }}
        />
        {showZone && (
          <span id={zoneId} className="shrink-0 whitespace-nowrap text-xs text-muted-foreground" suppressHydrationWarning>
            {zone}
          </span>
        )}
      </div>
    )
  },
)
