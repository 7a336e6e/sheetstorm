"use client"

/**
 * Shows a new API key's secret exactly once (create / rotate).
 *
 * The full key lives only in the `result` prop the parent keeps in component
 * state: never in a store, the query cache or browser storage. The dialog
 * cannot be dismissed (Escape, outside click, X) until "I have stored this
 * key" is ticked; closing calls `onClose`, the parent drops `result`, and
 * the secret leaves the DOM. A rotation is explained with the grace period.
 */
import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Copy } from 'lucide-react'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { MCP_API_KEY_ENV, MCP_CONFIG_HINT, envSnippet } from '@/lib/endpoints/api-keys'
import type { ApiKeyWithSecret } from '@/types'

export interface SecretResult {
  key: ApiKeyWithSecret
  mode: 'created' | 'rotated'
  /** Rotation only: minutes the previous key keeps working. */
  graceMinutes?: number
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function CopyButton({ text, label, onCopied }: { text: string; label: string; onCopied?: () => void }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        const ok = await copyText(text)
        setState(ok ? 'copied' : 'failed')
        if (ok) onCopied?.()
        if (timer.current) clearTimeout(timer.current)
        timer.current = setTimeout(() => setState('idle'), 2000)
      }}
    >
      {state === 'copied' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed: select and copy manually' : label}
    </Button>
  )
}

export function ApiKeySecretDialog({
  result,
  onClose,
}: {
  /** null = closed. */
  result: SecretResult | null
  onClose: () => void
}) {
  return (
    <Dialog
      open={result !== null}
      onOpenChange={() => {
        // Closing is only possible through the acknowledged button below.
      }}
    >
      <DialogContent
        className="max-w-xl"
        onEscapeKeyDown={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        {/* Unmounts with `result`, so the acknowledgement and the secret never outlive it. */}
        {result && <SecretBody key={result.key.id} result={result} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function SecretBody({ result, onClose }: { result: SecretResult; onClose: () => void }) {
  const { key, mode, graceMinutes } = result
  const [stored, setStored] = useState(false)
  const secret = key.secret

  return (
    <>
      <DialogHeader>
        <DialogTitle>{mode === 'rotated' ? 'API key rotated' : 'API key created'}</DialogTitle>
        <DialogDescription>
          Copy the key for <span className="font-medium text-foreground">{key.name}</span> now. It is shown only once
          and cannot be retrieved later.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4">
        {mode === 'rotated' && (
          <p className="text-sm text-muted-foreground">
            {graceMinutes && graceMinutes > 0
              ? `The previous key keeps working for ${formatGrace(graceMinutes)}, then stops. Switch your clients to the new key before then.`
              : 'The previous key stopped working immediately.'}
          </p>
        )}

        <div className="space-y-2">
          <Label htmlFor="api-key-secret">API key</Label>
          <div className="flex items-center gap-2">
            <code
              id="api-key-secret"
              data-testid="api-key-secret"
              className="min-w-0 flex-1 select-all break-all rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs"
            >
              {secret}
            </code>
            <CopyButton text={secret} label="Copy" />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">Use it with the MCP server or bridge</p>
            <CopyButton text={envSnippet(secret)} label={`Copy ${MCP_API_KEY_ENV}=…`} />
          </div>
          <p className="text-xs text-muted-foreground">
            Export <code className="font-mono">{MCP_API_KEY_ENV}</code> in the environment your MCP client starts from,
            and reference it from the client config instead of pasting the key:
          </p>
          <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">
            {MCP_CONFIG_HINT}
          </pre>
        </div>

        <p role="note" className="flex items-start gap-2 text-xs text-amber-500">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          Treat this key like a password. Do not commit it or share it in chat. Revoke it from this page if it leaks.
        </p>
      </DialogBody>
      <DialogFooter className="items-center gap-3 sm:justify-between sm:space-x-0">
        <div className="flex items-center gap-2">
          <Checkbox id="api-key-stored" checked={stored} onCheckedChange={(v) => setStored(v === true)} />
          <Label htmlFor="api-key-stored" className="text-sm font-normal">
            I have stored this key
          </Label>
        </div>
        <Button type="button" disabled={!stored} onClick={onClose}>
          Done
        </Button>
      </DialogFooter>
    </>
  )
}

/** `90 minutes`, `2 hours`, `1 hour 30 minutes`. */
export function formatGrace(minutes: number): string {
  if (minutes < 60) return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const hours = `${h} ${h === 1 ? 'hour' : 'hours'}`
  return m ? `${hours} ${m} ${m === 1 ? 'minute' : 'minutes'}` : hours
}
