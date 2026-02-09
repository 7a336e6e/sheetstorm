"use client"

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { SearchInput } from '@/components/ui/input'
import { Badge, SeverityBadge, StatusBadge, PhaseBadge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  GlassTable,
  TableEmpty,
} from '@/components/ui/table'
import { SkeletonTableRow } from '@/components/ui/skeleton'
import { useIncidentStore } from '@/lib/store'
import { formatRelativeTime } from '@/lib/utils'
import { Plus, Search, Filter, AlertTriangle, ArrowRight, X, Shield, Trash2 } from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'

export default function IncidentsPage() {
  const { incidents, fetchIncidents, isLoading, deleteIncident } = useIncidentStore()
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const { toast } = useToast()
  const confirm = useConfirm()

  useEffect(() => {
    fetchIncidents()
  }, [fetchIncidents])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault()
    e.stopPropagation()

    const confirmed = await confirm({
      title: 'Delete Incident',
      description: 'Are you sure you want to delete this incident? This action cannot be undone.',
      confirmLabel: 'Delete',
      variant: 'destructive',
    })
    if (!confirmed) return

    try {
      await deleteIncident(id)
      toast({
        title: "Incident Deleted",
        description: "The incident has been permanently deleted.",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete incident",
        variant: "destructive"
      })
    }
  }

  const filteredIncidents = incidents.filter((incident) => {
    const matchesSearch =
      incident.title.toLowerCase().includes(search.toLowerCase()) ||
      incident.incident_number.toString().includes(search)
    const matchesSeverity = severityFilter === 'all' || incident.severity === severityFilter
    const matchesStatus = statusFilter === 'all' || incident.status === statusFilter
    return matchesSearch && matchesSeverity && matchesStatus
  })

  const hasFilters = search || severityFilter !== 'all' || statusFilter !== 'all'

  const clearFilters = () => {
    setSearch('')
    setSeverityFilter('all')
    setStatusFilter('all')
  }

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-foreground">Incidents</h1>
          <p className="text-muted-foreground mt-1">Manage and track security incidents</p>
        </div>
        <Link href="/dashboard/incidents/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            New Incident
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1">
              <SearchInput
                placeholder="Search by title or incident number..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onSearch={(val) => setSearch(val)}
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue placeholder="All Severities" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severities</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>

              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="contained">Contained</SelectItem>
                  <SelectItem value="eradicated">Eradicated</SelectItem>
                  <SelectItem value="recovered">Recovered</SelectItem>
                  <SelectItem value="closed">Closed</SelectItem>
                </SelectContent>
              </Select>

              {hasFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters} className="h-10">
                  <X className="mr-2 h-4 w-4" />
                  Clear
                </Button>
              )}
            </div>
          </div>

          {/* Active filter chips */}
          {hasFilters && (
            <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-border">
              {search && (
                <Badge variant="glass" className="gap-1.5">
                  Search: {search}
                  <button onClick={() => setSearch('')} className="hover:text-foreground">
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {severityFilter !== 'all' && (
                <Badge variant={severityFilter as any} className="gap-1.5">
                  {severityFilter}
                  <button onClick={() => setSeverityFilter('all')} className="hover:text-foreground">
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {statusFilter !== 'all' && (
                <Badge variant={statusFilter as any} className="gap-1.5">
                  {statusFilter}
                  <button onClick={() => setStatusFilter('all')} className="hover:text-foreground">
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Incidents Table */}
      <GlassTable>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[100px]">ID</TableHead>
              <TableHead>Incident</TableHead>
              <TableHead className="w-[120px]">Severity</TableHead>
              <TableHead className="w-[120px]">Status</TableHead>
              <TableHead className="w-[180px]">Phase</TableHead>
              <TableHead className="w-[140px] text-right">Created</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <>
                <SkeletonTableRow columns={7} />
                <SkeletonTableRow columns={7} />
                <SkeletonTableRow columns={7} />
                <SkeletonTableRow columns={7} />
                <SkeletonTableRow columns={7} />
              </>
            ) : filteredIncidents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-[300px]">
                  <TableEmpty
                    icon={<Shield className="h-10 w-10" />}
                    title={hasFilters ? "No matching incidents" : "No incidents yet"}
                    description={
                      hasFilters
                        ? "Try adjusting your filters to find what you're looking for"
                        : "Create your first incident to get started tracking security events"
                    }
                    action={
                      hasFilters ? (
                        <Button variant="outline" size="sm" onClick={clearFilters}>
                          Clear filters
                        </Button>
                      ) : (
                        <Link href="/dashboard/incidents/new">
                          <Button size="sm">
                            <Plus className="mr-2 h-4 w-4" />
                            Create Incident
                          </Button>
                        </Link>
                      )
                    }
                  />
                </TableCell>
              </TableRow>
            ) : (
              filteredIncidents.map((incident) => (
                <TableRow key={incident.id} className="group cursor-pointer">
                  <TableCell>
                    <Link
                      href={`/dashboard/incidents/${incident.id}`}
                      className="block"
                    >
                      <span className="font-mono text-sm text-muted-foreground">
                        #{incident.incident_number}
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/dashboard/incidents/${incident.id}`}
                      className="block"
                    >
                      <div className="flex items-center gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-foreground truncate group-hover:text-cyan-400 transition-colors">
                            {incident.title}
                          </p>
                          {incident.counts && (
                            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                              <span>{incident.counts.timeline_events} events</span>
                              <span>{incident.counts.compromised_hosts} hosts</span>
                              <span>{incident.counts.tasks} tasks</span>
                            </div>
                          )}
                        </div>
                        <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                      </div>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/dashboard/incidents/${incident.id}`}
                      className="block"
                    >
                      <SeverityBadge severity={incident.severity as any} />
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/dashboard/incidents/${incident.id}`}
                      className="block"
                    >
                      <StatusBadge status={incident.status as any} />
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/dashboard/incidents/${incident.id}`}
                      className="block"
                    >
                      <PhaseBadge phase={incident.phase} />
                    </Link>
                  </TableCell>
                  <TableCell className="text-right">
                    <Link
                      href={`/dashboard/incidents/${incident.id}`}
                      className="block"
                    >
                      <span className="text-sm text-muted-foreground">
                        {formatRelativeTime(incident.created_at)}
                      </span>
                      {incident.lead_responder && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {incident.lead_responder.name}
                        </p>
                      )}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => handleDelete(e, incident.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </GlassTable>

      {/* Results count */}
      {!isLoading && filteredIncidents.length > 0 && (
        <div className="text-sm text-muted-foreground text-center">
          Showing {filteredIncidents.length} of {incidents.length} incident{incidents.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  )
}
