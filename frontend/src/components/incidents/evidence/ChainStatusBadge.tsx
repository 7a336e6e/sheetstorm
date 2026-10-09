"use client"

/**
 * Verdict of a custody-chain verification (`ChainVerification.status`), plus
 * the UI-only states `checking`, `error` and `unknown` (not run yet).
 *
 * Never colour alone: every state has its own icon and wording, and
 * `data-status` carries the machine value (tests, e2e).
 */
import { Loader2, ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX } from 'lucide-react'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ChainStatus } from '@/types'
import { CHAIN_STATUS_LABELS } from './evidence-helpers'

export type ChainBadgeStatus = ChainStatus | 'checking' | 'error' | 'unknown'

interface StatusStyle {
  label: string
  short: string
  variant: NonNullable<BadgeProps['variant']>
  Icon: typeof ShieldCheck
  spin?: boolean
}

export const CHAIN_BADGE_STYLES: Record<ChainBadgeStatus, StatusStyle> = {
  intact: { label: CHAIN_STATUS_LABELS.intact, short: 'Verified', variant: 'success', Icon: ShieldCheck },
  intact_with_unsigned_legacy: {
    label: CHAIN_STATUS_LABELS.intact_with_unsigned_legacy,
    short: 'Verified (legacy)',
    variant: 'info',
    Icon: ShieldCheck,
  },
  unverifiable: {
    label: CHAIN_STATUS_LABELS.unverifiable,
    short: 'Unverifiable',
    variant: 'warning',
    Icon: ShieldQuestion,
  },
  broken: { label: CHAIN_STATUS_LABELS.broken, short: 'Broken', variant: 'destructive', Icon: ShieldX },
  compromised: {
    label: CHAIN_STATUS_LABELS.compromised,
    short: 'Tampered',
    variant: 'destructive',
    Icon: ShieldAlert,
  },
  checking: { label: 'Verifying chain…', short: 'Verifying…', variant: 'default', Icon: Loader2, spin: true },
  error: { label: 'Could not verify chain', short: 'Verify failed', variant: 'warning', Icon: ShieldQuestion },
  unknown: { label: 'Chain not verified yet', short: 'Not verified', variant: 'default', Icon: ShieldQuestion },
}

export interface ChainStatusBadgeProps {
  status: ChainBadgeStatus
  /** Short wording (register rows, table cells). */
  compact?: boolean
  /** Extra tooltip text, e.g. "Head #12". */
  detail?: string
  /** Renders as a button (re-verify). */
  onClick?: () => void
  className?: string
}

export function ChainStatusBadge({ status, compact = false, detail, onClick, className }: ChainStatusBadgeProps) {
  const style = CHAIN_BADGE_STYLES[status] ?? CHAIN_BADGE_STYLES.unknown
  const { Icon } = style
  const text = compact ? style.short : style.label
  const title = detail ? `${style.label}. ${detail}` : style.label
  const content = (
    <>
      <Icon className={cn('mr-1 h-3.5 w-3.5 shrink-0', style.spin && 'animate-spin')} aria-hidden />
      {text}
    </>
  )
  const classes = cn('gap-0 whitespace-nowrap', onClick && 'cursor-pointer hover:opacity-80', className)

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        title={title}
        aria-label={`${style.label}. Click to verify again`}
        data-status={status}
        className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Badge variant={style.variant} className={classes}>
          {content}
        </Badge>
      </button>
    )
  }
  return (
    <Badge
      variant={style.variant}
      className={classes}
      title={title}
      role="status"
      aria-label={style.label}
      data-status={status}
    >
      {content}
    </Badge>
  )
}
