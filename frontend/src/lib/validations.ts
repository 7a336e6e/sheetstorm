import { z } from 'zod'

// ── Incident Schemas ──────────────────────────────────────────────

export const createIncidentSchema = z.object({
  title: z
    .string()
    .min(1, 'Title is required')
    .max(200, 'Title must be 200 characters or fewer'),
  description: z.string().max(5000, 'Description must be 5000 characters or fewer').optional(),
  severity: z.enum(['low', 'medium', 'high', 'critical'], {
    required_error: 'Severity is required',
  }),
  classification: z.string().optional(),
})

export type CreateIncidentInput = z.infer<typeof createIncidentSchema>

export const editIncidentSchema = z.object({
  title: z
    .string()
    .min(1, 'Title is required')
    .max(200, 'Title must be 200 characters or fewer'),
  executive_summary: z.string().max(10000).optional(),
  severity: z.enum(['low', 'medium', 'high', 'critical']),
  phase: z.number().int().min(1).max(6),
  classification: z.string().optional(),
})

export type EditIncidentInput = z.infer<typeof editIncidentSchema>

// ── Host Schemas ──────────────────────────────────────────────────

export const hostSchema = z.object({
  hostname: z
    .string()
    .min(1, 'Hostname is required')
    .max(255, 'Hostname must be 255 characters or fewer')
    .regex(/^[a-zA-Z0-9._-]+$/, 'Hostname contains invalid characters'),
  ip_address: z
    .string()
    .max(45)
    .refine(
      (val) =>
        !val ||
        /^(\d{1,3}\.){3}\d{1,3}$/.test(val) ||
        /^[a-fA-F0-9:]+$/.test(val),
      { message: 'Invalid IP address format' }
    )
    .optional()
    .or(z.literal('')),
  system_type: z.enum(['workstation', 'server', 'domain_controller'], {
    required_error: 'System type is required',
  }),
  os_version: z.string().max(100).optional().or(z.literal('')),
  containment_status: z.enum(['active', 'isolated', 'reimaged', 'decommissioned']),
  evidence: z.string().max(5000).optional().or(z.literal('')),
  notes: z.string().max(5000).optional().or(z.literal('')),
})

export type HostInput = z.infer<typeof hostSchema>

// ── Task Schemas ──────────────────────────────────────────────────

export const taskSchema = z.object({
  title: z
    .string()
    .min(1, 'Title is required')
    .max(200, 'Title must be 200 characters or fewer'),
  description: z.string().max(5000).optional().or(z.literal('')),
  priority: z.enum(['low', 'medium', 'high', 'critical']),
  phase: z
    .string()
    .optional()
    .or(z.literal('')),
  assignee_id: z.string().uuid('Invalid assignee').optional().or(z.literal('')),
  due_date: z
    .string()
    .optional()
    .or(z.literal(''))
    .refine(
      (val) => !val || !isNaN(new Date(val).getTime()),
      { message: 'Invalid date format' }
    ),
})

export type TaskInput = z.infer<typeof taskSchema>

// ── Timeline Event Schemas ────────────────────────────────────────

export const timelineEventSchema = z.object({
  timestamp: z
    .string()
    .min(1, 'Timestamp is required')
    .refine(
      (val) => !isNaN(new Date(val).getTime()),
      { message: 'Invalid timestamp' }
    ),
  activity: z
    .string()
    .min(1, 'Activity description is required')
    .max(2000, 'Activity must be 2000 characters or fewer'),
  host_id: z.string().uuid().optional().or(z.literal('')),
  source: z.string().max(200).optional().or(z.literal('')),
  mitre_tactic: z.string().max(100).optional().or(z.literal('')),
  mitre_technique: z.string().max(100).optional().or(z.literal('')),
  is_key_event: z.boolean().default(false),
  is_ioc: z.boolean().default(false),
})

export type TimelineEventInput = z.infer<typeof timelineEventSchema>

// ── Account Schemas ───────────────────────────────────────────────

export const accountSchema = z.object({
  account_name: z
    .string()
    .min(1, 'Account name is required')
    .max(255),
  host_id: z.string().uuid().optional().or(z.literal('')),
  host_system: z.string().max(255).optional().or(z.literal('')),
  domain: z.string().max(255).optional().or(z.literal('')),
  account_type: z.enum(['domain', 'local', 'ftp', 'service', 'application', 'admin', 'other']),
  is_privileged: z.boolean().default(false),
  status: z.enum(['active', 'disabled', 'reset', 'deleted']),
  sid: z.string().max(200).optional().or(z.literal('')),
  notes: z.string().max(5000).optional().or(z.literal('')),
})

export type AccountInput = z.infer<typeof accountSchema>

// ── Utility: extract field errors ─────────────────────────────────

export function getFieldErrors(error: z.ZodError): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const issue of error.issues) {
    const key = issue.path.join('.')
    if (!errors[key]) {
      errors[key] = issue.message
    }
  }
  return errors
}

/**
 * Validate data against a Zod schema, returning either success data or field errors.
 */
export function validate<T>(
  schema: z.ZodSchema<T>,
  data: unknown
): { success: true; data: T } | { success: false; errors: Record<string, string> } {
  const result = schema.safeParse(data)
  if (result.success) {
    return { success: true, data: result.data }
  }
  return { success: false, errors: getFieldErrors(result.error) }
}
