import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { provenanceApi } from '@/lib/endpoints/provenance'
import type { CompromisedHost } from '@/types'
import { ClockSkewEditor } from './ClockSkewEditor'

const host = (over: Record<string, unknown> = {}) =>
  ({
    id: 'h1', incident_id: 'i1', hostname: 'WS-01', containment_status: 'active', created_at: '2026-10-01T00:00:00Z',
    version: 4, clock_skew_seconds: null, clock_skew_basis: null, timezone: null, ...over,
  }) as CompromisedHost & { version: number }

beforeEach(() => {
  jest.useFakeTimers()
})
afterEach(() => {
  cleanup()
  jest.useRealTimers()
  jest.restoreAllMocks()
})

const renderEditor = (h = host(), onSaved = jest.fn()) =>
  render(<ClockSkewEditor incidentId="i1" host={h} open onOpenChange={() => {}} onSaved={onSaved} />)

describe('ClockSkewEditor', () => {
  it('saves the signed offset with its basis and time zone, using the row version', async () => {
    const spy = jest.spyOn(provenanceApi, 'setClockSkew').mockResolvedValue(host({ version: 5, clock_skew_seconds: -90 }))
    const onSaved = jest.fn()
    renderEditor(host(), onSaved)

    fireEvent.change(screen.getByLabelText('Minutes'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Seconds'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('combobox', { name: 'Direction' }))
    fireEvent.click(await screen.findByRole('option', { name: /Host behind/ }))
    expect(screen.getByText(/Skew: -1m 30s \(-90 seconds\)/)).toBeTruthy()

    const save = screen.getByRole('button', { name: 'Save skew' })
    expect((save as HTMLButtonElement).disabled).toBe(true) // basis required for a non-zero skew
    fireEvent.change(screen.getByLabelText(/Basis/), { target: { value: 'compared against the DC at triage' } })
    fireEvent.change(screen.getByLabelText('Host time zone'), { target: { value: 'Europe/Berlin' } })
    fireEvent.click(save)

    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(spy).toHaveBeenCalledWith(
      'i1', 'h1',
      { clock_skew_seconds: -90, clock_skew_basis: 'compared against the DC at triage', timezone: 'Europe/Berlin' },
      4,
    )
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('rejects out-of-range input before calling the server', () => {
    const spy = jest.spyOn(provenanceApi, 'setClockSkew')
    renderEditor()
    fireEvent.change(screen.getByLabelText('Hours'), { target: { value: '170' } }) // > 7 days
    expect(screen.getByText(/at most ±604800 seconds/)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Save skew' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Hours'), { target: { value: '1.5' } })
    expect((screen.getByRole('button', { name: 'Save skew' }) as HTMLButtonElement).disabled).toBe(true)
    expect(spy).not.toHaveBeenCalled()
  })

  it('previews the re-normalization (dry run) and applies it with the saved version', async () => {
    const reapply = jest.spyOn(provenanceApi, 'reapplyClockSkew')
    reapply.mockResolvedValueOnce({
      dry_run: true, count: 2, truncated: false,
      changes: [
        { kind: 'timeline_event', id: 'e1', field: 'timestamp', old: '2026-10-01T12:00:00+00:00', new: '2026-10-01T12:03:20+00:00', old_skew: 300, new_skew: 100 },
        { kind: 'host_ioc', id: 'x1', field: 'datetime', old: '2026-10-01T12:00:00+00:00', new: '2026-10-01T12:03:20+00:00', old_skew: 300, new_skew: 100 },
      ],
    })
    reapply.mockResolvedValueOnce({ dry_run: false, count: 2, truncated: false, changes: [] })
    const onSaved = jest.fn()
    renderEditor(host({ clock_skew_seconds: 100, clock_skew_basis: 'ntp' }), onSaved)

    fireEvent.click(screen.getByRole('button', { name: 'Preview changes' }))
    expect(await screen.findByText('2 records would change.')).toBeTruthy()
    expect(reapply).toHaveBeenLastCalledWith('i1', 'h1', true)
    expect(screen.getAllByText('2026-10-01 12:03:20Z').length).toBe(2)

    fireEvent.click(screen.getByRole('button', { name: 'Re-normalize 2 records' }))
    await waitFor(() => expect(reapply).toHaveBeenCalledTimes(2))
    expect(reapply).toHaveBeenLastCalledWith('i1', 'h1', false, 4)
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    await act(async () => {})
  })

  it('says so when nothing needs re-normalizing', async () => {
    jest.spyOn(provenanceApi, 'reapplyClockSkew').mockResolvedValue({ dry_run: true, count: 0, changes: [], truncated: false })
    renderEditor()
    fireEvent.click(screen.getByRole('button', { name: 'Preview changes' }))
    expect(await screen.findByText('No records need re-normalizing.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^Re-normalize \d/ })).toBeNull()
  })
})
