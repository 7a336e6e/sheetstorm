"use client"

/**
 * Admin → Case Templates → Question library (DFIQ). Platform administrators
 * import Google's DFIQ questions (Apache-2.0) with one click: the server
 * downloads the pinned release from GitHub and checks its SHA-256. Offline
 * installs upload the same archive instead. Everyone with access sees the status.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpen, Download, Loader2, Trash2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { dfiqApi } from '@/lib/endpoints/questions'
import { notifyError, notifySuccess } from '@/lib/errors'
import type { DfiqStatus } from '@/types'

export function DfiqLibraryCard() {
  const confirm = useConfirm()
  const [status, setStatus] = useState<DfiqStatus | null>(null)
  const [busy, setBusy] = useState<'download' | 'upload' | 'remove' | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      setStatus(await dfiqApi.status())
    } catch (err) {
      notifyError(err, 'load the question library status')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (!status) return null

  const run = async (kind: 'download' | 'upload', file?: File) => {
    setBusy(kind)
    try {
      const next = await dfiqApi.importLibrary(file)
      setStatus(next)
      notifySuccess('DFIQ imported', `${next.counts?.questions ?? 0} questions are now in the library.`)
    } catch (err) {
      notifyError(err, 'import DFIQ')
    } finally {
      setBusy(null)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const remove = async () => {
    const ok = await confirm({
      title: 'Remove the DFIQ library?',
      description: 'Questions already added to incidents keep their text. Templates that reference DFIQ questions stop adding them.',
      confirmLabel: 'Remove',
      variant: 'destructive',
    })
    if (!ok) return
    setBusy('remove')
    try {
      setStatus(await dfiqApi.remove())
      notifySuccess('DFIQ library removed')
    } catch (err) {
      notifyError(err, 'remove the DFIQ library')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BookOpen className="h-4 w-4" /> Question library: DFIQ
        </CardTitle>
        <CardDescription>
          Digital Forensics Investigative Questions by Google ({status.license}). Imported questions appear in every
          organization&apos;s question library next to the SheetStorm core questions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {status.vendored_files ? (
          <p>DFIQ is bundled with this installation.</p>
        ) : status.imported ? (
          <p>
            Imported: {status.counts?.questions} questions in {status.counts?.scenarios} scenarios, commit{' '}
            <code className="text-xs">{status.commit?.slice(0, 12)}</code>
            {status.imported_at && (
              <>
                {' '}on <Timestamp value={status.imported_at} seconds={false} />
              </>
            )}
            {status.imported_by?.name ? ` by ${status.imported_by.name}` : ''}.
          </p>
        ) : (
          <p className="text-muted-foreground">Not imported.</p>
        )}
        <p className="text-xs text-muted-foreground">
          Pinned release <code>{status.pinned_commit.slice(0, 12)}</code>; the archive is accepted only if its SHA-256 is{' '}
          <code className="break-all">{status.pinned_sha256}</code>. {status.attribution}.
        </p>

        {status.can_import && !status.vendored_files ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void run('download')} disabled={busy !== null}>
              {busy === 'download' ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
              {status.imported ? 'Re-import DFIQ' : 'Import DFIQ'}
            </Button>
            <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy !== null}>
              {busy === 'upload' ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Upload className="mr-1.5 h-4 w-4" />}
              Upload archive (offline)
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".tar.gz,.tgz,application/gzip"
              className="hidden"
              aria-label="DFIQ archive"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void run('upload', file)
              }}
            />
            {status.imported && (
              <Button variant="ghost" onClick={() => void remove()} disabled={busy !== null}>
                <Trash2 className="mr-1.5 h-4 w-4" /> Remove
              </Button>
            )}
          </div>
        ) : !status.can_import ? (
          <p className="text-xs text-muted-foreground">Only platform administrators can import or remove it.</p>
        ) : null}
      </CardContent>
    </Card>
  )
}
