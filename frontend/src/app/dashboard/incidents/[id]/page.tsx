"use client"

import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SeverityBadge, StatusBadge, PhaseBadge, TLPBadge } from '@/components/ui/badge'
import { TimeModeToggle } from '@/components/ui/time-mode-toggle'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useIncidentStore } from '@/lib/store'
import { describeError } from '@/lib/errors'
import { isApiError } from '@/lib/api'
import { subscribe } from '@/lib/query-cache'
import { usePermission, usePermissionCheck } from '@/components/auth/permission-gate'
import type { Incident, Versioned } from '@/types'
import { ArrowLeft, Upload, Zap, Edit2, Download } from 'lucide-react'

import { IRPhaseTracker } from '@/components/incidents/IRPhaseTracker'
import { ImportWizardModal } from '@/components/incidents/import-wizard/ImportWizardModal'
import { IncidentDetailSkeleton } from '@/components/incidents/detail/IncidentDetailSkeleton'
import { DescriptionBlock } from '@/components/incidents/detail/DescriptionBlock'
import { EditIncidentModal, UpdateStatusModal, ReportModal } from '@/components/incidents/detail/IncidentModals'
import { DEFAULT_TAB, TAB_REGISTRY, resolveTab } from './tabs'

/** Refetch the incident (header, counts) this long after the last list change. */
const INCIDENT_REFRESH_DEBOUNCE_MS = 400

export default function IncidentDetailPage() {
  // useSearchParams (tab/row and every tab's list state) needs a boundary.
  return (
    <Suspense fallback={<div className="p-8"><IncidentDetailSkeleton /></div>}>
      <IncidentDetail />
    </Suspense>
  )
}

function IncidentDetail() {
  const params = useParams()
  const incidentId = params.id as string
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { currentIncident, fetchIncident } = useIncidentStore()
  const can = usePermissionCheck()
  const canUpdateIncident = usePermission('incidents:update')
  const canGenerateReport = usePermission('reports:generate')

  const [loadError, setLoadError] = useState<unknown>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Modal visibility
  const [showEditModal, setShowEditModal] = useState(false)
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [showReportModal, setShowReportModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)

  const reloadIncident = useCallback(async () => {
    try {
      await fetchIncident(incidentId)
      setLoadError(null)
    } catch (err) {
      setLoadError(err)
    } finally {
      setIsLoading(false)
    }
  }, [fetchIncident, incidentId])

  useEffect(() => {
    if (!incidentId) return
    setIsLoading(true)
    void reloadIncident()
  }, [incidentId, reloadIncident])

  // Any list mutation under this incident (`invalidate('/incidents/<id>/…')`)
  // can change the header counts: refetch the incident, debounced.
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!incidentId) return
    const unsubscribe = subscribe(`/incidents/${incidentId}`, (ev) => {
      if (ev.type !== 'invalidate') return
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
      refreshTimer.current = setTimeout(() => void reloadIncident(), INCIDENT_REFRESH_DEBOUNCE_MS)
    })
    return () => {
      unsubscribe()
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
    }
  }, [incidentId, reloadIncident])

  // ─── Tabs: `?tab=<id>&row=<uuid>` ──────────────────────────────────────
  const visibleTabs = TAB_REGISTRY.filter((t) => can(t.permission))
  const activeTab = resolveTab(searchParams?.get('tab'), can, TAB_REGISTRY)
  const focusRow = searchParams?.get('row') || null

  // Lazy mount: a keep-mounted tab is rendered from its first visit on.
  const [visited, setVisited] = useState<Set<string>>(() => new Set([activeTab]))
  if (!visited.has(activeTab)) setVisited(new Set(visited).add(activeTab))

  const navigate = useCallback(
    (tab: string, row?: string | null) => {
      const next = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
      if (tab === DEFAULT_TAB) next.delete('tab')
      else next.set('tab', tab)
      if (row) next.set('row', row)
      else next.delete('row')
      const qs = next.toString()
      router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
    },
    [router, pathname]
  )

  // ─── Loading / Not Found ───────────────────────────────────────────────

  const incident = currentIncident && currentIncident.id === incidentId ? (currentIncident as Incident & Versioned) : null

  if (!incident) {
    if (isLoading) {
      return <div className="p-8"><IncidentDetailSkeleton /></div>
    }
    const notFound = !loadError || (isApiError(loadError) && (loadError.status === 404 || loadError.status === 403))
    return (
      <div className="p-8 space-y-3">
        <p className="text-muted-foreground">
          {notFound ? 'Incident not found' : describeError(loadError).description}
        </p>
        {!notFound && (
          <Button variant="outline" size="sm" onClick={() => { setIsLoading(true); void reloadIncident() }}>
            Retry
          </Button>
        )}
      </div>
    )
  }

  // ─── Render ────────────────────────────────────────────────────────────

  return (
    <>
      <div className="p-6 lg:p-8 space-y-6">
        {/* Header */}
        <div>
          <Link
            href="/dashboard/incidents"
            className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Incidents
          </Link>

          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div className="space-y-3 min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-sm text-muted-foreground">
                  #{incident.incident_number}
                </span>
                <SeverityBadge severity={incident.severity} />
                <StatusBadge status={incident.status} />
                <PhaseBadge phase={incident.phase} />
                <TLPBadge tlp={incident.tlp || 'amber'} />
                <TimeModeToggle />
              </div>
              <h1 className="text-2xl lg:text-3xl font-bold text-foreground">{incident.title}</h1>
              {incident.description && (
                <DescriptionBlock text={incident.description} />
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {canGenerateReport && (
                <Button variant="outline" onClick={() => setShowReportModal(true)}>
                  <Download className="mr-2 h-4 w-4" /> Generate Report
                </Button>
              )}
              {canUpdateIncident && (
                <>
                  <Button variant="outline" onClick={() => setShowImportModal(true)}>
                    <Upload className="mr-2 h-4 w-4" /> Import
                  </Button>
                  <Button variant="outline" onClick={() => setShowEditModal(true)}>
                    <Edit2 className="mr-2 h-4 w-4" /> Edit
                  </Button>
                  <Button onClick={() => setShowStatusModal(true)}>
                    <Zap className="mr-2 h-4 w-4" /> Update Status
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Phase Progress */}
        <IRPhaseTracker currentPhase={incident.phase} context="incident" />

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(tab) => navigate(tab)} className="w-full">
          <TabsList variant="underline" className="w-full justify-start flex-wrap h-auto gap-y-2">
            {visibleTabs.map(({ id, label, icon: Icon }) => (
              <TabsTrigger key={id} variant="underline" value={id} className="gap-2">
                <Icon className="h-4 w-4" /> {label}
              </TabsTrigger>
            ))}
          </TabsList>

          {visibleTabs.map((def) => {
            const isActive = def.id === activeTab
            const Panel = def.component
            const panel = (
              <Panel
                incident={incident}
                incidentId={incidentId}
                focusRowId={isActive ? focusRow : null}
                onNavigate={navigate}
                onIncidentChanged={() => void reloadIncident()}
              />
            )
            if (def.keepMounted) {
              if (!visited.has(def.id)) return null
              return (
                <TabsContent key={def.id} value={def.id} forceMount hidden={!isActive}>
                  {panel}
                </TabsContent>
              )
            }
            return (
              <TabsContent key={def.id} value={def.id}>
                {isActive && panel}
              </TabsContent>
            )
          })}
        </Tabs>
      </div>

      {/* Modals */}
      {canUpdateIncident && (
        <>
          <EditIncidentModal
            open={showEditModal}
            onOpenChange={setShowEditModal}
            incident={incident}
            incidentId={incidentId}
            onUpdated={() => void reloadIncident()}
          />

          <UpdateStatusModal
            open={showStatusModal}
            onOpenChange={setShowStatusModal}
            currentStatus={incident.status}
            incidentVersion={incident.version}
            incidentId={incidentId}
            onUpdated={() => void reloadIncident()}
          />

          <ImportWizardModal
            isOpen={showImportModal}
            onOpenChange={setShowImportModal}
            incidentId={incidentId}
          />
        </>
      )}

      {canGenerateReport && (
        <ReportModal
          open={showReportModal}
          onOpenChange={setShowReportModal}
          incidentId={incidentId}
          incidentNumber={incident.incident_number}
        />
      )}
    </>
  )
}
