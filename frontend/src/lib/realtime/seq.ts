/**
 * Per-scope `seq` tracking for gap detection (pure).
 *
 * The server numbers events per (incident, scope). The client remembers the
 * last seq it saw per scope; a jump means events were missed (e.g. while the
 * socket was reconnecting), so that scope is resynced. `seq: null` (server
 * without Redis) disables detection for that event.
 */
import type { JoinAck } from './types'

export type SeqState = Readonly<Record<string, number>>

export function trackSeq(
  state: SeqState,
  scope: string,
  seq: number | null | undefined
): { state: SeqState; gap: boolean } {
  if (typeof seq !== 'number' || !Number.isFinite(seq)) return { state, gap: false }
  const last = state[scope]
  if (last === undefined) return { state: { ...state, [scope]: seq }, gap: false }
  // Duplicate or reordered delivery: nothing missed, keep the high-water mark.
  if (seq <= last) return { state, gap: false }
  return { state: { ...state, [scope]: seq }, gap: seq > last + 1 }
}

/**
 * Reconcile the join ack with what we saw before. On the first join it only
 * records the server's counters. On a rejoin (reconnect) every scope whose
 * counter moved, went backwards (counter reset) or is unknown is reported.
 */
export function gapsAfterJoin(
  state: SeqState,
  ack: Pick<JoinAck, 'scopes' | 'seq'>,
  rejoin: boolean
): { state: SeqState; gaps: string[] } {
  const seqs = ack.seq ?? {}
  const next: Record<string, number> = {}
  const gaps: string[] = []
  for (const scope of ack.scopes ?? []) {
    const s = seqs[scope]
    const last = state[scope]
    if (typeof s === 'number' && Number.isFinite(s)) {
      if (rejoin) {
        next[scope] = s
        if (s !== last) gaps.push(scope)
      } else {
        // Events may have arrived between the join and its ack.
        next[scope] = last === undefined ? s : Math.max(s, last)
      }
    } else if (rejoin) {
      gaps.push(scope)
    }
  }
  return { state: next, gaps }
}
