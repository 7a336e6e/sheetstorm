import { describe, expect, it } from '@jest/globals'
import { render, screen } from '@testing-library/react'
import { AuditLogDetail, actionLabel, humanize } from './AuditLogDetail'

describe('audit action labels', () => {
  it('labels custody chain verification (evidence item opened) readably, with its result', () => {
    expect(actionLabel('custody_chain_verified')).toBe('Custody chain verified')
    expect(actionLabel('custody_chain_verified', { status: 'ok' })).toBe('Custody chain verified (ok)')
    expect(actionLabel('custody_chain_verified', { status: 'broken' })).toBe('Custody chain verified (broken)')
  })

  it('falls back to a humanized action', () => {
    expect(actionLabel('update_role')).toBe('Update Role')
    expect(humanize('evidence_item')).toBe('Evidence Item')
  })

  it('renders the label and the raw action in the detail panel', () => {
    render(
      <AuditLogDetail
        log={{
          id: 'l1',
          event_type: 'security_event',
          action: 'custody_chain_verified',
          resource_type: 'evidence_item',
          created_at: '2026-10-09T08:00:00+00:00',
          details: { status: 'compromised', break_count: 1 },
        }}
      />
    )
    expect(screen.getByText('Custody chain verified (compromised)')).toBeInTheDocument()
    expect(screen.getByText('(custody_chain_verified)')).toBeInTheDocument()
    expect(screen.getByText('Evidence Item')).toBeInTheDocument()
  })
})
