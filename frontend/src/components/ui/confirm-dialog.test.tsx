import { afterEach, describe, expect, it } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ConfirmDialogProvider, confirmDelete, useConfirm, type ConfirmFn } from './confirm-dialog'

afterEach(cleanup)

function setup() {
  let confirm: ConfirmFn = () => Promise.resolve(false)
  function Grab() {
    confirm = useConfirm()
    return null
  }
  render(
    <ConfirmDialogProvider>
      <Grab />
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
