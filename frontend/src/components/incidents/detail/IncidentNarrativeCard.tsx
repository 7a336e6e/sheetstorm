"use client"

/**
 * Executive summary and lessons learned (W2-DFIR-B). Rendered as plain text
 * (`whitespace-pre-wrap`, React escaping; never markdown or HTML). Editing is
 * gated on `incidents:update`, capped at 20000 characters (the server cap)
 * and saved with If-Match.
 */
import { useState } from 'react'
import { Edit2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/input'
import { usePermission } from '@/components/auth/permission-gate'
import { notifyError } from '@/lib/errors'
import { incidentOverview } from '@/lib/endpoints/incident-overview'
import type { Incident, Versioned } from '@/types'

export const NARRATIVE_MAX = 20000

type NarrativeField = 'executive_summary' | 'lessons_learned'

const SECTIONS: { field: NarrativeField; label: string; empty: string }[] = [
  { field: 'executive_summary', label: 'Executive summary', empty: 'No executive summary yet.' },
  { field: 'lessons_learned', label: 'Lessons learned', empty: 'No lessons learned recorded yet.' },
]

interface IncidentNarrativeCardProps {
  incident: Incident & Versioned
  onSaved: () => void
}

export function IncidentNarrativeCard({ incident, onSaved }: IncidentNarrativeCardProps) {
  const canEdit = usePermission('incidents:update')
  const [editing, setEditing] = useState<NarrativeField | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const start = (field: NarrativeField) => {
    setDraft(incident[field] ?? '')
    setEditing(field)
  }

  const save = async () => {
    if (!editing || draft.length > NARRATIVE_MAX) return
    setSaving(true)
    try {
      await incidentOverview.update(incident.id, { [editing]: draft }, incident.version)
      setEditing(null)
      onSaved()
    } catch (err) {
      notifyError(err, 'save the text')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">Narrative</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {SECTIONS.map(({ field, label, empty }) => {
          const value = incident[field]
          const isEditing = editing === field
          const tooLong = draft.length > NARRATIVE_MAX
          return (
            <section key={field} aria-label={label} className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs uppercase tracking-wider text-muted-foreground">{label}</h3>
                {canEdit && !isEditing && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs"
                    onClick={() => start(field)}
                    disabled={editing !== null}
                    aria-label={`Edit ${label.toLowerCase()}`}
                  >
                    <Edit2 className="mr-1 h-3 w-3" /> Edit
                  </Button>
                )}
              </div>
              {isEditing ? (
                <div className="space-y-2">
                  <Textarea
                    aria-label={label}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    disabled={saving}
                    error={tooLong}
                    className="min-h-[160px]"
                  />
                  <div className="flex items-center justify-between">
                    <span className={`text-[11px] ${tooLong ? 'text-red-400' : 'text-muted-foreground'}`}>
                      {draft.length.toLocaleString()} / {NARRATIVE_MAX.toLocaleString()}
                    </span>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => setEditing(null)} disabled={saving}>
                        Cancel
                      </Button>
                      <Button size="sm" onClick={() => void save()} disabled={saving || tooLong}>
                        {saving && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                        Save
                      </Button>
                    </div>
                  </div>
                </div>
              ) : value ? (
                <p className="whitespace-pre-wrap break-words text-sm text-foreground">{value}</p>
              ) : (
                <p className="text-sm text-muted-foreground">{empty}</p>
              )}
            </section>
          )
        })}
      </CardContent>
    </Card>
  )
}
