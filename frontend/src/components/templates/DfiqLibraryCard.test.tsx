import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api from '@/lib/api'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { DfiqLibraryCard } from './DfiqLibraryCard'
import type { DfiqStatus } from '@/types'

const status = (extra: Partial<DfiqStatus> = {}): DfiqStatus => ({
  imported: false, commit: null, sha256: null, method: null, imported_at: null, imported_by: null, counts: null,
  version: 0, pinned_commit: 'f07e5f2a5255afda7be9d9de13300d3df12d15f8', pinned_sha256: 'e3'.repeat(32),
  download_url: 'https://codeload.github.com/google/dfiq/tar.gz/x', source: 'https://github.com/google/dfiq',
  license: 'Apache-2.0', attribution: 'Questions marked DFIQ are © 2024 Google LLC, Apache-2.0',
  vendored_files: false, can_import: true, ...extra,
})

const renderCard = () => render(<ConfirmDialogProvider><DfiqLibraryCard /></ConfirmDialogProvider>)

beforeEach(() => {
  jest.restoreAllMocks()
})
afterEach(() => cleanup())

describe('DfiqLibraryCard', () => {
  it('imports with one click', async () => {
    jest.spyOn(api, 'get').mockResolvedValue(status() as never)
    const post = jest.spyOn(api, 'post').mockResolvedValue(
      status({ imported: true, commit: 'f07e5f2a5255', counts: { scenarios: 6, facets: 29, questions: 90 } }) as never
    )
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /import dfiq/i }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/questions/library/dfiq/import', {}))
    expect(await screen.findByText(/90 questions in 6 scenarios/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /re-import dfiq/i })).toBeTruthy()
  })

  it('is read-only for non platform admins', async () => {
    jest.spyOn(api, 'get').mockResolvedValue(status({ can_import: false }) as never)
    renderCard()
    expect(await screen.findByText(/Only platform administrators/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /import dfiq/i })).toBeNull()
  })
})
