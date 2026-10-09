"use client"

/**
 * Adapters that give the incident tabs which need more than a table the
 * uniform `IncidentTabProps` shape used by `TAB_REGISTRY`.
 *
 * Whole-incident datasets (timeline, hosts) come from `useAllPages`, which
 * shares one cached request between Overview, Events views, MITRE and the
 * graph, and refetches everywhere on `invalidate('/incidents/<id>/<entity>')`.
 */
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Clock, LayoutList, Star } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { OverviewTab } from '@/components/incidents/detail/OverviewTab'
import { EventsTable } from '@/components/incidents/EventsTable'
import { IOCVisualTimeline, PinnedTimelineTab } from '@/components/incidents/timeline/IOCVisualTimeline'
import { AttackGraphViewer } from '@/components/attack-graph/AttackGraphViewer'
import { MitreNavigator } from '@/components/incidents/MitreNavigator'
import { useAllPages } from '@/hooks/use-paginated-query'
import type { CompromisedHost, TimelineEvent } from '@/types'
import type { IncidentTabProps } from './tabs'

// `useAllPages().items` is a fresh [] on every render until data arrives;
// hand children a stable empty list so their prop-driven effects settle.
const NO_HOSTS: CompromisedHost[] = []
const NO_EVENTS: TimelineEvent[] = []

export function OverviewPanel({ incident, incidentId, onNavigate, onIncidentChanged }: IncidentTabProps) {
  return (
    <OverviewTab
      incident={incident}
      incidentId={incidentId}
      onViewEvents={() => onNavigate('events')}
      onIncidentUpdated={onIncidentChanged}
    />
  )
}

const EVENT_VIEWS = [
  { id: 'table', label: 'Table', icon: LayoutList },
  { id: 'timeline', label: 'Visual Timeline', icon: Clock },
  { id: 'table-timeline', label: 'Table Timeline', icon: Star },
] as const
type EventsView = (typeof EVENT_VIEWS)[number]['id']
const EVENTS_VIEW_PARAM = 'events.view'

export function EventsPanel({ incidentId, focusRowId }: IncidentTabProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const raw = searchParams?.get(EVENTS_VIEW_PARAM)
  const view: EventsView = EVENT_VIEWS.some((v) => v.id === raw) ? (raw as EventsView) : 'table'

  const setView = (next: EventsView) => {
    const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
    if (next === 'table') params.delete(EVENTS_VIEW_PARAM)
    else params.set(EVENTS_VIEW_PARAM, next)
    const qs = params.toString()
    router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-2" role="group" aria-label="Events view">
        {EVENT_VIEWS.map(({ id, label, icon: Icon }) => (
          <Button
            key={id}
            variant={view === id ? 'default' : 'outline'}
            size="sm"
            aria-pressed={view === id}
            onClick={() => setView(id)}
            className="gap-1.5"
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </Button>
        ))}
      </div>
      {view === 'table' ? (
        <EventsTable incidentId={incidentId} focusRowId={focusRowId} />
      ) : view === 'timeline' ? (
        <IOCVisualTimeline incidentId={incidentId} />
      ) : (
        <PinnedTimelineTab incidentId={incidentId} />
      )}
    </>
  )
}

export function GraphPanel({ incidentId }: IncidentTabProps) {
  const hosts = useAllPages<CompromisedHost>(`/incidents/${incidentId}/hosts`, { live: 'host' })
  const timeline = useAllPages<TimelineEvent>(`/incidents/${incidentId}/timeline`, { live: 'timeline_event' })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Attack Graph</CardTitle>
        <CardDescription>Auto-generated visualization of the attack path</CardDescription>
      </CardHeader>
      <CardContent>
        <AttackGraphViewer
          incidentId={incidentId}
          hosts={hosts.items.length ? hosts.items : NO_HOSTS}
          timeline={timeline.items.length ? timeline.items : NO_EVENTS}
        />
      </CardContent>
    </Card>
  )
}

export function MitrePanel({ incidentId }: IncidentTabProps) {
  const timeline = useAllPages<TimelineEvent>(`/incidents/${incidentId}/timeline`, { live: 'timeline_event' })
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>MITRE ATT&CK Matrix</CardTitle>
          <CardDescription>Visualize technique coverage and attack chains from timeline events</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {timeline.truncated && (
          <p className="mb-3 text-xs text-amber-400">
            Showing the first {timeline.items.length.toLocaleString()} of {timeline.total.toLocaleString()} events.
          </p>
        )}
        <MitreNavigator events={timeline.items.length ? timeline.items : NO_EVENTS} incidentId={incidentId} />
      </CardContent>
    </Card>
  )
}
