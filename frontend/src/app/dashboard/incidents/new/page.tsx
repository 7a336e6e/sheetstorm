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
import api from '@/lib/api'

interface Team {
  id: string
  name: string
  member_count: number
}

export default function NewIncidentPage() {
  const router = useRouter()
  const { createIncident } = useIncidentStore()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formData, setFormData] = useState<CreateIncidentInput>({
    title: '',
    description: '',
    severity: 'medium',
    classification: '',
  })

  useEffect(() => {
    api.get<{ items: Team[] }>('/teams').then(res => {
      setTeams(res.items || [])
    }).catch(() => {})
  }, [])

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

    try {
      const incident = await createIncident(result.data)
      toast({
        title: 'Incident created',
        description: `Incident #${incident.incident_number} has been created.`,
      })
      router.push(`/dashboard/incidents/${incident.id}`)
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to create incident',
        variant: 'destructive',
      })
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
            <div className="space-y-2">
              <Label htmlFor="title">Title *</Label>
              <Input
                id="title"
                placeholder="Brief description of the incident"
                value={formData.title}
                onChange={(e) => {
                  setFormData({ ...formData, title: e.target.value })
                  if (fieldErrors.title) setFieldErrors((prev) => { const { title, ...rest } = prev; return rest })
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
                          : 'border-white/10 bg-white/5 text-muted-foreground hover:border-white/20'
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
