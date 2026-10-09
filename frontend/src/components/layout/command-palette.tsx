"use client"

/**
 * Command palette (mod+K, or the sidebar "Search" button).
 *
 * - Navigation commands, filtered by permission, match instantly.
 * - From 3 characters on, entities come from `GET /search` (debounced 250ms,
 *   stale requests aborted), grouped by type with the facet counts, 5 per
 *   group, plus "See all N results" → /dashboard/search?q=.
 * - ARIA combobox + listbox with `aria-activedescendant`: ArrowUp/Down move
 *   (wrapping), Home/End jump, Enter runs the active option, Escape closes.
 * - Recent queries (text only) are kept in sessionStorage.
 */
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { create } from 'zustand'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  FileText,
  History,
  Keyboard,
  LayoutDashboard,
  Loader2,
  Plus,
  Search,
  User,
} from 'lucide-react'
import api, { isAbortError, withQuery } from '@/lib/api'
import { describeError } from '@/lib/errors'
import { useHotkey } from '@/hooks/use-hotkeys'
import { usePermissionCheck, type PermissionRequirement } from '@/components/auth/permission-gate'
import {
  loadRecentSearches,
  normalizeSearchQuery,
  PALETTE_MIN_QUERY,
  saveRecentSearch,
  SEARCH_ENDPOINT,
  SEARCH_TYPE_LABELS,
  SEARCH_TYPE_ORDER,
  searchResultHref,
  splitHighlight,
} from '@/lib/global-search'
import { useShortcutsHelp } from '@/components/layout/shortcuts-help'
import { adminNavigation } from '@/components/layout/nav-config'
import { cn } from '@/lib/utils'
import type { SearchResponse, SearchResult } from '@/types'

export const PALETTE_DEBOUNCE_MS = 250
export const PALETTE_PER_GROUP = 5

// ── Open state (shared with the sidebar button) ───────────────────────

interface PaletteState {
  open: boolean
  setOpen: (open: boolean) => void
  toggle: () => void
}

export const useCommandPalette = create<PaletteState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),
}))

// ── Navigation commands ───────────────────────────────────────────────

export interface NavCommand {
  id: string
  label: string
  href?: string
  /** Runs instead of navigating. */
  action?: 'shortcuts'
  icon: LucideIcon
  keywords?: string
  /** Any of these permissions (empty/undefined = everyone). */
  anyOf?: string[]
}

/**
 * Admin entries mirror the route guards (`auth-provider.tsx`, guardrails
 * §3.7 `anyOf`); gating here is cosmetic, the pages and API enforce.
 */
export const NAV_COMMANDS: NavCommand[] = [
  { id: 'nav-dashboard', label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, keywords: 'home overview' },
  { id: 'nav-incidents', label: 'Incidents', href: '/dashboard/incidents', icon: AlertTriangle, keywords: 'cases list' },
  {
    id: 'nav-new-incident',
    label: 'New incident',
    href: '/dashboard/incidents/new',
    icon: Plus,
    keywords: 'create open case',
    anyOf: ['incidents:create'],
  },
  { id: 'nav-search', label: 'Search all records', href: '/dashboard/search', icon: Search, keywords: 'find global' },
  { id: 'nav-reports', label: 'Reports', href: '/dashboard/reports', icon: FileText, anyOf: ['reports:read'] },
  { id: 'nav-threat-intel', label: 'Threat intel', href: '/dashboard/threat-intel', icon: Search, keywords: 'lookup enrich ioc' },
  { id: 'nav-kb', label: 'Knowledge base', href: '/dashboard/knowledge-base', icon: BookOpen, keywords: 'kb docs lolbas' },
  // Admin pages: same items and permission sets as the sidebar (nav-config.ts).
  ...adminNavigation.map((item) => ({
    id: `nav-${item.id}`,
    label: item.name,
    href: item.href,
    icon: item.icon,
    keywords: item.keywords,
    anyOf: item.anyOf,
  })),
  { id: 'nav-profile', label: 'Profile', href: '/dashboard/profile', icon: User, keywords: 'account mfa password' },
  { id: 'nav-shortcuts', label: 'Keyboard shortcuts', action: 'shortcuts', icon: Keyboard, keywords: 'help keys hotkeys' },
]

/** Permitted commands matching `q` (label or keywords, case-insensitive). */
export function filterNavCommands(
  commands: NavCommand[],
  q: string,
  can: (perm: PermissionRequirement, mode?: 'all' | 'any') => boolean
): NavCommand[] {
  const needle = q.trim().toLowerCase()
  return commands.filter((c) => {
    if (c.anyOf && c.anyOf.length > 0 && !can(c.anyOf, 'any')) return false
    if (!needle) return true
    return `${c.label} ${c.keywords ?? ''}`.toLowerCase().includes(needle)
  })
}

// ── Options model ─────────────────────────────────────────────────────

type Option =
  | { kind: 'nav'; id: string; group: string; command: NavCommand }
  | { kind: 'recent'; id: string; group: string; query: string }
  | { kind: 'result'; id: string; group: string; result: SearchResult; href: string }
  | { kind: 'all'; id: string; group: string; total: number }

function Highlight({ text, q }: { text: string; q: string }) {
  return (
    <>
      {splitHighlight(text, q).map((part, i) =>
        part.match ? (
          <mark key={i} className="rounded-sm bg-cyan-500/20 text-cyan-200">
            {part.text}
          </mark>
        ) : (
          <React.Fragment key={i}>{part.text}</React.Fragment>
        )
      )}
    </>
  )
}

export function CommandPalette() {
  const open = useCommandPalette((s) => s.open)
  const setOpen = useCommandPalette((s) => s.setOpen)
  const toggle = useCommandPalette((s) => s.toggle)

  useHotkey('mod+k', () => toggle())

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/70 data-[state=open]:animate-overlay-in data-[state=closed]:animate-overlay-out" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[12vh] z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border border-white/10 bg-slate-900 shadow-2xl data-[state=open]:animate-dialog-in data-[state=closed]:animate-dialog-out"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          {open && <PaletteBody onClose={() => setOpen(false)} />}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

function PaletteBody({ onClose }: { onClose: () => void }) {
  const router = useRouter()
  const can = usePermissionCheck()
  const openShortcuts = useShortcutsHelp((s) => s.setOpen)
  const listId = React.useId()

  const [text, setText] = React.useState('')
  const [debounced, setDebounced] = React.useState('')
  const [data, setData] = React.useState<{ q: string; res: SearchResponse } | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [active, setActive] = React.useState(0)
  const [recent, setRecent] = React.useState<string[]>(() => loadRecentSearches())

  const q = normalizeSearchQuery(text)
  const searching = debounced.length >= PALETTE_MIN_QUERY

  React.useEffect(() => {
    const value = normalizeSearchQuery(text)
    const t = setTimeout(() => setDebounced(value), PALETTE_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [text])

  React.useEffect(() => {
    if (debounced.length < PALETTE_MIN_QUERY) return
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    api
      .get<SearchResponse>(withQuery(SEARCH_ENDPOINT, { q: debounced, per_page: 20, sort: 'relevance' }), {
        signal: ctrl.signal,
      })
      .then((res) => setData({ q: debounced, res }))
      .catch((err) => {
        if (isAbortError(err) || ctrl.signal.aborted) return
        setData(null)
        setError(describeError(err).description)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [debounced])

  // ── Build the flat option list ──────────────────────────────────────
  const options = React.useMemo<Option[]>(() => {
    const out: Option[] = []
    if (!q) {
      recent.forEach((r, i) => out.push({ kind: 'recent', id: `recent-${i}`, group: 'Recent searches', query: r }))
    }
    filterNavCommands(NAV_COMMANDS, q, can).forEach((command) =>
      out.push({ kind: 'nav', id: command.id, group: 'Go to', command })
    )
    const res = searching && data && data.q === debounced ? data.res : null
    if (res) {
      SEARCH_TYPE_ORDER.forEach((type) => {
        const hits = res.results.filter((r) => r.type === type).slice(0, PALETTE_PER_GROUP)
        hits.forEach((result) => {
          const href = searchResultHref(result)
          if (!href) return
          const count = res.facets[type] ?? hits.length
          out.push({
            kind: 'result',
            id: `res-${type}-${result.id}`,
            group: `${SEARCH_TYPE_LABELS[type]} (${count})`,
            result,
            href,
          })
        })
      })
      if (res.total > 0) out.push({ kind: 'all', id: 'see-all', group: 'All results', total: res.total })
    }
    return out
  }, [q, recent, can, searching, data, debounced])

  // Keep the active option in range; reset it when the query changes.
  const [activeFor, setActiveFor] = React.useState(q)
  if (activeFor !== q) {
    setActiveFor(q)
    setActive(0)
  }
  const safeActive = options.length ? Math.min(active, options.length - 1) : -1
  const activeOption = safeActive >= 0 ? options[safeActive] : undefined

  React.useEffect(() => {
    if (!activeOption) return
    document.getElementById(`${listId}-${activeOption.id}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [activeOption, listId])

  const go = (href: string) => {
    onClose()
    router.push(href)
  }

  const run = (option: Option) => {
    switch (option.kind) {
      case 'nav':
        if (option.command.action === 'shortcuts') {
          onClose()
          openShortcuts(true)
        } else if (option.command.href) {
          go(option.command.href)
        }
        break
      case 'recent':
        setText(option.query)
        break
      case 'result':
        setRecent(saveRecentSearch(debounced))
        go(option.href)
        break
      case 'all':
        setRecent(saveRecentSearch(debounced))
        go(`/dashboard/search?q=${encodeURIComponent(debounced)}`)
        break
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const n = options.length
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        if (n) setActive((safeActive + 1) % n)
        break
      case 'ArrowUp':
        e.preventDefault()
        if (n) setActive((safeActive - 1 + n) % n)
        break
      case 'Home':
        if (n && !text) {
          e.preventDefault()
          setActive(0)
        }
        break
      case 'End':
        if (n && !text) {
          e.preventDefault()
          setActive(n - 1)
        }
        break
      case 'Enter':
        if (activeOption) {
          e.preventDefault()
          run(activeOption)
        }
        break
    }
  }

  // Group consecutive options under headings.
  const groups: { name: string; items: { option: Option; index: number }[] }[] = []
  options.forEach((option, index) => {
    const last = groups[groups.length - 1]
    if (last && last.name === option.group) last.items.push({ option, index })
    else groups.push({ name: option.group, items: [{ option, index }] })
  })

  const showLoading = loading && searching
  const statusText = showLoading
    ? 'Searching…'
    : error && searching
      ? error
      : q.length > 0 && q.length < PALETTE_MIN_QUERY
        ? `Type at least ${PALETTE_MIN_QUERY} characters to search records`
        : searching && data?.q === debounced && data.res.total === 0
          ? 'No matching records'
          : null

  return (
    <div className="flex max-h-[70vh] flex-col">
      <div className="flex items-center gap-2 border-b border-white/10 px-3">
        <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <input
          autoFocus
          role="combobox"
          aria-label="Search or jump to"
          aria-expanded={options.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeOption ? `${listId}-${activeOption.id}` : undefined}
          value={text}
          maxLength={200}
          placeholder="Search incidents, hosts, IOCs… or jump to a page"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          className="h-12 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
        {showLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />}
        <kbd className="hidden rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">Esc</kbd>
      </div>

      <ul id={listId} role="listbox" aria-label="Results" className="flex-1 overflow-y-auto py-2">
        {groups.map((g) => (
          <li key={g.name} role="presentation">
            <div className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground" aria-hidden>
              {g.name}
            </div>
            <ul role="group" aria-label={g.name}>
              {g.items.map(({ option, index }) => (
                <OptionRow
                  key={option.id}
                  id={`${listId}-${option.id}`}
                  option={option}
                  q={debounced}
                  active={index === safeActive}
                  onHover={() => setActive(index)}
                  onSelect={() => run(option)}
                />
              ))}
            </ul>
          </li>
        ))}
      </ul>

      {statusText && (
        <p role="status" className="border-t border-white/10 px-3 py-2 text-xs text-muted-foreground">
          {statusText}
        </p>
      )}
    </div>
  )
}

function OptionRow({
  id,
  option,
  q,
  active,
  onHover,
  onSelect,
}: {
  id: string
  option: Option
  q: string
  active: boolean
  onHover: () => void
  onSelect: () => void
}) {
  let icon: React.ReactNode
  let label: React.ReactNode
  let description: React.ReactNode = null

  switch (option.kind) {
    case 'nav': {
      const Icon = option.command.icon
      icon = <Icon className="h-4 w-4" />
      label = option.command.label
      break
    }
    case 'recent':
      icon = <History className="h-4 w-4" />
      label = option.query
      break
    case 'result': {
      const r = option.result
      icon = <ArrowRight className="h-4 w-4" />
      label = <Highlight text={r.title || '(untitled)'} q={q} />
      const where = r.type === 'incident' ? null : r.incident_title
      description = (
        <>
          {where && <span>{where}</span>}
          {where && r.snippet && <span aria-hidden> · </span>}
          {r.snippet && <Highlight text={r.snippet} q={q} />}
        </>
      )
      break
    }
    case 'all':
      icon = <Search className="h-4 w-4" />
      label = `See all ${option.total.toLocaleString()} results`
      break
  }

  return (
    <li
      id={id}
      role="option"
      aria-selected={active}
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onClick={onSelect}
      className={cn(
        'mx-2 flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm',
        active ? 'bg-white/10 text-foreground' : 'text-foreground/80'
      )}
    >
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate">{label}</span>
        {description && <span className="block truncate text-xs text-muted-foreground">{description}</span>}
      </span>
    </li>
  )
}
