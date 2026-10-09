import { afterEach, describe, expect, it } from '@jest/globals'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ProvenanceLevel } from '@/types'
import { ProvenanceBadge } from './ProvenanceBadge'
import { ProvenanceDetails } from './ProvenanceDetails'

afterEach(cleanup)

describe('ProvenanceBadge', () => {
  const levels: [ProvenanceLevel, string][] = [
    ['none', 'No provenance'],
    ['partial', 'Partial provenance'],
    ['full', 'Full provenance'],
    ['verified', 'Verified provenance'],
  ]
  it.each(levels)('labels the %s level', (level, label) => {
    render(<ProvenanceBadge record={{ provenance_level: level }} />)
    expect(screen.getByRole('button', { name: label })).toBeTruthy()
  })

  it('defaults to none for legacy rows without the field', () => {
    render(<ProvenanceBadge record={{}} />)
    expect(screen.getByRole('button', { name: 'No provenance' })).toBeTruthy()
  })

  it('lists the known provenance in the tooltip, as text', async () => {
    render(
      <ProvenanceBadge
        record={{
          provenance_level: 'verified',
          source_evidence_id: 'ev1',
          source_record_type: 'url',
          source_record_ref: 'javascript:alert(1)',
          raw_timestamp: '2026-10-01 14:05:00',
          source_timezone: 'Europe/Berlin',
          timestamp_derivation: 'computed',
          clock_skew_applied_seconds: 300,
          extraction_tool: 'EvtxECmd',
          extraction_tool_version: '1.5',
          provenance_verifier: { id: 'u2', name: 'Dana' },
          provenance_verified_at: '2026-10-02T08:00:00Z',
        }}
      />,
    )
    fireEvent.focus(screen.getByRole('button', { name: 'Verified provenance' }))
    const tip = (await screen.findAllByText(/javascript:alert\(1\)/))[0]
    expect(tip.closest('a')).toBeNull() // never a link
    expect((await screen.findAllByText(/host skew \+5m 0s removed/))[0]).toBeTruthy()
    expect((await screen.findAllByText(/EvtxECmd 1.5/))[0]).toBeTruthy()
    expect((await screen.findAllByText(/Dana/))[0]).toBeTruthy()
  })
})

describe('ProvenanceDetails', () => {
  it('renders the record reference as plain text', () => {
    const { container } = render(
      <ProvenanceDetails
        record={{
          provenance_level: 'full',
          source_record_type: 'url',
          source_record_ref: 'https://evil.example/x',
          raw_timestamp: '2026-10-01 14:05:00',
          source_timezone: 'UTC',
          timestamp_type: 'logged',
        }}
      />,
    )
    expect(screen.getByText(/Full provenance/)).toBeTruthy()
    expect(screen.getByText(/https:\/\/evil.example\/x/)).toBeTruthy()
    expect(container.querySelector('a')).toBeNull()
    expect(screen.getByText(/Logged/)).toBeTruthy()
  })
})
