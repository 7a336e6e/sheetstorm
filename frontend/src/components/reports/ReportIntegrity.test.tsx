import { afterEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ReportIntegrityBadge, shortHash } from './ReportIntegrity'

afterEach(() => cleanup())

const SHA = 'ab12cd34ef56'.repeat(5) + 'abcd'

describe('ReportIntegrityBadge', () => {
  it('snapshot: badge, truncated SHA-256 with the full value in the title, and a copy button', async () => {
    const writeText = jest.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<ReportIntegrityBadge report={{ is_snapshot: true, sha256: SHA, size_bytes: 1000 }} />)

    expect(screen.getByText('Snapshot')).toBeTruthy()
    const code = screen.getByText(/SHA-256 ab12cd34ef56…/)
    expect(code.getAttribute('title')).toBe(SHA)
    fireEvent.click(screen.getByRole('button', { name: 'Copy SHA-256' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHA))
  })

  it('legacy: marked as re-rendered, no hash', () => {
    render(<ReportIntegrityBadge report={{ is_snapshot: false, sha256: null }} />)
    expect(screen.getByText('Legacy (re-rendered)')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Copy SHA-256' })).toBeNull()
  })

  it('a row without snapshot fields (older API) is legacy too', () => {
    render(<ReportIntegrityBadge report={{}} />)
    expect(screen.getByText('Legacy (re-rendered)')).toBeTruthy()
  })

  it('shortHash keeps short values whole', () => {
    expect(shortHash('abc')).toBe('abc')
    expect(shortHash(SHA, 8)).toBe('ab12cd34…')
  })
})
