import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'
import { AcknowledgeDialog } from './AcknowledgeDialog'
import { CustodyTimeline, entryDetails } from './CustodyTimeline'
import { VerifyHashDialog } from './VerifyHashDialog'
import { RESPONDER, makeEntry, makeItem } from './test-fixtures'

beforeEach(() => resetTabTest())
afterEach(() => {
  cleanup()
  resetTabTest()
})

const transfer = makeEntry({
  id: 't1',
  seq: 2,
  action: 'transfer',
  transfer_method: 'courier',
  purpose: 'Released to counsel',
  external_party: { name: 'Jane Roe', organization_name: 'Roe LLP' },
  extra_data: { tracking_number: 'TRK-1' },
})

describe('entryDetails', () => {
  it('describes a transfer with party, method, reason and tracking', () => {
    expect(entryDetails(transfer)).toEqual([
      'To Jane Roe (Roe LLP)',
      'Method: Courier',
      'Reason: Released to counsel',
      'Tracking: TRK-1',
    ])
  })

  it('describes check-in, verification, hash and hold entries', () => {
    expect(
      entryDetails(makeEntry({ action: 'check_in', extra_data: { state_after: { storage_location: 'Locker 9' }, seal_intact: false } }))
    ).toEqual(['Stored at Locker 9', 'Seal broken or missing'])
    expect(entryDetails(makeEntry({ action: 'verify', verification_result: 'mismatch', extra_data: { algorithm: 'sha256' } }))).toEqual([
      'SHA-256 does NOT match the recorded value',
    ])
    expect(
      entryDetails(makeEntry({ action: 'add_hash', extra_data: { hash: { algorithm: 'md5', value: 'a'.repeat(32), supersedes: 'b'.repeat(32) } }, purpose: 'typo' }))
    ).toEqual([`MD5 ${'a'.repeat(10)}…${'a'.repeat(6)}`, `Supersedes ${'b'.repeat(10)}…${'b'.repeat(6)}`, 'Reason: typo'])
    expect(entryDetails(makeEntry({ action: 'legal_hold', extra_data: { hold: false } }))).toEqual(['Hold released'])
  })
})

describe('CustodyTimeline', () => {
  it('marks tampered signatures, broken links and legacy rows distinctly', () => {
    setPermissions(RESPONDER)
    render(
      <CustodyTimeline
        entries={[
          makeEntry({ id: 'a', signature_status: 'valid' }),
          makeEntry({ id: 'b', action: 'update', signature_status: 'invalid', link_status: 'entry_hash_mismatch,prev_hash_mismatch' }),
          makeEntry({ id: 'c', action: 'upload', chain_version: null, seq: null, signature_status: 'unsigned_legacy', link_status: 'legacy' }),
        ]}
      />
    )
    const marks = Array.from(document.querySelectorAll('[data-signature]')).map((m) => m.getAttribute('data-signature'))
    expect(marks).toEqual(['valid', 'invalid', 'unsigned_legacy'])
    expect(screen.getByText(/TAMPERED: signature does not match/)).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toMatch(/Chain link not verified: entry hash mismatch, prev hash mismatch/)
  })

  it('shows "awaiting acknowledgment" as a button only to users who can acknowledge', () => {
    const onAcknowledge = jest.fn()
    const { rerender } = render(<CustodyTimeline entries={[transfer]} canAcknowledge onAcknowledge={onAcknowledge} />)
    fireEvent.click(screen.getByRole('button', { name: /awaiting acknowledgment/i }))
    expect(onAcknowledge).toHaveBeenCalledWith(transfer)

    rerender(<CustodyTimeline entries={[transfer]} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('Awaiting acknowledgment')).toBeTruthy()

    rerender(<CustodyTimeline entries={[{ ...transfer, acknowledged_by_entry_id: 'x' }]} canAcknowledge onAcknowledge={onAcknowledge} />)
    expect(screen.queryByText(/awaiting acknowledgment/i)).toBeNull()
  })
})

describe('AcknowledgeDialog', () => {
  it('needs the typed name, then posts the acknowledgment for that entry', async () => {
    setPermissions(RESPONDER)
    const api = mockApi()
    renderTab(<AcknowledgeDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem()} entry={transfer} />)

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
    expect(await screen.findByText(/types their full name/i)).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: 'Jane Roe' } })
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/incidents/i1/evidence/ev1/custody/t1/acknowledge', {
      typed_name: 'Jane Roe',
      statement: undefined,
      stated_at: null,
      receipt_artifact_id: undefined,
    })
  })
})

describe('VerifyHashDialog', () => {
  it('validates the observed hash length and reports the verdict', async () => {
    setPermissions(RESPONDER)
    const api = mockApi()
    api.post.mockResolvedValueOnce({
      verification: { algorithm: 'sha256', expected_hash: 'a'.repeat(64), observed_hash: 'c'.repeat(64), match: false },
    } as never)
    renderTab(<VerifyHashDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem()} />)

    fireEvent.change(screen.getByLabelText(/observed hash/i), { target: { value: 'c'.repeat(10) } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByText(/SHA-256 must be 64 characters \(got 10\)/)).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/observed hash/i), { target: { value: 'C'.repeat(64) } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/incidents/i1/evidence/ev1/verify', {
      algorithm: 'sha256',
      observed_hash: 'c'.repeat(64),
      method: undefined,
      tool: undefined,
      notes: undefined,
    })
    expect(await screen.findByText('Hash mismatch')).toBeTruthy()
  })

  it('offers a recompute of a stored copy only when one exists', async () => {
    setPermissions(RESPONDER)
    const api = mockApi()
    const copy = {
      id: 'a1',
      evidence_item_id: 'ev1',
      original_filename: 'disk.E01',
      file_size: 10,
      storage_type: 'local' as const,
      md5: '',
      sha256: 'a'.repeat(64),
      sha512: '',
      purpose: 'evidence',
      is_verified: false,
      verification_status: 'pending' as const,
      deleted_at: null,
      deletion_reason: null,
      content_purged: false,
      created_at: '2026-01-01T00:00:00Z',
    }
    const { unmount } = renderTab(<VerifyHashDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem()} />)
    expect(screen.queryByRole('radio', { name: 'Recompute stored file' })).toBeNull()
    unmount()

    renderTab(<VerifyHashDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem()} artifacts={[copy, { ...copy, id: 'a2', original_filename: 'gone.bin', deleted_at: '2026-01-02T00:00:00Z' }]} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Recompute stored file' }))
    expect(screen.getAllByRole('option', { name: 'disk.E01' })).toHaveLength(1)
    expect(screen.queryByRole('option', { name: 'gone.bin' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/incidents/i1/evidence/ev1/verify', {
      recompute: true,
      artifact_id: 'a1',
      algorithm: 'sha256',
      notes: undefined,
    })
  })
})
