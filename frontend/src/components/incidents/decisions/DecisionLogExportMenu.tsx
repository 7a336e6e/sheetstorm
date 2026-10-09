"use client"

/**
 * Decision-log export (CSV / JSON / PDF). Needs `incidents:export` (C24);
 * the privileged variant is offered only with `decisions:read_privileged`.
 * Every export is audited server-side.
 */
import { useState } from 'react'
import { Download, FileJson, FileSpreadsheet, FileText, Lock } from 'lucide-react'
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
import { decisionLog, type DecisionLogExportFormat } from '@/lib/endpoints/decisions'
import { notifyError } from '@/lib/errors'

export function DecisionLogExportMenu({ incidentId, incidentNumber }: { incidentId: string; incidentNumber?: number }) {
  const canExport = usePermission('incidents:export')
  const canPrivileged = usePermission('decisions:read_privileged')
  const [busy, setBusy] = useState(false)
  if (!canExport) return null

  const run = async (format: DecisionLogExportFormat, includePrivileged = false) => {
    setBusy(true)
    try {
      await decisionLog.exportLog(incidentId, format, {
        includePrivileged,
        includeRevisions: format === 'json',
        fallbackName: `incident_${incidentNumber ?? 'x'}_decision_log.${format}`,
      })
    } catch (err) {
      notifyError(err, 'export the decision log')
    } finally {
      setBusy(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" loading={busy} aria-label="Export decision log">
          <Download className="h-4 w-4" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[15rem]">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Decisions and response actions. Exports are audited.
        </DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => void run('pdf')}>
          <FileText className="mr-2 h-4 w-4" /> Report (PDF)
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void run('csv')}>
          <FileSpreadsheet className="mr-2 h-4 w-4" /> Table (CSV)
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void run('json')}>
          <FileJson className="mr-2 h-4 w-4" /> Full record with signed revisions (JSON)
        </DropdownMenuItem>
        {canPrivileged && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void run('json', true)}>
              <Lock className="mr-2 h-4 w-4" /> Including privileged decisions (JSON)
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
