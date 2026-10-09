"use client"

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useIncidentStore, type Incident } from '@/lib/store'
import { useToast } from '@/components/ui/use-toast'
import { ArrowLeft, Loader2, Users } from 'lucide-react'
import { createIncidentSchema, validate, type CreateIncidentInput } from '@/lib/validations'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { UserPicker } from '@/components/ui/entity-picker'
import { usePermission } from '@/components/auth/permission-gate'
import { tlpColors } from '@/lib/design-tokens'
import { describeError } from '@/lib/errors'
import api from '@/lib/api'
import { caseTemplatesApi } from '@/lib/endpoints/questions'
import type { CaseTemplate } from '@/types'
import type { TLPLevel } from '@/types'

interface Team {
  id: string
  name: string
  member_count: number
}

/** TLP select options; labels and colors from the design tokens (TLP 2.0 names). */
const TLP_OPTIONS: { value: TLPLevel; token: keyof typeof tlpColors }[] = [
  { value: 'white', token: 'CLEAR' },
  { value: 'green', token: 'GREEN' },
  { value: 'amber', token: 'AMBER' },
  { value: 'amber_strict', token: 'AMBER+STRICT' },
  { value: 'red', token: 'RED' },
]

const TLP_HINT: Partial<Record<TLPLevel, string>> = {
  amber_strict: 'AMBER+STRICT: values are not sent for third-party enrichment unless your organization allows it.',
  red: 'RED: values are never sent for third-party enrichment, and AI features are limited by your organization policy.',
}

const NO_TEMPLATE = '__none__'

export default function NewIncidentPage() {
  const router = useRouter()
  const { createIncident } = useIncidentStore()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const canPickLead = usePermission('users:read')
  const [leadName, setLeadName] = useState<string | undefined>()
  const [templates, setTemplates] = useState<CaseTemplate[]>([])
  const [templateRef, setTemplateRef] = useState('')
  const [formData, setFormData] = useState<CreateIncidentInput>({
    title: '',
    description: '',
    severity: 'medium',
    classification: '',
    tlp: 'amber',
    detected_at: null,
    lead_responder_id: null,
  })

  const clearError = (field: string) =>
    setFieldErrors((prev) => {
      if (!(field in prev)) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })

  useEffect(() => {
    api.get<{ items: Team[] }>('/teams').then(res => {
      setTeams(res.items || [])
    }).catch(() => {})
    caseTemplatesApi.list({ includeDefinition: true }).then(res => {
      setTemplates(res.items.filter((t) => t.is_active))
    }).catch(() => {})
  }, [])

  /** Picking a template pre-fills its defaults; the server applies the rest. */
  const pickTemplate = (ref: string) => {
    setTemplateRef(ref)
    const defaults = templates.find((t) => t.id === ref)?.definition?.defaults
    if (!defaults) return
    setFormData((prev) => ({
      ...prev,
      ...(defaults.severity ? { severity: defaults.severity } : {}),
      ...(defaults.tlp ? { tlp: defaults.tlp } : {}),
      ...(defaults.classification ? { classification: defaults.classification } : {}),
    }))
  }

  const toggleTeam = (teamId: string) => {
    setSelectedTeamIds(prev =>
      prev.includes(teamId) ? prev.filter(id => id !== teamId) : [...prev, teamId]
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const dataWithTeams = { ...formData, team_ids: selectedTeamIds.length > 0 ? selectedTeamIds : undefined }
    const result = validate(createIncidentSchema, dataWithTeams)
    if (!result.success) {
      setFieldErrors(result.errors)
      const firstError = Object.values(result.errors)[0]
      toast({
        title: 'Validation Error',
        description: firstError,
        variant: 'destructive',
      })
      return
    }
    setFieldErrors({})
    setIsLoading(true)

    // Drop empty optionals: the server defaults detected_at to now.
    const { detected_at, lead_responder_id, classification, ...rest } = result.data
    const payload = {
      ...rest,
      ...(classification ? { classification } : {}),
      ...(detected_at ? { detected_at } : {}),
      ...(lead_responder_id ? { lead_responder_id } : {}),
      ...(templateRef ? { case_template: templateRef } : {}),
    }

    try {
      const incident = await createIncident(payload)
      toast({
        title: 'Incident created',
        description: `Incident #${incident.incident_number} has been created.`,
      })
      router.push(`/dashboard/incidents/${incident.id}`)
    } catch (error) {
      const { title, description } = describeError(error)
      toast({ title, description, variant: 'destructive' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto">
      <Link
        href="/dashboard/incidents"
        className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Incidents
      </Link>

      <Card>
        <CardHeader>
          <CardTitle>Create New Incident</CardTitle>
          <CardDescription>
            Document a new security incident for investigation and response.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {templates.length > 0 && (
              <div className="space-y-2">
                <Label htmlFor="case-template">Case template</Label>
                <Select value={templateRef || NO_TEMPLATE} onValueChange={(v) => pickTemplate(v === NO_TEMPLATE ? '' : v)} disabled={isLoading}>
                  <SelectTrigger id="case-template" variant="glass" aria-label="Case template">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_TEMPLATE}>No template</SelectItem>
                    {templates.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}{t.is_builtin ? ' (built-in)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {templateRef && (
                  <p className="text-xs text-muted-foreground">
                    {(() => {
                      const t = templates.find((x) => x.id === templateRef)
                      if (!t) return null
                      const parts = [`${t.summary.questions} questions`, `${t.summary.leads} leads`]
                      if (t.summary.playbook) parts.push('a playbook')
                      if (t.summary.custom_fields) parts.push(`${t.summary.custom_fields} custom fields`)
                      return `Adds ${parts.join(', ')}.`
                    })()}
                  </p>
                )}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="title">Title *</Label>
              <Input
                id="title"
                placeholder="Brief description of the incident"
                value={formData.title}
                onChange={(e) => {
                  setFormData({ ...formData, title: e.target.value })
                  clearError('title')
                }}
                required
                disabled={isLoading}
                variant="glass"
                className={fieldErrors.title ? 'border-red-500' : ''}
              />
              {fieldErrors.title && (
                <p className="text-sm text-red-400">{fieldErrors.title}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Detailed description of what was observed..."
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                disabled={isLoading}
                variant="glass"
                className="min-h-[120px]"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="severity">Severity *</Label>
                <Select
                  value={formData.severity}
                  onValueChange={(value) =>
                    setFormData({
                      ...formData,
                      severity: value as Incident['severity'],
                    })
                  }
                  disabled={isLoading}
                >
                  <SelectTrigger variant="glass">
                    <SelectValue placeholder="Select severity" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="classification">Classification</Label>
                <Select
                  value={formData.classification}
                  onValueChange={(value) => setFormData({ ...formData, classification: value })}
                  disabled={isLoading}
                >
                  <SelectTrigger variant="glass">
                    <SelectValue placeholder="Select classification..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="malware">Malware</SelectItem>
                    <SelectItem value="phishing">Phishing</SelectItem>
                    <SelectItem value="ransomware">Ransomware</SelectItem>
                    <SelectItem value="data_breach">Data Breach</SelectItem>
                    <SelectItem value="insider_threat">Insider Threat</SelectItem>
                    <SelectItem value="dos">Denial of Service</SelectItem>
                    <SelectItem value="unauthorized_access">Unauthorized Access</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="tlp">TLP *</Label>
                <Select
                  value={formData.tlp}
                  onValueChange={(value) => setFormData({ ...formData, tlp: value as TLPLevel })}
                  disabled={isLoading}
                >
                  <SelectTrigger id="tlp" variant="glass" aria-label="TLP">
                    <SelectValue placeholder="Select TLP..." />
                  </SelectTrigger>
                  <SelectContent>
                    {TLP_OPTIONS.map(({ value, token }) => (
                      <SelectItem key={value} value={value}>
                        <span className={tlpColors[token].text}>{tlpColors[token].label}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {TLP_HINT[formData.tlp] && (
                  <p className="text-xs text-muted-foreground">{TLP_HINT[formData.tlp]}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="detected_at">Detected at</Label>
                <DateTimeInput
                  id="detected_at"
                  value={formData.detected_at ?? null}
                  onChange={(iso) => {
                    setFormData({ ...formData, detected_at: iso })
                    clearError('detected_at')
                  }}
                  disabled={isLoading}
                  aria-invalid={!!fieldErrors.detected_at || undefined}
                />
                {fieldErrors.detected_at ? (
                  <p className="text-sm text-red-400">{fieldErrors.detected_at}</p>
                ) : (
                  <p className="text-xs text-muted-foreground">Leave empty to use the current time.</p>
                )}
              </div>
            </div>

            {canPickLead && (
              <div className="space-y-2">
                <Label>Lead responder</Label>
                <UserPicker
                  value={formData.lead_responder_id ?? null}
                  valueLabel={leadName}
                  onChange={(id, user) => {
                    setFormData({ ...formData, lead_responder_id: id })
                    setLeadName(user ? user.name || user.email : undefined)
                    clearError('lead_responder_id')
                  }}
                  ariaLabel="Lead responder"
                  placeholder="Search users…"
                  disabled={isLoading}
                />
                {fieldErrors.lead_responder_id && (
                  <p className="text-sm text-red-400">{fieldErrors.lead_responder_id}</p>
                )}
              </div>
            )}

            {teams.length > 0 && (
              <div className="space-y-2">
                <Label>
                  <Users className="h-4 w-4 inline mr-1.5" />
                  Team Access
                </Label>
                <p className="text-xs text-muted-foreground">
                  Select which teams can access this incident. Leave empty for organization-wide access.
                </p>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {teams.map(team => (
                    <button
                      key={team.id}
                      type="button"
                      onClick={() => toggleTeam(team.id)}
                      disabled={isLoading}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm text-left transition-colors ${
                        selectedTeamIds.includes(team.id)
                          ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                          : 'border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 text-muted-foreground hover:border-black/10 dark:hover:border-white/20'
                      }`}
                    >
                      <Users className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{team.name}</span>
                      <span className="text-xs opacity-60 ml-auto">({team.member_count})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-4 pt-4">
              <Link href="/dashboard/incidents">
                <Button type="button" variant="outline" disabled={isLoading}>
                  Cancel
                </Button>
              </Link>
              <Button type="submit" disabled={isLoading || !formData.title.trim()}>
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Incident'
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
