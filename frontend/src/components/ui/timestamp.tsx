'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useTimePrefStore } from '@/lib/store'
import { formatTs, parseTs, type TimeMode } from '@/lib/time'

export interface TimestampProps {
  /** ISO string from the API (or a Date). */
  value: string | Date | null | undefined
  /** Override the user's preference (default: the UTC/Local toggle). */
  mode?: TimeMode
  /** Show seconds (default true). */
  seconds?: boolean
  /** Rendered when value is empty or invalid. */
  fallback?: ReactNode
  className?: string
}

/**
 * A timestamp in the user's display mode, with the other mode in the
 * tooltip. Renders a semantic `<time dateTime>` element.
 */
export function Timestamp({ value, mode, seconds = true, fallback = '—', className }: TimestampProps) {
  const prefMode = useTimePrefStore((s) => s.mode)
  const effective = mode ?? prefMode
  const date = parseTs(value)
  if (!date) return <span className={className}>{fallback}</span>

  const other: TimeMode = effective === 'utc' ? 'local' : 'utc'
  return (
    <time
      dateTime={date.toISOString()}
      title={formatTs(date, other)}
      className={cn('tabular-nums', className)}
      suppressHydrationWarning
    >
      {formatTs(date, effective, { seconds })}
    </time>
  )
}
