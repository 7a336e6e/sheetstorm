/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { AlertTriangle } from "lucide-react"

export interface ConfirmOptions {
  title?: string
  description: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  variant?: "default" | "destructive"
  /**
   * Type-to-confirm: the confirm button stays disabled until the user types
   * exactly this text (case-sensitive). For irreversible bulk actions.
   */
  requireText?: string
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

interface ConfirmState extends ConfirmOptions {
  resolve: (value: boolean) => void
}

const ConfirmContext = React.createContext<ConfirmFn>(() => Promise.resolve(false))

export function useConfirm(): ConfirmFn {
  return React.useContext(ConfirmContext)
}

/**
 * Standard copy for deleting one thing:
 *   if (!(await confirmDelete(confirm, 'host', host.hostname))) return
 */
export function confirmDelete(
  confirm: ConfirmFn,
  noun: string,
  name?: string,
  extra?: Pick<ConfirmOptions, "requireText">
): Promise<boolean> {
  return confirm({
    title: `Delete ${noun}?`,
    description: name
      ? `"${name}" will be permanently deleted. This can't be undone.`
      : `This ${noun} will be permanently deleted. This can't be undone.`,
    confirmLabel: "Delete",
    variant: "destructive",
    ...extra,
  })
}

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<ConfirmState | null>(null)
  const [typed, setTyped] = React.useState("")
  const stateRef = React.useRef<ConfirmState | null>(null)

  const confirm = React.useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      // A newer request supersedes an open one: settle the old promise.
      stateRef.current?.resolve(false)
      const next = { ...options, resolve }
      stateRef.current = next
      setTyped("")
      setState(next)
    })
  }, [])

  const handleResponse = React.useCallback((value: boolean) => {
    stateRef.current?.resolve(value)
    stateRef.current = null
    setState(null)
    setTyped("")
  }, [])

  const textOk = !state?.requireText || typed === state.requireText
  const inputId = React.useId()

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state !== null && (
        <Dialog
          open={true}
          onOpenChange={(open) => {
            if (!open) handleResponse(false)
          }}
        >
          <DialogContent className="max-w-md z-[60]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {state.variant === "destructive" && (
                  <AlertTriangle className="h-5 w-5 text-destructive" />
                )}
                {state.title || "Confirm"}
              </DialogTitle>
              <DialogDescription>{state.description}</DialogDescription>
            </DialogHeader>
            {state.requireText && (
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (textOk) handleResponse(true)
                }}
              >
                <label htmlFor={inputId} className="text-sm text-muted-foreground">
                  Type <span className="font-mono font-semibold text-foreground">{state.requireText}</span> to confirm
                </label>
                <Input
                  id={inputId}
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  autoComplete="off"
                  autoFocus
                  spellCheck={false}
                />
              </form>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => handleResponse(false)}>
                {state.cancelLabel || "Cancel"}
              </Button>
              <Button
                variant={state.variant === "destructive" ? "destructive" : "default"}
                onClick={() => handleResponse(true)}
                disabled={!textOk}
              >
                {state.confirmLabel || "Confirm"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </ConfirmContext.Provider>
  )
}
