import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { ApiError } from '@/lib/api'
import { provenanceApi } from '@/lib/endpoints/provenance'
import { useAuthStore } from '@/lib/store'
import { clearCache } from '@/lib/query-cache'
import type { ProvenanceFormValue } from '@/types'
import { ProvenanceSection, PREVIEW_DEBOUNCE_MS } from './ProvenanceSection'
import { emptyProvenance } from './provenance-form'

const previewSpy = () => jest.spyOn(provenanceApi, 'normalizePreview')

function Harness({
  initial = emptyProvenance(),
  timestamp = null,
  onUseComputed,
  hostId = null,
  onValue,
}: {
  initial?: ProvenanceFormValue
  timestamp?: string | null
  onUseComputed?: (utc: string) => void
  hostId?: string | null
  onValue?: (v: ProvenanceFormValue) => void
}) {
  const [value, setValue] = useState(initial)
  return (
    <ProvenanceSection
      incidentId="i1"
      value={value}
      onChange={(v) => {
        setValue(v)
        onValue?.(v)
      }}
      timestamp={timestamp}
      onUseComputed={onUseComputed}
      hostId={hostId}
    />
  )
}

beforeEach(() => {
  jest.useFakeTimers()
  clearCache()
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x.test', name: 'U', roles: [], permissions: ['artifacts:read', 'timeline:create'] },
    } as never)
  })
})
afterEach(() => {
  cleanup()
  jest.useRealTimers()
  jest.restoreAllMocks()
  act(() => useAuthStore.setState({ user: null } as never))
})

const flush = async (ms = PREVIEW_DEBOUNCE_MS + 10) => {
  await act(async () => {
    jest.advanceTimersByTime(ms)
  })
}

describe('ProvenanceSection', () => {
  it('is collapsed and empty until opened', () => {
    render(<Harness />)
    const toggle = screen.getByRole('button', { name: /provenance/i })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByLabelText('Raw timestamp')).toBeNull()
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByLabelText('Raw timestamp')).toBeTruthy()
  })

  it('starts expanded when the record already has provenance', () => {
    render(<Harness initial={{ ...emptyProvenance(), source_record_ref: 'a.evtx#1' }} />)
    expect(screen.getByDisplayValue('a.evtx#1')).toBeTruthy()
  })

  it('debounces the normalize preview and shows the UTC value and skew', async () => {
    const spy = previewSpy().mockResolvedValue({
      utc: '2026-10-01T12:00:00+00:00', skew_applied: 300, timezone_used: 'Europe/Berlin', offset_seconds: 7200,
    })
    render(<Harness initial={{ ...emptyProvenance(), source_record_ref: 'x' }} hostId="h1" />)
    const raw = screen.getByLabelText('Raw timestamp')
    fireEvent.change(raw, { target: { value: '2026-10-01 1' } })
    fireEvent.change(raw, { target: { value: '2026-10-01 14:05:00' } })
    fireEvent.change(screen.getByLabelText('Source time zone'), { target: { value: 'Europe/Berlin' } })

    await flush(PREVIEW_DEBOUNCE_MS - 50)
    expect(spy).not.toHaveBeenCalled()
    await flush(100)
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith(
      'i1',
      { raw_timestamp: '2026-10-01 14:05:00', source_timezone: 'Europe/Berlin', host_id: 'h1' },
      expect.objectContaining({ signal: expect.anything() }),
    )
    const box = screen.getByTestId('provenance-preview')
    expect(box.textContent).toContain('2026-10-01 12:00:00Z')
    expect(box.textContent).toContain('Europe/Berlin')
    expect(box.textContent).toContain('+5m 0s')
  })

  it('"Use computed" fills the timestamp when it differs, and can keep a manual one', async () => {
    previewSpy().mockResolvedValue({
      utc: '2026-10-01T12:00:00+00:00', skew_applied: 0, timezone_used: 'UTC', offset_seconds: 0,
    })
    const onUse = jest.fn()
    const seen: ProvenanceFormValue[] = []
    render(
      <Harness
        initial={{ ...emptyProvenance(), raw_timestamp: '2026-10-01 12:00', source_timezone: 'UTC' }}
        timestamp="2026-10-01T13:00:00.000Z"
        onUseComputed={onUse}
        onValue={(v) => seen.push(v)}
      />,
    )
    await flush()
    expect(screen.getByText(/differs from the computed value/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Use computed' }))
    expect(onUse).toHaveBeenCalledWith('2026-10-01T12:00:00+00:00')

    fireEvent.click(screen.getByLabelText(/Keep my timestamp/))
    expect(seen[seen.length - 1].keep_manual).toBe(true)
  })

  it('shows no mismatch notice when the timestamp agrees', async () => {
    previewSpy().mockResolvedValue({
      utc: '2026-10-01T12:00:00+00:00', skew_applied: 0, timezone_used: 'UTC', offset_seconds: 0,
    })
    render(
      <Harness
        initial={{ ...emptyProvenance(), raw_timestamp: '2026-10-01 12:00', source_timezone: 'UTC' }}
        timestamp="2026-10-01T12:00:00.000Z"
      />,
    )
    await flush()
    expect(screen.getByTestId('provenance-preview').textContent).toContain('2026-10-01 12:00:00Z')
    expect(screen.queryByText(/differs from the computed value/)).toBeNull()
  })

  it('shows the server message, and a fold chooser for an ambiguous local time', async () => {
    previewSpy().mockRejectedValue(
      new ApiError(400, 'is ambiguous in Europe/Berlin (daylight-saving fold)', { code: 'ambiguous_local_time' }),
    )
    const seen: ProvenanceFormValue[] = []
    render(
      <Harness
        initial={{ ...emptyProvenance(), raw_timestamp: '2026-10-25 02:30:00', source_timezone: 'Europe/Berlin' }}
        onValue={(v) => seen.push(v)}
      />,
    )
    await flush()
    expect(screen.getByText(/is ambiguous in Europe\/Berlin/)).toBeTruthy()
    expect(screen.getByText('This local time happens twice')).toBeTruthy()
    expect(screen.getByRole('combobox', { name: 'Which occurrence' })).toBeTruthy()
  })

  it('makes no request without a raw timestamp', async () => {
    const spy = previewSpy().mockResolvedValue({
      utc: 'x', skew_applied: 0, timezone_used: 'UTC', offset_seconds: 0,
    })
    render(<Harness initial={{ ...emptyProvenance(), source_record_ref: 'x' }} />)
    await flush(2000)
    expect(spy).not.toHaveBeenCalled()
    expect(screen.queryByTestId('provenance-preview')).toBeNull()
  })

  it('hides the evidence picker for users without access to the register', () => {
    act(() => {
      useAuthStore.setState({
        user: { id: 'u1', email: 'u@x.test', name: 'U', roles: [], permissions: ['timeline:create'] },
      } as never)
    })
    render(<Harness initial={{ ...emptyProvenance(), source_record_ref: 'x' }} />)
    expect(screen.queryByRole('combobox', { name: 'Source evidence item' })).toBeNull()
    expect(screen.getByText(/access to the evidence register/)).toBeTruthy()
  })
})
