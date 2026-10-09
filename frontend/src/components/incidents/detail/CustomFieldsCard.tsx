"use client"

/**
 * Incident custom fields (W4-QST-UI). Definitions come from applied case
 * templates; values are edited inline and saved with the incident version
 * (If-Match), so a concurrent edit opens the conflict dialog. Hidden when the
 * incident has no definitions.
 */
import { useEffect, useState } from 'react'
import { ListPlus, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePermission } from '@/components/auth/permission-gate'
import { customFieldsApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import { subscribe } from '@/lib/query-cache'
import type { CustomFieldDef, CustomFieldValue, CustomFieldsResponse } from '@/types'

const NONE = '__none__'

export function displayCustomValue(def: CustomFieldDef, value: CustomFieldValue | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  if (def.type === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

/** Form string → stored value for a definition (empty → null). */
export function parseCustomValue(def: CustomFieldDef, raw: string | boolean): CustomFieldValue {
  if (def.type === 'boolean') return Boolean(raw)
  const text = String(raw).trim()
  if (!text) return null
  if (def.type === 'number') {
    const n = Number(text)
    return Number.isFinite(n) ? n : null
  }
  return text
}

export function CustomFieldsCard({ incidentId }: { incidentId: string }) {
  const canEdit = usePermission('incidents:update')
  const [data, setData] = useState<CustomFieldsResponse | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string | boolean>>({})
  const [saving, setSaving] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => subscribe(`/incidents/${incidentId}`, () => setTick((t) => t + 1)), [incidentId])

  useEffect(() => {
    const ctrl = new AbortController()
    customFieldsApi
      .get(incidentId, { signal: ctrl.signal })
      .then(setData)
      .catch(() => {
        /* optional card: stays hidden when the read fails */
      })
    return () => ctrl.abort()
  }, [incidentId, tick])

  if (!data || data.definitions.length === 0) return null

  const startEdit = () => {
    const next: Record<string, string | boolean> = {}
    for (const def of data.definitions) {
      const v = data.values[def.key]
      next[def.key] = def.type === 'boolean' ? Boolean(v) : v === null || v === undefined ? '' : String(v)
    }
    setDraft(next)
    setEditing(true)
  }

  const missingRequired = data.definitions.filter(
    (d) => d.required && d.type !== 'boolean' && !String(draft[d.key] ?? '').trim()
  )

  const save = async () => {
    setSaving(true)
    try {
      const values: Record<string, CustomFieldValue> = {}
      for (const def of data.definitions) values[def.key] = parseCustomValue(def, draft[def.key] ?? '')
      setData(await customFieldsApi.put(incidentId, values, data.version))
      setEditing(false)
      notifySuccess('Custom fields saved')
    } catch (err) {
      notifyError(err, 'save the custom fields')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <ListPlus className="h-4 w-4" /> Custom fields
        </CardTitle>
        {canEdit && !editing && (
          <Button variant="ghost" size="sm" onClick={startEdit} aria-label="Edit custom fields">
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {!editing ? (
          <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            {data.definitions.map((def) => (
              <div key={def.key}>
                <dt className="text-xs text-muted-foreground">{def.label}</dt>
                <dd>{displayCustomValue(def, data.values[def.key])}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <div className="space-y-3">
            {data.definitions.map((def) => {
              const id = `cf-${def.key}`
              const label = `${def.label}${def.required ? ' *' : ''}`
              if (def.type === 'boolean') {
                return (
                  <div key={def.key} className="flex items-center justify-between">
                    <Label htmlFor={id}>{label}</Label>
                    <Switch id={id} checked={Boolean(draft[def.key])} onCheckedChange={(v) => setDraft({ ...draft, [def.key]: v })} />
                  </div>
                )
              }
              if (def.type === 'select') {
                return (
                  <div key={def.key} className="space-y-1">
                    <Label>{label}</Label>
                    <Select
                      value={String(draft[def.key] || NONE)}
                      onValueChange={(v) => setDraft({ ...draft, [def.key]: v === NONE ? '' : v })}
                    >
                      <SelectTrigger aria-label={def.label}><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>Not set</SelectItem>
                        {(def.options ?? []).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )
              }
              return (
                <div key={def.key} className="space-y-1">
                  <Label htmlFor={id}>{label}</Label>
                  <Input
                    id={id}
                    type={def.type === 'number' ? 'number' : def.type === 'date' ? 'date' : 'text'}
                    value={String(draft[def.key] ?? '')}
                    onChange={(e) => setDraft({ ...draft, [def.key]: e.target.value })}
                  />
                </div>
              )
            })}
            {missingRequired.length > 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                Required: {missingRequired.map((d) => d.label).join(', ')}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
              <Button size="sm" onClick={save} disabled={saving || missingRequired.length > 0}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
