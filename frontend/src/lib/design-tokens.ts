/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

/**
 * SheetStorm Design System — Centralized Design Tokens
 * ═══════════════════════════════════════════════════════
 * SINGLE SOURCE OF TRUTH for all semantic colors, phases, and status mappings.
 * All colors are functional — they communicate meaning, not decoration.
 * 
 * Palette: restrained, premium, enterprise-grade.
 * - Severity: soft red → warm amber → muted gold → desaturated teal
 * - Status: professional, differentiated hues
 * - Phase: subtle, distinguishable IR lifecycle colors
 * - NO neon, NO garish, NO default Tailwind raw colors outside this file.
 */

// ─── IR Lifecycle Phases (1-6) — THE canonical definition ─────────────────
// Used by: dashboard, incident detail, phase tracker, badges, landing page
export const PHASE_INFO = {
  1: {
    number: 1,
    name: 'Preparation',
    short: 'Prep',
    color: 'text-muted-foreground',
    bg: 'bg-muted',
    border: 'border-muted-foreground/20',
    accent: 'hsl(220, 10%, 55%)',
  },
  2: {
    number: 2,
    name: 'Identification',
    short: 'Ident',
    color: 'text-primary',
    bg: 'bg-primary/10',
    border: 'border-primary/20',
    accent: 'hsl(215, 55%, 55%)',
  },
  3: {
    number: 3,
    name: 'Containment',
    short: 'Contain',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    accent: 'hsl(38, 65%, 50%)',
  },
  4: {
    number: 4,
    name: 'Eradication',
    short: 'Erad',
    color: 'text-orange-600 dark:text-orange-400',
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/20',
    accent: 'hsl(24, 60%, 50%)',
  },
  5: {
    number: 5,
    name: 'Recovery',
    short: 'Recov',
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/20',
    accent: 'hsl(160, 45%, 45%)',
  },
  6: {
    number: 6,
    name: 'Lessons Learned',
    short: 'Lessons',
    color: 'text-secondary',
    bg: 'bg-secondary/10',
    border: 'border-secondary/20',
    accent: 'hsl(258, 28%, 58%)',
  },
} as const

// ─── Status → Phase mapping ──────────────────────────────────────────────
export const STATUS_OPTIONS = {
  open: { label: 'Open', phase: 1, phaseName: 'Preparation', color: 'text-primary', bg: 'bg-primary/10' },
  investigating: { label: 'Investigating', phase: 2, phaseName: 'Identification', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-500/10' },
  contained: { label: 'Contained', phase: 3, phaseName: 'Containment', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-500/10' },
  eradicated: { label: 'Eradicated', phase: 4, phaseName: 'Eradication', color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-500/10' },
  recovered: { label: 'Recovered', phase: 5, phaseName: 'Recovery', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-500/10' },
  closed: { label: 'Closed', phase: 6, phaseName: 'Lessons Learned', color: 'text-muted-foreground', bg: 'bg-muted' },
} as const

// ─── Severity Colors ─────────────────────────────────────────────────────
// Soft, professional. Not garish.
export const severityColors = {
  critical: {
    bg: 'bg-red-500/10 dark:bg-red-500/15',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500/20 dark:border-red-500/25',
    badge: 'badge-critical',
    dot: 'bg-red-500',
    accent: 'hsl(0, 55%, 55%)',
  },
  high: {
    bg: 'bg-amber-500/10 dark:bg-amber-500/15',
    text: 'text-amber-700 dark:text-amber-400',
    border: 'border-amber-500/20 dark:border-amber-500/25',
    badge: 'badge-high',
    dot: 'bg-amber-500',
    accent: 'hsl(38, 65%, 50%)',
  },
  medium: {
    bg: 'bg-yellow-500/10 dark:bg-yellow-500/12',
    text: 'text-yellow-700 dark:text-yellow-400',
    border: 'border-yellow-500/20 dark:border-yellow-500/20',
    badge: 'badge-medium',
    dot: 'bg-yellow-500',
    accent: 'hsl(48, 55%, 50%)',
  },
  low: {
    bg: 'bg-teal-500/10 dark:bg-teal-500/15',
    text: 'text-teal-700 dark:text-teal-400',
    border: 'border-teal-500/20 dark:border-teal-500/25',
    badge: 'badge-low',
    dot: 'bg-teal-500',
    accent: 'hsl(170, 40%, 45%)',
  },
} as const

// ─── Status Colors ───────────────────────────────────────────────────────
export const statusColors = {
  open: {
    bg: 'bg-primary/10',
    text: 'text-primary',
    border: 'border-primary/20',
    dot: 'bg-primary',
  },
  investigating: {
    bg: 'bg-blue-500/10',
    text: 'text-blue-600 dark:text-blue-400',
    border: 'border-blue-500/20',
    dot: 'bg-blue-500',
  },
  contained: {
    bg: 'bg-amber-500/10',
    text: 'text-amber-600 dark:text-amber-400',
    border: 'border-amber-500/20',
    dot: 'bg-amber-500',
  },
  eradicated: {
    bg: 'bg-orange-500/10',
    text: 'text-orange-600 dark:text-orange-400',
    border: 'border-orange-500/20',
    dot: 'bg-orange-500',
  },
  recovered: {
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-600 dark:text-emerald-400',
    border: 'border-emerald-500/20',
    dot: 'bg-emerald-500',
  },
  closed: {
    bg: 'bg-muted',
    text: 'text-muted-foreground',
    border: 'border-border',
    dot: 'bg-muted-foreground',
  },
} as const

// ─── Phase Colors (flat variant for backward compat) ─────────────────────
export const phaseColors = {
  1: { name: 'Preparation', bg: PHASE_INFO[1].bg, text: PHASE_INFO[1].color },
  2: { name: 'Identification', bg: PHASE_INFO[2].bg, text: PHASE_INFO[2].color },
  3: { name: 'Containment', bg: PHASE_INFO[3].bg, text: PHASE_INFO[3].color },
  4: { name: 'Eradication', bg: PHASE_INFO[4].bg, text: PHASE_INFO[4].color },
  5: { name: 'Recovery', bg: PHASE_INFO[5].bg, text: PHASE_INFO[5].color },
  6: { name: 'Lessons Learned', bg: PHASE_INFO[6].bg, text: PHASE_INFO[6].color },
} as const

// ─── TLP Colors ──────────────────────────────────────────────────────────
export const tlpColors = {
  RED: {
    bg: 'bg-red-500/10 dark:bg-red-500/15',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500/20',
    label: 'TLP:RED',
  },
  AMBER: {
    bg: 'bg-amber-500/10 dark:bg-amber-500/15',
    text: 'text-amber-700 dark:text-amber-400',
    border: 'border-amber-500/20',
    label: 'TLP:AMBER',
  },
  'AMBER+STRICT': {
    bg: 'bg-amber-500/10 dark:bg-amber-500/15',
    text: 'text-amber-700 dark:text-amber-400',
    border: 'border-amber-500/20',
    label: 'TLP:AMBER+STRICT',
  },
  GREEN: {
    bg: 'bg-emerald-500/10 dark:bg-emerald-500/15',
    text: 'text-emerald-700 dark:text-emerald-400',
    border: 'border-emerald-500/20',
    label: 'TLP:GREEN',
  },
  CLEAR: {
    bg: 'bg-muted',
    text: 'text-muted-foreground',
    border: 'border-border',
    label: 'TLP:CLEAR',
  },
} as const

// ─── Attack graph node types ─────────────────────────────────────────────
export const nodeTypeColors = {
  host: { bg: 'bg-primary/10', text: 'text-primary' },
  account: { bg: 'bg-secondary/10', text: 'text-secondary' },
  malware: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400' },
  tool: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400' },
  technique: { bg: 'bg-yellow-500/10', text: 'text-yellow-600 dark:text-yellow-400' },
  ioc: { bg: 'bg-muted', text: 'text-muted-foreground' },
} as const

// ─── Task priority (maps to severity) ───────────────────────────────────
export const priorityColors = {
  urgent: severityColors.critical,
  high: severityColors.high,
  medium: severityColors.medium,
  low: severityColors.low,
} as const

// ─── Helper functions ────────────────────────────────────────────────────

export function getSeverityClasses(severity: keyof typeof severityColors): string {
  const colors = severityColors[severity]
  return `${colors.bg} ${colors.text}`
}

export function getStatusClasses(status: keyof typeof statusColors): string {
  const colors = statusColors[status]
  return `${colors.bg} ${colors.text}`
}

export function getPhaseClasses(phase: keyof typeof phaseColors): string {
  const colors = phaseColors[phase]
  return `${colors.bg} ${colors.text}`
}

export function getTlpClasses(tlp: keyof typeof tlpColors): string {
  const colors = tlpColors[tlp]
  return `${colors.bg} ${colors.text} ${colors.border}`
}

// ─── Type exports ────────────────────────────────────────────────────────

export type Severity = keyof typeof severityColors
export type Status = keyof typeof statusColors
export type Phase = keyof typeof phaseColors
export type NodeType = keyof typeof nodeTypeColors
export type Priority = keyof typeof priorityColors
export type TLP = keyof typeof tlpColors
