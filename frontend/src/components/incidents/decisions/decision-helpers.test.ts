/**
 * @jest-environment node
 */
import { describe, expect, it } from '@jest/globals'
import { actionEvents, actorLabel, decisionEvents, reasonRequired, statusTone } from './decision-helpers'
import { formatAlternatives, parseAlternatives } from './DecisionFormDialog'
import { blankTransitionForm, transitionBody, type TransitionTarget } from './TransitionDialog'
import { defaultTargetType } from './ResponseActionFormDialog'
import type { Decision, ResponseAction } from '@/types'

const can = (...perms: string[]) => (p: string) => perms.includes(p)

describe('decisionEvents', () => {
  it('offers approve (external attestation) to updaters and reject only to approvers', () => {
    expect(decisionEvents({ status: 'proposed' }, can('decisions:update'))).toEqual(['approve', 'supersede'])
    expect(decisionEvents({ status: 'proposed' }, can('decisions:approve'))).toEqual(['approve', 'reject'])
    expect(decisionEvents({ status: 'rejected' }, can('decisions:update'))).toEqual(['reopen'])
    expect(decisionEvents({ status: 'superseded' }, can('decisions:update', 'decisions:approve'))).toEqual([])
    expect(decisionEvents({ status: 'proposed' }, can())).toEqual([])
  })
})

describe('actionEvents', () => {
  it('follows the state machine and the permissions', () => {
    expect(actionEvents({ status: 'requested' }, can('response_actions:authorize'))).toEqual(['authorize'])
    expect(actionEvents({ status: 'requested' }, can('response_actions:update'))).toEqual(['authorize', 'cancel'])
    expect(actionEvents({ status: 'authorized' }, can('response_actions:update'))).toEqual(['start', 'execute', 'cancel'])
    expect(actionEvents({ status: 'executed' }, can('response_actions:update'))).toEqual(['fail', 'verify', 'rollback'])
    expect(actionEvents({ status: 'verified' }, can('response_actions:update'))).toEqual(['rollback'])
    expect(actionEvents({ status: 'cancelled' }, can('response_actions:update'))).toEqual([])
    expect(actionEvents({ status: 'executed' }, can('response_actions:read'))).toEqual([])
  })
})

describe('helpers', () => {
  it('requires reasons where the server does', () => {
    expect(reasonRequired('reject')).toBe(true)
    expect(reasonRequired('cancel')).toBe(true)
    expect(reasonRequired('approve')).toBe(false)
    expect(reasonRequired('authorize', 'requested')).toBe(false)
    expect(reasonRequired('authorize', 'failed')).toBe(true)
  })

  it('labels in-app actors and recorded names', () => {
    expect(actorLabel({ users: { approved_by_user_id: { name: 'Pat' } } }, 'approved_by_user_id', null)).toBe('Pat')
    expect(actorLabel({ users: {} }, 'approved_by_user_id', 'General Counsel')).toBe('General Counsel (recorded)')
    expect(actorLabel({}, 'x', null)).toBeNull()
    expect(statusTone('rejected')).toContain('red')
  })

  it('round-trips alternatives', () => {
    const alts = parseAlternatives('Pay — against policy\n\n  Negotiate  ')
    expect(alts).toEqual([
      { option: 'Pay', reason_not_chosen: 'against policy' },
      { option: 'Negotiate', reason_not_chosen: null },
    ])
    expect(formatAlternatives(alts)).toBe('Pay — against policy\nNegotiate')
  })

  it('maps action types to target types', () => {
    expect(defaultTargetType('isolate_host')).toBe('host')
    expect(defaultTargetType('disable_account')).toBe('account')
    expect(defaultTargetType('notify_party')).toBe('external')
    expect(defaultTargetType('patch')).toBe('none')
  })
})

describe('transitionBody', () => {
  const decision = { id: 'd1', status: 'proposed', version: 2 } as Decision
  const action = { id: 'a1', status: 'executed', version: 5, target_state_after: { field: 'containment_status', value: 'isolated' } } as ResponseAction
  const t = (target: TransitionTarget, over: Partial<ReturnType<typeof blankTransitionForm>>) =>
    transitionBody(target, { ...blankTransitionForm(target), ...over })

  it('builds approve bodies (in-app vs external) and validates them', () => {
    const target: TransitionTarget = { kind: 'decision', record: decision, event: 'approve' }
    expect(t(target, {})).toEqual({ body: {} })
    expect(t(target, { external: true })).toEqual({ error: 'Enter who gave the approval.' })
    expect(t(target, { external: true, name: ' GC ', at: '2026-01-01T00:00:00Z' })).toEqual({
      body: { approved_by_name: 'GC', approved_at: '2026-01-01T00:00:00Z' },
    })
  })

  it('requires reasons and verification details', () => {
    expect(t({ kind: 'decision', record: decision, event: 'reject' }, {})).toEqual({ error: 'A reason is required.' })
    const verify: TransitionTarget = { kind: 'action', record: action, event: 'verify' }
    expect(t(verify, {})).toEqual({ error: 'Describe how the action was verified.' })
    expect(t(verify, { method: 'EDR', result: 'partial' })).toEqual({
      body: { verification_result: 'partial', verification_method: 'EDR' },
    })
  })

  it('rolls back restoring the target by default when a state was applied', () => {
    const rollback: TransitionTarget = { kind: 'action', record: action, event: 'rollback' }
    expect(t(rollback, { reason: 'fp' })).toEqual({ body: { reason: 'fp', restore_target_state: true } })
    const execute: TransitionTarget = { kind: 'action', record: { ...action, status: 'authorized' }, event: 'execute' }
    expect(t(execute, { applyState: true })).toEqual({ body: { apply_target_state: true } })
  })
})
