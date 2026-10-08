'use client'

import { cn } from '@/lib/utils'
import { useTimePrefStore } from '@/lib/store'
import type { TimeMode } from '@/lib/time'

const OPTIONS: { value: TimeMode; label: string; title: string }[] = [
  { value: 'utc', label: 'UTC', title: 'Show and enter times in UTC' },
  { value: 'local', label: 'Local', title: 'Show and enter times in your browser time zone' },
]

export interface TimeModeToggleProps {
  className?: string
}

/** Two-segment `UTC | Local` control bound to the user's time preference. */
export function TimeModeToggle({ className }: TimeModeToggleProps) {
  const mode = useTimePrefStore((s) => s.mode)
  const setMode = useTimePrefStore((s) => s.setMode)

  return (
    <div
      role="group"
      aria-label="Time zone for timestamps"
      className={cn('inline-flex h-7 items-center rounded-md border border-white/10 bg-slate-900 p-0.5 text-xs', className)}
    >
      {OPTIONS.map((opt) => {
        const active = mode === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            title={opt.title}
            aria-pressed={active}
            suppressHydrationWarning
            onClick={() => setMode(opt.value)}
            className={cn(
              'h-full rounded px-2 font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary',
              active ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
