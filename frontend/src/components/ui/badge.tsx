/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default:
          "border-border bg-secondary text-secondary-foreground",
        outline:
          "border-border text-foreground",
        // Severity variants - functional colors
        critical:
          "border-red-200 bg-red-100 text-red-800 dark:border-red-800 dark:bg-red-900/50 dark:text-red-200",
        high:
          "border-orange-200 bg-orange-100 text-orange-800 dark:border-orange-800 dark:bg-orange-900/50 dark:text-orange-200",
        medium:
          "border-yellow-200 bg-yellow-100 text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200",
        low:
          "border-green-200 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-900/50 dark:text-green-200",
        // Status variants
        open:
          "border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-800 dark:bg-blue-900/50 dark:text-blue-200",
        contained:
          "border-purple-200 bg-purple-100 text-purple-800 dark:border-purple-800 dark:bg-purple-900/50 dark:text-purple-200",
        eradicated:
          "border-indigo-200 bg-indigo-100 text-indigo-800 dark:border-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200",
        recovered:
          "border-green-200 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-900/50 dark:text-green-200",
        closed:
          "border-gray-200 bg-gray-100 text-gray-800 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200",
        // Utility variants
        destructive:
          "border-red-200 bg-red-100 text-red-800 dark:border-red-800 dark:bg-red-900/50 dark:text-red-200",
        success:
          "border-green-200 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-900/50 dark:text-green-200",
        warning:
          "border-yellow-200 bg-yellow-100 text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200",
        info:
          "border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-800 dark:bg-blue-900/50 dark:text-blue-200",
        // Glass variant for backward compatibility (styled same as outline)
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
  status: 'open' | 'contained' | 'eradicated' | 'recovered' | 'closed'
}

function StatusBadge({ status, children, ...props }: StatusBadgeProps) {
  return (
    <Badge variant={status} {...props}>
      {children || status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  )
}

// Phase Badge - for IR lifecycle phases
interface PhaseBadgeProps extends Omit<BadgeProps, 'variant'> {
  phase: number
}

const phaseLabels: Record<number, string> = {
  1: 'Preparation',
  2: 'Identification',
  3: 'Containment',
  4: 'Eradication',
  5: 'Recovery',
  6: 'Lessons Learned',
}

const phaseVariants: Record<number, BadgeProps['variant']> = {
  1: 'default',
  2: 'info',
  3: 'warning',
  4: 'high',
  5: 'success',
  6: 'contained',
}

function PhaseBadge({ phase, ...props }: PhaseBadgeProps) {
  return (
    <Badge variant={phaseVariants[phase] || 'default'} {...props}>
      {phase}: {phaseLabels[phase] || 'Unknown'}
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

export { Badge, SeverityBadge, StatusBadge, PhaseBadge, RoleBadge, badgeVariants }
