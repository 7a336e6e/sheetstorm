// Example of a component test (jsdom + Testing Library): render through the
// real provider, interact the way a user would, assert on accessible roles.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfirmDialogProvider, useConfirm } from './confirm-dialog'

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
