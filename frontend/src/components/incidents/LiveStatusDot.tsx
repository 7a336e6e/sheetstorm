"use client"

/**
 * Connection state of the incident's live updates: live / connecting /
 * offline ("Live updates paused" while the socket is down).
 */
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { LiveStatus } from '@/lib/realtime/types'

const COPY: Record<LiveStatus, { label: string; hint: string; dot: string }> = {
  live: {
    label: 'Live',
    hint: 'Changes by others appear as they happen.',
    dot: 'bg-emerald-500',
  },
  connecting: {
    label: 'Connecting',
    hint: 'Joining live updates…',
    dot: 'bg-amber-500 animate-pulse',
  },
  offline: {
    label: 'Offline',
    hint: 'Live updates paused. Reconnecting; the page resyncs when back online.',
    dot: 'bg-muted-foreground',
  },
}

export function LiveStatusDot({ status, className }: { status: LiveStatus; className?: string }) {
  const c = COPY[status]
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            role="status"
            aria-label={`Live updates: ${c.label}`}
            data-status={status}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2 py-0.5 text-xs text-muted-foreground',
              className
            )}
          >
            <span aria-hidden className={cn('h-2 w-2 rounded-full', c.dot)} />
            {c.label}
          </span>
        </TooltipTrigger>
        <TooltipContent>{c.hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export default LiveStatusDot
