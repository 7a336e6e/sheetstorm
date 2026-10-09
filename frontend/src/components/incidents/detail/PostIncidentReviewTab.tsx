"use client"

/**
 * Post-incident review tab (W3-RT-POST): the structured after-action review
 * (what went well / wrong, root cause, contributing factors, detection
 * source, participants) and the improvement actions it produced.
 *
 * - Anyone with `incidents:update` edits a draft; finalizing, reopening and
 *   editing a final review need the unrestricted tier (`can_manage`, i.e.
 *   `improvements:create` + `improvements:update`). Viewers see it read-only.
 * - Saves send `If-Match` with the review version (409 opens the conflict
 *   dialog). A remote change (`review` realtime entity) never overwrites an
 *   open form: a banner offers to load it.
 * - The legacy free-text `lessons_learned` is shown read-only.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, Loader2, Lock, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { ContributingFactorsEditor } from '@/components/incidents/post-incident/ContributingFactorsEditor'
import { ParticipantsEditor } from '@/components/incidents/post-incident/ParticipantsEditor'
import { ImprovementActionDialog } from '@/components/incidents/post-incident/ImprovementActionDialog'
import {
  ActionStatusSelect,
  DueCell,
  PriorityBadge,
  controlText,
} from '@/components/incidents/post-incident/ActionCells'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { postIncident, incidentActionsEndpoint, IMPROVEMENT_ACTIONS_ENDPOINT } from '@/lib/endpoints/post-incident'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import { subscribeEntity } from '@/lib/realtime/live'
import { DETECTION_SOURCE_OPTIONS, STATUS_OPTIONS } from '@/lib/post-incident'
import { useAuthStore } from '@/lib/store'
import type { IncidentTabBaseProps } from '@/components/incidents/table-helpers'
import type {
  ContributingFactor,
  DetectionSource,
  ImprovementAction,
  IncidentReview,
  ReviewInput,
  ReviewResponse,
} from '@/types'

const NONE = '__none__'

interface Draft {
  what_went_well: string
  what_went_wrong: string
  root_cause: string
  contributing_factors: ContributingFactor[]
  detection_source: DetectionSource | typeof NONE
  review_date: string
  participants: string[]
  names: Record<string, string>
}

const emptyDraft = (): Draft => ({
  what_went_well: '',
  what_went_wrong: '',
  root_cause: '',
  contributing_factors: [],
  detection_source: NONE,
  review_date: '',
  participants: [],
  names: {},
})

function draftOf(review: IncidentReview | null): Draft {
  if (!review) return emptyDraft()
  return {
    what_went_well: review.what_went_well ?? '',
    what_went_wrong: review.what_went_wrong ?? '',
    root_cause: review.root_cause ?? '',
    contributing_factors: review.contributing_factors ?? [],
    detection_source: review.detection_source ?? NONE,
    review_date: review.review_date ?? '',
    participants: review.participants ?? [],
    names: Object.fromEntries((review.participant_users ?? []).map((u) => [u.id, u.name])),
  }
}

const sameFactors = (a: ContributingFactor[], b: ContributingFactor[]) =>
  a.length === b.length && a.every((f, i) => f.category === b[i].category && f.description === b[i].description)

function isDirty(draft: Draft, base: Draft): boolean {
  return (
    draft.what_went_well !== base.what_went_well ||
    draft.what_went_wrong !== base.what_went_wrong ||
    draft.root_cause !== base.root_cause ||
    draft.detection_source !== base.detection_source ||
    draft.review_date !== base.review_date ||
    draft.participants.join() !== base.participants.join() ||
    !sameFactors(draft.contributing_factors, base.contributing_factors)
  )
}

function inputOf(draft: Draft): ReviewInput {
  return {
    what_went_well: draft.what_went_well,
    what_went_wrong: draft.what_went_wrong,
    root_cause: draft.root_cause,
    contributing_factors: draft.contributing_factors,
    detection_source: draft.detection_source === NONE ? null : draft.detection_source,
    review_date: draft.review_date || null,
    participants: draft.participants,
  }
}

type PageProps = IncidentTabBaseProps

export function PostIncidentReviewTab({ incidentId }: PageProps) {
  const [loaded, setLoaded] = useState<ReviewResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [base, setBase] = useState<Draft>(emptyDraft)
  const [remote, setRemote] = useState<IncidentReview | null>(null)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false) // our own save echoes back over the socket: not a remote change
  const confirm = useConfirm()

  const canUpdate = usePermission('incidents:update')
  const review = loaded?.review ?? null
  const final = review?.status === 'final'
  const canManage = loaded?.can_manage ?? false
  const editable = canUpdate && (!final || canManage)
  const dirty = isDirty(draft, base)

  const apply = useCallback((response: ReviewResponse) => {
    const next = draftOf(response.review)
    setLoaded(response)
    setDraft(next)
    setBase(next)
    setRemote(null)
  }, [])

  const load = useCallback(async () => {
    try {
      apply(await postIncident.getReview(incidentId))
      setLoadError(null)
    } catch (err) {
      setLoadError(describeError(err).description)
    }
  }, [apply, incidentId])

  useEffect(() => {
    let cancelled = false
    postIncident
      .getReview(incidentId)
      .then((response) => {
        if (!cancelled) apply(response)
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(describeError(err).description)
      })
    return () => {
      cancelled = true
    }
  }, [apply, incidentId])

  // A change made elsewhere: apply it unless this form has unsaved edits.
  const version = review?.version ?? 0
  useEffect(() => {
    return subscribeEntity('review', (change) => {
      if (change.incident_id !== incidentId || change.op === 'deleted') return
      const incoming = change.data as IncidentReview | undefined
      if (savingRef.current || !incoming || (incoming.version ?? 0) <= version) return
      if (dirty) setRemote(incoming)
      else
        apply({
          review: incoming,
          legacy_lessons_learned: loaded?.legacy_lessons_learned ?? null,
          can_manage: loaded?.can_manage ?? false,
        })
    })
  }, [incidentId, version, dirty, apply, loaded])

  const persist = async (extra: Pick<ReviewInput, 'status'> = {}, what = 'save the review') => {
    setSaving(true)
    savingRef.current = true
    try {
      await postIncident.saveReview(incidentId, { ...inputOf(draft), ...extra }, review?.version)
      await load()
      return true
    } catch (err) {
      notifyError(err, what)
      return false
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const finalize = async () => {
    const ok = await confirm({
      title: 'Finalize this review?',
      description: 'A final review can only be edited again by an incident responder or manager.',
      confirmLabel: 'Finalize',
    })
    if (!ok) return
    if (await persist({ status: 'final' }, 'finalize the review')) notifySuccess('Review finalized')
  }

  const reopen = async () => {
    if (await persist({ status: 'draft' }, 'reopen the review')) notifySuccess('Review reopened as a draft')
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }))

  if (loadError && !loaded) {
    return (
      <p role="alert" className="text-sm text-red-400">
        Could not load the review: {loadError}
      </p>
    )
  }
  if (!loaded) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Loading review">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              Post-incident review
              <Badge variant={final ? 'success' : 'outline'} data-testid="review-status">
                {final ? 'Final' : 'Draft'}
              </Badge>
            </CardTitle>
            <CardDescription>
              {final && review?.finalized_at ? (
                <>
                  Finalized <Timestamp value={review.finalized_at} seconds={false} />
                  {review.finalized_by_user ? ` by ${review.finalized_by_user.name}` : ''}
                </>
              ) : (
                'Capture what happened, why, and what should change.'
              )}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {editable && (
              <Button onClick={() => void persist()} disabled={saving || !dirty}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save review
              </Button>
            )}
            {canManage && canUpdate && !final && review && (
              <Button variant="outline" onClick={() => void finalize()} disabled={saving || dirty}>
                <CheckCircle2 className="mr-1 h-4 w-4" /> Finalize
              </Button>
            )}
            {canManage && canUpdate && final && (
              <Button variant="outline" onClick={() => void reopen()} disabled={saving}>
                <RotateCcw className="mr-1 h-4 w-4" /> Reopen
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {final && !canManage && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Lock className="h-4 w-4" /> This review is final. An incident responder or manager can reopen it.
            </p>
          )}
          {remote && (
            <div
              role="status"
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300"
            >
              <span>This review changed while you were editing.</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  apply({
                    review: remote,
                    legacy_lessons_learned: loaded.legacy_lessons_learned,
                    can_manage: loaded.can_manage,
                  })
                }
              >
                Load their version
              </Button>
            </div>
          )}
          {loaded.legacy_lessons_learned && (
            <div className="rounded-md border border-border bg-muted/30 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Legacy notes</p>
              <p className="mt-1 whitespace-pre-wrap text-sm">{loaded.legacy_lessons_learned}</p>
            </div>
          )}

          {(
            [
              ['what_went_well', 'What went well'],
              ['what_went_wrong', 'What went wrong'],
              ['root_cause', 'Root cause'],
            ] as const
          ).map(([field, label]) => (
            <div key={field} className="space-y-1.5">
              <Label htmlFor={`review-${field}`}>{label}</Label>
              <Textarea
                id={`review-${field}`}
                rows={4}
                maxLength={20000}
                value={draft[field]}
                readOnly={!editable}
                onChange={(e) => set(field, e.target.value)}
              />
            </div>
          ))}

          <div className="space-y-1.5">
            <Label>Contributing factors</Label>
            <ContributingFactorsEditor
              value={draft.contributing_factors}
              onChange={(v) => set('contributing_factors', v)}
              disabled={!editable}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Detection source</Label>
              <Select
                value={draft.detection_source}
                onValueChange={(v) => set('detection_source', v as Draft['detection_source'])}
                disabled={!editable}
              >
                <SelectTrigger aria-label="Detection source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Not recorded</SelectItem>
                  {DETECTION_SOURCE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="review-date">Review date</Label>
              <Input
                id="review-date"
                type="date"
                value={draft.review_date}
                disabled={!editable}
                onChange={(e) => set('review_date', e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Participants</Label>
            <ParticipantsEditor
              value={draft.participants}
              names={draft.names}
              onChange={(ids, names) => setDraft((d) => ({ ...d, participants: ids, names }))}
              disabled={!editable}
            />
          </div>
        </CardContent>
      </Card>

      <ImprovementActionsSection incidentId={incidentId} reviewId={review?.id ?? null} />
    </div>
  )
}

// ─── Improvement actions of this incident ────────────────────────────────

function ImprovementActionsSection({ incidentId, reviewId }: { incidentId: string; reviewId: string | null }) {
  const canRead = usePermission('improvements:read')
  const canCreate = usePermission('improvements:create')
  const canUpdate = usePermission('improvements:update')
  const canDelete = usePermission('improvements:delete')
  const userId = useAuthStore((s) => s.user?.id)
  const confirm = useConfirm()
  const endpoint = incidentActionsEndpoint(incidentId)
  const query = usePaginatedQuery<ImprovementAction>({
    endpoint,
    urlKey: 'actions',
    live: 'improvement_action',
    enabled: canRead,
  })
  const [dialog, setDialog] = useState<{ open: boolean; action: ImprovementAction | null }>({ open: false, action: null })

  const mayChange = useCallback(
    (a: ImprovementAction) => canUpdate && (canCreate || a.owner_id === userId || a.created_by === userId),
    [canUpdate, canCreate, userId]
  )

  const columns = useMemo<DataTableColumn<ImprovementAction>[]>(
    () => [
      {
        id: 'title',
        header: 'Action',
        sortKey: 'title',
        cell: (a) => (
          <div className="min-w-[14rem]">
            <div className="font-medium">{a.title}</div>
            {controlText(a) && <div className="text-xs text-muted-foreground">{controlText(a)}</div>}
          </div>
        ),
      },
      { id: 'owner', header: 'Owner', hideBelow: 'md', cell: (a) => a.owner?.name ?? <span className="text-muted-foreground">Unassigned</span> },
      { id: 'priority', header: 'Priority', sortKey: 'priority', hideBelow: 'sm', cell: (a) => <PriorityBadge priority={a.priority} /> },
      { id: 'due', header: 'Due', sortKey: 'due_date', cell: (a) => <DueCell action={a} /> },
      {
        id: 'status',
        header: 'Status',
        sortKey: 'status',
        cell: (a) => <ActionStatusSelect action={a} canChange={mayChange(a)} />,
      },
    ],
    [mayChange]
  )

  const rowActions = (a: ImprovementAction): RowAction[] => [
    {
      label: 'Edit',
      icon: Pencil,
      permission: 'improvements:update',
      disabled: !mayChange(a),
      onSelect: () => setDialog({ open: true, action: a }),
    },
    {
      label: 'Delete',
      icon: Trash2,
      destructive: true,
      permission: 'improvements:delete',
      onSelect: async () => {
        if (!(await confirmDelete(confirm, 'improvement action', a.title))) return
        try {
          await postIncident.deleteAction(a.id, a.version)
          invalidate(endpoint)
          invalidate(IMPROVEMENT_ACTIONS_ENDPOINT)
        } catch (err) {
          notifyError(err, 'delete the improvement action')
        }
      },
    },
  ]

  if (!canRead) return null
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Improvement actions</CardTitle>
          <CardDescription>
            Tracked follow-ups with an owner and due date{reviewId ? '' : ' (save the review to link them to it)'}.
            They stay listed organization-wide if this incident is deleted.
          </CardDescription>
        </div>
        {canCreate && (
          <Button onClick={() => setDialog({ open: true, action: null })}>
            <Plus className="mr-1 h-4 w-4" /> Add action
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <DataTable<ImprovementAction>
          query={query}
          columns={columns}
          getRowId={(a) => a.id}
          ariaLabel="Improvement actions"
          rowActions={canUpdate || canDelete ? rowActions : undefined}
          toolbar={
            <FilterSelect
              label="Status"
              allLabel="All statuses"
              value={query.state.filters.status}
              onChange={(v) => query.setFilter('status', v)}
              options={STATUS_OPTIONS}
            />
          }
          empty={{ title: 'No improvement actions yet', description: 'Add the follow-ups this review calls for.' }}
        />
      </CardContent>
      <ImprovementActionDialog
        open={dialog.open}
        onOpenChange={(open) => setDialog((d) => ({ ...d, open }))}
        incidentId={incidentId}
        action={dialog.action}
      />
    </Card>
  )
}
