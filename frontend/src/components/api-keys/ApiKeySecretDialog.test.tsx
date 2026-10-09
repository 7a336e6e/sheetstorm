import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { ApiKeySecretDialog, formatGrace, type SecretResult } from './ApiKeySecretDialog'
import { SECRET, withSecret } from './test-fixtures'

const created: SecretResult = { key: withSecret(), mode: 'created' }

function Host({ initial = created, onClose }: { initial?: SecretResult | null; onClose?: () => void }) {
  const [result, setResult] = useState<SecretResult | null>(initial)
  return (
    <ApiKeySecretDialog
      result={result}
      onClose={() => {
        onClose?.()
        setResult(null)
      }}
    />
  )
}

let writeText: jest.Mock<(text: string) => Promise<void>>

beforeEach(() => {
  writeText = jest.fn(async () => {})
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
})
afterEach(cleanup)

describe('ApiKeySecretDialog', () => {
  it('shows the secret and the MCP setup hint with ${env:...}, never the key in the hint', () => {
    render(<Host />)
    expect(screen.getByTestId('api-key-secret')).toHaveTextContent(SECRET)
    const hint = document.querySelector('pre')!
    expect(hint.textContent).toContain('"SHEETSTORM_API_KEY": "${env:SHEETSTORM_API_KEY}"')
    expect(hint.textContent).not.toContain(SECRET)
  })

  it('copies the key and the .env line', async () => {
    render(<Host />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SECRET))
    fireEvent.click(screen.getByRole('button', { name: /Copy SHEETSTORM_API_KEY/ }))
    await waitFor(() => expect(writeText).toHaveBeenLastCalledWith(`SHEETSTORM_API_KEY=${SECRET}`))
  })

  it('cannot be dismissed until the key is acknowledged', () => {
    const onClose = jest.fn()
    render(<Host onClose={onClose} />)
    const done = screen.getByRole('button', { name: 'Done' })
    expect(done).toBeDisabled()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByTestId('api-key-secret')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('I have stored this key'))
    expect(done).toBeEnabled()
  })

  it('is shown once: closing removes the secret from the DOM, reopening needs a new result', async () => {
    const onClose = jest.fn()
    const { rerender } = render(<Host onClose={onClose} />)
    fireEvent.click(screen.getByLabelText('I have stored this key'))
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByTestId('api-key-secret')).toBeNull())
    expect(document.body.textContent).not.toContain(SECRET)

    // A fresh host starts closed: the acknowledgement does not carry over either.
    rerender(<Host initial={null} />)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.body.textContent).not.toContain(SECRET)
  })

  it('does not persist the secret in browser storage', () => {
    render(<Host />)
    const dump = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage })
    expect(dump).not.toContain(SECRET)
  })

  it('explains the grace period after a rotation', () => {
    render(<Host initial={{ key: withSecret(), mode: 'rotated', graceMinutes: 90 }} />)
    expect(screen.getByText('API key rotated')).toBeInTheDocument()
    expect(screen.getByText(/previous key keeps working for 1 hour 30 minutes/)).toBeInTheDocument()
  })

  it('says an immediate rotation stopped the old key', () => {
    render(<Host initial={{ key: withSecret(), mode: 'rotated', graceMinutes: 0 }} />)
    expect(screen.getByText(/previous key stopped working immediately/)).toBeInTheDocument()
  })

  it('formats grace periods', () => {
    expect(formatGrace(1)).toBe('1 minute')
    expect(formatGrace(15)).toBe('15 minutes')
    expect(formatGrace(60)).toBe('1 hour')
    expect(formatGrace(1440)).toBe('24 hours')
  })
})
