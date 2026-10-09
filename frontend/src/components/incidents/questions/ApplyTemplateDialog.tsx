"use client"

/**
 * Apply a case template to an existing incident (W4-QST-UI): pick a template
 * and the parts to apply, preview the merge (dry run), then apply. The server
 * never recreates archived questions and runs no playbook actions unless asked.
 */
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { caseTemplatesApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import type { ApplyPart, CaseTemplate, CaseTemplateApplyResult } from '@/types'

interface Props {
  incidentId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onApplied: () => void
}

const PARTS: { id: ApplyPart; label: string }[] = [
  { id: 'questions', label: 'Questions' },
  { id: 'leads', label: 'Leads (tasks)' },
  { id: 'playbook', label: 'Playbook' },
  { id: 'custom_fields', label: 'Custom fields' },
]

export function describeApplyResult(r: CaseTemplateApplyResult): string {
  const bits = [
    `${r.created.questions} question${r.created.questions === 1 ? '' : 's'}`,
    `${r.created.leads} lead${r.created.leads === 1 ? '' : 's'}`,
  ]
  if (r.custom_fields_added) bits.push(`${r.custom_fields_added} custom field${r.custom_fields_added === 1 ? '' : 's'}`)
  if (r.playbook) bits.push(`playbook ${r.playbook.status.replace(/_/g, ' ')}`)
  if (r.skipped.length) bits.push(`${r.skipped.length} skipped`)
  return bits.join(', ')
}

export function ApplyTemplateDialog({ incidentId, open, onOpenChange, onApplied }: Props) {
  const [templates, setTemplates] = useState<CaseTemplate[]>([])
  const [ref, setRef] = useState('')
  const [parts, setParts] = useState<Set<ApplyPart>>(new Set(PARTS.map((p) => p.id)))
  const [applyDefaults, setApplyDefaults] = useState(false)
  const [preview, setPreview] = useState<CaseTemplateApplyResult | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setRef('')
    setPreview(null)
    setApplyDefaults(false)
    setParts(new Set(PARTS.map((p) => p.id)))
    const ctrl = new AbortController()
    caseTemplatesApi
      .list({ signal: ctrl.signal })
      .then((r) => setTemplates(r.items.filter((t) => t.is_active)))
      .catch((err) => {
        if ((err as Error)?.name !== 'AbortError') notifyError(err, 'load the case templates')
      })
    return () => ctrl.abort()
  }, [open])

  const togglePart = (id: ApplyPart) => {
    setPreview(null)
    setParts((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const run = async (dryRun: boolean) => {
    if (!ref || !parts.size) return
    setBusy(true)
    try {
      const result = await caseTemplatesApi.apply(incidentId, ref, {
        include: Array.from(parts),
        apply_defaults: applyDefaults,
        dry_run: dryRun,
      })
      if (dryRun) {
        setPreview(result)
      } else {
        notifySuccess('Template applied', describeApplyResult(result))
        onApplied()
        onOpenChange(false)
      }
    } catch (err) {
      notifyError(err, dryRun ? 'preview the template' : 'apply the template')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Apply case template</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>Template</Label>
            <Select
              value={ref}
              onValueChange={(v) => {
                setRef(v)
                setPreview(null)
              }}
            >
              <SelectTrigger aria-label="Template"><SelectValue placeholder="Choose a template" /></SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}{t.is_builtin ? ' (built-in)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Apply</legend>
            {PARTS.map((p) => (
              <div key={p.id} className="flex items-center gap-2">
                <Checkbox id={`part-${p.id}`} checked={parts.has(p.id)} onCheckedChange={() => togglePart(p.id)} />
                <label htmlFor={`part-${p.id}`} className="text-sm">{p.label}</label>
              </div>
            ))}
            <div className="flex items-center gap-2 pt-1">
              <Checkbox
                id="apply-defaults"
                checked={applyDefaults}
                onCheckedChange={(v) => {
                  setApplyDefaults(v === true)
                  setPreview(null)
                }}
              />
              <label htmlFor="apply-defaults" className="text-sm">Also set the template&apos;s severity, TLP and classification</label>
            </div>
          </fieldset>
          {preview && (
            <div role="status" className="rounded-md border border-border bg-muted/40 p-3 text-sm">
              <p className="font-medium">Preview: {describeApplyResult(preview)}</p>
              {preview.defaults_applied.length > 0 && (
                <p className="mt-1 text-muted-foreground">
                  Changes {preview.defaults_applied.map((d) => d.field).join(', ')}
                </p>
              )}
            </div>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="outline" onClick={() => run(true)} disabled={!ref || !parts.size || busy}>Preview</Button>
          <Button onClick={() => run(false)} disabled={!ref || !parts.size || busy}>Apply</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
