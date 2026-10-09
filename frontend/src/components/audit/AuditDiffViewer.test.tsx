import { describe, expect, it } from '@jest/globals'
import { render, screen, within } from '@testing-library/react'
import { AuditDiffViewer, formatDiffValue, hasChanges, normalizeChanges } from './AuditDiffViewer'

const row = (field: string) => {
  const el = document.querySelector(`tr[data-field="${CSS.escape(field)}"]`)
  if (!el) throw new Error(`no row for ${field}`)
  return el as HTMLElement
}

describe('normalizeChanges', () => {
  it('maps every diff shape of utils/audit_diff.py', () => {
    const { rows, truncated } = normalizeChanges({
      name: { from: 'Analyst', to: 'Senior analyst' },
      permissions: { added: ['audit_logs:export'], removed: ['incidents:read'] },
      password: { changed: true },
      'settings.ai_tlp_policy.red': { from: 'local_only', to: 'block' },
      _truncated: true,
    })
    expect(truncated).toBe(true)
    expect(rows).toEqual([
      { field: 'name', path: ['name'], kind: 'value', from: 'Analyst', to: 'Senior analyst' },
      { field: 'permissions', path: ['permissions'], kind: 'list', added: ['audit_logs:export'], removed: ['incidents:read'] },
      { field: 'password', path: ['password'], kind: 'redacted' },
      {
        field: 'settings.ai_tlp_policy.red',
        path: ['settings', 'ai_tlp_policy', 'red'],
        kind: 'value',
        from: 'local_only',
        to: 'block',
      },
    ])
  })

  it('treats a list diff with only one side as a list', () => {
    expect(normalizeChanges({ roles: { added: ['Viewer'] } }).rows[0]).toEqual({
      field: 'roles', path: ['roles'], kind: 'list', added: ['Viewer'], removed: [],
    })
  })

  it('ignores non-object input and keeps unknown entry shapes visible', () => {
    expect(normalizeChanges(null)).toEqual({ rows: [], truncated: false })
    expect(normalizeChanges(['x'])).toEqual({ rows: [], truncated: false })
    expect(normalizeChanges({ odd: 'raw' }).rows).toEqual([
      { field: 'odd', path: ['odd'], kind: 'value', from: undefined, to: 'raw' },
    ])
  })

  it('hasChanges looks at details.changes', () => {
    expect(hasChanges({ changes: { a: { from: 1, to: 2 } } })).toBe(true)
    expect(hasChanges({ changes: {} })).toBe(false)
    expect(hasChanges({ args: {} })).toBe(false)
    expect(hasChanges(undefined)).toBe(false)
  })

  it('formats values', () => {
    expect(formatDiffValue(null)).toBe('—')
    expect(formatDiffValue(undefined)).toBe('—')
    expect(formatDiffValue('')).toBe('""')
    expect(formatDiffValue(false)).toBe('false')
    expect(formatDiffValue(30)).toBe('30')
    expect(formatDiffValue({ a: 1 })).toBe('{"a":1}')
  })
})

describe('AuditDiffViewer', () => {
  it('renders before/after for a value change', () => {
    render(<AuditDiffViewer changes={{ is_active: { from: true, to: false }, timezone: { from: null, to: 'UTC' } }} />)
    const active = row('is_active')
    expect(within(active).getByText('true')).toBeInTheDocument()
    expect(within(active).getByText('false')).toBeInTheDocument()
    const cells = within(row('timezone')).getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('—')
    expect(cells[1]).toHaveTextContent('UTC')
  })

  it('renders removed chips under Before and added chips under After', () => {
    render(<AuditDiffViewer changes={{ permissions: { added: ['a:x', 'b:y'], removed: ['c:z'] } }} />)
    const [before, after] = within(row('permissions')).getAllByRole('cell')
    expect(within(before).getByRole('list', { name: 'removed' })).toHaveTextContent('c:z')
    const added = within(after).getByRole('list', { name: 'added' })
    expect(within(added).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['a:x', 'b:y'])
  })

  it('shows a redacted badge and never a value for sensitive fields', () => {
    render(<AuditDiffViewer changes={{ 'config.api_key': { changed: true } }} />)
    const r = row('config.api_key')
    expect(within(r).getByText('changed (redacted)')).toBeInTheDocument()
    expect(within(r).getAllByRole('cell')).toHaveLength(1)
  })

  it('shows nested org settings keys as path segments', () => {
    render(
      <AuditDiffViewer
        changes={{
          'settings.ai_tlp_policy.amber': { from: 'allow', to: 'local_only' },
          'settings.auto_enrich_iocs': { from: true, to: false },
        }}
      />
    )
    const r = row('settings.ai_tlp_policy.amber')
    const header = within(r).getByRole('rowheader')
    expect(header).toHaveTextContent('settings›ai_tlp_policy›amber')
    expect(header.querySelector('[title="settings.ai_tlp_policy.amber"]')).not.toBeNull()
    expect(within(r).getByText('allow')).toBeInTheDocument()
    expect(within(r).getByText('local_only')).toBeInTheDocument()
    expect(within(row('settings.auto_enrich_iocs')).getByRole('rowheader')).toHaveTextContent('settings›auto_enrich_iocs')
  })

  it('notes a truncated diff and handles the empty case', () => {
    const { unmount } = render(<AuditDiffViewer changes={{ a: { from: 1, to: 2 }, _truncated: true }} />)
    expect(screen.getByText(/diff was truncated/i)).toBeInTheDocument()
    expect(document.querySelector('tr[data-field="_truncated"]')).toBeNull()
    unmount()
    render(<AuditDiffViewer changes={{}} />)
    expect(screen.getByText('No field changes recorded.')).toBeInTheDocument()
  })
})
