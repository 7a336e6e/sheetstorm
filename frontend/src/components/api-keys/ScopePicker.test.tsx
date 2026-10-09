import { afterEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import type { ApiKeyScopeGroup } from '@/types'
import { ScopePicker, presetScopes } from './ScopePicker'
import { SCOPES } from './test-fixtures'

afterEach(cleanup)

function Harness({
  groups = SCOPES.groups,
  onChange,
}: {
  groups?: ApiKeyScopeGroup[]
  onChange?: (scopes: string[]) => void
}) {
  const [value, setValue] = useState<string[]>([])
  return (
    <ScopePicker
      groups={groups}
      value={value}
      onChange={(v) => {
        setValue(v)
        onChange?.(v)
      }}
    />
  )
}

const selected = () =>
  screen
    .getAllByRole('checkbox')
    .filter((c) => c.getAttribute('aria-checked') === 'true')
    .map((c) => c.getAttribute('id'))

describe('ScopePicker', () => {
  it('groups scopes by catalog group, in server order', () => {
    render(<Harness />)
    const groups = Array.from(document.querySelectorAll('fieldset')).map((f) => f.getAttribute('data-group'))
    expect(groups).toEqual(['incidents', 'timeline', 'users'])
    expect(screen.getByLabelText('View timeline events')).toBeInTheDocument()
  })

  it('flags sensitive scopes and warns once one is selected', () => {
    render(<Harness />)
    const exportRow = screen.getByLabelText('Export incident data').closest('li')!
    expect(within(exportRow).getByText('Sensitive')).toBeInTheDocument()
    expect(within(screen.getByLabelText('View incidents').closest('li')!).queryByText('Sensitive')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    fireEvent.click(screen.getByLabelText('Export incident data'))
    expect(screen.getByRole('status')).toHaveTextContent('1 sensitive scope selected')
  })

  it('hides scopes the server marks as not grantable (and then-empty groups)', () => {
    const groups: ApiKeyScopeGroup[] = [
      {
        group: 'incidents',
        label: 'Incidents',
        scopes: [
          { value: 'incidents:read', label: 'View incidents', sensitive: false },
          { value: 'incidents:purge', label: 'Permanently delete incidents', sensitive: true, grantable: false },
        ],
      },
      {
        group: 'api_keys',
        label: 'API keys',
        scopes: [{ value: 'api_keys:manage', label: 'Manage API keys', sensitive: true, grantable: false }],
      },
    ]
    render(<Harness groups={groups} />)
    expect(screen.getByLabelText('View incidents')).toBeInTheDocument()
    expect(screen.queryByLabelText('Permanently delete incidents')).toBeNull()
    expect(screen.queryByText('API keys')).toBeNull()
  })

  it('selects and clears a whole group with its checkbox (indeterminate when partial)', () => {
    render(<Harness />)
    const all = screen.getByLabelText('Select all Timeline')
    fireEvent.click(all)
    expect(selected()).toEqual(
      expect.arrayContaining(['scope-timeline:read', 'scope-timeline:create', 'scope-timeline:update', 'scope-timeline:delete'])
    )
    fireEvent.click(screen.getByLabelText('Delete timeline events'))
    expect(screen.getByLabelText('Select all Timeline')).toHaveAttribute('aria-checked', 'mixed')
    fireEvent.click(screen.getByLabelText('Select all Timeline'))
    expect(screen.getByLabelText('Select all Timeline')).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByLabelText('Select all Timeline'))
    expect(selected().filter((id) => id?.startsWith('scope-timeline'))).toEqual([])
  })

  it('applies the presets using only available scopes', () => {
    const onChange = jest.fn()
    render(<Harness onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Read-only' }))
    expect(onChange).toHaveBeenLastCalledWith(['incidents:read', 'timeline:read', 'users:read'])
    fireEvent.click(screen.getByRole('button', { name: 'MCP analyst' }))
    expect(onChange).toHaveBeenLastCalledWith([
      'incidents:read',
      'timeline:create',
      'timeline:read',
      'timeline:update',
      'users:read',
    ])
    expect(screen.getByText('5 selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByText('0 selected')).toBeInTheDocument()
  })

  it('presetScopes never invents keys that are not offered', () => {
    expect(presetScopes('read-only', [{ group: 'users', label: 'Users', scopes: [] }])).toEqual([])
  })

  it('says so when nothing can be granted', () => {
    render(<Harness groups={[]} />)
    expect(screen.getByText('No scopes can be granted to this owner.')).toBeInTheDocument()
  })
})
