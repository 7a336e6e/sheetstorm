"use client"

/**
 * Global keyboard shortcuts and their help dialog (`?`).
 *
 *   mod+K   command palette (registered by CommandPalette)
 *   g i     go to incidents
 *   g d     go to dashboard
 *   n       new item in the current list (PrimaryActionProvider)
 *   ?       this help
 *   Esc     close dialogs
 *
 * Mount <ShortcutsHelp /> once (dashboard layout).
 */
import { useRouter } from 'next/navigation'
import { create } from 'zustand'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useHotkey } from '@/hooks/use-hotkeys'

interface ShortcutsHelpState {
  open: boolean
  setOpen: (open: boolean) => void
}

export const useShortcutsHelp = create<ShortcutsHelpState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
}))

export const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ['mod', 'K'], label: 'Open the command palette' },
  { keys: ['g', 'i'], label: 'Go to incidents' },
  { keys: ['g', 'd'], label: 'Go to dashboard' },
  { keys: ['n'], label: 'New item in the current list' },
  { keys: ['?'], label: 'Show keyboard shortcuts' },
  { keys: ['Esc'], label: 'Close dialogs and panels' },
]

function isMac(): boolean {
  if (typeof navigator === 'undefined') return false
  return /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent || '')
}

function Key({ k }: { k: string }) {
  const label = k === 'mod' ? (isMac() ? '⌘' : 'Ctrl') : k
  return (
    <kbd className="min-w-[1.5rem] rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-center font-mono text-xs text-foreground">
      {label}
    </kbd>
  )
}

export function ShortcutsHelp() {
  const router = useRouter()
  const open = useShortcutsHelp((s) => s.open)
  const setOpen = useShortcutsHelp((s) => s.setOpen)

  useHotkey('?', () => setOpen(true))
  useHotkey('g i', () => router.push('/dashboard/incidents'))
  useHotkey('g d', () => router.push('/dashboard'))

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md border-white/10 bg-slate-900">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Shortcuts are ignored while typing in a field, except the palette.</DialogDescription>
        </DialogHeader>
        <dl className="divide-y divide-white/10">
          {SHORTCUTS.map((s) => (
            <div key={s.label} className="flex items-center justify-between gap-4 py-2 text-sm">
              <dt className="text-muted-foreground">{s.label}</dt>
              <dd className="flex shrink-0 items-center gap-1">
                {s.keys.map((k, i) => (
                  <Key key={i} k={k} />
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}
