/**
 * IR-aligned playbook runner for an incident: phase-gated checklists +
 * investigation-augmenting actions (enrich/summarize/suggest/create-task).
 */
"use client"

import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2, Play, ChevronRight, ListChecks, BookOpen } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { api } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { PHASE_INFO } from '@/lib/design-tokens'
import { useToast } from '@/components/ui/use-toast'
import type { IncidentPlaybook, Playbook } from '@/types'

type Template = Pick<Playbook, 'id' | 'name' | 'description' | 'incident_type'>

function phaseName(phase: number): string {
  return PHASE_INFO[phase as keyof typeof PHASE_INFO]?.name ?? ''
}

export function IncidentPlaybookTab({ incidentId }: { incidentId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuthStore()
  // Mirrors the backend: activate/advance/execute/task-toggle all require
  // incidents:update. Viewers get a read-only view.
  const canEdit = hasPermission('incidents:update')
  const [loading, setLoading] = useState(true)
  const [pb, setPb] = useState<IncidentPlaybook | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<{ incident_playbook: IncidentPlaybook | null }>(`/incidents/${incidentId}/playbook`)
      setPb(res.incident_playbook)
      if (!res.incident_playbook) {
        const t = await api.get<{ items: Template[] }>('/playbooks').catch(() => ({ items: [] }))
        setTemplates(t.items || [])
      }
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [incidentId])

  useEffect(() => { load() }, [load])

  const activate = async (id: string) => {
    setBusy(id)
    try { await api.post(`/incidents/${incidentId}/playbooks/${id}/activate`); toast({ title: 'Playbook activated' }); load() }
    catch { toast({ title: 'Error', description: 'Could not activate playbook', variant: 'destructive' }) }
    finally { setBusy(null) }
  }
  const advance = async () => {
    setBusy('advance')
    try { const r = await api.put<{ incident_playbook: IncidentPlaybook }>(`/incidents/${incidentId}/playbook/advance`); setPb(r.incident_playbook); toast({ title: 'Advanced to next phase' }) }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setBusy(null) }
  }
  const runAction = async (key: string) => {
    setBusy(key)
    try {
      const r = await api.post<{ result: { status?: string; message?: string }; incident_playbook: IncidentPlaybook }>(`/incidents/${incidentId}/playbook/execute`, { action_key: key })
      setPb(r.incident_playbook)
      toast({ title: r.result?.status === 'success' ? 'Action ran' : 'Action', description: r.result?.message })
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setBusy(null) }
  }
  const toggleTask = async (key: string, done: boolean) => {
    try { const r = await api.put<{ incident_playbook: IncidentPlaybook }>(`/incidents/${incidentId}/playbook/task`, { task_key: key, done }); setPb(r.incident_playbook) }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }

  if (loading) return <div className="flex justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>

  if (!pb) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <BookOpen className="h-4 w-4" />
          {canEdit
            ? 'No playbook active. Activate a runbook to track phase-gated tasks and run IR-augmenting actions.'
            : 'No playbook is active for this incident.'}
        </div>
        {!canEdit ? null : templates.length === 0 ? (
          <Card className="border-dashed"><CardContent className="p-8 text-center text-muted-foreground text-sm">No playbook templates yet. Create them via the API (or seed defaults).</CardContent></Card>
        ) : (
          <div className="grid gap-3">
            {templates.map(t => (
              <Card key={t.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <h4 className="font-medium">{t.name}</h4>
                    <p className="text-xs text-muted-foreground">{t.description || t.incident_type || ''}</p>
                  </div>
                  <Button size="sm" onClick={() => activate(t.id)} disabled={busy === t.id}>
                    {busy === t.id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1.5 h-3.5 w-3.5" />}Activate
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    )
  }

  const phases = pb.definition?.phases || []
  const taskState = pb.state?.tasks || {}
  const currentPhaseDef = phases.find(p => p.phase === pb.current_phase)
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">{pb.name}</h3>
          <p className="text-sm text-muted-foreground">Current phase: <Badge variant="outline">{pb.current_phase}. {currentPhaseDef?.name || phaseName(pb.current_phase)}</Badge></p>
        </div>
        {canEdit && (
          <Button variant="outline" size="sm" onClick={advance} disabled={busy === 'advance' || pb.current_phase >= 6}>
            {busy === 'advance' ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <ChevronRight className="mr-1.5 h-3.5 w-3.5" />}Advance Phase
          </Button>
        )}
      </div>

      {phases.map(ph => (
        <Card key={ph.phase} className={ph.phase === pb.current_phase ? PHASE_INFO[ph.phase as keyof typeof PHASE_INFO]?.border ?? '' : ''}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Badge variant={ph.phase === pb.current_phase ? 'default' : 'outline'} className="text-xs">{ph.phase}</Badge>
              {ph.name || phaseName(ph.phase)}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(ph.tasks || []).length > 0 && (
              <div className="space-y-1.5">
                {(ph.tasks || []).map((t, i) => {
                  const key = `${ph.phase}:${i}`
                  return (
                    <label key={key} className={`flex items-center gap-2 text-sm ${canEdit ? 'cursor-pointer' : ''}`}>
                      <Checkbox
                        checked={!!taskState[key]}
                        disabled={!canEdit}
                        onCheckedChange={checked => toggleTask(key, checked === true)}
                      />
                      <span className={taskState[key] ? 'line-through text-muted-foreground' : ''}>{t.title}</span>
                      {t.owner_role && <span className="text-xs text-muted-foreground">· {t.owner_role}</span>}
                    </label>
                  )
                })}
              </div>
            )}
            {canEdit && (ph.actions || []).length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {(ph.actions || []).map(a => (
                  <Button key={a.key} variant="outline" size="sm" onClick={() => runAction(a.key)} disabled={busy === a.key}>
                    {busy === a.key ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1.5 h-3.5 w-3.5" />}
                    {a.name}{a.auto_run ? <Badge variant="outline" className="ml-1.5 text-[10px]">auto</Badge> : null}
                  </Button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {(pb.state?.action_runs || []).length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><ListChecks className="h-4 w-4" /> Action History</CardTitle></CardHeader>
          <CardContent className="space-y-1.5">
            {(pb.state.action_runs || []).slice().reverse().slice(0, 10).map((r, i) => (
              <div key={i} className="text-xs flex items-center justify-between gap-3">
                <span className="shrink-0">{r.name || r.type}</span>
                <span className={r.result?.status === 'success' ? 'text-green-400' : r.result?.status === 'skipped' ? 'text-yellow-400' : 'text-red-400'}>
                  {r.result?.status}: {r.result?.message}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
