"use client"

/**
 * Median / p90 per metric as plain Tailwind horizontal bars (no chart
 * dependency). The numbers are always printed, so the bars are decoration
 * (`aria-hidden`). `scale` gives each metric's bar maximum in seconds, shared
 * across groups so they stay comparable.
 */
import { AlertTriangle } from 'lucide-react'
import { barPercent, formatSeconds, METRIC_DEFS } from '@/lib/post-incident'
import type { MetricName, MetricStats } from '@/types'

export type MetricScale = Partial<Record<MetricName, number>>

/** Largest p90 (falling back to median) of each metric over several stat sets. */
export function metricScale(sets: MetricStats[]): MetricScale {
  const scale: MetricScale = {}
  for (const stats of sets) {
    for (const { key } of METRIC_DEFS) {
      const s = stats[key]
      const top = Math.max(s?.p90 ?? 0, s?.median ?? 0)
      if (top > (scale[key] ?? 0)) scale[key] = top
    }
  }
  return scale
}

export function MetricBars({
  stats,
  scale,
  minSize,
}: {
  stats: MetricStats
  scale: MetricScale
  /** Values needed before a median is shown (server `min_group_size`). */
  minSize: number
}) {
  return (
    <div role="table" aria-label="Response metrics" className="space-y-3">
      <div role="row" className="hidden grid-cols-[11rem_1fr_6rem_6rem_3rem] gap-3 text-xs text-muted-foreground sm:grid">
        <span role="columnheader">Metric</span>
        <span role="columnheader" aria-hidden="true" />
        <span role="columnheader" className="text-right">Median</span>
        <span role="columnheader" className="text-right">p90</span>
        <span role="columnheader" className="text-right">n</span>
      </div>
      {METRIC_DEFS.map(({ key, label, hint }) => {
        const s = stats[key]
        const max = scale[key] ?? 0
        const enough = s.n >= minSize
        return (
          <div
            key={key}
            role="row"
            data-testid={`metric-row-${key}`}
            title={hint}
            className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[11rem_1fr_6rem_6rem_3rem]"
          >
            <span role="rowheader" className="flex items-center gap-1 text-sm">
              {label}
              {s.anomalies > 0 && (
                <span title={`${s.anomalies} incident(s) with out-of-order times, not counted`}>
                  <AlertTriangle className="h-3 w-3 text-amber-400" aria-label={`${s.anomalies} out of order`} />
                </span>
              )}
            </span>
            <div aria-hidden="true" className="relative order-last col-span-2 h-3 rounded bg-muted/50 sm:order-none sm:col-span-1">
              {enough && (
                <>
                  <div
                    className="absolute inset-y-0 left-0 rounded bg-primary/30"
                    style={{ width: `${barPercent(s.p90, max)}%` }}
                  />
                  <div
                    className="absolute inset-y-0 left-0 rounded bg-primary"
                    style={{ width: `${barPercent(s.median, max)}%` }}
                  />
                </>
              )}
            </div>
            <span role="cell" className="text-right text-sm tabular-nums" data-testid={`median-${key}`}>
              {enough ? formatSeconds(s.median) : '—'}
            </span>
            <span role="cell" className="hidden text-right text-sm tabular-nums sm:block" data-testid={`p90-${key}`}>
              {enough ? formatSeconds(s.p90) : '—'}
            </span>
            <span
              role="cell"
              className="hidden text-right text-xs tabular-nums text-muted-foreground sm:block"
              title={enough ? undefined : `Needs at least ${minSize} incidents with this interval`}
            >
              {s.n}
            </span>
          </div>
        )
      })}
    </div>
  )
}
