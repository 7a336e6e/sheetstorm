/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import { ApiError } from '@/lib/api'
import { describeError } from '@/lib/errors'
import {
  canGrant,
  groupCatalog,
  isAdminCore,
  missingPermissions,
  permissionsFromError,
  withImplied,
} from './rbac'
import type { PermissionCatalog } from '@/types'

const perm = (key: string, group: string, extra: Partial<PermissionCatalog['items'][number]> = {}) => ({
  key,
  group,
  label: key,
  description: '',
  dangerous: false,
  privileged: false,
  api_key_grantable: true,
  platform_only: false,
  ...extra,
})

describe('grant ceiling helpers', () => {
  it('expands implied permissions like the backend', () => {
    expect(Array.from(withImplied(['incidents:read_all'])).sort()).toEqual([
      'incidents:read_all',
      'incidents:read_team',
      'incidents:read_tlp_white',
    ])
  })

  it('lists what the caller lacks and allows subsets only', () => {
    const caller = ['incidents:read', 'incidents:read_all', 'users:read']
    expect(missingPermissions(['users:manage', 'incidents:read_team', 'users:manage'], caller)).toEqual(['users:manage'])
    expect(canGrant(caller, ['incidents:read', 'incidents:read_tlp_white'])).toBe(true)
    expect(canGrant(caller, ['roles:manage'])).toBe(false)
    expect(canGrant(undefined, [])).toBe(true)
  })

  it('detects the admin core', () => {
    expect(isAdminCore(['users:manage', 'roles:manage', 'x:y'])).toBe(true)
    expect(isAdminCore(['users:manage'])).toBe(false)
  })
})

describe('groupCatalog', () => {
  it('keeps the server group order and appends unknown groups', () => {
    const catalog: PermissionCatalog = {
      groups: [
        { key: 'incidents', label: 'Incidents' },
        { key: 'users', label: 'Users' },
        { key: 'empty', label: 'Empty' },
      ],
      items: [perm('users:read', 'users'), perm('incidents:read', 'incidents'), perm('x:y', 'other')],
    }
    expect(groupCatalog(catalog).map((g) => [g.key, g.items.map((p) => p.key)])).toEqual([
      ['incidents', ['incidents:read']],
      ['users', ['users:read']],
      ['other', ['x:y']],
    ])
    expect(groupCatalog(null)).toEqual([])
  })
})

describe('guard errors', () => {
  it('extracts missing / platform_only / unknown keys', () => {
    const err = new ApiError(403, "You cannot grant permissions you don't hold", {
      code: 'privilege_escalation',
      details: { error: 'privilege_escalation', missing: ['users:manage'], platform_only: ['system:manage'] },
    })
    expect(permissionsFromError(err)).toEqual(['users:manage', 'system:manage'])
    expect(permissionsFromError(new Error('x'))).toEqual([])
  })

  it.each([
    ['privilege_escalation', 403, { missing: ['roles:manage'] }, 'Exceeds your permissions', /Missing: roles:manage/],
    ['insufficient_privilege', 403, { missing: ['users:manage'] }, 'Insufficient privilege', /This user holds permissions/],
    ['last_admin', 409, {}, 'Last administrator', /Server says no/],
    ['self_lockout', 409, {}, 'Would lock you out', /Server says no/],
    ['self_action', 400, { action: 'disable' }, 'Not allowed on your own account', /Server says no/],
    ['use_change_password', 400, {}, 'Use Change password', /current password/],
    ['unknown_permissions', 400, { unknown: ['incidents:nuke'] }, 'Unknown permissions', /incidents:nuke/],
  ])('describes %s', (code, status, extra, title, description) => {
    const message =
      code === 'insufficient_privilege'
        ? 'This user holds permissions you do not have'
        : code === 'privilege_escalation' || code === 'unknown_permissions'
          ? 'Refused'
          : 'Server says no'
    const err = new ApiError(status, message, { code, details: { error: code, message, ...extra } })
    const out = describeError(err)
    expect(out.title).toBe(title)
    expect(out.description).toMatch(description)
  })

  it('names platform-only refusals', () => {
    const err = new ApiError(403, 'Platform-only permissions cannot be granted in this organization', {
      code: 'privilege_escalation',
      details: { missing: [], platform_only: ['system:manage'] },
    })
    expect(describeError(err)).toEqual({
      title: 'Platform-only permission',
      description: 'Platform-only permissions cannot be granted in this organization (system:manage)',
    })
  })

  it('maps ai_blocked_by_tlp to the egress policy copy', () => {
    const err = new ApiError(403, 'x', { code: 'ai_blocked_by_tlp', details: { tlp: 'red', mode: 'block' } })
    expect(describeError(err).title).toBe('Blocked by data egress policy')
    expect(describeError(err).description).toContain('TLP:RED')
  })
})
