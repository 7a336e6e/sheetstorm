"use client"

/**
 * Add questions from the library (SheetStorm core + DFIQ when vendored) to an
 * incident. Questions already on the incident are skipped by the server.
 */
import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { SearchInput } from '@/components/ui/input'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { questionsApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import { priorityLabel } from '@/lib/questions'
import type { QuestionLibraryTree } from '@/types'

interface Props {
  incidentId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onAdded: () => void
}

const MAX_REFS = 100

export function LibraryDialog({ incidentId, open, onOpenChange, onAdded }: Props) {
  const [tree, setTree] = useState<QuestionLibraryTree | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [filter, setFilter] = useState('')
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    if (!open) return
    setSelected(new Set())
    setFilter('')
    const ctrl = new AbortController()
    questionsApi
      .library({ signal: ctrl.signal })
      .then((t) => {
        setTree(t)
        setLoadError(false)
      })
      .catch((err) => {
        if ((err as Error)?.name === 'AbortError') return
        setLoadError(true)
        notifyError(err, 'load the question library')
      })
    return () => ctrl.abort()
  }, [open])

  const groups = useMemo(() => {
    if (!tree) return []
    const needle = filter.trim().toLowerCase()
    return tree.groups
      .map((g) => ({
        ...g,
        facets: g.facets
          .map((f) => ({
            ...f,
            questions: needle ? f.questions.filter((q) => q.question.toLowerCase().includes(needle)) : f.questions,
          }))
          .filter((f) => f.questions.length > 0),
      }))
      .filter((g) => g.facets.length > 0)
  }, [tree, filter])

  const toggle = (ref: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(ref)) next.delete(ref)
      else if (next.size < MAX_REFS) next.add(ref)
      return next
    })

  const add = async () => {
    if (!selected.size) return
    setAdding(true)
    try {
      const res = await questionsApi.bulkAdd(incidentId, Array.from(selected))
      const skipped = res.skipped.length
      notifySuccess(
        `Added ${res.created.length} question${res.created.length === 1 ? '' : 's'}`,
        skipped ? `${skipped} already on the incident or archived` : undefined
      )
      onAdded()
      onOpenChange(false)
    } catch (err) {
      notifyError(err, 'add the questions')
    } finally {
      setAdding(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Add questions from the library</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <SearchInput
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter questions"
            aria-label="Filter library questions"
          />
          <div className="max-h-[55vh] space-y-4 overflow-y-auto pr-1">
            {!tree && !loadError && <p className="text-sm text-muted-foreground">Loading…</p>}
            {tree && groups.length === 0 && <p className="text-sm text-muted-foreground">No matching questions.</p>}
            {groups.map((g) => (
              <section key={g.ref} aria-label={g.name}>
                <h3 className="mb-1 text-sm font-semibold">{g.name}</h3>
                {g.facets.map((f) => (
                  <div key={f.ref} className="mb-2">
                    <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">{f.name}</p>
                    <ul className="space-y-1">
                      {f.questions.map((q) => (
                        <li key={q.ref} className="flex items-start gap-2 rounded px-1 py-0.5 hover:bg-muted/40">
                          <Checkbox
                            id={`lib-${q.ref}`}
                            checked={selected.has(q.ref)}
                            onCheckedChange={() => toggle(q.ref)}
                            aria-label={q.question}
                          />
                          <label htmlFor={`lib-${q.ref}`} className="flex-1 cursor-pointer text-sm">
                            {q.question}
                            <span className="ml-2 text-xs text-muted-foreground">{priorityLabel(q.priority)}</span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </section>
            ))}
          </div>
          {tree && tree.sources.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Sources: {tree.sources.map((s) => `${s.name} (${s.license})`).join(', ')}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <span className="mr-auto text-sm text-muted-foreground">{selected.size} selected (max {MAX_REFS})</span>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={add} disabled={!selected.size || adding}>{adding ? 'Adding…' : 'Add selected'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
