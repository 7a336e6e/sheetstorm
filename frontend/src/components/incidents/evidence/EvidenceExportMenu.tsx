"use client"

/**
 * Evidence exports.
 *
 *   register mode (no `item`)  CSV / PDF / verifiable bundle of the whole
 *                              register: needs `incidents:export` for every
 *                              format, so the menu is absent without it.
 *   item mode                  one item's custody paperwork: JSON, CSV, PDF
 *                              report and the printable form need only
 *                              `artifacts:read`; the verifiable bundle also
 *                              needs `incidents:export` (C24).
 *
 * The server enforces both; this just does not offer what would be refused.
 * Every export is written to the custody ledger / audit log.
 */
import { useState } from 'react'
import { Download, FileArchive, FileSpreadsheet, FileText, FileJson, Printer } from 'lucide-react'
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
import { evidenceApi } from '@/lib/endpoints/evidence'
import { notifyError, notifySuccess } from '@/lib/errors'
import type { EvidenceItem, ItemExportFormat, RegisterExportFormat } from '@/types'

export const EXPORT_PERMISSION = 'incidents:export'

export interface EvidenceExportMenuProps {
  incidentId: string
  /** Export this item's custody record; omit to export the whole register. */
  item?: Pick<EvidenceItem, 'id' | 'evidence_number'>
  /** Button label (register mode defaults to "Export register"). */
  label?: string
  variant?: 'default' | 'outline' | 'ghost'
}

export function EvidenceExportMenu({ incidentId, item, label, variant = 'outline' }: EvidenceExportMenuProps) {
  const canExport = usePermission(EXPORT_PERMISSION)
  const [busy, setBusy] = useState<string | null>(null)

  // The register has no export formats a user without incidents:export may use.
  if (!item && !canExport) return null

  const run = async (key: string, what: string, fn: () => Promise<string>) => {
    setBusy(key)
    try {
      const name = await fn()
      notifySuccess(`${what} downloaded`, name)
    } catch (e) {
      notifyError(e, `export ${what.toLowerCase()}`)
    } finally {
      setBusy(null)
    }
  }

  const exportItem = (fmt: ItemExportFormat, what: string) =>
    run(`item-${fmt}`, what, () => evidenceApi.exportItem(incidentId, item!.id, fmt))
  const exportRegister = (fmt: RegisterExportFormat, what: string) =>
    run(`register-${fmt}`, what, () => evidenceApi.exportRegister(incidentId, fmt))

  const triggerLabel = label ?? (item ? 'Export' : 'Export register')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={variant} size="sm" loading={!!busy} aria-label={item ? `Export ${item.evidence_number}` : triggerLabel}>
          <Download className="h-4 w-4" />
          {triggerLabel}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[16rem]">
        {item ? (
          <>
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
              {item.evidence_number} custody record. Each export is logged in the ledger.
            </DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => void exportItem('form', 'Custody form')}>
              <Printer className="mr-2 h-4 w-4" />
              Printable custody form (PDF)
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void exportItem('pdf', 'Custody report')}>
              <FileText className="mr-2 h-4 w-4" />
              Custody report (PDF)
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void exportItem('csv', 'Custody entries')}>
              <FileSpreadsheet className="mr-2 h-4 w-4" />
              Custody entries (CSV)
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void exportItem('json', 'Custody record')}>
              <FileJson className="mr-2 h-4 w-4" />
              Custody record (JSON)
            </DropdownMenuItem>
            {canExport && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => void exportItem('bundle', 'Verifiable bundle')}>
                  <FileArchive className="mr-2 h-4 w-4" />
                  Verifiable bundle (ZIP)
                </DropdownMenuItem>
              </>
            )}
          </>
        ) : (
          <>
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
              Evidence register for this incident
            </DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => void exportRegister('csv', 'Register CSV')}>
              <FileSpreadsheet className="mr-2 h-4 w-4" />
              Register (CSV)
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void exportRegister('pdf', 'Register PDF')}>
              <FileText className="mr-2 h-4 w-4" />
              Register (PDF)
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void exportRegister('bundle', 'Verifiable bundle')}>
              <FileArchive className="mr-2 h-4 w-4" />
              Verifiable bundle (ZIP)
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
