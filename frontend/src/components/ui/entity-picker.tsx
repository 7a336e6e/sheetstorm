"use client"

/**
 * Async, server-searched pickers (ARIA combobox + listbox).
 *
 *   <UserPicker value={id} onChange={(id, user) => …} ariaLabel="Assignee" />
 *   <IncidentPicker value={id} onChange={…} ariaLabel="Incident" />
 *
 * Results come from `<endpoint>?q=&per_page=20&…params` (debounced 250ms,
 * stale requests aborted), so they are never truncated to a first page.
 * Keyboard: ArrowUp/Down, Enter selects, Escape closes.
 */
import * as React from 'react'
import { Check, ChevronsUpDown, Loader2, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import api, { isAbortError, withQuery } from '@/lib/api'
import { describeError } from '@/lib/errors'
import type { Incident, PaginatedResponse, User } from '@/types'

export const PICKER_DEBOUNCE_MS = 250

export interface EntityPickerProps<T> {
  value: string | null
  onChange: (id: string | null, item: T | null) => void
  /** List endpoint honouring the pagination contract, e.g. `/users`. */
  endpoint: string
  /** Fixed query params, e.g. `{ is_active: true, sort: 'name' }`. */
  params?: Record<string, string | number | boolean | undefined>
  getId: (item: T) => string
  getLabel: (item: T) => string
  getDescription?: (item: T) => string | undefined
  /** Label for the current value when the item is not loaded yet. */
  valueLabel?: string
  /** Fetch the current item when no label is known (e.g. `id => /users/${id}`). */
  itemEndpoint?: (id: string) => string
  ariaLabel: string
  placeholder?: string
  emptyMessage?: string
  disabled?: boolean
  clearable?: boolean
  perPage?: number
  className?: string
}

export function EntityPicker<T>({
  value,
  onChange,
  endpoint,
  params,
  getId,
  getLabel,
  getDescription,
  valueLabel,
  itemEndpoint,
  ariaLabel,
  placeholder = 'Search…',
  emptyMessage = 'No matches',
  disabled = false,
  clearable = true,
  perPage = 20,
  className,
}: EntityPickerProps<T>) {
  const [open, setOpen] = React.useState(false)
  const [text, setText] = React.useState('')
  const [debounced, setDebounced] = React.useState('')
  const [results, setResults] = React.useState<T[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [active, setActive] = React.useState(0)
  const [selectedLabel, setSelectedLabel] = React.useState<string | null>(valueLabel ?? null)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const listId = React.useId()
  const paramsSig = JSON.stringify(params ?? {})

  // Keep the shown label in step with the value.
  const [labelFor, setLabelFor] = React.useState<string | null>(value)
  if (labelFor !== value) {
    setLabelFor(value)
    setSelectedLabel(value ? valueLabel ?? null : null)
  }

  React.useEffect(() => {
    if (!value || selectedLabel || !itemEndpoint) return
    const ctrl = new AbortController()
    api
      .get<T>(itemEndpoint(value), { signal: ctrl.signal })
      .then((item) => setSelectedLabel(getLabel(item)))
      .catch(() => undefined)
    return () => ctrl.abort()
    // getLabel/itemEndpoint are usually inline; the value is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, selectedLabel])

  // Debounce typing.
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(text.trim()), PICKER_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [text])

  // Search while open.
  React.useEffect(() => {
    if (!open) return
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    const fixed = JSON.parse(paramsSig) as Record<string, string | number | boolean | undefined>
    api
      .get<PaginatedResponse<T>>(withQuery(endpoint, { ...fixed, q: debounced || undefined, per_page: perPage }), {
        signal: ctrl.signal,
      })
      .then((res) => {
        setResults(res.items ?? [])
        setActive(0)
      })
      .catch((err) => {
        if (isAbortError(err)) return
        setResults([])
        setError(describeError(err).description)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [open, debounced, endpoint, paramsSig, perPage])

  // Close on outside click.
  React.useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const select = (item: T) => {
    setSelectedLabel(getLabel(item))
    setLabelFor(getId(item))
    onChange(getId(item), item)
    setText('')
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) setOpen(true)
      else setActive((i) => Math.min(results.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter') {
      if (open && results[active]) {
        e.preventDefault()
        select(results[active])
      }
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault()
        e.stopPropagation()
        setOpen(false)
      }
    }
  }

  const activeId = open && results[active] ? `${listId}-opt-${active}` : undefined
  const shown = open ? text : selectedLabel ?? (value ? '…' : '')

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      <div
        className={cn(
          'flex h-10 items-center rounded-md border border-input bg-background px-3 text-sm focus-within:ring-1 focus-within:ring-ring',
          disabled && 'pointer-events-none opacity-50'
        )}
      >
        <input
          role="combobox"
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          value={shown}
          placeholder={selectedLabel ?? placeholder}
          disabled={disabled}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
          }}
          onKeyDown={onKeyDown}
          className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
        {loading && <Loader2 className="ml-1 h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />}
        {clearable && value && !disabled && (
          <button
            type="button"
            aria-label={`Clear ${ariaLabel}`}
            onClick={() => {
              onChange(null, null)
              setSelectedLabel(null)
              setText('')
            }}
            className="ml-1 rounded p-0.5 text-muted-foreground hover:bg-white/10 hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 text-muted-foreground/50" aria-hidden />
      </div>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          className="absolute z-50 mt-1 max-h-[240px] w-full overflow-y-auto rounded-md border border-border bg-popover py-1 shadow-lg"
        >
          {error ? (
            <li className="px-3 py-3 text-center text-sm text-destructive">{error}</li>
          ) : results.length === 0 ? (
            <li className="px-3 py-3 text-center text-sm text-muted-foreground">{loading ? 'Searching…' : emptyMessage}</li>
          ) : (
            results.map((item, i) => {
              const id = getId(item)
              const isSelected = id === value
              const description = getDescription?.(item)
              return (
                <li
                  key={id}
                  id={`${listId}-opt-${i}`}
                  role="option"
                  aria-selected={isSelected}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => select(item)}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 px-3 py-2 text-sm',
                    i === active && 'bg-accent/15'
                  )}
                >
                  <Check className={cn('h-3.5 w-3.5 shrink-0 text-primary', !isSelected && 'opacity-0')} aria-hidden />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-foreground">{getLabel(item)}</span>
                    {description && <span className="truncate text-[11px] text-muted-foreground">{description}</span>}
                  </div>
                </li>
              )
            })
          )}
        </ul>
      )}
    </div>
  )
}

type PickerShortcutProps<T> = Omit<
  EntityPickerProps<T>,
  'endpoint' | 'getId' | 'getLabel' | 'getDescription' | 'itemEndpoint'
>

/** Active users of the caller's org, searched by name/email. */
export function UserPicker(props: PickerShortcutProps<User>) {
  return (
    <EntityPicker<User>
      placeholder="Search users…"
      {...props}
      endpoint="/users"
      params={{ is_active: true, sort: 'name', ...props.params }}
      getId={(u) => u.id}
      getLabel={(u) => u.name || u.email}
      getDescription={(u) => (u.name ? u.email : undefined)}
      itemEndpoint={(id) => `/users/${id}`}
    />
  )
}

/** Incidents the caller can access, searched by title / number. */
export function IncidentPicker(props: PickerShortcutProps<Incident>) {
  return (
    <EntityPicker<Incident>
      placeholder="Search incidents…"
      {...props}
      endpoint="/incidents"
      getId={(i) => i.id}
      getLabel={(i) => `#${i.incident_number} ${i.title}`}
      getDescription={(i) => i.status}
      itemEndpoint={(id) => `/incidents/${id}`}
    />
  )
}
