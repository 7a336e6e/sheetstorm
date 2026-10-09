'use client'

/**
 * A secret shown exactly once (invite link, reset link, temporary password):
 * read-only field + copy button + warning. The value lives only in the
 * owning dialog's state, which clears it on close; it is never cached,
 * stored or logged.
 */
import { useState } from 'react'
import { AlertTriangle, Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function OneTimeSecret({
  label,
  value,
  warning,
  monospace = true,
}: {
  label: string
  value: string
  warning: string
  monospace?: boolean
}) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard blocked (insecure origin / permissions): the field stays
      // selectable for a manual copy.
      setCopied(false)
    }
  }

  return (
    <div className="space-y-2">
      <div
        className="flex gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400"
        role="status"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p>{warning}</p>
      </div>
      <Label htmlFor="one-time-secret">{label}</Label>
      <div className="flex gap-2">
        <Input
          id="one-time-secret"
          readOnly
          value={value}
          onFocus={(e) => e.currentTarget.select()}
          className={monospace ? 'font-mono text-xs' : undefined}
          autoComplete="off"
          spellCheck={false}
        />
        <Button type="button" variant="outline" onClick={() => void copy()} aria-label={`Copy ${label.toLowerCase()}`}>
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          <span className="ml-1.5">{copied ? 'Copied' : 'Copy'}</span>
        </Button>
      </div>
    </div>
  )
}
