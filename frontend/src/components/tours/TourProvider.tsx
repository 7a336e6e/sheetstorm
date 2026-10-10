"use client"

/**
 * Guided tours (see lib/tours.ts). Mounted once in the dashboard layout:
 * starts the current page's tour on the first visit (unless an admin switched
 * tours off for the user), and lets `useTourStore().start()` replay it.
 * Finished or skipped tours are saved to `preferences.tours_seen`.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { usePathname } from 'next/navigation'
import { create } from 'zustand'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { tourForPath, visibleSteps, type TourDef, type TourStep } from '@/lib/tours'

interface TourState {
  /** Tour being shown, if any. */
  active: TourDef | null
  steps: TourStep[]
  index: number
  start: (tour: TourDef) => void
  stop: () => void
  go: (index: number) => void
}

export const useTourStore = create<TourState>((set) => ({
  active: null,
  steps: [],
  index: 0,
  start: (tour) => {
    const steps = visibleSteps(tour)
    if (steps.length) set({ active: tour, steps, index: 0 })
  },
  stop: () => set({ active: null, steps: [], index: 0 }),
  go: (index) => set({ index }),
}))

/** Remember a finished/skipped tour (optimistic; best effort on the server). */
function markSeen(tourId: string) {
  const { user } = useAuthStore.getState()
  if (!user) return
  const seen = Array.from(new Set([...(user.preferences?.tours_seen ?? []), tourId]))
  useAuthStore.setState({ user: { ...user, preferences: { ...user.preferences, tours_seen: seen } } })
  api.patch('/auth/me/preferences', { tours_seen: seen }).catch(() => {
    /* not critical: the tour may show once more */
  })
}

/** Auto-start delay, so the page has rendered its anchors. */
const START_DELAY_MS = 900

export function TourProvider() {
  const pathname = usePathname()
  const user = useAuthStore((s) => s.user)
  const { active, start, stop } = useTourStore()
  const enabled = !!user && user.tours_enabled !== false && !user.must_change_password

  useEffect(() => {
    if (!enabled || active) return
    const tour = tourForPath(pathname)
    if (!tour || (user?.preferences?.tours_seen ?? []).includes(tour.id)) return
    const timer = window.setTimeout(() => start(tour), START_DELAY_MS)
    return () => window.clearTimeout(timer)
    // Only on navigation / when the user (or their switch) changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, enabled, user?.id])

  // Leaving the page ends its tour.
  useEffect(() => {
    if (active && !active.match(pathname ?? '')) stop()
  }, [pathname, active, stop])

  if (!active) return null
  return <TourOverlay onClose={(id) => { markSeen(id); stop() }} />
}

interface Rect {
  top: number
  left: number
  width: number
  height: number
}

const PAD = 6
const CARD_W = 340

function TourOverlay({ onClose }: { onClose: (tourId: string) => void }) {
  const { active, steps, index, go } = useTourStore()
  const step = steps[index]
  const [rect, setRect] = useState<Rect | null>(null)

  const measure = useCallback(() => {
    if (!step?.target) {
      setRect(null)
      return
    }
    const el = document.querySelector(`[data-tour="${step.target}"]`)
    if (!el) {
      setRect(null)
      return
    }
    const r = el.getBoundingClientRect()
    setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 })
  }, [step])

  useLayoutEffect(() => {
    const el = step?.target ? document.querySelector(`[data-tour="${step.target}"]`) : null
    el?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    measure()
    const t = window.setTimeout(measure, 350) // after smooth scrolling
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.clearTimeout(t)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [step, measure])

  const last = index === steps.length - 1
  const finish = useCallback(() => active && onClose(active.id), [active, onClose])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') finish()
      else if (e.key === 'ArrowRight' && !last) go(index + 1)
      else if (e.key === 'ArrowLeft' && index > 0) go(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [finish, go, index, last])

  const cardStyle = useMemo(() => {
    if (!rect || typeof window === 'undefined') return { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
    const vw = window.innerWidth
    const vh = window.innerHeight
    const left = Math.min(Math.max(12, rect.left), vw - CARD_W - 12)
    const below = rect.top + rect.height + 12
    const top = below + 200 < vh ? below : Math.max(12, rect.top - 212)
    return { top, left }
  }, [rect])

  if (!active || !step) return null
  return (
    <div className="fixed inset-0 z-[90]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* Dim everything except the highlighted element (one big box-shadow). */}
      {rect ? (
        <div
          className="pointer-events-none fixed rounded-lg ring-2 ring-primary transition-all duration-200"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height, boxShadow: '0 0 0 9999px rgba(0,0,0,0.6)' }}
        />
      ) : (
        <div className="fixed inset-0 bg-black/60" />
      )}
      <div
        className="fixed w-[340px] max-w-[calc(100vw-24px)] space-y-3 rounded-lg border border-white/10 bg-slate-900 p-4 shadow-2xl"
        style={cardStyle}
      >
        <div className="flex items-baseline justify-between gap-2">
          <h2 id="tour-title" className="text-sm font-semibold">{step.title}</h2>
          <span className="shrink-0 text-xs text-muted-foreground">{index + 1} / {steps.length}</span>
        </div>
        <p className="text-sm text-muted-foreground">{step.body}</p>
        <div className="flex items-center justify-between gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={finish}>{last ? 'Close' : 'Skip tour'}</Button>
          <div className="flex gap-2">
            {index > 0 && <Button variant="outline" size="sm" onClick={() => go(index - 1)}>Back</Button>}
            <Button size="sm" onClick={() => (last ? finish() : go(index + 1))} autoFocus>
              {last ? 'Done' : 'Next'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Sidebar button: replay the current page's tour (hidden when tours are off). */
export function useCurrentTour(): { tour: TourDef | null; enabled: boolean } {
  const pathname = usePathname()
  const user = useAuthStore((s) => s.user)
  return { tour: tourForPath(pathname), enabled: !!user && user.tours_enabled !== false }
}
