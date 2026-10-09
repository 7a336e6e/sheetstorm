import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api from '@/lib/api'
import { useIncidentStore } from '@/lib/store'
import { BulkEnrichAction } from './BulkEnrichAction'

function setTlp(tlp: string) {
  act(() => {
    useIncidentStore.setState({ currentIncident: { id: 'i1', tlp } } as never)
  })
}

function orgAllowsStrict(allowed: boolean) {
  return jest.spyOn(api, 'get').mockResolvedValue({ id: 'o1', settings: { enrichment_allow_amber_strict: allowed } } as never)
}

const RESULT = {
  total: 2,
  enriched: 1,
  failed: 0,
  blocked: 1,
  providers: ['virustotal'],
  results: [
    { value: 'one.example', type: 'domain', status: 'success', summary: 'virustotal: malicious 3' },
    { value: 'two.example', type: 'domain', status: 'blocked', error: 'tlp_restricted', summary: 'blocked: TLP-restricted value' },
  ],
}

beforeEach(() => {
  jest.restoreAllMocks()
})
afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useIncidentStore.setState({ currentIncident: null } as never)
  })
})

const open = () => fireEvent.click(screen.getByRole('button', { name: /^Enrich \(/ }))

describe('BulkEnrichAction', () => {
  it('shows the count and is disabled without values', () => {
    setTlp('amber')
    const { rerender } = render(<BulkEnrichAction incidentId="i1" values={['a.example', 'b.example']} noun="network IOC" />)
    expect(screen.getByRole('button', { name: 'Enrich (2)' })).toBeTruthy()
    rerender(<BulkEnrichAction incidentId="i1" values={[]} noun="network IOC" />)
    expect((screen.getByRole('button', { name: 'Enrich (0)' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('AMBER: a plain confirmation naming the TLP and the third-party providers, then a result table', async () => {
    setTlp('amber')
    const post = jest.spyOn(api, 'post').mockResolvedValue(RESULT as never)
    const onDone = jest.fn()
    render(<BulkEnrichAction incidentId="i1" values={['one.example', 'two.example', 'nope!']} noun="network IOC" onDone={onDone} />)

    open()
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('TLP:AMBER')).toBeTruthy()
    expect(within(dialog).getByText(/sent to the third-party/)).toBeTruthy()
    expect(within(dialog).getByText(/1 selected value is not an IP, domain, e-mail or hash/)).toBeTruthy()
    expect(within(dialog).queryByRole('checkbox')).toBeNull()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enrich' }))

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/bulk-enrich', {
        incident_id: 'i1',
        ioc_values: [
          { value: 'one.example', type: 'domain' },
          { value: 'two.example', type: 'domain' },
        ],
      })
    )
    const table = await screen.findByRole('table', { name: 'Enrichment results' })
    expect(within(table).getByText('virustotal: malicious 3')).toBeTruthy()
    expect(within(table).getByText('Blocked')).toBeTruthy()
    expect(screen.getByText(/1 enriched, 0 failed, 1 blocked/)).toBeTruthy()
    expect(screen.getByText(/providers: virustotal/)).toBeTruthy()
    expect(onDone).not.toHaveBeenCalled() // the selection stays until the results were closed
    fireEvent.click(within(screen.getByRole('dialog')).getAllByRole('button', { name: 'Close' }).slice(-1)[0])
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
  })

  it('RED is shown as blocked: nothing can be sent', async () => {
    setTlp('red')
    const post = jest.spyOn(api, 'post').mockResolvedValue(RESULT as never)
    const get = jest.spyOn(api, 'get')
    render(<BulkEnrichAction incidentId="i1" values={['one.example']} noun="network IOC" />)

    open()
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Enrichment blocked')).toBeTruthy()
    expect(within(dialog).getByRole('alert').textContent).toMatch(/TLP:RED data is never sent/)
    expect(within(dialog).queryByRole('button', { name: /enrich$|send for enrichment/i })).toBeNull()
    expect(post).not.toHaveBeenCalled()
    expect(get).not.toHaveBeenCalled() // no setting can unblock RED: no need to ask for the org setting
  })

  it('AMBER+STRICT when the org allows it: destructive dialog, explicit acknowledgement required', async () => {
    setTlp('amber_strict')
    orgAllowsStrict(true)
    const post = jest.spyOn(api, 'post').mockResolvedValue(RESULT as never)
    render(<BulkEnrichAction incidentId="i1" values={['one.example']} noun="network IOC" />)

    open()
    const send = await screen.findByRole('button', { name: 'Send for enrichment' })
    expect((send as HTMLButtonElement).disabled).toBe(true)
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('TLP:AMBER+STRICT')).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('checkbox'))
    expect((send as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(send)
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
  })

  it('AMBER+STRICT when the org does not allow it: blocked', async () => {
    setTlp('amber_strict')
    orgAllowsStrict(false)
    const post = jest.spyOn(api, 'post')
    render(<BulkEnrichAction incidentId="i1" values={['one.example']} noun="network IOC" />)

    open()
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText(/does not allow TLP:AMBER\+STRICT indicator values/)
    expect(within(dialog).queryByRole('button', { name: /send for enrichment/i })).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })

  it('a server refusal (403 tlp_restricted) is reported and closes the dialog', async () => {
    setTlp('green')
    const { ApiError } = await import('@/lib/api')
    jest.spyOn(api, 'post').mockRejectedValue(new ApiError(403, 'restricted', { code: 'tlp_restricted' }))
    render(<BulkEnrichAction incidentId="i1" values={['one.example']} noun="network IOC" />)
    open()
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Enrich' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByRole('table')).toBeNull()
  })
})
