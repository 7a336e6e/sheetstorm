import { afterEach, describe, expect, it, jest } from '@jest/globals'
import * as React from 'react'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { PrimaryActionProvider, usePrimaryActionRegistration } from './primary-action'

afterEach(cleanup)

function List({ label, onSelect, hidden }: { label: string; onSelect: () => void; hidden?: boolean }) {
  const ref = React.useRef<HTMLDivElement>(null)
  const action = React.useMemo(() => ({ label, onSelect }), [label, onSelect])
  usePrimaryActionRegistration(action, ref)
  return (
    <div hidden={hidden}>
      <div ref={ref}>{label}</div>
    </div>
  )
}

describe('primary action', () => {
  it('`n` runs the latest visible registration only', () => {
    const hosts = jest.fn()
    const tasks = jest.fn()
    render(
      <PrimaryActionProvider>
        <List label="hosts" onSelect={hosts} />
        <List label="tasks" onSelect={tasks} hidden />
      </PrimaryActionProvider>
    )
    fireEvent.keyDown(document, { key: 'n' })
    expect(hosts).toHaveBeenCalledTimes(1)
    expect(tasks).not.toHaveBeenCalled()
  })

  it('is a no-op without a provider', () => {
    const fn = jest.fn()
    render(<List label="x" onSelect={fn} />)
    fireEvent.keyDown(document, { key: 'n' })
    expect(fn).not.toHaveBeenCalled()
  })
})
