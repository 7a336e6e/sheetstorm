/**
 * Pure helpers for the decision log UI (labels, options, which transitions a
 * user may start). The server enforces every rule; these only decide what to
 * offer.
 */
import type {
  Decision,
  DecisionCategory,
  DecisionEvent,
  DecisionStatus,
  ResponseAction,
  ResponseActionEvent,
  ResponseActionStatus,
  ResponseActionType,
  ResponseTargetType,
} from '@/types'

const titleCase = (v: string) => v.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const DECISION_CATEGORIES: DecisionCategory[] = [
  'containment', 'eradication', 'recovery', 'notification', 'ransom_legal', 'scope', 'communication', 'evidence', 'other',
]
export const DECISION_STATUSES: DecisionStatus[] = ['proposed', 'approved', 'rejected', 'superseded']
export const ACTION_TYPES: ResponseActionType[] = [
  'isolate_host', 'release_host', 'contain_host', 'reimage_host', 'decommission_host', 'disable_account',
  'reset_credentials', 'revoke_sessions', 'delete_account', 'block_ioc', 'sinkhole_domain', 'quarantine_file',
  'remove_persistence', 'patch', 'notify_party', 'other',
]
export const ACTION_STATUSES: ResponseActionStatus[] = [
  'requested', 'authorized', 'in_progress', 'executed', 'verified', 'failed', 'rolled_back', 'cancelled',
]
export const TARGET_TYPES: ResponseTargetType[] = ['host', 'account', 'network_ioc', 'host_ioc', 'malware', 'external', 'none']

export const CATEGORY_LABELS: Record<DecisionCategory, string> = {
  containment: 'Containment',
  eradication: 'Eradication',
  recovery: 'Recovery',
  notification: 'Notification',
  ransom_legal: 'Ransom / legal',
  scope: 'Scope',
  communication: 'Communication',
  evidence: 'Evidence',
  other: 'Other',
}

export const label = (value: string | null | undefined): string => (value ? titleCase(value) : '—')

export const options = <T extends string>(values: T[], labels?: Partial<Record<T, string>>) =>
  values.map((value) => ({ value, label: labels?.[value] ?? titleCase(value) }))

/** Action types that can set the target's state on execute, and the target they need. */
export const TARGET_STATE_ACTIONS: Partial<Record<ResponseActionType, 'host' | 'account'>> = {
  isolate_host: 'host',
  contain_host: 'host',
  reimage_host: 'host',
  decommission_host: 'host',
  release_host: 'host',
  disable_account: 'account',
  reset_credentials: 'account',
  delete_account: 'account',
}

/** Status tone for badges (dark theme classes). */
export function statusTone(status: DecisionStatus | ResponseActionStatus | string): string {
  switch (status) {
    case 'approved':
    case 'verified':
    case 'executed':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
    case 'rejected':
    case 'failed':
      return 'border-red-500/30 bg-red-500/10 text-red-300'
    case 'superseded':
    case 'cancelled':
    case 'rolled_back':
      return 'border-white/10 bg-white/5 text-slate-400'
    case 'authorized':
    case 'in_progress':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-300'
    default:
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  }
}

type Can = (perm: string) => boolean

/** Decision transitions offered to a user (approve also covers recording an external approval). */
export function decisionEvents(d: Pick<Decision, 'status'>, can: Can): DecisionEvent[] {
  const out: DecisionEvent[] = []
  if (d.status === 'proposed') {
    if (can('decisions:approve') || can('decisions:update')) out.push('approve')
    if (can('decisions:approve')) out.push('reject')
  }
  if (d.status === 'rejected' && can('decisions:update')) out.push('reopen')
  if ((d.status === 'proposed' || d.status === 'approved') && can('decisions:update')) out.push('supersede')
  return out
}

const ACTION_FLOW: Record<ResponseActionEvent, ResponseActionStatus[]> = {
  authorize: ['requested', 'failed'],
  start: ['authorized'],
  execute: ['authorized', 'in_progress'],
  fail: ['in_progress', 'executed'],
  verify: ['executed'],
  rollback: ['executed', 'verified'],
  cancel: ['requested', 'authorized', 'in_progress'],
}

/** Action transitions valid from the current status that the user may start. */
export function actionEvents(a: Pick<ResponseAction, 'status'>, can: Can): ResponseActionEvent[] {
  return (Object.keys(ACTION_FLOW) as ResponseActionEvent[]).filter((ev) => {
    if (!ACTION_FLOW[ev].includes(a.status)) return false
    if (ev === 'authorize') return can('response_actions:authorize') || can('response_actions:update')
    return can('response_actions:update')
  })
}

/** Events whose dialog requires a reason. */
export function reasonRequired(event: DecisionEvent | ResponseActionEvent, fromStatus?: string): boolean {
  if (event === 'authorize') return fromStatus === 'failed'
  return ['reject', 'reopen', 'fail', 'rollback', 'cancel'].includes(event)
}

/** "Name" for a user/attested-name pair: in-app user, else "<name> (recorded)". */
export function actorLabel(
  rec: { users?: Record<string, { name: string } | null> },
  userField: string,
  name: string | null | undefined
): string | null {
  const user = rec.users?.[userField]
  if (user) return user.name
  return name ? `${name} (recorded)` : null
}
