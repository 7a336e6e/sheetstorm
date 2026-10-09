"use client"

/**
 * Create or edit an organization case template (W4-QST-UI). The definition is
 * edited as JSON and checked client-side (`checkDefinition`) before the server
 * validates it again. Built-ins are never edited here; clone them first.
 */
import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { caseTemplatesApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import { TEMPLATE_KEY_RE, checkDefinition, formatDefinition } from '@/lib/template-definition'
import type { CaseTemplate } from '@/types'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** null = new template; otherwise an organization template with its definition. */
  template: CaseTemplate | null
  onSaved: () => void
}

export function TemplateEditorDialog({ open, onOpenChange, template, onSaved }: Props) {
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [incidentType, setIncidentType] = useState('')
  const [source, setSource] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setKey(template?.key ?? '')
    setName(template?.name ?? '')
    setDescription(template?.description ?? '')
    setIncidentType(template?.incident_type ?? '')
    setSource(formatDefinition(template?.definition))
  }, [open, template])

  const check = useMemo(() => checkDefinition(source), [source])
  const keyOk = !!template || TEMPLATE_KEY_RE.test(key)
  const canSave = keyOk && name.trim().length > 0 && !!check.definition && !saving

  const save = async () => {
    if (!canSave || !check.definition) return
    setSaving(true)
    try {
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        incident_type: incidentType.trim() || null,
        definition: check.definition,
      }
      if (template) await caseTemplatesApi.update(template.id, body, template.version)
      else await caseTemplatesApi.create({ ...body, key })
      notifySuccess(template ? 'Template saved' : 'Template created')
      onSaved()
      onOpenChange(false)
    } catch (err) {
      notifyError(err, 'save the template')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{template ? `Edit ${template.name}` : 'New case template'}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="tpl-key">Key</Label>
              <Input
                id="tpl-key"
                value={key}
                disabled={!!template}
                onChange={(e) => setKey(e.target.value.toLowerCase())}
                placeholder="e.g. bec-investigation"
              />
              {!keyOk && key && <p className="text-xs text-amber-600 dark:text-amber-400">2-64 characters: a-z, 0-9 and -.</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="tpl-name">Name</Label>
              <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tpl-type">Incident type</Label>
              <Input id="tpl-type" value={incidentType} onChange={(e) => setIncidentType(e.target.value)} placeholder="optional" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tpl-desc">Description</Label>
              <Input id="tpl-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tpl-def">Definition (JSON)</Label>
            <Textarea
              id="tpl-def"
              value={source}
              rows={16}
              spellCheck={false}
              className="font-mono text-xs"
              onChange={(e) => setSource(e.target.value)}
            />
          </div>
          {check.errors.length > 0 && (
            <ul role="alert" className="max-h-32 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs text-amber-600 dark:text-amber-400">
              {check.errors.map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={!canSave}>{saving ? 'Saving…' : 'Save'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
