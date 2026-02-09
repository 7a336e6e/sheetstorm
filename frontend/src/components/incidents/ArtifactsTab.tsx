"use client"

import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow, GlassTable, TableEmpty,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogBody,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import api from '@/lib/api'
import { formatDateTime, formatBytes } from '@/lib/utils'
import type { Artifact } from '@/types'
import {
  Upload, Download, FileText, Shield, ShieldCheck, ShieldX, Trash2, Loader2,
  Clock, User, ChevronRight, AlertTriangle, CheckCircle2, XCircle,
  HardDrive, FolderOpen, ExternalLink,
} from 'lucide-react'

interface ArtifactsTabProps {
  incidentId: string
}

interface CustodyEntry {
  id: string
  action: string
  performed_by: { id: string; name: string }
  details?: Record<string, unknown>
  hash_at_action?: string
  created_at: string
}

export function ArtifactsTab({ incidentId }: ArtifactsTabProps) {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [verifying, setVerifying] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  // Custody dialog
  const [custodyArtifact, setCustodyArtifact] = useState<Artifact | null>(null)
  const [custodyEntries, setCustodyEntries] = useState<CustodyEntry[]>([])
  const [loadingCustody, setLoadingCustody] = useState(false)

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<Artifact | null>(null)

  // Google Drive
  const [driveStatus, setDriveStatus] = useState<{
    configured: boolean
    connected: boolean
    email?: string
    message?: string
  } | null>(null)
  const [loadingDrive, setLoadingDrive] = useState(true)
  const [settingUpCase, setSettingUpCase] = useState(false)
  const [caseSetup, setCaseSetup] = useState(false)
  const [uploadingToDrive, setUploadingToDrive] = useState<string | null>(null)

  const fetchArtifacts = useCallback(async () => {
    try {
      const res = await api.get<{ items: Artifact[] }>(`/incidents/${incidentId}/artifacts`)
      setArtifacts(res.items || [])
    } catch {
      toast({ title: 'Error', description: 'Failed to load artifacts', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [incidentId, toast])

  useEffect(() => { fetchArtifacts() }, [fetchArtifacts])

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        await api.uploadFile(`/incidents/${incidentId}/artifacts`, file)
      }
      toast({ title: 'Upload Complete', description: `${files.length} file(s) uploaded successfully` })
      fetchArtifacts()
    } catch (err) {
      toast({
        title: 'Upload Failed',
        description: err instanceof Error ? err.message : 'Failed to upload file',
        variant: 'destructive',
      })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleUpload(e.dataTransfer.files)
  }

  const handleDownload = async (artifact: Artifact) => {
    try {
      const blob = await api.downloadFile(`/incidents/${incidentId}/artifacts/${artifact.id}/download`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = artifact.original_filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast({ title: 'Downloaded', description: artifact.original_filename })
    } catch {
      toast({ title: 'Download Failed', description: 'Could not download artifact', variant: 'destructive' })
    }
  }

  const handleVerify = async (artifact: Artifact) => {
    setVerifying(artifact.id)
    try {
      const result = await api.post<{ is_valid: boolean; details: Record<string, unknown> }>(
        `/incidents/${incidentId}/artifacts/${artifact.id}/verify`
      )
      if (result.is_valid) {
        toast({ title: 'Verification Passed', description: 'File integrity verified — hashes match' })
      } else {
        toast({ title: 'Verification Failed', description: 'Hash mismatch detected!', variant: 'destructive' })
      }
      fetchArtifacts()
    } catch {
      toast({ title: 'Verification Error', description: 'Could not verify artifact', variant: 'destructive' })
    } finally {
      setVerifying(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(deleteTarget.id)
    try {
      await api.delete(`/incidents/${incidentId}/artifacts/${deleteTarget.id}`)
      toast({ title: 'Deleted', description: `${deleteTarget.original_filename} removed` })
      setArtifacts(prev => prev.filter(a => a.id !== deleteTarget.id))
      setDeleteTarget(null)
    } catch {
      toast({ title: 'Error', description: 'Failed to delete artifact', variant: 'destructive' })
    } finally {
      setDeleting(null)
    }
  }

  const openCustody = async (artifact: Artifact) => {
    setCustodyArtifact(artifact)
    setLoadingCustody(true)
    try {
      const res = await api.get<{ items: CustodyEntry[] }>(
        `/incidents/${incidentId}/artifacts/${artifact.id}/custody`
      )
      setCustodyEntries(res.items || [])
    } catch {
      setCustodyEntries([])
    } finally {
      setLoadingCustody(false)
    }
  }

  const VerificationIcon = ({ status }: { status: string }) => {
    if (status === 'verified') return <ShieldCheck className="h-4 w-4 text-green-400" />
    if (status === 'mismatch') return <ShieldX className="h-4 w-4 text-red-400" />
    return <Shield className="h-4 w-4 text-muted-foreground" />
  }

  // Google Drive functions
  const fetchDriveStatus = useCallback(async () => {
    try {
      const res = await api.get<{
        configured: boolean
        connected: boolean
        email?: string
        message?: string
      }>('/google-drive/status')
      setDriveStatus(res)
    } catch {
      setDriveStatus({ configured: false, connected: false })
    } finally {
      setLoadingDrive(false)
    }
  }, [])

  useEffect(() => { fetchDriveStatus() }, [fetchDriveStatus])

  const handleSetupCaseFolder = async () => {
    setSettingUpCase(true)
    try {
      await api.post(`/incidents/${incidentId}/google-drive/setup`)
      toast({ title: 'Case Folder Created', description: 'Google Drive case folder structure has been set up.' })
      setCaseSetup(true)
    } catch (err) {
      toast({
        title: 'Setup Failed',
        description: err instanceof Error ? err.message : 'Failed to create case folder',
        variant: 'destructive',
      })
    } finally {
      setSettingUpCase(false)
    }
  }

  const handleUploadToDrive = async (artifact: Artifact) => {
    setUploadingToDrive(artifact.id)
    try {
      const result = await api.post<{ message: string; web_link?: string }>(
        `/incidents/${incidentId}/google-drive/upload`,
        { artifact_id: artifact.id, subfolder: 'Artifacts' }
      )
      toast({
        title: 'Uploaded to Google Drive',
        description: result.web_link
          ? `${artifact.original_filename} uploaded successfully`
          : result.message,
      })
    } catch (err) {
      toast({
        title: 'Upload Failed',
        description: err instanceof Error ? err.message : 'Failed to upload to Drive',
        variant: 'destructive',
      })
    } finally {
      setUploadingToDrive(null)
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>Evidence & Artifacts</CardTitle>
            <CardDescription>Upload, verify, and manage digital evidence</CardDescription>
          </div>
          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
            Upload File
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
              dragOver
                ? 'border-cyan-500 bg-cyan-500/5'
                : 'border-white/10 hover:border-white/20'
            }`}
          >
            <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              Drag & drop files here, or click "Upload File" above
            </p>
            {uploading && (
              <div className="flex items-center justify-center gap-2 mt-3 text-sm text-cyan-400">
                <Loader2 className="h-4 w-4 animate-spin" /> Uploading...
              </div>
            )}
          </div>

          {/* Google Drive Integration */}
          {!loadingDrive && driveStatus?.configured && (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${driveStatus.connected ? 'bg-green-500/20' : 'bg-white/10'}`}>
                    <HardDrive className={`h-5 w-5 ${driveStatus.connected ? 'text-green-400' : 'text-muted-foreground'}`} />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Google Drive</p>
                    <p className="text-xs text-muted-foreground">
                      {driveStatus.connected
                        ? `Connected as ${driveStatus.email}`
                        : driveStatus.message || 'Not connected'}
                    </p>
                  </div>
                </div>
                {driveStatus.connected && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSetupCaseFolder}
                      disabled={settingUpCase}
                    >
                      {settingUpCase ? (
                        <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <FolderOpen className="mr-2 h-3.5 w-3.5" />
                      )}
                      {caseSetup ? 'Case Folder Ready' : 'Setup Case Folder'}
                    </Button>
                  </div>
                )}
                {!driveStatus.connected && (
                  <Button variant="outline" size="sm" asChild>
                    <a href="/dashboard/admin">
                      Connect <ExternalLink className="ml-2 h-3.5 w-3.5" />
                    </a>
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Artifacts table */}
          <GlassTable className="border-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>SHA-256</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead className="w-[180px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 6 }).map((_, j) => (
                        <TableCell key={j}><div className="h-4 bg-white/5 rounded animate-pulse" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : artifacts.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <TableEmpty title="No artifacts" icon={<FileText className="w-10 h-10" />} />
                    </TableCell>
                  </TableRow>
                ) : (
                  artifacts.map(artifact => (
                    <TableRow key={artifact.id} className="group">
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div className="min-w-0">
                            <p className="font-medium truncate">{artifact.original_filename}</p>
                            {artifact.description && (
                              <p className="text-xs text-muted-foreground truncate">{artifact.description}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{formatBytes(artifact.file_size)}</TableCell>
                      <TableCell>
                        <code className="text-xs text-muted-foreground font-mono">
                          {artifact.sha256?.slice(0, 16)}...
                        </code>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <VerificationIcon status={artifact.verification_status} />
                          <span className="text-xs capitalize">{artifact.verification_status}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(artifact.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button variant="ghost" size="sm" onClick={() => handleDownload(artifact)} title="Download">
                            <Download className="h-4 w-4" />
                          </Button>
                          {driveStatus?.connected && (
                            <Button
                              variant="ghost" size="sm"
                              onClick={() => handleUploadToDrive(artifact)}
                              disabled={uploadingToDrive === artifact.id}
                              title="Upload to Google Drive"
                            >
                              {uploadingToDrive === artifact.id
                                ? <Loader2 className="h-4 w-4 animate-spin" />
                                : <HardDrive className="h-4 w-4" />
                              }
                            </Button>
                          )}
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => handleVerify(artifact)}
                            disabled={verifying === artifact.id}
                            title="Verify integrity"
                          >
                            {verifying === artifact.id
                              ? <Loader2 className="h-4 w-4 animate-spin" />
                              : <Shield className="h-4 w-4" />
                            }
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => openCustody(artifact)} title="Chain of custody">
                            <Clock className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => setDeleteTarget(artifact)}
                            className="hover:text-red-400"
                            title="Delete"
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
        </CardContent>
      </Card>

      {/* Chain of Custody Dialog */}
      <Dialog open={!!custodyArtifact} onOpenChange={() => setCustodyArtifact(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Chain of Custody</DialogTitle>
            <DialogDescription>{custodyArtifact?.original_filename}</DialogDescription>
          </DialogHeader>
          <DialogBody>
            {loadingCustody ? (
              <div className="flex items-center justify-center py-8 gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading...
              </div>
            ) : custodyEntries.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">No custody records</div>
            ) : (
              <div className="space-y-4">
                {custodyEntries.map((entry, idx) => (
                  <div key={entry.id} className="relative flex gap-4">
                    {idx < custodyEntries.length - 1 && (
                      <div className="absolute left-[15px] top-8 bottom-0 w-px bg-white/10" />
                    )}
                    <div className="relative z-10 w-8 h-8 rounded-full bg-white/10 flex items-center justify-center shrink-0">
                      {entry.action === 'upload' && <Upload className="h-3.5 w-3.5 text-cyan-400" />}
                      {entry.action === 'download' && <Download className="h-3.5 w-3.5 text-blue-400" />}
                      {entry.action === 'verify' && <Shield className="h-3.5 w-3.5 text-green-400" />}
                      {!['upload', 'download', 'verify'].includes(entry.action) && (
                        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0 pb-4">
                      <p className="text-sm font-medium capitalize">{entry.action}</p>
                      <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                        <User className="h-3 w-3" /> {entry.performed_by?.name || 'System'}
                        <span className="mx-1">·</span>
                        {formatDateTime(entry.created_at)}
                      </p>
                      {entry.hash_at_action && (
                        <code className="text-[10px] text-muted-foreground font-mono mt-1 block">
                          SHA-256: {entry.hash_at_action.slice(0, 24)}...
                        </code>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Artifact</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.original_filename}&quot;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} loading={!!deleting}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
