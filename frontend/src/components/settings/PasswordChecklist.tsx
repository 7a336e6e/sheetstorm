'use client'

/**
 * Live password checklist for the org password policy (hints only; the
 * server validates every write, including history and the email address).
 */
import { Check, X } from 'lucide-react'
import { checkPassword, DEFAULT_PASSWORD_RULES, describePasswordRules } from '@/lib/endpoints/security'
import { cn } from '@/lib/utils'
import type { PasswordRules } from '@/types'

export function PasswordChecklist({
  password,
  rules = DEFAULT_PASSWORD_RULES,
  className,
}: {
  password: string
  rules?: PasswordRules
  className?: string
}) {
  const checks = checkPassword(password, rules)
  return (
    <ul className={cn('mt-2 grid grid-cols-2 gap-1.5 text-xs', className)} aria-label="Password requirements">
      {checks.map(({ key, label, met }) => (
        <li key={key} className="flex items-center gap-1.5">
          {met ? (
            <Check className="h-3 w-3 text-emerald-400" aria-hidden />
          ) : (
            <X className="h-3 w-3 text-muted-foreground" aria-hidden />
          )}
          <span className={cn(met ? 'text-emerald-400' : 'text-muted-foreground')}>
            {label}
            <span className="sr-only">{met ? ' (met)' : ' (missing)'}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** The rules as one sentence, for a form's helper text. */
export function PasswordRulesHint({ rules, className }: { rules: PasswordRules; className?: string }) {
  return <p className={cn('text-xs text-muted-foreground', className)}>{describePasswordRules(rules)}</p>
}
