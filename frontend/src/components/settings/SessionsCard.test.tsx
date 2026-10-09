import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api from '@/lib/api'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { UserSession } from '@/types'
import { describeUserAgent } from '@/lib/endpoints/security'
import { SessionsCard } from './SessionsCard'

const FIREFOX = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:131.0) Gecko/20100101 Firefox/131.0'
const CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'

function session(id: string, ua: string, current = false): UserSession {
  return {
    id,
    user_id: 'u1',
    ip_address: current ? '10.0.0.1' : '203.0.113.9',
    user_agent: ua,
    auth_method: 'password',
    created_at: '2026-10-01T10:00:00Z',
    last_seen_at: '2026-10-09T10:00:00Z',
    expires_at: '2026-10-16T10:00:00Z',
    revoked_at: null,
    current,
  }
}

let items: UserSession[]
let deleteSpy: jest.Mock<(endpoint: string) => Promise<unknown>>

beforeEach(() => {
  items = [session('s-current', FIREFOX, true), session('s-other', CHROME)]
  jest.spyOn(api, 'get').mockImplementation((async () => ({
    items, total: items.length, page: 1, per_page: 100, pages: 1,
  })) as unknown as typeof api.get)
  deleteSpy = jest.fn<(endpoint: string) => Promise<unknown>>(async (endpoint: string) => {
    if (endpoint.includes('except_current')) {
      items = items.filter((s) => s.current)
      return { id: 'u1', revoked: 1 }
    }
    items = items.filter((s) => !endpoint.endsWith(s.id))
    return { id: 's-other', revoked: true }
  })
  jest.spyOn(api, 'delete').mockImplementation(deleteSpy as unknown as typeof api.delete)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
})

function renderCard(self = true) {
  return render(
    <ConfirmDialogProvider>
      <SessionsCard userId="u1" self={self} userLabel="Alice" />
    </ConfirmDialogProvider>
  )
}

async function confirmIn(name: string) {
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name }))
}

describe('SessionsCard', () => {
  it('lists sessions with the current one marked', async () => {
    renderCard()
    const list = await screen.findByRole('list', { name: 'Active sessions' })
    expect(within(list).getByText('Firefox on macOS')).toBeInTheDocument()
    expect(within(list).getByText('Chrome on Windows')).toBeInTheDocument()
    expect(within(list).getAllByText('This session')).toHaveLength(1)
  })

  it('revokes another session after confirmation', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke session Chrome on Windows' }))
    await confirmIn('Revoke')
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith('/users/u1/sessions/s-other'))
    await waitFor(() => expect(screen.queryByText('Chrome on Windows')).toBeNull())
  })

  it('signs out other devices but keeps the current session', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out other devices' }))
    await confirmIn('Sign out others')
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith('/users/u1/sessions?except_current=true'))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Sign out other devices' })).toBeNull())
    expect(screen.getByText('Firefox on macOS')).toBeInTheDocument()
  })

  it('admin view revokes every session of the user', async () => {
    renderCard(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke all sessions' }))
    await confirmIn('Revoke all')
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith('/users/u1/sessions'))
  })

  it('cancelling the confirmation does nothing', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke session Chrome on Windows' }))
    await confirmIn('Cancel')
    await act(async () => {})
    expect(deleteSpy).not.toHaveBeenCalled()
  })
})

describe('describeUserAgent', () => {
  it('summarises common agents', () => {
    expect(describeUserAgent(FIREFOX)).toBe('Firefox on macOS')
    expect(describeUserAgent(CHROME)).toBe('Chrome on Windows')
    expect(describeUserAgent('python-httpx/0.27')).toBe('Script')
    expect(describeUserAgent(null)).toBe('Unknown device')
  })
})
