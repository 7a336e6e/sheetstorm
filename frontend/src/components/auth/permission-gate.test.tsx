import { afterEach, describe, expect, it } from '@jest/globals'
import { act, cleanup, render, renderHook, screen } from '@testing-library/react'
import { useAuthStore, type User } from '@/lib/store'
import { PermissionGate, checkPermission, usePermission, usePermissionCheck } from './permission-gate'

function setPermissions(permissions: string[] | undefined) {
  const user: User | null =
    permissions === undefined ? null : { id: 'u1', email: 'a@b.c', name: 'A', roles: [], permissions }
  act(() => {
    useAuthStore.setState({ user })
  })
}

afterEach(() => {
  cleanup()
  setPermissions(undefined)
})

describe('checkPermission', () => {
  it('requires all by default and any with mode=any', () => {
    expect(checkPermission(['a', 'b'], ['a', 'b'])).toBe(true)
    expect(checkPermission(['a'], ['a', 'b'])).toBe(false)
    expect(checkPermission(['a'], ['a', 'b'], 'any')).toBe(true)
    expect(checkPermission(['c'], ['a', 'b'], 'any')).toBe(false)
    expect(checkPermission(['a'], 'a')).toBe(true)
  })

  it('treats an empty requirement as no requirement and no user as no permissions', () => {
    expect(checkPermission(undefined, [])).toBe(true)
    expect(checkPermission(undefined, 'a')).toBe(false)
  })

  it('uses exact matches only', () => {
    expect(checkPermission(['hosts:read'], 'hosts:read_all')).toBe(false)
    expect(checkPermission(['*'], 'hosts:read')).toBe(false)
  })
})

describe('usePermission / usePermissionCheck', () => {
  it('follows the auth store', () => {
    setPermissions(['hosts:create'])
    const { result, rerender } = renderHook(() => usePermission('hosts:create'))
    expect(result.current).toBe(true)
    setPermissions(['hosts:read'])
    rerender()
    expect(result.current).toBe(false)
  })

  it('returns a bound checker', () => {
    setPermissions(['a'])
    const { result } = renderHook(() => usePermissionCheck())
    expect(result.current('a')).toBe(true)
    expect(result.current(['a', 'b'], 'any')).toBe(true)
    expect(result.current(['a', 'b'])).toBe(false)
  })
})

describe('PermissionGate', () => {
  it('renders children only with the permission, else the fallback', () => {
    setPermissions(['tasks:delete'])
    render(
      <>
        <PermissionGate permission="tasks:delete">
          <button>Delete</button>
        </PermissionGate>
        <PermissionGate permission="tasks:create" fallback={<span>read only</span>}>
          <button>Add</button>
        </PermissionGate>
      </>
    )
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Add' })).toBeNull()
    expect(screen.queryByText('read only')).not.toBeNull()
  })

  it('supports mode=any', () => {
    setPermissions(['b'])
    render(
      <PermissionGate permission={['a', 'b']} mode="any">
        <span>shown</span>
      </PermissionGate>
    )
    expect(screen.queryByText('shown')).not.toBeNull()
  })
})
