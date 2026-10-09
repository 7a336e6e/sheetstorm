import { afterEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CHAIN_BADGE_STYLES, ChainStatusBadge, type ChainBadgeStatus } from './ChainStatusBadge'

afterEach(cleanup)

const CASES: Array<[ChainBadgeStatus, string, string]> = [
  ['intact', 'Chain verified', 'Verified'],
  ['intact_with_unsigned_legacy', 'Verified, legacy entries unsigned', 'Verified (legacy)'],
  ['unverifiable', 'Cannot verify (signing key changed)', 'Unverifiable'],
  ['broken', 'Chain broken', 'Broken'],
  ['compromised', 'Tampering detected', 'Tampered'],
  ['checking', 'Verifying chain…', 'Verifying…'],
  ['error', 'Could not verify chain', 'Verify failed'],
  ['unknown', 'Chain not verified yet', 'Not verified'],
]

describe('ChainStatusBadge', () => {
  it.each(CASES)('renders %s with its own wording', (status, label, short) => {
    const { unmount } = render(<ChainStatusBadge status={status} />)
    const badge = screen.getByRole('status')
    expect(badge.getAttribute('data-status')).toBe(status)
    expect(badge.getAttribute('aria-label')).toBe(label)
    expect(badge.textContent).toBe(label)
    unmount()

    render(<ChainStatusBadge status={status} compact />)
    expect(screen.getByRole('status').textContent).toBe(short)
  })

  it('covers every status the API can return', () => {
    // Backend CustodyLedger.verify: intact | intact_with_unsigned_legacy | unverifiable | broken | compromised
    const api: ChainBadgeStatus[] = ['intact', 'intact_with_unsigned_legacy', 'unverifiable', 'broken', 'compromised']
    api.forEach((s) => expect(CHAIN_BADGE_STYLES[s]).toBeDefined())
  })

  it('distinguishes bad states by more than colour (distinct icon-bearing wording)', () => {
    const labels = new Set(CASES.map(([, label]) => label))
    expect(labels.size).toBe(CASES.length)
    expect(CHAIN_BADGE_STYLES.broken.variant).toBe('destructive')
    expect(CHAIN_BADGE_STYLES.compromised.variant).toBe('destructive')
    expect(CHAIN_BADGE_STYLES.intact.variant).toBe('success')
  })

  it('shows the detail in the tooltip', () => {
    render(<ChainStatusBadge status="intact" detail="Head entry #12" />)
    expect(screen.getByRole('status').getAttribute('title')).toBe('Chain verified. Head entry #12')
  })

  it('becomes a button that re-verifies when clickable', () => {
    const onClick = jest.fn()
    render(<ChainStatusBadge status="broken" onClick={onClick} />)
    const button = screen.getByRole('button', { name: /chain broken\. click to verify again/i })
    expect(button.getAttribute('data-status')).toBe('broken')
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('falls back to "not verified" for an unexpected status value', () => {
    render(<ChainStatusBadge status={'surprise' as ChainBadgeStatus} />)
    expect(screen.getByRole('status').textContent).toBe('Chain not verified yet')
  })
})
