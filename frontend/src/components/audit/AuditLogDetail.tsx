"use client"

/**
 * Expanded audit row: identity, request, network, device, event, chain
 * position and, when the row carries `details.changes`, the before/after
 * diff. Other `details` keys are listed as plain key/value pairs.
 */
import * as React from 'react'
import {
  Activity, AlertTriangle, ArrowRight, Clock, Database, FileText, Gauge, Globe, Hash,
  Laptop, Link2, Link as LinkIcon, MapPin, Monitor, Server, Shield, User,
} from 'lucide-react'
import { Timestamp } from '@/components/ui/timestamp'
import { cn } from '@/lib/utils'
import type { AuditLogEntry } from '@/types'
import { AuditDiffViewer, hasChanges } from './AuditDiffViewer'
import { shortHash } from './AuditIntegrityPanel'

export function humanize(s: string | null | undefined): string {
  if (!s) return ''
  return s.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
}

/** Readable names for actions whose generic humanized form is unclear. */
export const ACTION_LABELS: Record<string, string> = {
  custody_chain_verified: 'Custody chain verified',
  update_audit_settings: 'Update audit settings',
  legal_hold_enabled: 'Legal hold placed',
  legal_hold_released: 'Legal hold released',
  audit_purge: 'Audit purge',
  audit_purge_skipped: 'Audit purge skipped (legal hold)',
  ai_tlp_policy_loosened: 'AI TLP policy loosened',
}

/**
 * Display label of an audit action. `custody_chain_verified` rows (opening /
 * verifying an evidence item) carry the verification result in
 * `details.status`, shown in parentheses.
 */
export function actionLabel(action: string, details?: unknown): string {
  const base = ACTION_LABELS[action] ?? humanize(action)
  if (action === 'custody_chain_verified' && details && typeof details === 'object') {
    const status = (details as Record<string, unknown>).status
    if (typeof status === 'string' && status) return `${base} (${status.replace(/_/g, ' ')})`
  }
  return base
}

export function statusTone(code?: number | null): string {
  if (!code) return 'text-muted-foreground'
  if (code < 300) return 'text-emerald-400'
  if (code < 400) return 'text-amber-400'
  return 'text-red-400'
}

function geoText(a: AuditLogEntry): string | null {
  const parts = [a.geo_city, a.geo_region, a.geo_country].filter(Boolean)
  return parts.length ? parts.join(', ') : null
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-white/5 pb-3 last:border-b-0 last:pb-0">
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</h4>
      <div className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </section>
  )
}

function Field({
  icon: Icon,
  label,
  children,
  mono,
  wrap,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  children: React.ReactNode
  mono?: boolean
  wrap?: boolean
  className?: string
}) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <p className="text-[11px] text-muted-foreground">{label}</p>
        <div className={cn('text-sm', mono && 'font-mono text-xs', wrap ? 'break-all' : 'truncate', className)}>{children}</div>
      </div>
    </div>
  )
}

function stringify(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}

export function AuditLogDetail({ log }: { log: AuditLogEntry }) {
  const geo = geoText(log)
  const details = (log.details ?? {}) as Record<string, unknown>
  const otherDetails = Object.entries(details).filter(([k]) => k !== 'changes')
  const showDiff = hasChanges(details)

  return (
    <div className="space-y-4 rounded-md border border-white/10 bg-slate-900/40 p-4" data-testid="audit-log-detail">
      {showDiff && (
        <section>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Changes</h4>
          <AuditDiffViewer changes={details.changes} />
        </section>
      )}

      <Section title="User & identity">
        <Field icon={User} label="User">{log.user?.name || log.user_email || 'System'}</Field>
        {(log.user?.email || log.user_email) && (
          <Field icon={Globe} label="Email">{log.user?.email || log.user_email}</Field>
        )}
        {log.user?.role && <Field icon={Shield} label="Role">{log.user.role}</Field>}
        {!log.user && log.user_id && (
          <Field icon={Hash} label="User ID (account removed)" mono>{log.user_id}</Field>
        )}
      </Section>

      <Section title="Event">
        <Field icon={Shield} label="Event type">{humanize(log.event_type)}</Field>
        <Field icon={Activity} label="Action">
          {actionLabel(log.action, log.details)} <span className="font-mono text-xs text-muted-foreground">({log.action})</span>
        </Field>
        {log.resource_type && <Field icon={Database} label="Resource type">{humanize(log.resource_type)}</Field>}
        {log.resource_id && <Field icon={Hash} label="Resource ID" mono wrap>{log.resource_id}</Field>}
        {(log.incident || log.incident_id) && (
          <Field icon={AlertTriangle} label="Incident">{log.incident?.title ?? log.incident_id}</Field>
        )}
        <Field icon={Clock} label="Timestamp"><Timestamp value={log.created_at} /></Field>
      </Section>

      {(log.request_method || log.request_path || log.status_code) && (
        <Section title="Request">
          {log.request_method && <Field icon={ArrowRight} label="Method" mono>{log.request_method}</Field>}
          {log.request_path && <Field icon={Link2} label="Path" mono wrap>{log.request_path}</Field>}
          {log.status_code != null && (
            <Field icon={Hash} label="Status code" mono className={statusTone(log.status_code)}>{log.status_code}</Field>
          )}
          {log.content_type && <Field icon={FileText} label="Content type" mono>{log.content_type}</Field>}
          {log.duration_ms != null && (
            <Field icon={Gauge} label="Duration" mono>{`${Number(log.duration_ms).toFixed(1)} ms`}</Field>
          )}
          {log.referrer && <Field icon={Link2} label="Referrer" mono wrap>{log.referrer}</Field>}
          {log.origin && <Field icon={Globe} label="Origin" mono>{log.origin}</Field>}
        </Section>
      )}

      {(log.ip_address || geo || log.cf_ray) && (
        <Section title="Network & location">
          {log.ip_address && <Field icon={Monitor} label="IP address" mono>{log.ip_address}</Field>}
          {geo && <Field icon={MapPin} label="Location">{geo}</Field>}
          {log.cf_ray && <Field icon={Server} label="CF-Ray" mono>{log.cf_ray}</Field>}
        </Section>
      )}

      {(log.browser || log.os || log.device_type || log.user_agent) && (
        <Section title="Device & browser">
          {log.browser && <Field icon={Globe} label="Browser">{log.browser}</Field>}
          {log.os && <Field icon={Laptop} label="Operating system">{log.os}</Field>}
          {log.device_type && <Field icon={Monitor} label="Device type">{log.device_type}</Field>}
          {log.user_agent && (
            <div className="col-span-full">
              <Field icon={FileText} label="User agent" mono wrap>{log.user_agent}</Field>
            </div>
          )}
        </Section>
      )}

      {log.chain_seq != null && (
        <Section title="Audit chain">
          <Field icon={LinkIcon} label="Sequence" mono>#{log.chain_seq}</Field>
          <Field icon={Hash} label="Row hash" mono>
            <span title={log.row_hash ?? undefined}>{shortHash(log.row_hash, 16)}</span>
          </Field>
          <Field icon={Hash} label="Previous hash" mono>
            <span title={log.prev_hash ?? undefined}>{shortHash(log.prev_hash, 16)}</span>
          </Field>
        </Section>
      )}

      {log.request_query_params && Object.keys(log.request_query_params).length > 0 && (
        <section className="border-b border-white/5 pb-3 last:border-b-0 last:pb-0">
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Query parameters</h4>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
            {Object.entries(log.request_query_params).map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-2">
                <dt className="shrink-0 font-mono text-muted-foreground">{k}:</dt>
                <dd className="truncate font-mono">{stringify(v)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {log.request_body_summary && Object.keys(log.request_body_summary).length > 0 && (
        <section className="border-b border-white/5 pb-3 last:border-b-0 last:pb-0">
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Request body (summary)</h4>
          <pre className="max-h-40 overflow-auto rounded bg-slate-950/60 p-2 font-mono text-xs text-foreground/80">
            {JSON.stringify(log.request_body_summary, null, 2)}
          </pre>
        </section>
      )}

      {otherDetails.length > 0 && (
        <section>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Additional details</h4>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
            {otherDetails.map(([k, v]) => (
              <div key={k} className="flex min-w-0 items-baseline gap-2">
                <dt className="shrink-0 text-muted-foreground">{humanize(k)}:</dt>
                <dd className="break-all font-mono">{stringify(v)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  )
}
