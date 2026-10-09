import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { correlationTypeLabel, IOCCorrelationDialog, otherIncidentMatches } from './IOCCorrelationDialog'

afterEach(() => {
  jest.restoreAllMocks()
})
beforeEach(() => {
  jest.restoreAllMocks()
})

const match = (value: string, type: string, incidents: { id: string; title: string }[]) => ({
  ioc_value: value,
  ioc_type: type,
  incident_count: incidents.length,
  incidents,
})

describe('helpers', () => {
  it('drops the current incident and matches that only live in it', () => {
    const out = otherIncidentMatches(
      [
        match('evil.example', 'network_ioc', [
          { id: 'i1', title: 'This' },
          { id: 'i2', title: 'Other' },
        ]),
        match('solo', 'hostname', [{ id: 'i1', title: 'This' }]),
      ],
      'i1'
    )
    expect(out).toHaveLength(1)
    expect(out[0].others.map((i) => i.id)).toEqual(['i2'])
  })

  it('labels types for people', () => {
    expect(correlationTypeLabel('network_ioc')).toBe('network ioc')
    expect(correlationTypeLabel('host_ioc:file')).toBe('host ioc: file')
    expect(correlationTypeLabel('sha256')).toBe('sha256')
  })
})

describe('IOCCorrelationDialog', () => {
  it('posts the incident id and lists each value with links to the OTHER incidents', async () => {
    const post = jest.spyOn(api, 'post').mockResolvedValue({
      total: 2,
      correlations: [
        match('evil.example', 'network_ioc', [
          { id: 'i1', title: 'Current case' },
          { id: 'i2', title: 'Phishing wave' },
          { id: 'i3', title: 'Old intrusion' },
        ]),
        match('a'.repeat(64), 'sha256', [
          { id: 'i1', title: 'Current case' },
          { id: 'i3', title: 'Old intrusion' },
        ]),
      ],
    } as never)
    render(<IOCCorrelationDialog open onOpenChange={() => {}} incidentId="i1" />)

    const list = await screen.findByRole('list', { name: 'Correlated indicators' })
    expect(post).toHaveBeenCalledWith('/correlate-iocs', { incident_id: 'i1' })
    expect(within(list).getByText('evil.example')).toBeTruthy()
    expect(within(list).getByText('network ioc')).toBeTruthy()
    expect(within(list).getByText('also in 2 other incidents')).toBeTruthy()
    expect(within(list).getByText('also in 1 other incident')).toBeTruthy()
    expect(within(list).queryByText('Current case')).toBeNull()
    const link = within(list).getByRole('link', { name: 'Phishing wave' })
    expect(link.getAttribute('href')).toBe('/dashboard/incidents/i2')
  })

  it('says so when nothing is shared', async () => {
    jest.spyOn(api, 'post').mockResolvedValue({ correlations: [], total: 0 } as never)
    render(<IOCCorrelationDialog open onOpenChange={() => {}} incidentId="i1" />)
    expect(await screen.findByText(/No indicator of this incident appears in another incident/)).toBeTruthy()
  })

  it('shows an error and retries', async () => {
    const post = jest
      .spyOn(api, 'post')
      .mockRejectedValueOnce(new ApiError(404, 'Incident not found', { code: 'not_found' }))
      .mockResolvedValueOnce({ correlations: [], total: 0 } as never)
    render(<IOCCorrelationDialog open onOpenChange={() => {}} incidentId="i1" />)
    const alert = await screen.findByRole('alert')
    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    await screen.findByText(/No indicator of this incident/)
    expect(post).toHaveBeenCalledTimes(2)
  })

  it('does nothing while closed and closes via the footer button', async () => {
    const post = jest.spyOn(api, 'post').mockResolvedValue({ correlations: [], total: 0 } as never)
    const onOpenChange = jest.fn()
    const { rerender } = render(<IOCCorrelationDialog open={false} onOpenChange={onOpenChange} incidentId="i1" />)
    expect(post).not.toHaveBeenCalled()
    rerender(<IOCCorrelationDialog open onOpenChange={onOpenChange} incidentId="i1" />)
    await waitFor(() => expect(post).toHaveBeenCalled())
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0])
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
