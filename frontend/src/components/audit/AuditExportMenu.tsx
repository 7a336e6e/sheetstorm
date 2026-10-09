"use client"

/**
 * Export the filtered audit log as CSV or JSONL. Rendered only for holders
 * of `audit_logs:export` (the endpoint enforces it too). The server caps the
 * export (422 `export_too_large`, never a partial file), rate-limits it
 * (10/h) and audits it before the first byte.
 */
import * as React from 'react'
import { Download, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { usePermission } from '@/components/auth/permission-gate'
import { auditLogsApi } from '@/lib/endpoints/admin'
import { notifyError, notifySuccess } from '@/lib/errors'
import type { AuditExportFormat, AuditLogFilters } from '@/types'

export const AUDIT_EXPORT_PERMISSION = 'audit_logs:export'

export function AuditExportMenu({ filters, disabled }: { filters: AuditLogFilters; disabled?: boolean }) {
  const allowed = usePermission(AUDIT_EXPORT_PERMISSION)
  const [busy, setBusy] = React.useState<AuditExportFormat | null>(null)

  if (!allowed) return null

  const run = async (format: AuditExportFormat) => {
    setBusy(format)
    try {
      const name = await auditLogsApi.exportFile(filters, format)
      notifySuccess('Audit log exported', name)
    } catch (err) {
      notifyError(err, 'export the audit log')
    } finally {
      setBusy(null)
    }
  }

  const filtered = Object.keys(filters).length > 0
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled || busy !== null}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          {filtered ? 'Rows matching the current filters' : 'All rows'}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void run('csv')}>CSV</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void run('jsonl')}>JSON Lines</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
