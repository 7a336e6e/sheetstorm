"use client"

/**
 * Incident header "Export" menu (W3-DFIR-C; C35). Lives in the header so the
 * seven tab toolbars stay untouched: it reads the active tab's search, sort
 * and filters from the URL state written by `usePaginatedQuery`
 * (`<tab>.q`, `<tab>.sort`, `<tab>.f.<name>`) and asks the server for the same
 * rows as CSV.
 *
 * Needs `incidents:export` (shown only then); each CSV also needs that
 * entity's read permission. STIX 2.1 and the cross-incident IOC correlation
 * dialog are in here too. Everything exported carries the incident's TLP
 * (file name; STIX marking-definition).
 */
import { useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Download, FileJson, Link2, Loader2, Table2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { usePermission, usePermissionCheck } from '@/components/auth/permission-gate'
import { notifyError, notifySuccess } from '@/lib/errors'
import {
  EXPORT_PERMISSION,
  TAB_EXPORTS,
  TLP_LABELS,
  exportParamsFromUrl,
  exportsApi,
} from '@/lib/endpoints/exports'
import type { ExportEntity, TLPLevel } from '@/types'
import { IOCCorrelationDialog } from './IOCCorrelationDialog'

interface Props {
  incidentId: string
  incidentNumber?: number
  tlp?: TLPLevel
  /** The active `?tab=` id: its list filters are applied to the CSV. */
  activeTab: string
}

function describeFilters(params: Record<string, string>): string {
  const n = Object.keys(params).length
  return n === 0 ? 'no filters' : `${n} filter${n === 1 ? '' : 's'} applied`
}

export function ExportMenu({ incidentId, incidentNumber, tlp, activeTab }: Props) {
  const canExport = usePermission(EXPORT_PERMISSION)
  const can = usePermissionCheck()
  const searchParams = useSearchParams()
  const [busy, setBusy] = useState<string | null>(null)
  const [correlationOpen, setCorrelationOpen] = useState(false)

  if (!canExport) return null

  const current = TAB_EXPORTS[activeTab]
  const currentAllowed = !!current && can(current.permission)
  const currentParams = currentAllowed && searchParams ? exportParamsFromUrl(searchParams, activeTab) : {}
  const label = incidentNumber !== undefined ? `incident-${incidentNumber}` : 'incident'

  const run = async (key: string, what: string, job: () => Promise<string>) => {
    setBusy(key)
    try {
      const name = await job()
      notifySuccess('Export ready', `${name} has been downloaded.`)
    } catch (err) {
      notifyError(err, `export ${what}`)
    } finally {
      setBusy(null)
    }
  }

  const csv = (entity: ExportEntity, text: string, params: Record<string, string>, defang = false) =>
    run(`${entity}${defang ? ':defang' : ''}`, text, () =>
      exportsApi.downloadCsv(incidentId, entity, {
        params,
        defang,
        fallbackName: `${label}-${entity}${defang ? '-defanged' : ''}.csv`,
      })
    )

  const readable = Object.entries(TAB_EXPORTS).filter(([, t]) => can(t.permission))

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" disabled={busy !== null} aria-label="Export">
            {busy !== null ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            Export
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          {tlp && (
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
              Exports are marked {TLP_LABELS[tlp] ?? tlp.toUpperCase()}
            </DropdownMenuLabel>
          )}

          {currentAllowed && current && (
            <>
              <DropdownMenuItem onSelect={() => void csv(current.entity, `${current.label} CSV`, currentParams)}>
                <Table2 className="mr-2 h-4 w-4" />
                <span className="min-w-0">
                  CSV: {current.label}
                  <span className="block text-xs text-muted-foreground">
                    current tab, {describeFilters(currentParams)}
                  </span>
                </span>
              </DropdownMenuItem>
              {current.ioc && (
                <DropdownMenuItem
                  onSelect={() => void csv(current.entity, `defanged ${current.label} CSV`, currentParams, true)}
                >
                  <Table2 className="mr-2 h-4 w-4" />
                  <span className="min-w-0">
                    CSV: {current.label} (defanged)
                    <span className="block text-xs text-muted-foreground">evil[.]com, hxxp://</span>
                  </span>
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
            </>
          )}

          <DropdownMenuItem
            onSelect={() => void run('stix', 'the STIX bundle', () => exportsApi.downloadStix(incidentId, `${label}-stix.json`))}
          >
            <FileJson className="mr-2 h-4 w-4" />
            STIX 2.1 bundle
          </DropdownMenuItem>

          {readable.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                CSV, all rows
              </DropdownMenuLabel>
              {readable.map(([tab, t]) => (
                <DropdownMenuItem key={tab} onSelect={() => void csv(t.entity, `${t.label} CSV`, {})}>
                  <Table2 className="mr-2 h-4 w-4" />
                  {t.label}
                </DropdownMenuItem>
              ))}
            </>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCorrelationOpen(true)}>
            <Link2 className="mr-2 h-4 w-4" />
            Correlate IOCs across incidents
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <IOCCorrelationDialog open={correlationOpen} onOpenChange={setCorrelationOpen} incidentId={incidentId} />
    </>
  )
}
