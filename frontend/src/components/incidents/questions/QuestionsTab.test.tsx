import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { envelope, mockApi, renderTab, resetTabTest, setRole } from '../test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let QuestionsTab: typeof import('./QuestionsTab').QuestionsTab
beforeAll(async () => {
  ;({ QuestionsTab } = await import('./QuestionsTab'))
})

const q = {
  id: 'q1',
  incident_id: 'i1',
  question: 'How did the attacker get in?',
  status: 'open',
  priority: 'high',
  evidence_refs: [],
  source: 'core',
  order_index: 0,
  is_archived: false,
  lead_ids: [],
  created_at: '2026-10-01T00:00:00Z',
  version: 4,
}
const summary = {
  total: 2, open: 1, in_progress: 0, answered: 1, unanswerable: 0, resolved: 1, progress: 0.5,
  open_high_priority: 1, top_open: [],
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('QuestionsTab', () => {
  it('Viewer sees questions and progress but no mutation controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/questions': envelope([q], { summary }) })
    renderTab(<QuestionsTab incidentId="i1" />)
    expect(await screen.findByText('How did the attacker get in?')).toBeTruthy()
    expect(await screen.findByText('1/2 answered')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /from library/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /apply template/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /add question/i })).toBeNull()
  })

  it('responder answers a question with If-Match; answered needs a confidence', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/questions': envelope([q], { summary }) })
    renderTab(<QuestionsTab incidentId="i1" />)
    expect(await screen.findByRole('button', { name: /from library/i })).toBeTruthy()
    fireEvent.click(await screen.findByText('How did the attacker get in?'))

    // Status: answered, with an answer but no confidence yet → blocked.
    fireEvent.click(await screen.findByRole('combobox', { name: 'Status' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Answered' }))
    fireEvent.change(screen.getByLabelText('Answer'), { target: { value: 'Phishing email with a macro.' } })
    expect((await screen.findByRole('alert')).textContent).toMatch(/confidence/)
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(screen.getByRole('combobox', { name: 'Confidence' }))
    fireEvent.click(await screen.findByRole('option', { name: 'High' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [url, body, opts] = api.put.mock.calls[0] as [string, Record<string, unknown>, { ifMatch?: number }]
    expect(url).toBe('/incidents/i1/questions/q1')
    expect(body).toMatchObject({ status: 'answered', answer: 'Phishing email with a macro.', confidence: 'high' })
    expect(opts.ifMatch).toBe(4)
  })
})
