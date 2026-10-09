import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { renderTab, resetTabTest, setPermissions } from '../test-utils'
import { EvidenceExportMenu } from './EvidenceExportMenu'
import { READ, RESPONDER } from './test-fixtures'

const item = { id: 'ev1', evidence_number: 'EV-0001' }

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

async function openMenu(name: RegExp) {
  fireEvent.keyDown(screen.getByRole('button', { name }), { key: 'Enter' })
  return within(await screen.findByRole('menu'))
}

describe('EvidenceExportMenu: register', () => {
  it('is absent without incidents:export (every register format needs it)', () => {
    setPermissions(READ)
    renderTab(<EvidenceExportMenu incidentId="i1" />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('offers CSV, PDF and the verifiable bundle with incidents:export, and downloads them', async () => {
    setPermissions(RESPONDER)
    const download = jest.spyOn(api, 'downloadTo').mockResolvedValue('register.csv')
    renderTab(<EvidenceExportMenu incidentId="i1" />)

    const menu = await openMenu(/export register/i)
    expect(menu.getAllByRole('menuitem').map((m) => m.textContent)).toEqual([
      'Register (CSV)',
      'Register (PDF)',
      'Verifiable bundle (ZIP)',
    ])
    fireEvent.click(menu.getByRole('menuitem', { name: 'Register (CSV)' }))
    await waitFor(() => expect(download).toHaveBeenCalled())
    expect(download).toHaveBeenCalledWith('/incidents/i1/evidence/export?format=csv', {
      fallbackName: 'evidence-register-i1.csv',
    })
  })

  it('requests the bundle format', async () => {
    setPermissions(RESPONDER)
    const download = jest.spyOn(api, 'downloadTo').mockResolvedValue('bundle.zip')
    renderTab(<EvidenceExportMenu incidentId="i1" />)
    const menu = await openMenu(/export register/i)
    fireEvent.click(menu.getByRole('menuitem', { name: 'Verifiable bundle (ZIP)' }))
    await waitFor(() => expect(download).toHaveBeenCalled())
    expect(String(download.mock.calls[0][0])).toBe('/incidents/i1/evidence/export?format=bundle')
  })

  it('reports a refused export (403) as an error toast and does not crash', async () => {
    setPermissions(RESPONDER)
    jest.spyOn(api, 'downloadTo').mockRejectedValue(new ApiError(403, 'Permission denied', { code: 'forbidden' }))
    renderTab(<EvidenceExportMenu incidentId="i1" />)
    const menu = await openMenu(/export register/i)
    fireEvent.click(menu.getByRole('menuitem', { name: 'Register (PDF)' }))
    await waitFor(() => expect(api.downloadTo).toHaveBeenCalled())
    // Menu closes and the trigger is usable again.
    await waitFor(() => expect(screen.getByRole('button', { name: /export register/i })).toBeTruthy())
  })
})

describe('EvidenceExportMenu: single item', () => {
  it('read-only users get the custody paperwork but not the bundle', async () => {
    setPermissions(READ)
    renderTab(<EvidenceExportMenu incidentId="i1" item={item} />)
    const menu = await openMenu(/export ev-0001/i)
    const labels = menu.getAllByRole('menuitem').map((m) => m.textContent)
    expect(labels).toEqual([
      'Printable custody form (PDF)',
      'Custody report (PDF)',
      'Custody entries (CSV)',
      'Custody record (JSON)',
    ])
  })

  it('users with incidents:export also get the verifiable bundle', async () => {
    setPermissions(RESPONDER)
    const download = jest.spyOn(api, 'downloadTo').mockResolvedValue('x.zip')
    renderTab(<EvidenceExportMenu incidentId="i1" item={item} />)
    const menu = await openMenu(/export ev-0001/i)
    expect(menu.getByRole('menuitem', { name: 'Verifiable bundle (ZIP)' })).toBeTruthy()
    fireEvent.click(menu.getByRole('menuitem', { name: 'Verifiable bundle (ZIP)' }))
    await waitFor(() => expect(download).toHaveBeenCalled())
    expect(String(download.mock.calls[0][0])).toBe('/incidents/i1/evidence/ev1/custody/export?format=bundle')
  })

  it('downloads the printable form with the form format', async () => {
    setPermissions(READ)
    const download = jest.spyOn(api, 'downloadTo').mockResolvedValue('form.pdf')
    renderTab(<EvidenceExportMenu incidentId="i1" item={item} />)
    const menu = await openMenu(/export ev-0001/i)
    fireEvent.click(menu.getByRole('menuitem', { name: 'Printable custody form (PDF)' }))
    await waitFor(() => expect(download).toHaveBeenCalled())
    expect(String(download.mock.calls[0][0])).toBe('/incidents/i1/evidence/ev1/custody/export?format=form')
  })
})
