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
import { AlertTriangle } from "lucide-react"

interface ConfirmOptions {
  title?: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: "default" | "destructive"
}

interface ConfirmState extends ConfirmOptions {
  resolve: (value: boolean) => void
}

const ConfirmContext = React.createContext<
  (options: ConfirmOptions) => Promise<boolean>
>(() => Promise.resolve(false))

export function useConfirm() {
  return React.useContext(ConfirmContext)
}

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<ConfirmState | null>(null)

  const confirm = React.useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      setState({ ...options, resolve })
    })
  }, [])

  const handleResponse = React.useCallback(
    (value: boolean) => {
      state?.resolve(value)
      setState(null)
    },
    [state]
  )

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
            <DialogFooter>
              <Button variant="outline" onClick={() => handleResponse(false)}>
                {state.cancelLabel || "Cancel"}
              </Button>
              <Button
                variant={state.variant === "destructive" ? "destructive" : "default"}
                onClick={() => handleResponse(true)}
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
