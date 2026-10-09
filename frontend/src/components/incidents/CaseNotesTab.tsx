"use client"

import { useEffect, useRef, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
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
import { TableEmpty } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { DataTablePager, FilterSelect } from '@/components/ui/data-table'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { formatRelativeTime } from '@/lib/utils'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { describeError, notifyError } from '@/lib/errors'
import type { CaseNote, VersionedRow } from '@/types'
import {
  Plus,
  StickyNote,
  Edit2,
  Trash2,
  Pin,
  PinOff,
  User,
  Clock,
  Search,
  HelpCircle,
  CheckSquare,
  ArrowRightLeft,
  FileSearch,
  Lightbulb,
  Tag,
  AlertTriangle,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { cn } from '@/lib/utils'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'

type NoteRow = VersionedRow<CaseNote>

const CATEGORY_OPTIONS = [
  { value: 'general', label: 'General', icon: StickyNote, color: 'bg-slate-500/20 text-slate-400 border-slate-500/30' },
  { value: 'finding', label: 'Finding', icon: FileSearch, color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  { value: 'question', label: 'Question', icon: HelpCircle, color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
  { value: 'action_item', label: 'Action Item', icon: CheckSquare, color: 'bg-green-500/20 text-green-400 border-green-500/30' },
  { value: 'handoff', label: 'Handoff', icon: ArrowRightLeft, color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  { value: 'evidence', label: 'Evidence', icon: Tag, color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
  { value: 'hypothesis', label: 'Hypothesis', icon: Lightbulb, color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
]

const getCategoryInfo = (category: string) =>
  CATEGORY_OPTIONS.find(c => c.value === category) || CATEGORY_OPTIONS[0]

export function CaseNotesTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
  const confirm = useConfirm()
  const endpoint = `/incidents/${incidentId}/case-notes`
  // Server default sort: pinned first, then newest.
  const query = usePaginatedQuery<NoteRow>({
    endpoint,
    urlKey: 'notes',
    focus: focusRowId,
    live: 'case_note',
  })
  const canWrite = usePermission('incidents:update')
  const canDelete = usePermission('case_notes:delete')

  const [showModal, setShowModal] = useState(false)
  const [editingNote, setEditingNote] = useState<NoteRow | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [form, setForm] = useState({
    title: '',
    content: '',
    category: 'general',
    is_pinned: false,
  })

  // Search box: local text, debounced by the query.
  const [search, setSearch] = useState(query.state.q ?? '')
  const [syncedQ, setSyncedQ] = useState(query.state.q)
  if (query.state.q !== syncedQ) {
    setSyncedQ(query.state.q)
    setSearch(query.state.q ?? '')
  }

  // Deep link: bring the focused note into view once it is rendered.
  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  useEffect(() => {
    if (!focusRowId) return
    cardRefs.current.get(focusRowId)?.scrollIntoView?.({ block: 'center' })
  }, [focusRowId, query.items])

  const resetForm = () => {
    setForm({ title: '', content: '', category: 'general', is_pinned: false })
    setEditingNote(null)
  }

  const handleOpenCreate = () => {
    resetForm()
    setShowModal(true)
  }

  const handleOpenEdit = (note: NoteRow) => {
    setEditingNote(note)
    setForm({
      title: note.title,
      content: note.content,
      category: note.category,
      is_pinned: note.is_pinned,
    })
    setShowModal(true)
  }

  const handleSubmit = async () => {
    if (!form.title.trim() || !form.content.trim()) return
    setIsSubmitting(true)
    try {
      if (editingNote) {
        await api.put(`${endpoint}/${editingNote.id}`, form, { ifMatch: editingNote.version })
      } else {
        await api.post(endpoint, form)
      }
      setShowModal(false)
      resetForm()
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, editingNote ? 'save the note' : 'add the note')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (note: NoteRow) => {
    if (!(await confirmDelete(confirm, 'case note', note.title))) return
    try {
      await api.delete(`${endpoint}/${note.id}`, undefined, { ifMatch: note.version })
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, 'delete the note')
    }
  }

  const handleTogglePin = async (note: NoteRow) => {
    try {
      await api.put(`${endpoint}/${note.id}`, { is_pinned: !note.is_pinned }, { ifMatch: note.version })
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, note.is_pinned ? 'unpin the note' : 'pin the note')
    }
  }

  const filtersActive = !!query.state.q || Object.keys(query.state.filters).length > 0
  const errorInfo = query.error ? describeError(query.error) : null
  const notes = query.items

  return (
    <>
      <div className="space-y-4">
        <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="note" />

        {/* Filters & Action */}
        <Card>
          <CardContent className="p-4">
            <div className="flex flex-col lg:flex-row gap-4 justify-between">
              <div className="flex flex-col lg:flex-row gap-4 flex-1">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="search"
                    aria-label="Search notes"
                    placeholder="Search notes..."
                    value={search}
                    onChange={e => {
                      setSearch(e.target.value)
                      query.setQuery(e.target.value)
                    }}
                    className="pl-10"
                    variant="glass"
                  />
                </div>
                <FilterSelect
                  label="Category"
                  allLabel="All categories"
                  value={query.state.filters.category}
                  onChange={(v) => query.setFilter('category', v)}
                  options={CATEGORY_OPTIONS.map((c) => ({ value: c.value, label: c.label }))}
                  className="w-[180px]"
                />
              </div>
              {canWrite && (
                <Button onClick={handleOpenCreate}>
                  <Plus className="mr-2 h-4 w-4" /> Add Note
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {errorInfo && notes.length > 0 && (
          <div role="alert" className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            <span>{errorInfo.description}</span>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => void query.refetch()}>
              Retry
            </Button>
          </div>
        )}

        {/* Notes List */}
        {query.isLoading ? (
          <div className="space-y-3" aria-busy="true">
            {[1, 2, 3].map(i => (
              <div key={i} className="rounded-xl bg-white/5 border border-white/10 p-4 space-y-3">
                <Skeleton className="h-5 w-1/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ))}
          </div>
        ) : errorInfo && notes.length === 0 ? (
          <Card>
            <CardContent className="py-12">
              <div role="alert" className="flex flex-col items-center gap-2 text-center">
                <AlertTriangle className="h-6 w-6 text-destructive" />
                <p className="text-sm font-medium">{errorInfo.title}</p>
                <p className="max-w-sm text-xs text-muted-foreground">{errorInfo.description}</p>
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  Retry
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : notes.length === 0 ? (
          <Card>
            <CardContent className="p-0">
              <TableEmpty
                title={filtersActive ? 'No matching notes' : 'No case notes yet'}
                description={filtersActive ? 'No notes match the current search or filters.' : 'Document your investigation findings, observations, and key decisions as you work through this incident.'}
                icon={<StickyNote className="w-8 h-8" />}
                action={filtersActive ? (
                  <Button size="sm" variant="outline" onClick={query.resetFilters}>
                    Clear filters
                  </Button>
                ) : canWrite ? (
                  <Button size="sm" variant="outline" onClick={handleOpenCreate}>
                    <Plus className="mr-2 h-3.5 w-3.5" /> Add Note
                  </Button>
                ) : undefined}
              />
            </CardContent>
          </Card>
        ) : (
          <div className={cn('space-y-3', query.isFetching && 'opacity-60 transition-opacity')} aria-busy={query.isFetching || undefined}>
            {notes.map(note => {
                const catInfo = getCategoryInfo(note.category)
                const CatIcon = catInfo.icon
                const isFocused = focusRowId === note.id
                return (
                  <div
                    key={note.id}
                    ref={(el) => {
                      if (el) cardRefs.current.set(note.id, el)
                      else cardRefs.current.delete(note.id)
                    }}
                    data-testid="case-note"
                    className={cn(
                      'rounded-xl bg-white/5 border p-4',
                      note.is_pinned ? 'border-yellow-500/30 bg-yellow-500/5' : 'border-white/10',
                      isFocused && 'ring-1 ring-primary/60 bg-primary/5'
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          {note.is_pinned && (
                            <Pin className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0" aria-label="Pinned" />
                          )}
                          <h4 className="font-medium text-foreground">{note.title}</h4>
                          <Badge className={`${catInfo.color} border text-[10px] px-1.5 py-0`}>
                            <CatIcon className="w-3 h-3 mr-1" />
                            {catInfo.label}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-2 whitespace-pre-wrap leading-relaxed">
                          {note.content}
                        </p>
                        <div className="flex items-center gap-3 mt-3 flex-wrap">
                          {note.author && (
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <User className="w-3 h-3" /> {note.author.name}
                            </span>
                          )}
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {formatRelativeTime(note.created_at)}
                          </span>
                          {note.updated_at && note.updated_at !== note.created_at && (
                            <span className="text-xs text-muted-foreground/50">
                              (edited {formatRelativeTime(note.updated_at)})
                            </span>
                          )}
                        </div>
                      </div>
                      {(canWrite || canDelete) && (
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {canWrite && (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleTogglePin(note)}
                                aria-label={note.is_pinned ? 'Unpin note' : 'Pin note'}
                                title={note.is_pinned ? 'Unpin' : 'Pin'}
                              >
                                {note.is_pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => handleOpenEdit(note)} aria-label="Edit note" title="Edit">
                                <Edit2 className="h-4 w-4" />
                              </Button>
                            </>
                          )}
                          {canDelete && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(note)}
                              aria-label="Delete note"
                              title="Delete"
                              className="text-red-400 hover:text-red-300"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
          </div>
        )}

        {!query.isLoading && query.total > 0 && (
          <DataTablePager
            page={query.state.page}
            pages={query.pages}
            perPage={query.state.perPage}
            total={query.total}
            onPage={query.setPage}
            onPerPage={query.setPerPage}
          />
        )}
      </div>

      {/* Create/Edit Modal */}
      <Dialog open={showModal} onOpenChange={(open) => { if (!open) { setShowModal(false); resetForm() } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingNote ? 'Edit Case Note' : 'New Case Note'}</DialogTitle>
            <DialogDescription>
              {editingNote ? 'Update this case note' : 'Document an investigation finding or observation'}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Title</Label>
              <Input
                value={form.title}
                onChange={e => setForm({ ...form, title: e.target.value })}
                placeholder="Note title"
                variant="glass"
              />
            </div>
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={form.category} onValueChange={v => setForm({ ...form, category: v })}>
                <SelectTrigger variant="glass">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORY_OPTIONS.map(cat => (
                    <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Content</Label>
              <Textarea
                value={form.content}
                onChange={e => setForm({ ...form, content: e.target.value })}
                placeholder="Write your note here..."
                variant="glass"
                rows={8}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="pin-note"
                checked={form.is_pinned}
                onChange={e => setForm({ ...form, is_pinned: e.target.checked })}
                className="rounded border-white/20 bg-white/5"
              />
              <Label htmlFor="pin-note" className="text-sm cursor-pointer">Pin this note to the top</Label>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setShowModal(false); resetForm() }}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={isSubmitting || !form.title.trim() || !form.content.trim()}>
              {isSubmitting ? 'Saving...' : editingNote ? 'Update Note' : 'Create Note'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
