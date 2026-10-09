/**
 * @jest-environment node
 */
import { beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'

const mockToast = jest.fn()
// Registered before errors.ts is first loaded (dynamic import below), so no hoisting is needed.
jest.mock('@/components/ui/use-toast', () => ({ toast: (...args: unknown[]) => mockToast(...args) }))

let ApiError: typeof import('./api').ApiError
let describeError: typeof import('./errors').describeError
let notifyError: typeof import('./errors').notifyError
let notifySuccess: typeof import('./errors').notifySuccess

beforeAll(async () => {
  ;({ ApiError } = await import('./api'))
  ;({ describeError, notifyError, notifySuccess } = await import('./errors'))
})

beforeEach(() => {
  mockToast.mockClear()
})

const apiErr = (status: number, message = 'server says', code?: string, details?: Record<string, unknown>) =>
  new ApiError(status, message, { code, details })

describe('describeError', () => {
  it.each([
    [0, 'Network error'],
    [401, 'Session expired'],
    [403, 'Permission denied'],
    [404, 'Not found'],
    [429, 'Too many requests'],
    [500, 'Server error'],
    [503, 'Server error'],
  ])('status %i → %s', (status, title) => {
    expect(describeError(apiErr(status)).title).toBe(title)
  })

  it('uses the server message for 400/422/409', () => {
    expect(describeError(apiErr(400, 'Title is required')).description).toBe('Title is required')
    expect(describeError(apiErr(422, 'Bad date')).description).toBe('Bad date')
    expect(describeError(apiErr(409, 'Cannot remove the last admin', 'last_admin')).description).toBe(
      'Cannot remove the last admin'
    )
  })

  it('never shows a 5xx server message', () => {
    expect(describeError(apiErr(500, 'Traceback (most recent call last)')).description).not.toContain(
      'Traceback'
    )
  })

  it('uses fixed copy for 403 and 404', () => {
    expect(describeError(apiErr(403, 'internal detail')).description).toBe("You don't have permission to do that.")
    expect(describeError(apiErr(404)).description).toBe('Not found — it may have been deleted.')
  })

  it('maps already_assigned to its own copy, not the edit-conflict copy', () => {
    const d = describeError(apiErr(409, 'User already assigned with this role', 'already_assigned'))
    expect(d.title).toBe('Already assigned')
    expect(d.description).toBe('User already assigned with this role')
  })

  it('maps user_has_records and names the counts', () => {
    const d = describeError(
      apiErr(409, 'x', 'user_has_records', { counts: { case_notes: 3, timeline_events: 12 }, hint: 'deactivate' })
    )
    expect(d.title).toBe('User has authored records')
    expect(d.description).toBe(
      'This user has authored records (3 case notes, 12 timeline events); deactivate the account instead.'
    )
    expect(describeError(apiErr(409, 'x', 'user_has_records', { counts: {} })).description).toBe(
      'This user has authored records; deactivate the account instead.'
    )
  })

  it('maps ai_blocked_by_tlp to a readable message', () => {
    const d = describeError(apiErr(403, 'x', 'ai_blocked_by_tlp', { tlp: 'red', mode: 'local_only' }))
    expect(d.title).toBe('Blocked by data egress policy')
    expect(d.description).toContain('TLP:RED')
    expect(d.description).toContain('local AI providers')
    const blocked = describeError(apiErr(403, 'x', 'ai_blocked_by_tlp', { tlp: 'amber_strict', mode: 'block' }))
    expect(blocked.description).toContain('TLP:AMBER+STRICT')
  })

  it('maps the optimistic-concurrency conflict', () => {
    expect(describeError(apiErr(409, 'x', 'conflict')).title).toBe('Changed by someone else')
  })

  it('handles plain errors and unknown values', () => {
    expect(describeError(new Error('boom')).description).toBe('boom')
    expect(describeError('weird').title).toBe('Something went wrong')
  })
})

describe('notifyError / notifySuccess', () => {
  it('toasts a destructive "Couldn\'t <action>"', () => {
    notifyError(apiErr(403), 'delete the host')
    expect(mockToast).toHaveBeenCalledWith({
      variant: 'destructive',
      title: "Couldn't delete the host",
      description: "You don't have permission to do that.",
    })
  })

  it('ignores aborts', () => {
    notifyError(Object.assign(new Error('x'), { name: 'AbortError' }), 'load')
    expect(mockToast).not.toHaveBeenCalled()
  })

  it('toasts success', () => {
    notifySuccess('Saved', 'Host updated')
    expect(mockToast).toHaveBeenCalledWith({ title: 'Saved', description: 'Host updated' })
  })
})
