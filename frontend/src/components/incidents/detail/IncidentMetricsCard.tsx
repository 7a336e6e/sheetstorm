"use client"

/**
 * Response metrics of one incident (W3-RT-POST), rendered in the Overview
 * `metricsSlot`: dwell, respond, contain, eradicate, recover, close and total
 * open time. Intervals that are negative (a legacy timestamp edited out of
 * order) show as "—" plus an anomaly note instead of a negative duration.
 * "Edit lifecycle times" opens the milestone editor (IRMilestoneStrip).
 */
import { AlertTriangle, Info, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { usePermission } from '@/components/auth/permission-gate'
import { useIncidentMetrics } from '@/hooks/use-incident-metrics'
import { formatSeconds, METRIC_DEFS, METRIC_LABELS } from '@/lib/post-incident'
import { EDIT_LIFECYCLE_EVENT } from './IRMilestoneStrip'
import type { FirstMaliciousSource, IncidentMetrics } from '@/types'

interface IncidentMetricsCardProps {
  incidentId: string
  /** The incident's `version`: a change (any lifecycle edit) refetches the metrics. */
  version?: number
}

const SOURCE_COPY: Record<NonNullable<FirstMaliciousSource>, string> = {
  override: 'Dwell time starts at the first malicious activity time set on this incident.',
  timeline: 'Dwell time starts at the earliest timeline event marked as malicious (IOC, MITRE-mapped or kill-chain).',
  restricted: 'Dwell time is not derived from the timeline because you do not have timeline access.',
}
const NO_SOURCE_COPY =
  'No dwell start yet: mark a timeline event as malicious, or set "First malicious activity" in the milestones.'

function Tiles({ data }: { data: IncidentMetrics }) {
  const anomalous = new Set(data.anomalies.map((a) => a.metric))
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
      {METRIC_DEFS.map(({ key, label, hint }) => {
        const value = data.durations[key]
        return (
          <div
            key={key}
            data-testid={`metric-${key}`}
            title={hint}
            className="rounded-lg border border-border bg-muted/50 px-3 py-2"
          >
            <dt className="flex items-center gap-1 text-xs text-muted-foreground">
              {anomalous.has(key) && <AlertTriangle className="h-3 w-3 text-amber-400" aria-label="out of order" />}
              {label}
            </dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums text-foreground">{formatSeconds(value)}</dd>
          </div>
        )
      })}
    </dl>
  )
}

export function IncidentMetricsCard({ incidentId, version }: IncidentMetricsCardProps) {
  const canEdit = usePermission('incidents:update')
  const { data, error, isLoading, refetch } = useIncidentMetrics(incidentId, version)

  return (
    <Card data-testid="incident-metrics">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">Response metrics</CardTitle>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" onClick={refetch} aria-label="Refresh metrics" title="Refresh">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          {canEdit && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => window.dispatchEvent(new Event(EDIT_LIFECYCLE_EVENT))}
            >
              Edit lifecycle times
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7" aria-busy="true" aria-label="Loading metrics">
            {METRIC_DEFS.map((m) => (
              <Skeleton key={m.key} className="h-16 w-full" />
            ))}
          </div>
        ) : error && !data ? (
          <p role="alert" className="text-sm text-red-400">
            Could not load the metrics: {error}
          </p>
        ) : data ? (
          <>
            <Tiles data={data} />
            {data.anomalies.length > 0 && (
              <div
                role="status"
                className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300"
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  Out-of-order lifecycle times:{' '}
                  {data.anomalies.map((a) => METRIC_LABELS[a.metric] ?? a.metric).join(', ')}. These intervals are not
                  counted; correct the timestamps.
                </span>
              </div>
            )}
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {data.sources.first_malicious ? SOURCE_COPY[data.sources.first_malicious] : NO_SOURCE_COPY}
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
