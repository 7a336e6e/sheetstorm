import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'
import { EvidenceUploadDialog } from './EvidenceUploadDialog'
import { RESPONDER } from './test-fixtures'

const file = (name: string) => new File(['data'], name, { type: 'application/octet-stream' })

beforeEach(() => {
  resetTabTest()
  setPermissions(RESPONDER)
})
afterEach(() => resetTabTest())

describe('EvidenceUploadDialog', () => {
  it('registers each file as its own evidence item through the artifacts upload route', async () => {
    mockApi({ '/google-drive/status': { configured: false, connected: false } })
    const upload = jest.spyOn(api, 'uploadFile').mockResolvedValue({ id: 'a1' } as never)
    const onOpenChange = jest.fn()
    const onUploaded = jest.fn()
    renderTab(
      <EvidenceUploadDialog
        open
        onOpenChange={onOpenChange}
        incidentId="i1"
        initialFiles={[file('mem.raw'), file('disk.E01')]}
        onUploaded={onUploaded}
      />
    )

    fireEvent.change(screen.getByLabelText(/^type/i), { target: { value: 'memory_capture' } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }))

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2))
    const [endpoint, form] = upload.mock.calls[0] as [string, FormData]
    expect(endpoint).toBe('/incidents/i1/artifacts')
    expect((form.get('file') as File).name).toBe('mem.raw')
    expect(form.get('evidence_type')).toBe('memory_capture')
    expect(form.has('evidence_item_id')).toBe(false)
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(onUploaded).toHaveBeenCalled()
  })

  it('attaches to an existing item instead of registering a new one', async () => {
    mockApi({ '/google-drive/status': { configured: false, connected: false } })
    const upload = jest.spyOn(api, 'uploadFile').mockResolvedValue({ id: 'a1' } as never)
    renderTab(
      <EvidenceUploadDialog
        open
        onOpenChange={jest.fn()}
        incidentId="i1"
        initialFiles={[file('copy.bin')]}
        attachTo={{ id: 'ev1', evidence_number: 'EV-0001', title: 'Laptop' }}
      />
    )
    expect(screen.getByText('Add a stored copy to EV-0001')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    await waitFor(() => expect(upload).toHaveBeenCalled())
    const form = (upload.mock.calls[0] as [string, FormData])[1]
    expect(form.get('evidence_item_id')).toBe('ev1')
    expect(form.has('evidence_type')).toBe(false)
  })

  it('keeps the dialog open and names the file that failed', async () => {
    mockApi({ '/google-drive/status': { configured: false, connected: false } })
    jest
      .spyOn(api, 'uploadFile')
      .mockResolvedValueOnce({ id: 'a1' } as never)
      .mockRejectedValueOnce(new ApiError(413, 'File too large', { code: 'payload_too_large' }))
    const onOpenChange = jest.fn()
    renderTab(
      <EvidenceUploadDialog open onOpenChange={onOpenChange} incidentId="i1" initialFiles={[file('ok.txt'), file('huge.bin')]} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/huge\.bin: File too large/)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('shows Google Drive status and case folder setup when configured', async () => {
    mockApi({ '/google-drive/status': { configured: true, connected: true, email: 'x@y.test' } })
    const api2 = jest.spyOn(api, 'post').mockResolvedValue({} as never)
    renderTab(<EvidenceUploadDialog open onOpenChange={jest.fn()} incidentId="i1" />)

    fireEvent.click(await screen.findByRole('button', { name: /set up case folder/i }))
    await waitFor(() => expect(api2).toHaveBeenCalledWith('/incidents/i1/google-drive/setup'))
  })
})
