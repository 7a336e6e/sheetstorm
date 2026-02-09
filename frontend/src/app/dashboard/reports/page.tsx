/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FileText, BarChart3, PieChart, TrendingUp, Download, Loader2, AlertCircle, Trash2 } from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'
import api from '@/lib/api'

interface IncidentOption {
    id: string
    incident_number: number
    title: string
    severity: string
    status: string
}

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

export default function ReportsPage() {
    const { toast } = useToast()
    const confirm = useConfirm()
    const [generating, setGenerating] = useState<string | null>(null)
    const [incidents, setIncidents] = useState<IncidentOption[]>([])
    const [selectedIncidentId, setSelectedIncidentId] = useState<string>('')
    const [reports, setReports] = useState<ReportRecord[]>([])
    const [loadingIncidents, setLoadingIncidents] = useState(true)
    const [loadingReports, setLoadingReports] = useState(false)
    const [deletingReportId, setDeletingReportId] = useState<string | null>(null)
    const [downloadingReportId, setDownloadingReportId] = useState<string | null>(null)

    // Fetch incidents for the selector
    useEffect(() => {
        const fetchIncidents = async () => {
            try {
                const response = await api.get<{ items: IncidentOption[] }>('/incidents')
                setIncidents(response.items)
                if (response.items.length > 0) {
                    setSelectedIncidentId(response.items[0].id)
                }
            } catch {
                toast({ title: 'Error', description: 'Failed to load incidents.', variant: 'destructive' })
            } finally {
                setLoadingIncidents(false)
            }
        }
        fetchIncidents()
    }, [toast])

    // Fetch reports when selected incident changes
    const fetchReports = useCallback(async (incidentId: string) => {
        if (!incidentId) return
        setLoadingReports(true)
        try {
            const response = await api.get<{ items: ReportRecord[] }>(`/incidents/${incidentId}/reports`)
            setReports(response.items)
        } catch {
            setReports([])
        } finally {
            setLoadingReports(false)
        }
    }, [])

    useEffect(() => {
        if (selectedIncidentId) {
            fetchReports(selectedIncidentId)
        } else {
            setReports([])
        }
    }, [selectedIncidentId, fetchReports])

    const handleDownloadReport = async (report: ReportRecord) => {
        if (!selectedIncidentId) return
        setDownloadingReportId(report.id)
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'
            const token = api.getToken()
            const response = await fetch(
                `${API_URL}/incidents/${selectedIncidentId}/reports/${report.id}/download`,
                {
                    method: 'GET',
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                }
            )
            if (!response.ok) throw new Error('Download failed')
            const blob = await response.blob()
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${report.title.replace(/\s+/g, '_')}.pdf`
            document.body.appendChild(a)
            a.click()
            document.body.removeChild(a)
            URL.revokeObjectURL(url)
        } catch {
            toast({ title: 'Download Failed', description: 'Could not download the report.', variant: 'destructive' })
        } finally {
            setDownloadingReportId(null)
        }
    }

    const handleDeleteReport = async (report: ReportRecord) => {
        if (!selectedIncidentId) return
        const confirmed = await confirm({
            title: 'Delete Report',
            description: `Delete "${report.title}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        setDeletingReportId(report.id)
        try {
            await api.delete(`/incidents/${selectedIncidentId}/reports/${report.id}`)
            toast({ title: 'Report Deleted', description: `${report.title} has been removed.` })
            setReports(prev => prev.filter(r => r.id !== report.id))
        } catch {
            toast({ title: 'Delete Failed', description: 'Could not delete the report.', variant: 'destructive' })
        } finally {
            setDeletingReportId(null)
        }
    }

    const handleGenerate = async (typeId: string, title: string) => {
        if (!selectedIncidentId) {
            toast({ title: 'No incident selected', description: 'Please select an incident first.', variant: 'destructive' })
            return
        }

        setGenerating(typeId)
        toast({ title: 'Generating Report', description: `Starting AI-powered generation of ${title}...` })

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'
            const token = api.getToken()
            const response = await fetch(`${API_URL}/incidents/${selectedIncidentId}/reports/generate-pdf`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ report_type: typeId }),
            })

            if (!response.ok) {
                const errData = await response.json().catch(() => ({ message: 'Report generation failed' }))
                throw new Error(errData.message || 'Report generation failed')
            }

            const pdfBlob = await response.blob()

            // Trigger browser download
            const url = URL.createObjectURL(pdfBlob)
            const a = document.createElement('a')
            a.href = url
            const selectedIncident = incidents.find(i => i.id === selectedIncidentId)
            a.download = `incident_${selectedIncident?.incident_number ?? 'report'}_${typeId}.pdf`
            document.body.appendChild(a)
            a.click()
            document.body.removeChild(a)
            URL.revokeObjectURL(url)

            toast({ title: 'Report Generated', description: `${title} has been downloaded.` })

            // Refresh the reports list
            fetchReports(selectedIncidentId)
        } catch (err) {
            toast({
                title: 'Generation Failed',
                description: err instanceof Error ? err.message : 'An error occurred while generating the report.',
                variant: 'destructive',
            })
        } finally {
            setGenerating(null)
        }
    }

    const selectedIncident = incidents.find(i => i.id === selectedIncidentId)

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-2xl font-semibold">Reports</h1>
                    <p className="text-sm text-muted-foreground mt-1">Generate and view incident response reports</p>
                </div>
                <div className="w-72">
                    {loadingIncidents ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground h-10">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Loading incidents...
                        </div>
                    ) : incidents.length === 0 ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground h-10">
                            <AlertCircle className="h-4 w-4" />
                            No incidents available
                        </div>
                    ) : (
                        <Select value={selectedIncidentId} onValueChange={setSelectedIncidentId}>
                            <SelectTrigger>
                                <SelectValue placeholder="Select an incident" />
                            </SelectTrigger>
                            <SelectContent>
                                {incidents.map((incident) => (
                                    <SelectItem key={incident.id} value={incident.id}>
                                        #{incident.incident_number} — {incident.title}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    )}
                </div>
            </div>

            {/* Report Types */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {reportTypes.map((report) => (
                    <Card key={report.id} className="hover:bg-muted/50 transition-colors cursor-pointer">
                        <CardHeader className="pb-3">
                            <CardTitle className="flex items-center gap-2 text-base">
                                <report.icon className="h-5 w-5 text-muted-foreground" />
                                {report.title}
                            </CardTitle>
                            <CardDescription>{report.description}</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <p className="text-sm text-muted-foreground mb-4">{report.detail}</p>
                            <Button
                                size="sm"
                                variant="outline"
                                className="w-full"
                                onClick={() => handleGenerate(report.id, report.title)}
                                disabled={generating === report.id || !selectedIncidentId}
                            >
                                {generating === report.id ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Download className="mr-2 h-4 w-4" />
                                )}
                                {generating === report.id ? 'Generating...' : 'Generate'}
                            </Button>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Recent Reports */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent Reports</CardTitle>
                    <CardDescription>
                        {selectedIncident
                            ? `Reports for #${selectedIncident.incident_number} — ${selectedIncident.title}`
                            : 'Previously generated reports'}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {loadingReports ? (
                        <div className="flex items-center justify-center py-8 gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Loading reports...
                        </div>
                    ) : reports.length === 0 ? (
                        <div className="text-center py-8">
                            <div className="mx-auto w-12 h-12 rounded-md bg-muted flex items-center justify-center mb-4">
                                <FileText className="h-6 w-6 text-muted-foreground" />
                            </div>
                            <p className="font-medium mb-1">No reports generated yet</p>
                            <p className="text-sm text-muted-foreground">
                                {selectedIncidentId
                                    ? 'Select a report type above to generate your first report'
                                    : 'Select an incident to get started'}
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {reports.map((report) => (
                                <div
                                    key={report.id}
                                    className="flex items-center justify-between rounded-md border p-3"
                                >
                                    <div className="flex items-center gap-3 min-w-0">
                                        <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium truncate">{report.title}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {new Date(report.created_at).toLocaleDateString(undefined, {
                                                    year: 'numeric', month: 'short', day: 'numeric',
                                                    hour: '2-digit', minute: '2-digit',
                                                })}
                                                {report.generator ? ` · ${report.generator.name}` : ''}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0">
                                        <span className="text-xs uppercase tracking-wide text-muted-foreground mr-2">
                                            {report.format}
                                        </span>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-8 w-8"
                                            title="Download report"
                                            disabled={downloadingReportId === report.id}
                                            onClick={() => handleDownloadReport(report)}
                                        >
                                            {downloadingReportId === report.id
                                                ? <Loader2 className="h-4 w-4 animate-spin" />
                                                : <Download className="h-4 w-4" />}
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-8 w-8 text-destructive hover:text-destructive"
                                            title="Delete report"
                                            disabled={deletingReportId === report.id}
                                            onClick={() => handleDeleteReport(report)}
                                        >
                                            {deletingReportId === report.id
                                                ? <Loader2 className="h-4 w-4 animate-spin" />
                                                : <Trash2 className="h-4 w-4" />}
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
