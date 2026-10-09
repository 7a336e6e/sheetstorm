/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { Suspense, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { DataTable, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { IncidentPicker } from '@/components/ui/entity-picker'
import { Timestamp } from '@/components/ui/timestamp'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { useAiAvailability } from '@/hooks/use-ai-availability'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import api, { downloadTo, isAbortError, withQuery } from '@/lib/api'
import { notifyError, notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import type { Incident, PaginatedResponse } from '@/types'
import { FileText, BarChart3, PieChart, TrendingUp, Download, Loader2, Trash2, BookOpenCheck, Info } from 'lucide-react'

interface ReportRecord {
    id: string
    title: string
    report_type: string
    format: string
    sections: string[]
    created_at: string
    generator?: { id: string; name: string } | null
    incident?: { id: string; title: string; incident_number: number } | null
}

const reportTypes = [
    {
        id: 'full',
        icon: BookOpenCheck,
        title: 'Full Incident Report',
        description: 'Comprehensive report with all sections',
        detail: 'Generate a complete report including summary, timeline, IOCs, and recommendations.',
        sections: ['summary', 'timeline', 'iocs', 'recommendations'],
    },
    {
        id: 'executive',
        icon: FileText,
        title: 'Executive Summary',
        description: 'High-level overview of incident response activities',
        detail: 'Generate a summary report suitable for executives and stakeholders.',
        sections: ['summary', 'recommendations'],
    },
    {
        id: 'metrics',
        icon: BarChart3,
        title: 'Incident Metrics',
        description: 'Statistical analysis of incidents over time',
        detail: 'View trends, response times, and incident categorization data.',
        sections: ['summary', 'timeline', 'iocs'],
    },
    {
        id: 'ioc',
        icon: PieChart,
        title: 'IOC Analysis',
        description: 'Indicators of compromise breakdown',
        detail: 'Analyze IOCs across incidents including hosts, accounts, and malware.',
        sections: ['iocs'],
    },
    {
        id: 'trends',
        icon: TrendingUp,
        title: 'Trend Report',
        description: 'Track incident patterns and emerging threats',
        detail: 'Monitor recurring attack vectors and compromised systems.',
        sections: ['summary', 'timeline', 'iocs', 'recommendations'],
    },
]

const reportsEndpoint = (incidentId: string) => `/incidents/${incidentId}/reports`

function ReportsContent() {
    const confirm = useConfirm()
    const canGenerate = usePermission('reports:generate')
    const [generating, setGenerating] = useState<string | null>(null)
    const [selectedIncident, setSelectedIncident] = useState<Pick<Incident, 'id' | 'incident_number' | 'title'> | null>(null)
    const selectedIncidentId = selectedIncident?.id ?? null
    // PDF reports always generate; AI analysis is added only when the org's
    // AI TLP policy allows a provider for this incident (server-enforced, with
    // a deterministic fallback). So the buttons stay enabled and the reason
    // is shown instead of disabling them (AiGate is for AI-only actions).
    const ai = useAiAvailability(selectedIncidentId, { enabled: canGenerate })

    // Preselect the most recent incident (one row, not a truncated list).
    const [preselectDone, setPreselectDone] = useState(false)
    useEffect(() => {
        if (preselectDone) return
        const ctrl = new AbortController()
        api.get<PaginatedResponse<Incident>>(withQuery('/incidents', { per_page: 1 }), { signal: ctrl.signal })
            .then((res) => {
                const first = res.items?.[0]
                if (first) setSelectedIncident((cur) => cur ?? first)
                setPreselectDone(true)
            })
            .catch((err) => {
                if (isAbortError(err)) return
                setPreselectDone(true)
                notifyError(err, 'load incidents')
            })
        return () => ctrl.abort()
    }, [preselectDone])

    const reports = usePaginatedQuery<ReportRecord>({
        endpoint: reportsEndpoint(selectedIncidentId ?? '_'),
        enabled: !!selectedIncidentId,
        defaults: { perPage: 25, sort: '-created_at' },
    })

    const handleDownloadReport = async (report: ReportRecord) => {
        if (!selectedIncidentId) return
        try {
            await downloadTo(`${reportsEndpoint(selectedIncidentId)}/${report.id}/download`, {
                fallbackName: `${report.title.replace(/\s+/g, '_')}.pdf`,
            })
        } catch (err) {
            notifyError(err, 'download the report')
        }
    }

    const handleDeleteReport = async (report: ReportRecord) => {
        if (!selectedIncidentId) return
        if (!(await confirmDelete(confirm, 'report', report.title))) return
        try {
            await api.delete(`${reportsEndpoint(selectedIncidentId)}/${report.id}`)
            notifySuccess('Report deleted', `${report.title} has been removed.`)
            invalidate(reportsEndpoint(selectedIncidentId))
        } catch (err) {
            notifyError(err, 'delete the report')
        }
    }

    const handleGenerate = async (typeId: string, title: string) => {
        if (!selectedIncident) return
        setGenerating(typeId)
        try {
            await downloadTo(`${reportsEndpoint(selectedIncident.id)}/generate-pdf`, {
                method: 'POST',
                data: { report_type: typeId },
                fallbackName: `incident_${selectedIncident.incident_number}_${typeId}.pdf`,
            })
            notifySuccess('Report generated', `${title} has been downloaded.`)
            invalidate(reportsEndpoint(selectedIncident.id))
        } catch (err) {
            notifyError(err, `generate the ${title.toLowerCase()}`)
        } finally {
            setGenerating(null)
        }
    }

    const columns = useMemo<DataTableColumn<ReportRecord>[]>(
        () => [
            {
                id: 'title',
                header: 'Report',
                cell: (r) => (
                    <div className="flex min-w-0 items-center gap-3">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate text-sm font-medium">{r.title}</span>
                    </div>
                ),
            },
            {
                id: 'type',
                header: 'Type',
                sortKey: 'report_type',
                className: 'w-[120px]',
                hideBelow: 'sm',
                cell: (r) => <span className="text-xs text-muted-foreground">{r.report_type}</span>,
            },
            {
                id: 'created',
                header: 'Generated',
                sortKey: 'created_at',
                className: 'w-[220px]',
                cell: (r) => (
                    <div className="text-xs text-muted-foreground">
                        <Timestamp value={r.created_at} seconds={false} />
                        {r.generator && <p className="mt-0.5">{r.generator.name}</p>}
                    </div>
                ),
            },
            {
                id: 'format',
                header: 'Format',
                className: 'w-[80px]',
                hideBelow: 'md',
                cell: (r) => <span className="text-xs uppercase tracking-wide text-muted-foreground">{r.format}</span>,
            },
        ],
        []
    )

    const rowActions = (r: ReportRecord): RowAction[] => [
        { label: 'Download', icon: Download, permission: 'reports:read', onSelect: () => void handleDownloadReport(r) },
        {
            label: 'Delete',
            icon: Trash2,
            destructive: true,
            permission: 'reports:generate',
            onSelect: () => void handleDeleteReport(r),
        },
    ]

    const generateButton = (typeId: string, title: string, variant: 'primary' | 'compact') => {
        const busy = generating === typeId
        const disabled = busy || !selectedIncidentId || generating !== null
        const button =
            variant === 'primary' ? (
                <Button size="sm" onClick={() => void handleGenerate(typeId, title)} disabled={disabled}>
                    {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
                    {busy ? 'Generating…' : 'Generate Report'}
                </Button>
            ) : (
                <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 shrink-0 px-3 text-xs"
                    onClick={() => void handleGenerate(typeId, title)}
                    disabled={disabled}
                    aria-label={`Generate ${title}`}
                >
                    {busy ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Download className="mr-1 h-3 w-3" />}
                    {busy ? '…' : 'Generate'}
                </Button>
            )
        return button
    }

    const full = reportTypes[0]

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-2xl font-semibold">Reports</h1>
                    <p className="text-sm text-muted-foreground mt-1">Generate and view incident response reports</p>
                </div>
                <div className="w-full sm:w-80">
                    <IncidentPicker
                        ariaLabel="Incident"
                        placeholder="Select an incident…"
                        value={selectedIncidentId}
                        valueLabel={selectedIncident ? `#${selectedIncident.incident_number} ${selectedIncident.title}` : undefined}
                        clearable={false}
                        onChange={(_id, incident) => setSelectedIncident(incident)}
                    />
                </div>
            </div>

            {canGenerate && (
                <>
                    {/* Full Incident Report — Primary CTA */}
                    <Card className="border-primary/20 bg-primary/[0.03]">
                        <CardContent className="p-5 flex items-center justify-between gap-6">
                            <div className="flex items-center gap-4 min-w-0">
                                <div className="shrink-0 flex items-center justify-center h-10 w-10 rounded-lg bg-primary/10 text-primary">
                                    <full.icon className="h-5 w-5" />
                                </div>
                                <div className="min-w-0">
                                    <p className="font-medium text-sm">{full.title}</p>
                                    <p className="text-xs text-muted-foreground truncate">{full.description}</p>
                                </div>
                            </div>
                            {generateButton(full.id, full.title, 'primary')}
                        </CardContent>
                    </Card>

                    {selectedIncidentId && !ai.loading && !ai.allowed && ai.reason && (
                        <div
                            role="note"
                            className="flex items-start gap-2 rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-muted-foreground"
                        >
                            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>
                                AI analysis is not available for this incident: {ai.reason} Reports are generated without
                                the AI-written analysis.
                            </span>
                        </div>
                    )}

                    {/* Sub-reports */}
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        {reportTypes.slice(1).map((report) => (
                            <Card key={report.id} className="hover:bg-muted/30 transition-colors">
                                <CardContent className="p-4 flex items-center justify-between gap-3">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <report.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium truncate">{report.title}</p>
                                            <p className="text-xs text-muted-foreground truncate">{report.description}</p>
                                        </div>
                                    </div>
                                    {generateButton(report.id, report.title, 'compact')}
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </>
            )}

            {/* Recent Reports */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent Reports</CardTitle>
                    <CardDescription>
                        {selectedIncident
                            ? `Reports for #${selectedIncident.incident_number} — ${selectedIncident.title}`
                            : 'Select an incident to see its reports'}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {selectedIncidentId ? (
                        <DataTable
                            query={reports}
                            columns={columns}
                            getRowId={(r) => r.id}
                            ariaLabel="Reports"
                            rowActions={rowActions}
                            pageSizes={[10, 25, 50]}
                            empty={{
                                title: 'No reports generated yet',
                                description: canGenerate
                                    ? 'Select a report type above to generate the first report.'
                                    : 'Reports generated for this incident appear here.',
                            }}
                        />
                    ) : (
                        <p className="py-8 text-center text-sm text-muted-foreground">
                            {preselectDone ? 'Select an incident to get started.' : 'Loading…'}
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}

export default function ReportsPage() {
    return (
        <Suspense fallback={null}>
            <ReportsContent />
        </Suspense>
    )
}
