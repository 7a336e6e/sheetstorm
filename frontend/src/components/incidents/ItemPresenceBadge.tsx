"use client"

/**
 * "Dana is editing" marker for a row or an edit dialog. Reads the incident
 * page's presence; renders nothing when nobody else is editing that item or
 * outside an incident page. Edit dialogs announce themselves with
 * `useIncidentRealtimeContext()?.setFocus({entity, id}, 'editing')` on open
 * and `setFocus(null)` on close.
 */
import { useIncidentRealtimeContext } from '@/hooks/use-incident-realtime'
import { cn } from '@/lib/utils'
import type { PresenceUser } from '@/lib/realtime/types'

/** Names of other users editing `entity`/`id` (deduplicated). */
export function editorsOf(users: PresenceUser[], entity: string, id: string, selfUserId?: string): string[] {
  const names = new Set<string>()
  users.forEach((u) => {
    if (u.user_id === selfUserId || u.mode !== 'editing' || !u.focus) return
    if (u.focus.entity === entity && u.focus.id === id) names.add(u.name || 'Someone')
  })
  return Array.from(names)
}

export function editingLabel(names: string[]): string {
  if (names.length === 0) return ''
  if (names.length === 1) return `${names[0]} is editing`
  if (names.length === 2) return `${names[0]} and ${names[1]} are editing`
  return `${names[0]} and ${names.length - 1} others are editing`
}

export function ItemPresenceBadge({ entity, id, className }: { entity: string; id: string; className?: string }) {
  const rt = useIncidentRealtimeContext()
  if (!rt) return null
  const names = editorsOf(rt.presence, entity, id, rt.selfUserId)
  if (names.length === 0) return null
  return (
    <span
      role="status"
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400',
        className
      )}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
      {editingLabel(names)}
    </span>
  )
}

export default ItemPresenceBadge
