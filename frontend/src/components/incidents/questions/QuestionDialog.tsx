"use client"

/**
 * Create a manual question, or edit/answer an existing one (W4-QST-UI).
 * The answer is plain text (rendered without HTML); the server re-checks the
 * same rules `answerProblem` mirrors.
 */
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { questionsApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import {
  MAX_ANSWER_LENGTH,
  MAX_QUESTION_LENGTH,
  QUESTION_CONFIDENCES,
  QUESTION_PRIORITIES,
  QUESTION_STATUSES,
  answerProblem,
  confidenceLabel,
  priorityLabel,
  statusLabel,
} from '@/lib/questions'
import type { InvestigativeQuestion, QuestionConfidence, QuestionInput, QuestionPriority, QuestionStatus } from '@/types'

interface Props {
  incidentId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** null = create a manual question. */
  question: InvestigativeQuestion | null
  onSaved: () => void
}

const NONE = '__none__'

export function QuestionDialog({ incidentId, open, onOpenChange, question, onSaved }: Props) {
  const [text, setText] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<QuestionStatus>('open')
  const [answer, setAnswer] = useState('')
  const [confidence, setConfidence] = useState<QuestionConfidence | ''>('')
  const [priority, setPriority] = useState<QuestionPriority>('medium')
  const [phase, setPhase] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setText(question?.question ?? '')
    setDescription(question?.description ?? '')
    setStatus(question?.status ?? 'open')
    setAnswer(question?.answer ?? '')
    setConfidence(question?.confidence ?? '')
    setPriority(question?.priority ?? 'medium')
    setPhase(question?.phase ? String(question.phase) : '')
  }, [open, question])

  const evidenceCount = question?.evidence_refs?.length ?? 0
  const problem = question ? answerProblem({ status, answer, confidence, evidenceCount }) : null
  const canSave = text.trim().length > 0 && !problem && !saving

  const save = async () => {
    if (!canSave) return
    setSaving(true)
    try {
      const body: QuestionInput = {
        question: text.trim(),
        description: description.trim() || null,
        priority,
        phase: phase ? Number(phase) : null,
      }
      if (question) {
        body.status = status
        body.answer = answer.trim() || null
        body.confidence = confidence || null
        await questionsApi.update(incidentId, question.id, body, question.version)
        notifySuccess('Question saved')
      } else {
        await questionsApi.create(incidentId, body)
        notifySuccess('Question added')
      }
      onSaved()
      onOpenChange(false)
    } catch (err) {
      notifyError(err, question ? 'save the question' : 'add the question')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{question ? 'Question' : 'Add question'}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="q-text">Question</Label>
            <Textarea
              id="q-text"
              value={text}
              maxLength={MAX_QUESTION_LENGTH}
              rows={2}
              onChange={(e) => setText(e.target.value)}
              placeholder="What do we need to find out?"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="q-desc">Context</Label>
            <Textarea id="q-desc" value={description} rows={2} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Priority</Label>
              <Select value={priority} onValueChange={(v) => setPriority(v as QuestionPriority)}>
                <SelectTrigger aria-label="Priority"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {QUESTION_PRIORITIES.map((p) => <SelectItem key={p} value={p}>{priorityLabel(p)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="q-phase">Phase</Label>
              <Input id="q-phase" type="number" min={1} max={20} value={phase} onChange={(e) => setPhase(e.target.value)} />
            </div>
          </div>
          {question && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Status</Label>
                  <Select value={status} onValueChange={(v) => setStatus(v as QuestionStatus)}>
                    <SelectTrigger aria-label="Status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {QUESTION_STATUSES.map((s) => <SelectItem key={s} value={s}>{statusLabel(s)}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Confidence</Label>
                  <Select value={confidence || NONE} onValueChange={(v) => setConfidence(v === NONE ? '' : (v as QuestionConfidence))}>
                    <SelectTrigger aria-label="Confidence"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>Not set</SelectItem>
                      {QUESTION_CONFIDENCES.map((c) => <SelectItem key={c} value={c}>{confidenceLabel(c)}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="q-answer">{status === 'unanswerable' ? 'Rationale' : 'Answer'}</Label>
                <Textarea
                  id="q-answer"
                  value={answer}
                  maxLength={MAX_ANSWER_LENGTH}
                  rows={5}
                  onChange={(e) => setAnswer(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {evidenceCount} linked evidence reference{evidenceCount === 1 ? '' : 's'}.
                </p>
              </div>
              {problem && (
                <p role="alert" className="text-sm text-amber-600 dark:text-amber-400">{problem.message}</p>
              )}
            </>
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
