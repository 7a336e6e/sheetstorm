"use client"

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogBody,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { CheckCircle2, Download, Loader2 } from 'lucide-react'
import { PHASE_INFO, STATUS_OPTIONS } from '@/lib/design-tokens'
import api from '@/lib/api'
import { useIncidentStore } from '@/lib/store'
import { useToast } from '@/components/ui/use-toast'
import type { Incident } from '@/types'

// ─── Edit Incident Modal ─────────────────────────────────────────────────

interface EditIncidentModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incident: Incident
  incidentId: string
  onUpdated: () => void
}

export function EditIncidentModal({
  open,
  onOpenChange,
  incident,
  incidentId,
  onUpdated,
}: EditIncidentModalProps) {
  const { fetchIncident } = useIncidentStore()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [form, setForm] = useState({
    title: incident.title,
    description: incident.description || '',
    severity: incident.severity,
    classification: incident.classification || '',
    tlp: incident.tlp || 'amber',
  })

  // Sync form when incident changes
  const handleOpen = (nextOpen: boolean) => {
    if (nextOpen) {
      setForm({
        title: incident.title,
        description: incident.description || '',
        severity: incident.severity,
        classification: incident.classification || '',
        tlp: incident.tlp || 'amber',
      })
    }
    onOpenChange(nextOpen)
  }

  const handleSubmit = async () => {
    if (!form.title) return
    setIsSubmitting(true)
    try {
      await api.put(`/incidents/${incidentId}`, {
        title: form.title,
        description: form.description,
        severity: form.severity,
        classification: form.classification,
        tlp: form.tlp,
      })
      await fetchIncident(incidentId)
      onOpenChange(false)
      onUpdated()
    } catch (error) {
      console.error('Failed to update incident:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Incident</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-2">
            <Label>Title</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Severity</Label>
            <Select
              value={form.severity}
              onValueChange={(v) => setForm({ ...form, severity: v as 'critical' | 'high' | 'medium' | 'low' })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Classification</Label>
            <Input
              value={form.classification}
              onChange={(e) => setForm({ ...form, classification: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>TLP Level</Label>
            <Select
              value={form.tlp}
              onValueChange={(v) => setForm({ ...form, tlp: v as Incident['tlp'] })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="white">TLP:WHITE — Unrestricted</SelectItem>
                <SelectItem value="green">TLP:GREEN — Community</SelectItem>
                <SelectItem value="amber">TLP:AMBER — Limited distribution</SelectItem>
                <SelectItem value="amber_strict">TLP:AMBER+STRICT — Restricted</SelectItem>
                <SelectItem value="red">TLP:RED — Named recipients only</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={isSubmitting}>
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Update Status Modal ─────────────────────────────────────────────────

interface UpdateStatusModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentStatus: string
  incidentId: string
  onUpdated: () => void
}

export function UpdateStatusModal({
  open,
  onOpenChange,
  currentStatus,
  incidentId,
  onUpdated,
}: UpdateStatusModalProps) {
  const { fetchIncident } = useIncidentStore()
  const { toast } = useToast()
  const [isSubmitting, setIsSubmitting] = useState(false)

  const statusEntries = Object.entries(STATUS_OPTIONS) as [
    string,
    (typeof STATUS_OPTIONS)[keyof typeof STATUS_OPTIONS]
  ][]

  const handleUpdateStatus = async (newStatus: string) => {
    const statusOpt = STATUS_OPTIONS[newStatus as keyof typeof STATUS_OPTIONS]
    if (!statusOpt) return
    setIsSubmitting(true)
    try {
      await api.patch(`/incidents/${incidentId}/status`, {
        status: newStatus,
        phase: statusOpt.phase,
      })
      await fetchIncident(incidentId)
      onOpenChange(false)
      onUpdated()
      toast({
        title: 'Status updated',
        description: `Moved to Phase ${statusOpt.phase}: ${statusOpt.phaseName}`,
      })
    } catch (error) {
      console.error('Failed to update status:', error)
      toast({
        title: 'Error',
        description: 'Failed to update incident status.',
        variant: 'destructive',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Update Status & Phase</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-2">
          {statusEntries.map(([value, opt]) => {
            const phaseInfo = PHASE_INFO[opt.phase as keyof typeof PHASE_INFO]
            const isActive = currentStatus === value
            return (
              <button
                key={value}
                onClick={() => handleUpdateStatus(value)}
                disabled={isSubmitting}
                className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                  isActive
                    ? 'bg-primary/10 border-primary/30'
                    : 'border-border hover:bg-muted/50'
                } disabled:opacity-50`}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${phaseInfo.bg} ${phaseInfo.color} ${phaseInfo.border} border`}
                >
                  {opt.phase}
                </div>
                <div className="flex flex-col items-start">
                  <span className="font-medium text-foreground">{opt.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {opt.phaseName}
                  </span>
                </div>
                {isActive && (
                  <CheckCircle2 className="h-4 w-4 text-primary ml-auto" />
                )}
              </button>
            )
          })}
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}

// ─── Report Generation Modal ─────────────────────────────────────────────

const REPORT_TYPE_OPTIONS = [
  {
    id: 'executive',
    label: 'Executive Summary',
    description: 'High-level overview for stakeholders',
  },
  {
    id: 'metrics',
    label: 'Incident Metrics',
    description: 'Statistical analysis and response metrics',
  },
  {
    id: 'ioc',
    label: 'IOC Analysis',
    description: 'Indicators of compromise breakdown',
  },
  {
    id: 'trends',
    label: 'Trend Report',
    description: 'Patterns and emerging threat analysis',
  },
]

interface ReportModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  incidentNumber?: number
}

export function ReportModal({
  open,
  onOpenChange,
  incidentId,
  incidentNumber,
}: ReportModalProps) {
  const { toast } = useToast()
  const [selectedType, setSelectedType] = useState('executive')
  const [isGenerating, setIsGenerating] = useState(false)

  const handleGenerate = async () => {
    setIsGenerating(true)
    const typeName =
      REPORT_TYPE_OPTIONS.find((r) => r.id === selectedType)?.label || 'Report'
    toast({
      title: 'Generating Report',
      description: `AI is generating ${typeName}...`,
    })
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1'
      const token = api.getToken()
      const response = await fetch(
        `${API_URL}/incidents/${incidentId}/reports/generate-pdf`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ report_type: selectedType }),
        }
      )
      if (!response.ok) {
        const errData = await response
          .json()
          .catch(() => ({ message: 'Generation failed' }))
        throw new Error(errData.message || 'Report generation failed')
      }
      const pdfBlob = await response.blob()
      const url = URL.createObjectURL(pdfBlob)
      const a = document.createElement('a')
      a.href = url
      a.download = `incident_${incidentNumber ?? 'report'}_${selectedType}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast({
        title: 'Report Generated',
        description: `${typeName} has been downloaded.`,
      })
      onOpenChange(false)
    } catch (err) {
      toast({
        title: 'Generation Failed',
        description:
          err instanceof Error
            ? err.message
            : 'An error occurred while generating the report.',
        variant: 'destructive',
      })
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Report</DialogTitle>
          <DialogDescription>
            Select a report type to generate an AI-powered PDF report for this
            incident.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="space-y-3">
            {REPORT_TYPE_OPTIONS.map((type) => (
              <label
                key={type.id}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedType === type.id
                    ? 'border-primary/30 bg-primary/10'
                    : 'border-border hover:border-border hover:bg-muted/50'
                }`}
              >
                <input
                  type="radio"
                  name="reportType"
                  value={type.id}
                  checked={selectedType === type.id}
                  onChange={(e) => setSelectedType(e.target.value)}
                  className="mt-1 accent-primary"
                />
                <div>
                  <p className="font-medium text-sm">{type.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {type.description}
                  </p>
                </div>
              </label>
            ))}
          </div>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isGenerating}
          >
            Cancel
          </Button>
          <Button onClick={handleGenerate} disabled={isGenerating}>
            {isGenerating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" /> Generate PDF
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
