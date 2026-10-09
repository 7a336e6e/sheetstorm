"use client"

/**
 * Who is on this incident: stacked initials (max 5, then +N), one per user
 * (a user with several tabs counts once; "editing" wins over "viewing").
 */
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { PresenceUser } from '@/lib/realtime/types'

export const MAX_AVATARS = 5

export interface PresenceSummary {
  userId: string
  name: string
  editing: PresenceUser['focus']
  isSelf: boolean
}

const ENTITY_LABEL: Record<string, string> = {
  timeline_event: 'an event',
  host: 'a host',
  account: 'an account',
  network_ioc: 'a network IOC',
  host_ioc: 'a host IOC',
  malware: 'a malware entry',
  task: 'a task',
  case_note: 'a note',
  graph_node: 'a graph node',
  graph_edge: 'a graph edge',
  incident: 'the incident',
}

export function describeFocus(focus: PresenceUser['focus']): string {
  if (!focus) return 'viewing'
  return `editing ${ENTITY_LABEL[focus.entity] ?? focus.entity.replace(/_/g, ' ')}`
}

/** One entry per user, self first, then by name. */
export function summarizePresence(users: PresenceUser[], selfUserId?: string): PresenceSummary[] {
  const byUser = new Map<string, PresenceSummary>()
  users.forEach((u) => {
    const editing = u.mode === 'editing' ? u.focus : null
    const prev = byUser.get(u.user_id)
    if (!prev) {
      byUser.set(u.user_id, { userId: u.user_id, name: u.name || 'Unknown', editing, isSelf: u.user_id === selfUserId })
    } else if (!prev.editing && editing) {
      prev.editing = editing
    }
  })
  return Array.from(byUser.values()).sort((a, b) =>
    a.isSelf !== b.isSelf ? (a.isSelf ? -1 : 1) : a.name.localeCompare(b.name)
  )
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const s = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]
  return s.toUpperCase()
}

export function PresenceAvatars({
  users,
  selfUserId,
  className,
}: {
  users: PresenceUser[]
  selfUserId?: string
  className?: string
}) {
  const people = summarizePresence(users, selfUserId)
  if (people.length === 0) return null
  const shown = people.slice(0, MAX_AVATARS)
  const extra = people.slice(MAX_AVATARS)

  return (
    <TooltipProvider delayDuration={150}>
      <div className={cn('flex items-center', className)} aria-label={`${people.length} on this incident`} role="group">
        {shown.map((p) => (
          <Tooltip key={p.userId}>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                data-testid="presence-avatar"
                aria-label={`${p.isSelf ? 'You' : p.name}, ${describeFocus(p.editing)}`}
                className={cn(
                  '-ml-1.5 first:ml-0 inline-flex h-7 w-7 items-center justify-center rounded-full border-2 border-background bg-slate-700 text-[11px] font-semibold text-foreground',
                  p.editing && 'ring-2 ring-amber-500/70',
                  p.isSelf && 'bg-primary/30'
                )}
              >
                {initials(p.name)}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {p.isSelf ? `${p.name} (you)` : p.name}: {describeFocus(p.editing)}
            </TooltipContent>
          </Tooltip>
        ))}
        {extra.length > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                aria-label={`${extra.length} more`}
                className="-ml-1.5 inline-flex h-7 min-w-7 items-center justify-center rounded-full border-2 border-background bg-slate-800 px-1 text-[11px] text-muted-foreground"
              >
                +{extra.length}
              </span>
            </TooltipTrigger>
            <TooltipContent>{extra.map((p) => p.name).join(', ')}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </TooltipProvider>
  )
}

export default PresenceAvatars
