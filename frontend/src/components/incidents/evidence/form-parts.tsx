"use client"

/**
 * Small form pieces shared by the evidence dialogs: a labelled field (the
 * label is wired to the control via the render-prop id) and a native select
 * for short enum lists (keyboard / mobile friendly, no portal).
 */
import * as React from 'react'
import { AlertTriangle } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

export function Field({
  label,
  required,
  error,
  hint,
  className,
  children,
}: {
  label: React.ReactNode
  required?: boolean
  error?: string | null
  hint?: React.ReactNode
  className?: string
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => React.ReactNode
}) {
  const id = React.useId()
  const msgId = `${id}-msg`
  const message = error || hint
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={id}>
        {label}
        {required && <span aria-hidden className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children({ id, describedBy: message ? msgId : undefined, invalid: !!error })}
      {message && (
        <p id={msgId} className={cn('text-xs', error ? 'text-destructive' : 'text-muted-foreground')}>
          {message}
        </p>
      )}
    </div>
  )
}

export interface NativeSelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'onChange'> {
  options: ReadonlyArray<{ value: string; label: string }>
  /** Text of the empty option; omit to have no empty option. */
  placeholder?: string
  onValueChange: (value: string) => void
  invalid?: boolean
}

export const NativeSelect = React.forwardRef<HTMLSelectElement, NativeSelectProps>(function NativeSelect(
  { options, placeholder, onValueChange, invalid, className, ...rest },
  ref
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50',
        invalid && 'border-destructive',
        className
      )}
      onChange={(e) => onValueChange(e.target.value)}
      {...rest}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
})

/** Inline server-side rejection inside a dialog (stays open so the user can fix it). */
export function FormError({ message }: { message: string | null | undefined }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
      <span>{message}</span>
    </div>
  )
}

/** Plain value for `<option>` lists built from a label map. */
export function optionsFrom<K extends string>(labels: Record<K, string>): Array<{ value: K; label: string }> {
  return (Object.keys(labels) as K[]).map((value) => ({ value, label: labels[value] }))
}
