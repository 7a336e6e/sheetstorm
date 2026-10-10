"use client"

/**
 * Server-driven table on top of `usePaginatedQuery`.
 *
 * - States: skeleton rows (first load), dimmed rows + top bar (refetch),
 *   error panel with Retry, "empty" vs "no matches" (when q/filters are set).
 * - Sorting: header buttons cycle asc → desc → default, with `aria-sort`.
 * - Selection is page-scoped and cleared on any page/sort/filter change.
 * - Keyboard (roving tabindex over rows): ArrowUp/Down, Home/End, Enter =
 *   onRowClick (or expand), Space = toggle selection, `.` / Shift+F10 = open
 *   the row menu.
 * - Row actions live in an always-visible kebab menu, filtered by
 *   permission; the menu is hidden when nothing is left.
 * - `primaryAction` is permission-gated and registered for the `n` shortcut.
 */
import * as React from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  MoreHorizontal,
  Plus,
  Search,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { describeError } from '@/lib/errors'
import { usePrimaryActionRegistration } from '@/lib/primary-action'
import type { PaginatedQuery } from '@/hooks/use-paginated-query'
import { usePermission, usePermissionCheck } from '@/components/auth/permission-gate'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export interface DataTableColumn<T> {
  id: string
  header: React.ReactNode
  cell: (row: T) => React.ReactNode
  /** Server sort key; makes the header a sort button. */
  sortKey?: string
  className?: string
  hideBelow?: 'sm' | 'md' | 'lg'
}

export interface RowAction {
  label: string
  icon?: LucideIcon
  onSelect: () => void
  destructive?: boolean
  permission?: string | string[]
  disabled?: boolean
}

export interface DataTableProps<T> {
  query: PaginatedQuery<T>
  columns: DataTableColumn<T>[]
  getRowId: (r: T) => string
  ariaLabel: string
  /** Renders a search box bound to `query.setQuery`. */
  searchPlaceholder?: string
  /** Filter controls (use <FilterSelect>). */
  toolbar?: React.ReactNode
  /** Create button; also what the `n` shortcut runs. */
  primaryAction?: { label: string; onSelect: () => void; permission: string | string[] }
  rowActions?: (r: T) => RowAction[]
  /** Names the row for assistive tech ("Actions for <label>"); default "row N". */
  rowLabel?: (r: T) => string
  onRowClick?: (r: T) => void
  /** Scrolled into view and highlighted (deep links). */
  focusedRowId?: string | null
  selectable?: boolean
  bulkActions?: (ids: string[], clear: () => void) => React.ReactNode
  empty?: { title: string; description?: string; action?: React.ReactNode }
  pageSizes?: number[]
  renderExpanded?: (r: T) => React.ReactNode
  className?: string
}

const HIDE_BELOW: Record<NonNullable<DataTableColumn<unknown>['hideBelow']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
}

const DEFAULT_PAGE_SIZES = [25, 50, 100, 200]
const ALL = '__all__'

/** Current direction of `sortKey` in a `sort` param (first field only). */
export function sortDirection(sort: string | undefined, sortKey: string): 'asc' | 'desc' | null {
  const first = sort?.split(',')[0]?.trim()
  if (!first) return null
  if (first === sortKey) return 'asc'
  if (first === `-${sortKey}`) return 'desc'
  return null
}

/** asc → desc → default (undefined). */
export function nextSort(sort: string | undefined, sortKey: string): string | undefined {
  const dir = sortDirection(sort, sortKey)
  if (dir === null) return sortKey
  if (dir === 'asc') return `-${sortKey}`
  return undefined
}

export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
  className,
}: {
  label: string
  value?: string
  onChange(v?: string): void
  options: { value: string; label: string }[]
  /** Label of the "no filter" option (default `All <label>`). */
  allLabel?: string
  className?: string
}) {
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
      <SelectTrigger aria-label={label} className={cn('h-9 w-[160px]', className)}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{allLabel ?? `All ${label.toLowerCase()}`}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function DataTablePager({
  page,
  pages,
  perPage,
  total,
  onPage,
  onPerPage,
  pageSizes = DEFAULT_PAGE_SIZES,
  className,
}: {
  page: number
  pages: number
  perPage: number
  total: number
  onPage(n: number): void
  onPerPage?(n: number): void
  pageSizes?: number[]
  className?: string
}) {
  const lastPage = Math.max(1, pages)
  const from = total === 0 ? 0 : (page - 1) * perPage + 1
  const to = Math.min(total, page * perPage)
  return (
    <div className={cn('flex flex-wrap items-center justify-between gap-3 px-1 py-2 text-sm', className)}>
      <p className="text-muted-foreground tabular-nums" aria-live="polite">
        {total === 0 ? '0 results' : `${from}–${to} of ${total.toLocaleString()}`}
      </p>
      <div className="flex items-center gap-2">
        {onPerPage && (
          <Select value={String(perPage)} onValueChange={(v) => onPerPage(Number(v))}>
            <SelectTrigger aria-label="Rows per page" className="h-8 w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from(new Set([...pageSizes, perPage]))
                .sort((a, b) => a - b)
                .map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n} / page
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        )}
        <Button variant="ghost" size="icon-sm" aria-label="First page" disabled={page <= 1} onClick={() => onPage(1)}>
          <ChevronsLeft className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="tabular-nums text-muted-foreground">
          {page} / {lastPage}
        </span>
        <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={page >= lastPage} onClick={() => onPage(page + 1)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Last page" disabled={page >= lastPage} onClick={() => onPage(lastPage)}>
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

function RowMenu({
  actions,
  open,
  onOpenChange,
  rowLabel,
}: {
  actions: RowAction[]
  open: boolean
  onOpenChange(open: boolean): void
  rowLabel: string
}) {
  const normal = actions.filter((a) => !a.destructive)
  const destructive = actions.filter((a) => a.destructive)
  const item = (a: RowAction) => {
    const Icon = a.icon
    return (
      <DropdownMenuItem
        key={a.label}
        disabled={a.disabled}
        onSelect={() => a.onSelect()}
        className={cn(a.destructive && 'text-destructive focus:text-destructive')}
      >
        {Icon && <Icon className="mr-2 h-4 w-4" />}
        {a.label}
      </DropdownMenuItem>
    )
  }
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Actions for ${rowLabel}`}
          className="text-muted-foreground hover:text-foreground"
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
        {normal.map(item)}
        {normal.length > 0 && destructive.length > 0 && <DropdownMenuSeparator />}
        {destructive.map(item)}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function DataTable<T>({
  query,
  columns,
  getRowId,
  ariaLabel,
  searchPlaceholder,
  toolbar,
  primaryAction,
  rowActions,
  rowLabel,
  onRowClick,
  focusedRowId,
  selectable = false,
  bulkActions,
  empty,
  pageSizes = DEFAULT_PAGE_SIZES,
  renderExpanded,
  className,
}: DataTableProps<T>) {
  const can = usePermissionCheck()
  const canPrimary = usePermission(primaryAction?.permission ?? [])
  const rootRef = React.useRef<HTMLDivElement>(null)
  const { state, items } = query

  // ── `n` shortcut ────────────────────────────────────────────────────
  const registered = React.useMemo(
    () => (primaryAction && canPrimary ? { label: primaryAction.label, onSelect: primaryAction.onSelect } : null),
    [primaryAction, canPrimary]
  )
  usePrimaryActionRegistration(registered, rootRef)

  // ── Search input (local text, debounced by the query) ───────────────
  const [search, setSearch] = React.useState(state.q ?? '')
  const [syncedQ, setSyncedQ] = React.useState(state.q)
  if (state.q !== syncedQ) {
    // External change (URL navigation, reset): adopt it.
    setSyncedQ(state.q)
    setSearch(state.q ?? '')
  }

  // ── Selection: page-scoped ──────────────────────────────────────────
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set())
  const stateSig = JSON.stringify(state)
  const [selectionSig, setSelectionSig] = React.useState(stateSig)
  if (selectionSig !== stateSig) {
    setSelectionSig(stateSig)
    if (selected.size) setSelected(new Set())
  }
  const clearSelection = React.useCallback(() => setSelected(new Set()), [])
  const pageIds = items.map(getRowId)
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id))
  const someSelected = !allSelected && pageIds.some((id) => selected.has(id))
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  // ── Rows: roving focus, menus, expansion ────────────────────────────
  const [activeIndex, setActiveIndex] = React.useState(0)
  const [menuRowId, setMenuRowId] = React.useState<string | null>(null)
  const [expanded, setExpanded] = React.useState<Set<string>>(() => new Set())
  const rowRefs = React.useRef<Map<string, HTMLTableRowElement>>(new Map())
  const safeActive = Math.min(activeIndex, Math.max(0, items.length - 1))

  const focusRow = (index: number) => {
    const clamped = Math.max(0, Math.min(items.length - 1, index))
    setActiveIndex(clamped)
    const id = pageIds[clamped]
    if (id !== undefined) rowRefs.current.get(id)?.focus()
  }

  const toggleExpanded = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  // Deep-link highlight.
  React.useEffect(() => {
    if (!focusedRowId) return
    const el = rowRefs.current.get(focusedRowId)
    el?.scrollIntoView?.({ block: 'center' })
  }, [focusedRowId, items])

  const filtersActive = !!state.q || Object.keys(state.filters).length > 0
  const visibleActions = (row: T) => (rowActions ? rowActions(row).filter((a) => !a.permission || can(a.permission)) : [])
  const hasActionsColumn = !!rowActions
  const colCount = columns.length + (selectable ? 1 : 0) + (renderExpanded ? 1 : 0) + (hasActionsColumn ? 1 : 0)

  const onRowKeyDown = (e: React.KeyboardEvent<HTMLTableRowElement>, row: T, index: number) => {
    if (e.target !== e.currentTarget) return // keys inside cell controls
    const id = getRowId(row)
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        focusRow(index + 1)
        break
      case 'ArrowUp':
        e.preventDefault()
        focusRow(index - 1)
        break
      case 'Home':
        e.preventDefault()
        focusRow(0)
        break
      case 'End':
        e.preventDefault()
        focusRow(items.length - 1)
        break
      case 'Enter':
        e.preventDefault()
        if (onRowClick) onRowClick(row)
        else if (renderExpanded) toggleExpanded(id)
        break
      case ' ':
        if (selectable) {
          e.preventDefault()
          toggle(id)
        }
        break
      case '.':
      case 'F10':
        if (e.key === 'F10' && !e.shiftKey) break
        if (visibleActions(row).length > 0) {
          e.preventDefault()
          setMenuRowId(id)
        }
        break
    }
  }

  const sortHeader = (col: DataTableColumn<T>) => {
    if (!col.sortKey) return col.header
    const dir = sortDirection(state.sort, col.sortKey)
    const Icon = dir === 'asc' ? ArrowUp : dir === 'desc' ? ArrowDown : ArrowUpDown
    return (
      <button
        type="button"
        className="inline-flex items-center gap-1 uppercase tracking-wider hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
        onClick={() => query.setSort(nextSort(state.sort, col.sortKey!))}
      >
        {col.header}
        <Icon className={cn('h-3 w-3', !dir && 'opacity-40')} aria-hidden />
      </button>
    )
  }

  const errorInfo = query.error ? describeError(query.error) : null
  const showBlockingError = !!query.error && items.length === 0
  const showEmpty = !query.isLoading && !query.error && items.length === 0

  return (
    <div ref={rootRef} className={cn('space-y-3', className)}>
      {(searchPlaceholder || toolbar || primaryAction) && (
        <div className="flex flex-wrap items-center gap-2">
          {searchPlaceholder && (
            <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                value={search}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="h-9 pl-8"
                onChange={(e) => {
                  setSearch(e.target.value)
                  query.setQuery(e.target.value)
                }}
              />
            </div>
          )}
          {toolbar}
          {primaryAction && canPrimary && (
            <Button size="sm" className="ml-auto" onClick={primaryAction.onSelect} title={`${primaryAction.label} (n)`}>
              <Plus className="h-4 w-4" />
              {primaryAction.label}
            </Button>
          )}
        </div>
      )}

      {selectable && selected.size > 0 && bulkActions && (
        <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
          <span className="tabular-nums">{selected.size} selected</span>
          {bulkActions(Array.from(selected), clearSelection)}
          <Button variant="ghost" size="sm" className="ml-auto" onClick={clearSelection}>
            Clear
          </Button>
        </div>
      )}

      {errorInfo && !showBlockingError && (
        <div role="alert" className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
          <AlertTriangle className="h-4 w-4 text-destructive" />
          <span>{errorInfo.description}</span>
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => void query.refetch()}>
            Retry
          </Button>
        </div>
      )}

      <div className="relative overflow-hidden rounded-lg border border-border bg-card">
        {query.isFetching && !query.isLoading && (
          <div className="absolute inset-x-0 top-0 z-10 h-0.5 animate-pulse bg-primary" aria-hidden />
        )}
        <div className="w-full overflow-auto">
          <table role="grid" aria-label={ariaLabel} aria-busy={query.isFetching || undefined} className="w-full caption-bottom text-sm">
            <thead className="border-b border-border">
              <tr>
                {selectable && (
                  <th className="w-10 px-4">
                    <Checkbox
                      aria-label="Select all rows on this page"
                      checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                      disabled={pageIds.length === 0}
                      onCheckedChange={(v) => setSelected(v === true ? new Set(pageIds) : new Set())}
                    />
                  </th>
                )}
                {renderExpanded && <th className="w-10 px-2"><span className="sr-only">Expand</span></th>}
                {columns.map((col) => {
                  const dir = col.sortKey ? sortDirection(state.sort, col.sortKey) : null
                  return (
                    <th
                      key={col.id}
                      scope="col"
                      aria-sort={col.sortKey ? (dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none') : undefined}
                      className={cn(
                        'h-11 px-4 text-left align-middle text-xs font-medium uppercase tracking-wider text-muted-foreground',
                        col.hideBelow && HIDE_BELOW[col.hideBelow],
                        col.className
                      )}
                    >
                      {sortHeader(col)}
                    </th>
                  )
                })}
                {hasActionsColumn && (
                  <th className="w-12 px-2">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className={cn('[&_tr:last-child]:border-0', query.isFetching && !query.isLoading && 'opacity-60 transition-opacity')}>
              {query.isLoading &&
                Array.from({ length: Math.min(state.perPage, 5) }).map((_, i) => (
                  <tr key={`sk-${i}`} className="border-b border-border" data-testid="skeleton-row">
                    {Array.from({ length: colCount }).map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    ))}
                  </tr>
                ))}

              {showBlockingError && errorInfo && (
                <tr>
                  <td colSpan={colCount} className="px-4 py-12">
                    <div role="alert" className="flex flex-col items-center gap-2 text-center">
                      <AlertTriangle className="h-6 w-6 text-destructive" />
                      <p className="text-sm font-medium">{errorInfo.title}</p>
                      <p className="max-w-sm text-xs text-muted-foreground">{errorInfo.description}</p>
                      <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                        Retry
                      </Button>
                    </div>
                  </td>
                </tr>
              )}

              {showEmpty && (
                <tr>
                  <td colSpan={colCount} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      {filtersActive ? (
                        <>
                          <p className="text-sm font-medium text-foreground/80">No matches</p>
                          <p className="text-xs text-muted-foreground">No rows match the current search or filters.</p>
                          <Button variant="outline" size="sm" onClick={query.resetFilters}>
                            Clear filters
                          </Button>
                        </>
                      ) : (
                        <>
                          <p className="text-sm font-medium text-foreground/80">{empty?.title ?? 'Nothing here yet'}</p>
                          {empty?.description && <p className="max-w-sm text-xs text-muted-foreground">{empty.description}</p>}
                          {empty?.action}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )}

              {!query.isLoading &&
                items.map((row, index) => {
                  const id = getRowId(row)
                  const actions = visibleActions(row)
                  const isSelected = selected.has(id)
                  const isExpanded = expanded.has(id)
                  const isFocused = focusedRowId === id
                  return (
                    <React.Fragment key={id}>
                      <tr
                        ref={(el) => {
                          if (el) rowRefs.current.set(id, el)
                          else rowRefs.current.delete(id)
                        }}
                        tabIndex={index === safeActive ? 0 : -1}
                        aria-selected={selectable ? isSelected : undefined}
                        aria-expanded={renderExpanded ? isExpanded : undefined}
                        data-state={isSelected ? 'selected' : undefined}
                        onFocus={() => setActiveIndex(index)}
                        onKeyDown={(e) => onRowKeyDown(e, row, index)}
                        onClick={onRowClick ? () => onRowClick(row) : undefined}
                        className={cn(
                          'border-b border-border outline-none hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring data-[state=selected]:bg-muted',
                          onRowClick && 'cursor-pointer',
                          isFocused && 'bg-primary/5 ring-1 ring-inset ring-primary/60'
                        )}
                      >
                        {selectable && (
                          <td className="w-10 px-4" onClick={(e) => e.stopPropagation()}>
                            <Checkbox aria-label="Select row" tabIndex={-1} checked={isSelected} onCheckedChange={() => toggle(id)} />
                          </td>
                        )}
                        {renderExpanded && (
                          <td className="w-10 px-2" onClick={(e) => e.stopPropagation()}>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              tabIndex={-1}
                              aria-label={isExpanded ? 'Collapse row' : 'Expand row'}
                              onClick={() => toggleExpanded(id)}
                            >
                              <ChevronDown className={cn('h-4 w-4 transition-transform', !isExpanded && '-rotate-90')} />
                            </Button>
                          </td>
                        )}
                        {columns.map((col) => (
                          <td key={col.id} className={cn('px-4 py-3 align-middle', col.hideBelow && HIDE_BELOW[col.hideBelow], col.className)}>
                            {col.cell(row)}
                          </td>
                        ))}
                        {hasActionsColumn && (
                          <td className="w-12 px-2 text-right" onClick={(e) => e.stopPropagation()}>
                            {actions.length > 0 && (
                              <RowMenu
                                actions={actions}
                                rowLabel={rowLabel?.(row) || `row ${index + 1}`}
                                open={menuRowId === id}
                                onOpenChange={(open) => setMenuRowId(open ? id : null)}
                              />
                            )}
                          </td>
                        )}
                      </tr>
                      {renderExpanded && isExpanded && (
                        <tr className="border-b border-border bg-muted/20">
                          <td colSpan={colCount} className="px-4 py-3">
                            {renderExpanded(row)}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
            </tbody>
          </table>
        </div>
      </div>

      {!query.isLoading && !showBlockingError && query.total > 0 && (
        <DataTablePager
          page={state.page}
          pages={query.pages}
          perPage={state.perPage}
          total={query.total}
          onPage={query.setPage}
          onPerPage={query.setPerPage}
          pageSizes={pageSizes}
        />
      )}
    </div>
  )
}
