/**
 * Coalesced per-key runner for resyncs.
 *
 * `request(key)` runs `run(key)` once after `delayMs`; further requests in
 * that window are absorbed. Requests that arrive while a run is in flight
 * schedule exactly one trailing run (after the flight, again delayed). So a
 * burst of seq gaps or `incident:resync` events costs one refetch per scope.
 */
export interface Coalescer {
  request(key: string): void
  /** Cancel pending runs; later requests are ignored. */
  dispose(): void
}

interface Slot {
  timer: ReturnType<typeof setTimeout> | null
  inFlight: boolean
  trailing: boolean
}

export function createCoalescer(run: (key: string) => Promise<unknown> | unknown, delayMs = 500): Coalescer {
  const slots = new Map<string, Slot>()
  let disposed = false

  const slot = (key: string): Slot => {
    let s = slots.get(key)
    if (!s) {
      s = { timer: null, inFlight: false, trailing: false }
      slots.set(key, s)
    }
    return s
  }

  const fire = (key: string) => {
    const s = slot(key)
    s.timer = null
    if (disposed) return
    s.inFlight = true
    let result: Promise<unknown>
    try {
      result = Promise.resolve(run(key))
    } catch {
      result = Promise.resolve()
    }
    result
      .catch(() => undefined)
      .then(() => {
        s.inFlight = false
        if (s.trailing && !disposed) {
          s.trailing = false
          request(key)
        }
      })
  }

  const request = (key: string) => {
    if (disposed) return
    const s = slot(key)
    if (s.timer) return
    if (s.inFlight) {
      s.trailing = true
      return
    }
    s.timer = setTimeout(() => fire(key), delayMs)
  }

  return {
    request,
    dispose() {
      disposed = true
      slots.forEach((s) => {
        if (s.timer) clearTimeout(s.timer)
        s.timer = null
      })
      slots.clear()
    },
  }
}
