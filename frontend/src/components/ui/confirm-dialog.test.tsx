import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfirmDialogProvider, confirmDelete, useConfirm, type ConfirmFn } from './confirm-dialog'

afterEach(cleanup)

function Grab({ onReady }: { onReady: (confirm: ConfirmFn) => void }) {
  onReady(useConfirm())
  return null
}

function setup() {
  let confirm: ConfirmFn = () => Promise.resolve(false)
  render(
    <ConfirmDialogProvider>
      <Grab onReady={(c) => (confirm = c)} />
    </ConfirmDialogProvider>
  )
  return () => confirm
}

const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement

describe('useConfirm', () => {
  it('resolves true on confirm and false on cancel', async () => {
    const confirm = setup()
    let p!: Promise<boolean>
    act(() => {
      p = confirm()({ description: 'Sure?' })
    })
    fireEvent.click(button('Confirm'))
    await expect(p).resolves.toBe(true)

    act(() => {
      p = confirm()({ description: 'Sure?' })
    })
    fireEvent.click(button('Cancel'))
    await expect(p).resolves.toBe(false)
  })

  it('requireText keeps confirm disabled until the exact text is typed', async () => {
    const confirm = setup()
    let p!: Promise<boolean>
    act(() => {
      p = confirm()({ description: 'Regenerate graph', requireText: 'REGENERATE', confirmLabel: 'Regenerate' })
    })
    const input = screen.getByLabelText(/to confirm/i)
    expect(button('Regenerate').disabled).toBe(true)
    fireEvent.change(input, { target: { value: 'regenerate' } })
    expect(button('Regenerate').disabled).toBe(true)
    fireEvent.change(input, { target: { value: 'REGENERATE' } })
    expect(button('Regenerate').disabled).toBe(false)
    fireEvent.submit(input.closest('form')!)
    await expect(p).resolves.toBe(true)
  })

  it('a second request settles the first as cancelled', async () => {
    const confirm = setup()
    let first!: Promise<boolean>
    let second!: Promise<boolean>
    act(() => {
      first = confirm()({ description: 'one' })
    })
    act(() => {
      second = confirm()({ description: 'two' })
    })
    await expect(first).resolves.toBe(false)
    fireEvent.click(button('Confirm'))
    await expect(second).resolves.toBe(true)
  })
})

describe('confirmDelete', () => {
  it('uses the standard destructive copy', async () => {
    const confirm = setup()
    let p!: Promise<boolean>
    act(() => {
      p = confirmDelete(confirm(), 'host', 'WS-01')
    })
    expect(screen.getByText('Delete host?')).toBeTruthy()
    expect(screen.getByText(/"WS-01" will be permanently deleted/)).toBeTruthy()
    fireEvent.click(button('Delete'))
    await expect(p).resolves.toBe(true)
  })
})

// Provider-level behaviour (from the W0-TH harness example).
function DeleteButton({ onResult }: { onResult: (ok: boolean) => void }) {
  const confirm = useConfirm()
  return (
    <button
      onClick={async () =>
        onResult(
          await confirm({
            title: 'Delete host?',
            description: 'This removes the host from the incident.',
            confirmLabel: 'Delete',
            variant: 'destructive',
          })
        )
      }
    >
      Delete host
    </button>
  )
}

function renderWithProvider(onResult: (ok: boolean) => void) {
  return render(
    <ConfirmDialogProvider>
      <DeleteButton onResult={onResult} />
    </ConfirmDialogProvider>
  )
}

describe('ConfirmDialogProvider', () => {
  it('opens a dialog with the requested copy', async () => {
    renderWithProvider(jest.fn())

    fireEvent.click(screen.getByRole('button', { name: 'Delete host' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Delete host?')
    expect(dialog).toHaveTextContent('This removes the host from the incident.')
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('resolves true on confirm and closes', async () => {
    const onResult = jest.fn()
    renderWithProvider(onResult)

    fireEvent.click(screen.getByRole('button', { name: 'Delete host' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('resolves false on cancel and on Escape', async () => {
    const onResult = jest.fn()
    renderWithProvider(onResult)

    fireEvent.click(screen.getByRole('button', { name: 'Delete host' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(onResult).toHaveBeenLastCalledWith(false))

    fireEvent.click(screen.getByRole('button', { name: 'Delete host' }))
    const dialog = await screen.findByRole('dialog')
    act(() => {
      fireEvent.keyDown(dialog, { key: 'Escape' })
    })
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(2))
    expect(onResult).toHaveBeenLastCalledWith(false)
  })
})
