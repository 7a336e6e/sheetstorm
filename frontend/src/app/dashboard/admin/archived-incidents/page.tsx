"use client"

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { SearchInput } from '@/components/ui/input'
import { Badge, SeverityBadge, StatusBadge } from '@/components/ui/badge'
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
import { Archive, ArchiveRestore, Trash2, X, AlertTriangle, Search } from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'

export default function ArchivedIncidentsPage() {
  const { archivedIncidents, fetchArchivedIncidents, isLoading, unarchiveIncident, permanentDeleteIncident } = useIncidentStore()
  const [search, setSearch] = useState('')
  const { toast } = useToast()
  const confirm = useConfirm()

  useEffect(() => {
    fetchArchivedIncidents()
  }, [fetchArchivedIncidents])

  const handleRestore = async (id: string) => {
    const confirmed = await confirm({
      title: 'Restore Incident',
      description: 'This will restore the incident and make it visible again to all users with access.',
      confirmLabel: 'Restore',
    })
    if (!confirmed) return

    try {
      await unarchiveIncident(id)
      toast({
        title: "Incident Restored",
        description: "The incident has been restored from the archive.",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to restore incident",
        variant: "destructive"
      })
    }
  }

  const handlePermanentDelete = async (id: string) => {
    const confirmed = await confirm({
      title: 'Permanently Delete Incident',
      description: 'WARNING: This action is irreversible. All data associated with this incident — including timeline events, IOCs, compromised assets, case notes, artifacts, tasks, and reports — will be permanently destroyed. This may have legal and compliance implications. Ensure you have exported any required data before proceeding.',
      confirmLabel: 'Permanently Delete',
      variant: 'destructive',
    })
    if (!confirmed) return

    try {
      await permanentDeleteIncident(id)
      toast({
        title: "Incident Permanently Deleted",
        description: "The incident and all associated data have been permanently destroyed.",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to permanently delete incident",
        variant: "destructive"
      })
    }
  }

  const filteredIncidents = archivedIncidents.filter((incident) => {
    if (!search) return true
    return (
      incident.title.toLowerCase().includes(search.toLowerCase()) ||
      incident.incident_number.toString().includes(search)
    )
  })

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-foreground">Archived Incidents</h1>
          <p className="text-muted-foreground mt-1">View and manage archived incidents. Only administrators can access this page.</p>
        </div>
      </div>

      {/* Warning Banner */}
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-amber-500">Archive Management</p>
            <p className="text-muted-foreground mt-1">
              Archived incidents are hidden from all users. Restoring an incident will make it visible again.
              Permanent deletion is irreversible and may have legal implications.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Search */}
      <Card>
        <CardContent className="p-4">
          <SearchInput
            placeholder="Search archived incidents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={(val) => setSearch(val)}
          />
        </CardContent>
      </Card>

      {/* Table */}
      <GlassTable>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[100px]">ID</TableHead>
              <TableHead>Incident</TableHead>
              <TableHead className="w-[120px]">Severity</TableHead>
              <TableHead className="w-[120px]">Status</TableHead>
              <TableHead className="w-[140px]">Archived</TableHead>
              <TableHead className="w-[160px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <>
                <SkeletonTableRow columns={6} />
                <SkeletonTableRow columns={6} />
                <SkeletonTableRow columns={6} />
              </>
            ) : filteredIncidents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-[300px]">
                  <TableEmpty
                    icon={<Archive className="h-10 w-10" />}
                    title={search ? "No matching archived incidents" : "No archived incidents"}
                    description={
                      search
                        ? "Try adjusting your search to find what you're looking for"
                        : "Archived incidents will appear here"
                    }
                    action={
                      search ? (
                        <Button variant="outline" size="sm" onClick={() => setSearch('')}>
                          Clear search
                        </Button>
                      ) : undefined
                    }
                  />
                </TableCell>
              </TableRow>
            ) : (
              filteredIncidents.map((incident) => (
                <TableRow key={incident.id}>
                  <TableCell>
                    <span className="font-mono text-sm text-muted-foreground">
                      #{incident.incident_number}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate">
                        {incident.title}
                      </p>
                      {incident.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[400px]">
                          {incident.description}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <SeverityBadge severity={incident.severity as any} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={incident.status as any} />
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-muted-foreground">
                      {incident.updated_at ? formatRelativeTime(incident.updated_at) : formatRelativeTime(incident.created_at)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-green-500"
                        onClick={() => handleRestore(incident.id)}
                        title="Restore incident"
                      >
                        <ArchiveRestore className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() => handlePermanentDelete(incident.id)}
                        title="Permanently delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
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
          Showing {filteredIncidents.length} archived incident{filteredIncidents.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  )
}
