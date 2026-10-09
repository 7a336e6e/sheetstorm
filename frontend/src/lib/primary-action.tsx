"use client"

/**
 * "Primary action" registry: the `n` shortcut triggers the create action of
 * the list the user is looking at.
 *
 * DataTable registers its (permitted) `primaryAction` together with its root
 * element. On `n`, the provider runs the most recently registered action
 * whose element is currently visible, so lists in hidden, kept-mounted tabs
 * never fire. Mount <PrimaryActionProvider> once (dashboard layout); without
 * it registration is a no-op.
 */
import * as React from 'react'
import { useHotkey } from '@/hooks/use-hotkeys'

export interface PrimaryAction {
  label: string
  onSelect: () => void
}

interface Registration {
  id: number
  action: React.MutableRefObject<PrimaryAction | null>
  element: React.RefObject<HTMLElement | null>
}

interface Registry {
  register: (r: Registration) => () => void
}

const PrimaryActionContext = React.createContext<Registry | null>(null)

/**
 * Visible = attached and not inside a `hidden` / `inert` / `aria-hidden`
 * subtree. Kept-mounted inactive tabs must use the `hidden` attribute (Radix
 * `TabsContent forceMount` does), not only a CSS class.
 */
export function isElementVisible(el: HTMLElement | null): boolean {
  if (!el || !el.isConnected) return false
  return !el.closest('[hidden], [aria-hidden="true"], [inert]')
}

/** The action `n` would run right now, if any. */
export function pickPrimaryAction(regs: Registration[]): PrimaryAction | null {
  for (let i = regs.length - 1; i >= 0; i--) {
    const r = regs[i]
    if (r.action.current && isElementVisible(r.element.current)) return r.action.current
  }
  return null
}

export function PrimaryActionProvider({ children }: { children: React.ReactNode }) {
  const regs = React.useRef<Registration[]>([])

  const registry = React.useMemo<Registry>(
    () => ({
      register: (r) => {
        regs.current = [...regs.current, r]
        return () => {
          regs.current = regs.current.filter((x) => x.id !== r.id)
        }
      },
    }),
    []
  )

  useHotkey('n', () => {
    pickPrimaryAction(regs.current)?.onSelect()
  })

  return <PrimaryActionContext.Provider value={registry}>{children}</PrimaryActionContext.Provider>
}

let nextId = 1

/**
 * Register `action` (null = none) for the list rooted at `element`.
 * Stays registered while mounted; always runs the latest `action`.
 */
export function usePrimaryActionRegistration(
  action: PrimaryAction | null,
  element: React.RefObject<HTMLElement | null>
): void {
  const registry = React.useContext(PrimaryActionContext)
  const actionRef = React.useRef<PrimaryAction | null>(action)
  React.useEffect(() => {
    actionRef.current = action
  }, [action])

  React.useEffect(() => {
    if (!registry) return
    return registry.register({ id: nextId++, action: actionRef, element })
  }, [registry, element])
}
