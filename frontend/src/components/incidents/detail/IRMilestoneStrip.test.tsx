import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { ApiError } from '@/lib/api'
import type { Incident } from '@/types'
import { mockApi, renderTab, resetTabTest, setRole } from '../test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let IRMilestoneStrip: typeof import('./IRMilestoneStrip').IRMilestoneStrip
let EDIT_LIFECYCLE_EVENT: string
beforeAll(async () => {
  ;({ IRMilestoneStrip, EDIT_LIFECYCLE_EVENT } = await import('./IRMilestoneStrip'))
})

const incident = {
  id: 'i1',
  incident_number: 7,
  title: 'Ransomware at HQ',
  severity: 'high',
  status: 'contained',
  phase: 3,
  phase_name: 'Containment',
  tlp: 'amber',
  created_at: '2026-01-01T00:00:00Z',
  detected_at: '2026-01-03T00:00:00Z',
  contained_at: '2026-01-04T12:00:00Z',
  version: 5,
} as Incident & { version: number }

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement

describe('IRMilestoneStrip', () => {
  it('shows each step with its delta and the dwell time', () => {
    setRole('viewer')
    mockApi()
    renderTab(<IRMilestoneStrip incident={incident} firstActivity="2026-01-01T00:00:00Z" onSaved={() => {}} />)
    expect(screen.getByTestId('milestone-detected_at').textContent).toContain('Dwell 2d')
    expect(screen.getByTestId('milestone-contained_at').textContent).toContain('+1d 12h')
    expect(screen.getByTestId('milestone-closed_at').textContent).toContain('—')
  })

  it('hides Edit from users without incidents:update', () => {
    setRole('viewer')
    mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    expect(screen.queryByRole('button', { name: /edit milestones/i })).toBeNull()
  })

  it('blocks an out-of-order edit client-side without calling the API', async () => {
    setRole('responder')
    const api = mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /edit milestones/i }))
    fireEvent.change(input('Eradicated'), { target: { value: '2026-01-02T00:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /save milestones/i }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/must not be after Eradicated/)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('blocks a future value client-side', async () => {
    setRole('responder')
    const api = mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /edit milestones/i }))
    fireEvent.change(input('Closed'), { target: { value: '2099-01-01T00:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /save milestones/i }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/future/)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('PUTs only the changed milestones with If-Match', async () => {
    setRole('responder')
    const api = mockApi()
    const onSaved = jest.fn()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={onSaved} />)
    fireEvent.click(screen.getByRole('button', { name: /edit milestones/i }))
    fireEvent.change(input('Eradicated'), { target: { value: '2026-01-05T00:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /save milestones/i }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1', { eradicated_at: '2026-01-05T00:00:00.000Z' }, { ifMatch: 5 })
    )
    expect(onSaved).toHaveBeenCalled()
  })

  it('shows the server 400 inline with readable labels', async () => {
    setRole('responder')
    const api = mockApi()
    api.put.mockImplementation((async () => {
      throw new ApiError(400, 'detected_at must not be after recovered_at', {
        code: 'invalid_milestones',
        details: { error: 'invalid_milestones', field: 'recovered_at', pair: ['detected_at', 'recovered_at'] },
      })
    }) as never)
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /edit milestones/i }))
    fireEvent.change(input('Recovered'), { target: { value: '2026-01-06T00:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /save milestones/i }))
    expect((await screen.findByRole('alert')).textContent).toBe('Detected must not be after Recovered.')
  })

  it('shows First malicious and Responded steps and puts dwell on the step into Detected', () => {
    setRole('viewer')
    mockApi()
    const withNew = { ...incident, first_malicious_at: '2026-01-02T00:00:00Z', responded_at: '2026-01-03T06:00:00Z' }
    renderTab(<IRMilestoneStrip incident={withNew} firstActivity="2026-01-01T00:00:00Z" onSaved={() => {}} />)
    expect(screen.getByTestId('milestone-first_malicious_at').textContent).toContain('First malicious activity')
    expect(screen.getByTestId('milestone-first_malicious_at').textContent).toContain('+1d')
    expect(screen.getByTestId('milestone-detected_at').textContent).toContain('Dwell 1d')
    expect(screen.getByTestId('milestone-responded_at').textContent).toContain('+6h')
    expect(screen.getByTestId('milestone-contained_at').textContent).toContain('+1d 6h')
  })

  it('edits the two new fields in the same dialog and PUTs only what changed', async () => {
    setRole('responder')
    const api = mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /edit milestones/i }))
    fireEvent.change(input('First malicious activity'), { target: { value: '2026-01-02T00:00:00' } })
    fireEvent.change(input('Responded'), { target: { value: '2026-01-03T01:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /save milestones/i }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(
        '/incidents/i1',
        { first_malicious_at: '2026-01-02T00:00:00.000Z', responded_at: '2026-01-03T01:00:00.000Z' },
        { ifMatch: 5 }
      )
    )
  })

  it('blocks a responded time before the detected time', async () => {
    setRole('responder')
    const api = mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /edit milestones/i }))
    fireEvent.change(input('Responded'), { target: { value: '2026-01-02T00:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /save milestones/i }))
    expect((await screen.findByRole('alert')).textContent).toBe('Detected must not be after Responded.')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('opens the editor when the metrics card asks for it (editors only)', async () => {
    setRole('responder')
    mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => {
      window.dispatchEvent(new Event(EDIT_LIFECYCLE_EVENT))
    })
    expect(await screen.findByRole('dialog', { name: /edit ir milestones/i })).toBeInTheDocument()
  })

  it('ignores that request for a viewer', () => {
    setRole('viewer')
    mockApi()
    renderTab(<IRMilestoneStrip incident={incident} onSaved={() => {}} />)
    act(() => {
      window.dispatchEvent(new Event(EDIT_LIFECYCLE_EVENT))
    })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
