/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { PHASE_INFO, tlpColors, type TLP } from "@/lib/design-tokens"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default:
          "border-border bg-muted text-muted-foreground",
        outline:
          "border-border text-foreground",
        // Severity variants — restrained, desaturated enterprise palette
        critical:
          "border-red-500/20 bg-red-500/10 text-red-700 dark:border-red-500/25 dark:bg-red-500/15 dark:text-red-400",
        high:
          "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:border-amber-500/25 dark:bg-amber-500/15 dark:text-amber-400",
        medium:
          "border-yellow-500/20 bg-yellow-500/10 text-yellow-700 dark:border-yellow-500/20 dark:bg-yellow-500/12 dark:text-yellow-400",
        low:
          "border-teal-500/20 bg-teal-500/10 text-teal-700 dark:border-teal-500/25 dark:bg-teal-500/15 dark:text-teal-400",
        // Status variants — matching design token system
        open:
          "border-primary/20 bg-primary/10 text-primary",
        investigating:
          "border-blue-500/20 bg-blue-500/10 text-blue-600 dark:border-blue-500/25 dark:bg-blue-500/15 dark:text-blue-400",
        contained:
          "border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400",
        eradicated:
          "border-orange-500/20 bg-orange-500/10 text-orange-600 dark:text-orange-400",
        recovered:
          "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
        closed:
          "border-border bg-muted text-muted-foreground",
        // Utility variants
        destructive:
          "border-red-500/20 bg-red-500/10 text-red-700 dark:bg-red-500/15 dark:text-red-400",
        success:
          "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
        warning:
          "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
        info:
          "border-primary/20 bg-primary/10 text-primary",
        // Glass alias — restrained solid style
        glass:
          "border-border bg-muted/50 text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
  VariantProps<typeof badgeVariants> { }

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

// Severity Badge
interface SeverityBadgeProps extends Omit<BadgeProps, 'variant'> {
  severity: 'critical' | 'high' | 'medium' | 'low'
}

function SeverityBadge({ severity, children, ...props }: SeverityBadgeProps) {
  return (
    <Badge variant={severity} {...props}>
      {children || severity.charAt(0).toUpperCase() + severity.slice(1)}
    </Badge>
  )
}

// Status Badge
interface StatusBadgeProps extends Omit<BadgeProps, 'variant'> {
  status: 'open' | 'investigating' | 'contained' | 'eradicated' | 'recovered' | 'closed'
}

function StatusBadge({ status, children, ...props }: StatusBadgeProps) {
  return (
    <Badge variant={status} {...props}>
      {children || status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  )
}

// Phase Badge - for IR lifecycle phases (uses canonical PHASE_INFO)
interface PhaseBadgeProps extends Omit<BadgeProps, 'variant'> {
  phase: number
}

const phaseVariants: Record<number, BadgeProps['variant']> = {
  1: 'default',
  2: 'info',
  3: 'warning',
  4: 'high',
  5: 'success',
  6: 'default',
}

function PhaseBadge({ phase, ...props }: PhaseBadgeProps) {
  const info = PHASE_INFO[phase as keyof typeof PHASE_INFO]
  return (
    <Badge variant={phaseVariants[phase] || 'default'} {...props}>
      {phase}: {info?.name || 'Unknown'}
    </Badge>
  )
}

// Role Badge
interface RoleBadgeProps extends Omit<BadgeProps, 'variant'> {
  role: string
}

const roleVariants: Record<string, BadgeProps['variant']> = {
  Administrator: 'critical',
  'Incident Responder': 'high',
  Analyst: 'info',
  Manager: 'contained',
  Operator: 'success',
  Viewer: 'default',
}

function RoleBadge({ role, ...props }: RoleBadgeProps) {
  return (
    <Badge variant={roleVariants[role] || 'default'} {...props}>
      {role}
    </Badge>
  )
}

// TLP Badge
interface TLPBadgeProps extends Omit<BadgeProps, 'variant'> {
  tlp: string
}

const tlpVariantMap: Record<string, BadgeProps['variant']> = {
  red: 'critical',
  amber: 'warning',
  amber_strict: 'high',
  green: 'success',
  white: 'default',
  clear: 'default',
}

const tlpLabels: Record<string, string> = {
  white: 'TLP:WHITE',
  clear: 'TLP:CLEAR',
  green: 'TLP:GREEN',
  amber: 'TLP:AMBER',
  amber_strict: 'TLP:AMBER+STRICT',
  red: 'TLP:RED',
}

function TLPBadge({ tlp, ...props }: TLPBadgeProps) {
  const normalised = tlp?.toLowerCase().replace('+', '_') || 'amber'
  return (
    <Badge
      variant={tlpVariantMap[normalised] || 'warning'}
      className="font-mono text-[10px]"
      {...props}
    >
      {tlpLabels[normalised] || `TLP:${tlp?.toUpperCase()}`}
    </Badge>
  )
}

export { Badge, SeverityBadge, StatusBadge, PhaseBadge, TLPBadge, RoleBadge, badgeVariants }
