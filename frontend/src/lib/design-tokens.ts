/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

/**
 * Centralized design tokens for consistent styling across the application.
 * All colors are functional - they communicate meaning, not decoration.
 */

// Severity levels for incidents and issues
export const severityColors = {
  critical: {
    bg: 'bg-red-100 dark:bg-red-900/50',
    text: 'text-red-800 dark:text-red-200',
    border: 'border-red-200 dark:border-red-800',
    badge: 'badge-critical',
  },
  high: {
    bg: 'bg-orange-100 dark:bg-orange-900/50',
    text: 'text-orange-800 dark:text-orange-200',
    border: 'border-orange-200 dark:border-orange-800',
    badge: 'badge-high',
  },
  medium: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/50',
    text: 'text-yellow-800 dark:text-yellow-200',
    border: 'border-yellow-200 dark:border-yellow-800',
    badge: 'badge-medium',
  },
  low: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-800 dark:text-green-200',
    border: 'border-green-200 dark:border-green-800',
    badge: 'badge-low',
  },
} as const

// Incident status
export const statusColors = {
  open: {
    bg: 'bg-blue-100 dark:bg-blue-900/50',
    text: 'text-blue-800 dark:text-blue-200',
    border: 'border-blue-200 dark:border-blue-800',
  },
  contained: {
    bg: 'bg-purple-100 dark:bg-purple-900/50',
    text: 'text-purple-800 dark:text-purple-200',
    border: 'border-purple-200 dark:border-purple-800',
  },
  eradicated: {
    bg: 'bg-indigo-100 dark:bg-indigo-900/50',
    text: 'text-indigo-800 dark:text-indigo-200',
    border: 'border-indigo-200 dark:border-indigo-800',
  },
  recovered: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-800 dark:text-green-200',
    border: 'border-green-200 dark:border-green-800',
  },
  closed: {
    bg: 'bg-gray-100 dark:bg-gray-800/50',
    text: 'text-gray-800 dark:text-gray-200',
    border: 'border-gray-200 dark:border-gray-700',
  },
} as const

// IR lifecycle phases (1-6)
export const phaseColors = {
  1: { name: 'Preparation', bg: 'bg-slate-100 dark:bg-slate-800', text: 'text-slate-700 dark:text-slate-300' },
  2: { name: 'Identification', bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-700 dark:text-blue-300' },
  3: { name: 'Containment', bg: 'bg-yellow-100 dark:bg-yellow-900/50', text: 'text-yellow-700 dark:text-yellow-300' },
  4: { name: 'Eradication', bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-700 dark:text-orange-300' },
  5: { name: 'Recovery', bg: 'bg-green-100 dark:bg-green-900/50', text: 'text-green-700 dark:text-green-300' },
  6: { name: 'Lessons Learned', bg: 'bg-purple-100 dark:bg-purple-900/50', text: 'text-purple-700 dark:text-purple-300' },
} as const

// Attack graph node types
export const nodeTypeColors = {
  host: { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-800 dark:text-blue-200' },
  account: { bg: 'bg-purple-100 dark:bg-purple-900/50', text: 'text-purple-800 dark:text-purple-200' },
  malware: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-800 dark:text-red-200' },
  tool: { bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-800 dark:text-orange-200' },
  technique: { bg: 'bg-yellow-100 dark:bg-yellow-900/50', text: 'text-yellow-800 dark:text-yellow-200' },
  ioc: { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-800 dark:text-gray-200' },
} as const

// Task priority
export const priorityColors = {
  urgent: severityColors.critical,
  high: severityColors.high,
  medium: severityColors.medium,
  low: severityColors.low,
} as const

// Helper function to get severity class names
export function getSeverityClasses(severity: keyof typeof severityColors): string {
  const colors = severityColors[severity]
  return `${colors.bg} ${colors.text}`
}

// Helper function to get status class names
export function getStatusClasses(status: keyof typeof statusColors): string {
  const colors = statusColors[status]
  return `${colors.bg} ${colors.text}`
}

// Helper function to get phase class names
export function getPhaseClasses(phase: keyof typeof phaseColors): string {
  const colors = phaseColors[phase]
  return `${colors.bg} ${colors.text}`
}

export type Severity = keyof typeof severityColors
export type Status = keyof typeof statusColors
export type Phase = keyof typeof phaseColors
export type NodeType = keyof typeof nodeTypeColors
export type Priority = keyof typeof priorityColors
