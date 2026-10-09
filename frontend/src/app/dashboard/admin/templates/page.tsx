"use client"

/**
 * Case template administration (W4-QST-UI; route guard `templates:manage`).
 * Built-in templates are read-only and can be cloned; organization templates
 * can be edited (JSON definition), deactivated or deleted.
 */
import { useCallback, useEffect, useState } from 'react'
import { Copy, FileStack, Pencil, Plus, Power, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { TemplateEditorDialog } from '@/components/templates/TemplateEditorDialog'
import { caseTemplatesApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import { templateSummaryText } from '@/lib/template-definition'
import type { CaseTemplate } from '@/types'

export default function TemplatesPage() {
  const confirm = useConfirm()
  const [items, setItems] = useState<CaseTemplate[] | null>(null)
  const [editing, setEditing] = useState<CaseTemplate | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await caseTemplatesApi.list({ includeInactive: true, includeDefinition: true })
      setItems(res.items)
    } catch (err) {
      setItems([])
      notifyError(err, 'load the case templates')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const run = async (id: string, fn: () => Promise<unknown>, done: string, action: string) => {
    setBusy(id)
    try {
      await fn()
      notifySuccess(done)
      await load()
    } catch (err) {
      notifyError(err, action)
    } finally {
      setBusy(null)
    }
  }

  const clone = (t: CaseTemplate) =>
    run(t.id, () => caseTemplatesApi.clone(t.id), `Cloned ${t.name}`, 'clone the template')

  const toggleActive = (t: CaseTemplate) =>
    run(
      t.id,
      () => caseTemplatesApi.update(t.id, { is_active: !t.is_active }, t.version),
      t.is_active ? 'Template deactivated' : 'Template activated',
      'update the template'
    )

  const remove = async (t: CaseTemplate) => {
    if (!(await confirmDelete(confirm, 'case template', t.name))) return
    run(t.id, () => caseTemplatesApi.remove(t.id, t.version), 'Template deleted', 'delete the template')
  }

  const openEditor = (t: CaseTemplate | null) => {
    setEditing(t)
    setEditorOpen(true)
  }

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground lg:text-3xl">Case templates</h1>
          <p className="mt-1 text-muted-foreground">
            Templates seed an incident with investigative questions, leads, a playbook and custom fields. Built-in templates are read-only; clone one to adapt it.
          </p>
        </div>
        <Button onClick={() => openEditor(null)}>
          <Plus className="mr-1.5 h-4 w-4" /> New template
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table aria-label="Case templates">
            <TableHeader>
              <TableRow>
                <TableHead>Template</TableHead>
                <TableHead className="hidden md:table-cell">Contents</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items === null && (
                <TableRow><TableCell colSpan={4} className="text-muted-foreground">Loading…</TableCell></TableRow>
              )}
              {items?.length === 0 && (
                <TableRow><TableCell colSpan={4} className="text-muted-foreground">No templates.</TableCell></TableRow>
              )}
              {items?.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <div className="flex items-center gap-2 font-medium">
                      <FileStack className="h-4 w-4 text-muted-foreground" />
                      {t.name}
                      {t.is_builtin && <Badge variant="outline" className="text-[10px]">Built-in</Badge>}
                    </div>
                    {t.description && <p className="mt-0.5 text-xs text-muted-foreground">{t.description}</p>}
                  </TableCell>
                  <TableCell className="hidden text-sm text-muted-foreground md:table-cell">{templateSummaryText(t)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{t.is_active ? 'Active' : 'Inactive'}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => clone(t)} disabled={busy === t.id} aria-label={`Clone ${t.name}`}>
                        <Copy className="h-4 w-4" />
                      </Button>
                      {!t.is_builtin && (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => openEditor(t)} aria-label={`Edit ${t.name}`}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => toggleActive(t)} disabled={busy === t.id} aria-label={`${t.is_active ? 'Deactivate' : 'Activate'} ${t.name}`}>
                            <Power className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => remove(t)} disabled={busy === t.id} aria-label={`Delete ${t.name}`}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <TemplateEditorDialog open={editorOpen} onOpenChange={setEditorOpen} template={editing} onSaved={load} />
    </div>
  )
}
