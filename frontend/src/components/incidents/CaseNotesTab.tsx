"use client"

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
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
import { formatDateTime, formatRelativeTime } from '@/lib/utils'
import api from '@/lib/api'
import type { CaseNote } from '@/types'
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
  Filter,
  MessageSquare,
  HelpCircle,
  CheckSquare,
  ArrowRightLeft,
  FileSearch,
  Lightbulb,
  Tag,
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { useAuthStore } from '@/lib/store'

interface CaseNotesTabProps {
  incidentId: string
}

const CATEGORY_OPTIONS = [
  { value: 'general', label: 'General', icon: StickyNote, color: 'bg-slate-500/20 text-slate-400 border-slate-500/30' },
  { value: 'finding', label: 'Finding', icon: FileSearch, color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  { value: 'question', label: 'Question', icon: HelpCircle, color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
  { value: 'action_item', label: 'Action Item', icon: CheckSquare, color: 'bg-green-500/20 text-green-400 border-green-500/30' },
  { value: 'handoff', label: 'Handoff', icon: ArrowRightLeft, color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  { value: 'evidence', label: 'Evidence', icon: Tag, color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
  { value: 'hypothesis', label: 'Hypothesis', icon: Lightbulb, color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
]

export function CaseNotesTab({ incidentId }: CaseNotesTabProps) {
  const confirm = useConfirm()
  const { user } = useAuthStore()
  const [notes, setNotes] = useState<CaseNote[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [showModal, setShowModal] = useState(false)
  const [editingNote, setEditingNote] = useState<CaseNote | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const [form, setForm] = useState({
    title: '',
    content: '',
    category: 'general',
    is_pinned: false,
  })

  const loadNotes = async () => {
    try {
      setIsLoading(true)
      const res = await api.get<{ items: CaseNote[] }>(`/incidents/${incidentId}/case-notes`)
      setNotes(res.items || [])
    } catch (error) {
      console.error('Failed to load case notes:', error)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadNotes()
  }, [incidentId])

  const resetForm = () => {
    setForm({ title: '', content: '', category: 'general', is_pinned: false })
    setEditingNote(null)
  }

  const handleOpenCreate = () => {
    resetForm()
    setShowModal(true)
  }

  const handleOpenEdit = (note: CaseNote) => {
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
        await api.put(`/incidents/${incidentId}/case-notes/${editingNote.id}`, form)
      } else {
        await api.post(`/incidents/${incidentId}/case-notes`, form)
      }
      setShowModal(false)
      resetForm()
      await loadNotes()
    } catch (error) {
      console.error('Failed to save case note:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (note: CaseNote) => {
    const ok = await confirm({
      title: 'Delete Case Note',
      description: `Are you sure you want to delete "${note.title}"? This cannot be undone.`,
      confirmText: 'Delete',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await api.delete(`/incidents/${incidentId}/case-notes/${note.id}`)
      await loadNotes()
    } catch (error) {
      console.error('Failed to delete case note:', error)
    }
  }

  const handleTogglePin = async (note: CaseNote) => {
    try {
      await api.put(`/incidents/${incidentId}/case-notes/${note.id}`, {
        is_pinned: !note.is_pinned,
      })
      await loadNotes()
    } catch (error) {
      console.error('Failed to toggle pin:', error)
    }
  }

  // Filter and sort
  const filteredNotes = notes
    .filter(n => {
      if (categoryFilter !== 'all' && n.category !== categoryFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q)
      }
      return true
    })
    .sort((a, b) => {
      // Pinned first, then by created_at descending
      if (a.is_pinned && !b.is_pinned) return -1
      if (!a.is_pinned && b.is_pinned) return 1
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  const getCategoryInfo = (category: string) => {
    return CATEGORY_OPTIONS.find(c => c.value === category) || CATEGORY_OPTIONS[0]
  }

  const canEdit = (note: CaseNote) => {
    if (!user) return false
    return note.author?.id === user.id || user.role === 'admin'
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Case Notes</CardTitle>
          <CardDescription>Loading...</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="rounded-xl bg-white/5 border border-white/10 p-4 space-y-3">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
              <div className="flex items-center gap-3">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-20" />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>Case Notes</CardTitle>
            <CardDescription>Investigation notes, findings, and observations</CardDescription>
          </div>
          <Button onClick={handleOpenCreate}>
            <Plus className="mr-2 h-4 w-4" /> Add Note
          </Button>
        </CardHeader>
        <CardContent>
          {/* Filters */}
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search notes..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-10"
                variant="glass"
              />
            </div>
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger variant="glass" className="w-[160px]">
                <Filter className="h-4 w-4 mr-2" />
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {CATEGORY_OPTIONS.map(cat => (
                  <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Notes List */}
          {filteredNotes.length === 0 ? (
            <TableEmpty
              title={search || categoryFilter !== 'all' ? 'No matching notes' : 'No case notes yet'}
              description={search || categoryFilter !== 'all' ? 'Try adjusting your filters' : 'Add notes to document investigation findings and observations'}
              icon={<StickyNote className="w-10 h-10" />}
            />
          ) : (
            <div className="space-y-3">
              {filteredNotes.map(note => {
                const catInfo = getCategoryInfo(note.category)
                const CatIcon = catInfo.icon
                return (
                  <div
                    key={note.id}
                    className={`rounded-xl bg-white/5 border p-4 ${note.is_pinned ? 'border-yellow-500/30 bg-yellow-500/5' : 'border-white/10'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          {note.is_pinned && (
                            <Pin className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0" />
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
                      {canEdit(note) && (
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleTogglePin(note)}
                            title={note.is_pinned ? 'Unpin' : 'Pin'}
                          >
                            {note.is_pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleOpenEdit(note)}>
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleDelete(note)} className="text-red-400 hover:text-red-300">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

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
