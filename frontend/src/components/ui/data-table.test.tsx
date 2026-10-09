import { afterEach, beforeAll, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type { PaginatedQuery, ListState } from '@/hooks/use-paginated-query'
import { ApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { DataTable, nextSort, sortDirection, type DataTableColumn } from './data-table'

beforeAll(() => {
  // Radix popper measures with ResizeObserver, which jsdom lacks.
  const g = globalThis as unknown as { ResizeObserver?: unknown }
  if (!g.ResizeObserver) {
    g.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
})

afterEach(() => {
  cleanup()
  act(() => {
    useAuthStore.setState({ user: null })
  })
})

type Host = { id: string; hostname: string }

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({ user: { id: 'u', email: 'u@x', name: 'U', roles: [], permissions } })
  })
}

function makeQuery(over: Partial<PaginatedQuery<Host>> = {}, state: Partial<ListState> = {}): PaginatedQuery<Host> {
  const items = over.items ?? [
    { id: 'h1', hostname: 'WS-01' },
    { id: 'h2', hostname: 'WS-02' },
    { id: 'h3', hostname: 'DC-01' },
  ]
  return {
    items,
    total: items.length,
    pages: 1,
    state: { page: 1, perPage: 50, filters: {}, ...state },
    isLoading: false,
    isFetching: false,
    error: null,
    setPage: jest.fn(),
    setPerPage: jest.fn(),
    setSort: jest.fn(),
    setQuery: jest.fn(),
    setFilter: jest.fn(),
    resetFilters: jest.fn(),
    refetch: jest.fn(async () => undefined),
    ...over,
  }
}

const columns: DataTableColumn<Host>[] = [
  { id: 'hostname', header: 'Hostname', cell: (h) => h.hostname, sortKey: 'hostname' },
  { id: 'id', header: 'ID', cell: (h) => h.id },
]

function rows() {
  return screen.getAllByRole('row').filter((r) => r.getAttribute('tabindex') !== null)
}

describe('sort helpers', () => {
  it('cycles asc → desc → default', () => {
    expect(nextSort(undefined, 'hostname')).toBe('hostname')
    expect(nextSort('hostname', 'hostname')).toBe('-hostname')
    expect(nextSort('-hostname', 'hostname')).toBeUndefined()
    expect(nextSort('-created_at', 'hostname')).toBe('hostname')
    expect(sortDirection('-hostname,created_at', 'hostname')).toBe('desc')
  })
})

describe('DataTable', () => {
  it('renders rows, aria-sort and cycles sort on header click', () => {
    const query = makeQuery({}, { sort: 'hostname' })
    render(<DataTable query={query} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" />)
    expect(screen.getByRole('grid', { name: 'Hosts' })).toBeTruthy()
    expect(rows()).toHaveLength(3)
    const header = screen.getByRole('columnheader', { name: /hostname/i })
    expect(header.getAttribute('aria-sort')).toBe('ascending')
    expect(screen.getByRole('columnheader', { name: 'ID' }).getAttribute('aria-sort')).toBeNull()
    fireEvent.click(within(header).getByRole('button'))
    expect(query.setSort).toHaveBeenCalledWith('-hostname')
    expect(screen.getByText('1–3 of 3')).toBeTruthy()
  })

  it('shows skeleton rows on first load', () => {
    render(
      <DataTable query={makeQuery({ isLoading: true, items: [] })} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" />
    )
    expect(screen.getAllByTestId('skeleton-row').length).toBeGreaterThan(0)
  })

  it('distinguishes empty from no matches', () => {
    const { rerender } = render(
      <DataTable
        query={makeQuery({ items: [] })}
        columns={columns}
        getRowId={(h) => h.id}
        ariaLabel="Hosts"
        empty={{ title: 'No hosts yet', description: 'Add the first compromised host.' }}
      />
    )
    expect(screen.getByText('No hosts yet')).toBeTruthy()
    expect(screen.queryByText('No matches')).toBeNull()

    const filtered = makeQuery({ items: [] }, { q: 'zzz' })
    rerender(
      <DataTable query={filtered} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" empty={{ title: 'No hosts yet' }} />
    )
    expect(screen.getByText('No matches')).toBeTruthy()
    expect(screen.queryByText('No hosts yet')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(filtered.resetFilters).toHaveBeenCalled()
  })

  it('shows an error panel with retry', () => {
    const query = makeQuery({ items: [], error: new ApiError(403, 'nope') })
    render(<DataTable query={query} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" />)
    expect(screen.getByRole('alert').textContent).toContain("You don't have permission to do that.")
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(query.refetch).toHaveBeenCalled()
  })

  it('filters row actions by permission and hides the menu when none remain', () => {
    const onEdit = jest.fn()
    const rowActions = (h: Host) => [
      { label: 'Edit', onSelect: () => onEdit(h.id), permission: 'hosts:update' },
      { label: 'Delete', onSelect: jest.fn(), permission: 'hosts:delete', destructive: true },
    ]
    setPermissions([])
    const { rerender } = render(
      <DataTable query={makeQuery()} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" rowActions={rowActions} />
    )
    expect(screen.queryAllByRole('button', { name: /actions for/i })).toHaveLength(0)

    setPermissions(['hosts:update'])
    rerender(<DataTable query={makeQuery()} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" rowActions={rowActions} />)
    // Always visible: one kebab per row, no hover-only styling.
    const kebabs = screen.getAllByRole('button', { name: /actions for/i })
    expect(kebabs).toHaveLength(3)
    expect(kebabs[0].className).not.toContain('opacity-0')

    fireEvent.keyDown(rows()[0], { key: '.' })
    const menu = screen.getByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit' })).toBeTruthy()
    expect(within(menu).queryByRole('menuitem', { name: 'Delete' })).toBeNull()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit' }))
    expect(onEdit).toHaveBeenCalledWith('h1')
  })

  it('gates the primary action', () => {
    const onSelect = jest.fn()
    setPermissions(['hosts:read'])
    const { rerender } = render(
      <DataTable
        query={makeQuery()}
        columns={columns}
        getRowId={(h) => h.id}
        ariaLabel="Hosts"
        primaryAction={{ label: 'Add host', onSelect, permission: 'hosts:create' }}
      />
    )
    expect(screen.queryByRole('button', { name: /add host/i })).toBeNull()
    setPermissions(['hosts:create'])
    rerender(
      <DataTable
        query={makeQuery()}
        columns={columns}
        getRowId={(h) => h.id}
        ariaLabel="Hosts"
        primaryAction={{ label: 'Add host', onSelect, permission: 'hosts:create' }}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /add host/i }))
    expect(onSelect).toHaveBeenCalled()
  })

  it('supports roving keyboard navigation, Enter and Space selection', () => {
    const onRowClick = jest.fn()
    render(
      <DataTable
        query={makeQuery()}
        columns={columns}
        getRowId={(h) => h.id}
        ariaLabel="Hosts"
        onRowClick={onRowClick}
        selectable
        bulkActions={(ids) => <span>bulk:{ids.join(',')}</span>}
      />
    )
    const r = rows()
    expect(r.map((x) => x.getAttribute('tabindex'))).toEqual(['0', '-1', '-1'])
    r[0].focus()
    fireEvent.keyDown(r[0], { key: 'ArrowDown' })
    expect(document.activeElement).toBe(r[1])
    fireEvent.keyDown(r[1], { key: 'End' })
    expect(document.activeElement).toBe(r[2])
    fireEvent.keyDown(r[2], { key: 'Home' })
    expect(document.activeElement).toBe(r[0])
    fireEvent.keyDown(r[0], { key: 'ArrowUp' })
    expect(document.activeElement).toBe(r[0])

    fireEvent.keyDown(r[0], { key: 'Enter' })
    expect(onRowClick).toHaveBeenCalledWith({ id: 'h1', hostname: 'WS-01' })

    fireEvent.keyDown(r[0], { key: ' ' })
    expect(r[0].getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('bulk:h1')).toBeTruthy()
  })

  it('clears the page-scoped selection when the list state changes', () => {
    const props = {
      columns,
      getRowId: (h: Host) => h.id,
      ariaLabel: 'Hosts',
      selectable: true,
      bulkActions: (ids: string[]) => <span>bulk:{ids.length}</span>,
    }
    const { rerender } = render(<DataTable query={makeQuery()} {...props} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }))
    expect(screen.getByText('bulk:3')).toBeTruthy()
    rerender(<DataTable query={makeQuery({}, { page: 2 })} {...props} />)
    expect(screen.queryByText(/bulk:/)).toBeNull()
  })

  it('binds the search box to setQuery and pages through the pager', () => {
    const query = makeQuery({ total: 120, pages: 3 })
    render(<DataTable query={query} columns={columns} getRowId={(h) => h.id} ariaLabel="Hosts" searchPlaceholder="Search hosts" />)
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search hosts' }), { target: { value: '10.0' } })
    expect(query.setQuery).toHaveBeenCalledWith('10.0')
    expect(screen.getByText('1–50 of 120')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(query.setPage).toHaveBeenCalledWith(2)
    fireEvent.click(screen.getByRole('button', { name: 'Last page' }))
    expect(query.setPage).toHaveBeenCalledWith(3)
  })

  it('expands detail rows', () => {
    render(
      <DataTable
        query={makeQuery()}
        columns={columns}
        getRowId={(h) => h.id}
        ariaLabel="Hosts"
        renderExpanded={(h) => <p>details of {h.hostname}</p>}
      />
    )
    fireEvent.keyDown(rows()[1], { key: 'Enter' })
    expect(screen.getByText('details of WS-02')).toBeTruthy()
  })
})
