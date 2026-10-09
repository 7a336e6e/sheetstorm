import { afterEach, beforeEach, describe, expect, it } from '@jest/globals'
import { fireEvent, render, screen } from '@testing-library/react'
import { mockApi, resetTabTest, setPermissions } from '../test-utils'
import { ResponseTimelineToggle } from './ResponseTimelineToggle'

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('ResponseTimelineToggle', () => {
  it('is hidden without decisions/response-actions read access', () => {
    setPermissions(['timeline:read'])
    mockApi()
    render(<ResponseTimelineToggle incidentId="i1" />)
    expect(screen.queryByRole('button', { name: /response actions/i })).toBeNull()
  })

  it('loads the virtual rows only when switched on', async () => {
    setPermissions(['timeline:read', 'response_actions:read'])
    const spies = mockApi({
      '/incidents/i1/response-timeline': {
        items: [{ kind: 'response', id: 'a1', display_id: 'A-001', timestamp: '2026-01-01T00:00:00Z',
                  activity: 'isolate_host WS-01', title: 'Isolate WS-01', status: 'executed' }],
      },
    })
    render(<ResponseTimelineToggle incidentId="i1" />)
    expect(spies.get).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /show response actions/i }))
    expect(await screen.findByText('A-001')).toBeInTheDocument()
    expect(screen.getByText(/Isolate WS-01/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /hide response actions/i })).toHaveAttribute('aria-pressed', 'true')
  })
})
