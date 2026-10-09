"use client"

/**
 * System status cards (`GET /admin/system-status`). Organization sections
 * are always shown; the deployment-global infra sections (version,
 * database, migrations, Redis, rate limiting, disk / S3 details) only when
 * the backend returns them, i.e. for platform admins. A failed probe
 * (`{ok: false, error}`) renders as "Unavailable".
 */
import * as React from 'react'
import {
  Bot, CheckCircle2, Database, Gauge, GitBranch, HardDrive, Layers, Package, Plug, Server, XCircle,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Timestamp } from '@/components/ui/timestamp'
import { cn } from '@/lib/utils'
import type { ProbeFailure, StatusStorage, SystemStatus } from '@/types'

export function isProbeFailure(v: unknown): v is ProbeFailure {
  return !!v && typeof v === 'object' && !Array.isArray(v) && (v as { ok?: unknown }).ok === false && 'error' in v
}

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

function Ok({ ok, label }: { ok: boolean | null | undefined; label?: string }) {
  if (ok === null || ok === undefined) return <span className="text-xs text-muted-foreground">{label ?? 'Unknown'}</span>
  const Icon = ok ? CheckCircle2 : XCircle
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs font-medium', ok ? 'text-emerald-400' : 'text-red-400')}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label ?? (ok ? 'OK' : 'Failing')}
    </span>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-right">{children}</dd>
    </div>
  )
}

function StatusCard({
  title,
  icon: Icon,
  section,
  children,
  testId,
}: {
  title: string
  icon: React.ComponentType<{ className?: string }>
  section?: unknown
  children: React.ReactNode
  testId?: string
}) {
  const failed = isProbeFailure(section)
  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {failed ? (
          <p className="inline-flex items-center gap-1 text-sm text-red-400">
            <XCircle className="h-4 w-4" aria-hidden />
            Unavailable
          </p>
        ) : (
          <dl className="space-y-1.5">{children}</dl>
        )}
      </CardContent>
    </Card>
  )
}

export function SystemStatusGrid({ status }: { status: SystemStatus }) {
  const { storage, ai_providers, integrations, counts } = status
  const store: StatusStorage | null = storage && !isProbeFailure(storage) ? storage : null
  const disk = store?.disk

  return (
    <div className="space-y-4" data-testid="system-status">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatusCard title="Storage" icon={HardDrive} section={storage} testId="status-storage">
          <Row label="Backend">{store?.backend ? store.backend.replace(/_/g, ' ') : '—'}</Row>
          {disk && !isProbeFailure(disk) && (
            <>
              <Row label="Free">{formatBytes(disk.free_bytes)} of {formatBytes(disk.total_bytes)}</Row>
              {disk.used_pct !== null && <Row label="Used">{disk.used_pct}%</Row>}
            </>
          )}
          {disk && isProbeFailure(disk) && <Row label="Disk">Unavailable</Row>}
          {store?.bucket && <Row label="Bucket">{store.bucket}</Row>}
          {store?.endpoint_host && <Row label="Endpoint">{store.endpoint_host}</Row>}
        </StatusCard>

        <StatusCard title="AI providers" icon={Bot} section={ai_providers} testId="status-ai">
          {Array.isArray(ai_providers) && ai_providers.length === 0 && (
            <p className="text-sm text-muted-foreground">None configured</p>
          )}
          {Array.isArray(ai_providers) &&
            ai_providers.map((p) => (
              <Row key={p.provider} label={`${p.provider} (${p.source})`}>
                <Ok ok={p.last_test_ok} label={p.last_test_ok === null ? 'Not tested' : undefined} />
              </Row>
            ))}
        </StatusCard>

        <StatusCard title="Integrations" icon={Plug} section={integrations} testId="status-integrations">
          {Array.isArray(integrations) && (
            <>
              <Row label="Enabled">
                {integrations.filter((i) => i.is_enabled).length} / {integrations.length}
              </Row>
              {integrations
                .filter((i) => i.is_enabled && (i.last_test_ok === false || !!i.last_error))
                .slice(0, 5)
                .map((i) => (
                  <Row key={i.id} label={i.name}>
                    <span className="text-xs text-red-400" title={i.last_error ?? undefined}>
                      {i.last_test_ok === false ? 'Test failed' : 'Error'}
                    </span>
                  </Row>
                ))}
            </>
          )}
        </StatusCard>

        <StatusCard title="Usage" icon={Layers} section={counts} testId="status-counts">
          {!isProbeFailure(counts) && counts && (
            <>
              <Row label="Users">{counts.active_users} active / {counts.users}</Row>
              <Row label="Incidents">{counts.open_incidents} open / {counts.incidents}</Row>
              <Row label="Artifacts">
                {counts.artifacts.toLocaleString()} · {formatBytes(counts.artifact_bytes)}
              </Row>
            </>
          )}
        </StatusCard>
      </div>

      {status.infra_visible && (
        <div className="space-y-2" data-testid="status-infra">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Deployment (platform admin)</h3>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {status.app !== undefined && (
              <StatusCard title="Version" icon={Package} section={status.app} testId="status-app">
                {!isProbeFailure(status.app) && (
                  <>
                    <Row label="Version">{status.app.version ?? '—'}</Row>
                    <Row label="Commit"><span className="font-mono text-xs">{status.app.commit?.slice(0, 12) ?? '—'}</span></Row>
                    <Row label="Environment">{status.app.environment}</Row>
                  </>
                )}
              </StatusCard>
            )}
            {status.database !== undefined && (
              <StatusCard title="Database" icon={Database} section={status.database} testId="status-database">
                {!isProbeFailure(status.database) && (
                  <>
                    <Row label="Status"><Ok ok={status.database.ok} /></Row>
                    <Row label="Latency">{status.database.latency_ms} ms</Row>
                    <Row label="PostgreSQL">{status.database.server_version}</Row>
                  </>
                )}
              </StatusCard>
            )}
            {status.alembic !== undefined && (
              <StatusCard title="Migrations" icon={GitBranch} section={status.alembic} testId="status-alembic">
                {!isProbeFailure(status.alembic) && (
                  <>
                    <Row label="Schema">
                      <Ok ok={status.alembic.up_to_date} label={status.alembic.up_to_date ? 'Up to date' : 'Pending'} />
                    </Row>
                    <Row label="Current"><span className="font-mono text-xs">{status.alembic.current.join(', ') || '—'}</span></Row>
                    {!status.alembic.up_to_date && (
                      <Row label="Head"><span className="font-mono text-xs">{status.alembic.head.join(', ')}</span></Row>
                    )}
                  </>
                )}
              </StatusCard>
            )}
            {status.redis !== undefined && (
              <StatusCard title="Redis" icon={Server} section={status.redis} testId="status-redis">
                {!isProbeFailure(status.redis) && (
                  <>
                    <Row label="Status"><Ok ok={status.redis.ok} /></Row>
                    <Row label="Latency">{status.redis.latency_ms} ms</Row>
                  </>
                )}
              </StatusCard>
            )}
            {status.rate_limiting !== undefined && (
              <StatusCard title="Rate limiting" icon={Gauge} section={status.rate_limiting} testId="status-rate-limiting">
                {!isProbeFailure(status.rate_limiting) && (
                  <>
                    <Row label="Enabled"><Ok ok={status.rate_limiting.enabled} label={status.rate_limiting.enabled ? 'Yes' : 'No'} /></Row>
                    <Row label="Storage">{status.rate_limiting.storage}</Row>
                    <Row label="Default">{status.rate_limiting.default_limit}</Row>
                  </>
                )}
              </StatusCard>
            )}
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Status as of <Timestamp value={status.generated_at} />
      </p>
    </div>
  )
}
