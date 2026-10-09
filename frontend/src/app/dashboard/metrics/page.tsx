"use client"

/**
 * Organization response metrics (W3-RT-POST, `metrics:read`): median and p90
 * of dwell, respond, contain, eradicate, recover and close times over the
 * incidents the caller can see, for a date range, optionally grouped by
 * severity, classification or detection source. A metric with fewer than
 * three values shows only its count.
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { MetricBars, metricScale } from '@/components/metrics/MetricBars'
import { isAbortError } from '@/lib/api'
import { postIncident } from '@/lib/endpoints/post-incident'
import { describeError } from '@/lib/errors'
import { GROUP_BY_OPTIONS, RANGE_PRESETS, groupLabel, presetRange, rangeProblem } from '@/lib/post-incident'
import type { MetricsDateField, MetricsGroupBy, OrgMetrics } from '@/types'

type Preset = (typeof RANGE_PRESETS)[number]['id'] | 'custom'

const DATE_FIELD_OPTIONS: { value: MetricsDateField; label: string }[] = [
  { value: 'detected_at', label: 'Detected in range' },
  { value: 'closed_at', label: 'Closed in range' },
]

export default function MetricsPage() {
  const [preset, setPreset] = useState<Preset>('90')
  const [custom, setCustom] = useState(() => presetRange(90))
  const [groupBy, setGroupBy] = useState<MetricsGroupBy>('none')
  const [dateField, setDateField] = useState<MetricsDateField>('detected_at')
  // The last settled response and the request it answered; `loading` is
  // derived (the response is not for the current request yet).
  const [result, setResult] = useState<{ key: string; data: OrgMetrics | null; error: string | null } | null>(null)

  const range = useMemo(() => {
    if (preset === 'custom') return custom
    return presetRange(RANGE_PRESETS.find((p) => p.id === preset)?.days ?? 90)
  }, [preset, custom])
  const problem = preset === 'custom' ? rangeProblem(custom.from, custom.to) : null

  const requestKey = `${range.from}|${range.to}|${groupBy}|${dateField}`

  useEffect(() => {
    if (problem) return
    const controller = new AbortController()
    postIncident
      .orgMetrics({ ...range, group_by: groupBy, date_field: dateField }, { signal: controller.signal })
      .then((data) => setResult({ key: requestKey, data, error: null }))
      .catch((err: unknown) => {
        if (isAbortError(err)) return
        setResult((prev) => ({ key: requestKey, data: prev?.data ?? null, error: describeError(err).description }))
      })
    return () => controller.abort()
  }, [range, groupBy, dateField, problem, requestKey])

  const data = result?.data ?? null
  const error = result?.error ?? null
  const loading = !problem && result?.key !== requestKey

  const scale = useMemo(
    () => (data ? metricScale([data.overall.metrics, ...data.groups.map((g) => g.metrics)]) : {}),
    [data]
  )

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Response metrics</h1>
        <p className="text-sm text-muted-foreground">
          Median and 90th percentile of the IR milestones over the incidents you can access.
        </p>
      </div>

      <Card>
        <CardContent className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Period</Label>
            <Select value={preset} onValueChange={(v) => setPreset(v as Preset)}>
              <SelectTrigger aria-label="Period">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RANGE_PRESETS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
                <SelectItem value="custom">Custom range</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Incidents</Label>
            <Select value={dateField} onValueChange={(v) => setDateField(v as MetricsDateField)}>
              <SelectTrigger aria-label="Date field">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DATE_FIELD_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Group by</Label>
            <Select value={groupBy} onValueChange={(v) => setGroupBy(v as MetricsGroupBy)}>
              <SelectTrigger aria-label="Group by">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GROUP_BY_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {preset === 'custom' && (
            <div className="grid grid-cols-2 gap-2 sm:col-span-2 lg:col-span-4 lg:max-w-md">
              <div className="space-y-1.5">
                <Label htmlFor="metrics-from">From</Label>
                <Input
                  id="metrics-from"
                  type="date"
                  value={custom.from}
                  onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="metrics-to">To</Label>
                <Input
                  id="metrics-to"
                  type="date"
                  value={custom.to}
                  onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))}
                />
              </div>
              {problem && (
                <p role="alert" className="col-span-2 text-sm text-red-400">
                  {problem}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {error && !problem && (
        <p role="alert" className="text-sm text-red-400">
          Could not load the metrics: {error}
        </p>
      )}

      {loading && !data ? (
        <div aria-busy="true" aria-label="Loading metrics" className="space-y-3">
          <Skeleton className="h-64 w-full" />
        </div>
      ) : data ? (
        <div className={loading ? 'space-y-6 opacity-60' : 'space-y-6'} aria-busy={loading}>
          <Card>
            <CardHeader>
              <CardTitle>All incidents</CardTitle>
              <CardDescription data-testid="overall-count">
                {data.overall.n} incident{data.overall.n === 1 ? '' : 's'} in range
                {data.overall.n === 0 ? '. Nothing to show for this period.' : ''}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MetricBars stats={data.overall.metrics} scale={scale} minSize={data.min_group_size} />
              <p className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                Medians need at least {data.min_group_size} values. Incidents with out-of-order timestamps are
                flagged and left out of that metric.
              </p>
            </CardContent>
          </Card>

          {data.groups.map((g) => (
            <Card key={String(g.key)} data-testid="metrics-group">
              <CardHeader>
                <CardTitle className="text-base">{groupLabel(data.group_by, g.key)}</CardTitle>
                <CardDescription>
                  {g.n} incident{g.n === 1 ? '' : 's'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <MetricBars stats={g.metrics} scale={scale} minSize={data.min_group_size} />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  )
}
