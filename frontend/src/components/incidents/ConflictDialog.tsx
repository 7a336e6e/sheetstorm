"use client"

/**
 * Edit-conflict dialog (409 `conflict` on a versioned write).
 *
 * Shows which of the fields the user sent differ from the server's current
 * copy, and offers "Reload theirs" (drop my change, show the latest) or
 * "Overwrite with mine" (re-send with the current version). Opened globally
 * by ConflictProvider; tabs only pass `ifMatch: row.version`.
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

/** Bookkeeping fields never shown as a difference. */
const IGNORED_FIELDS = new Set(['id', 'version', 'expected_version', 'created_at', 'updated_at'])
const MAX_VALUE_CHARS = 200

export interface ConflictField {
  field: string
  mine: unknown
  theirs: unknown
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function same(a: unknown, b: unknown): boolean {
  const norm = (v: unknown) => (v === undefined || v === '' ? null : v)
  return JSON.stringify(norm(a)) === JSON.stringify(norm(b))
}

/** Fields of my request body whose value differs from the current server copy. */
export function conflictFields(mine: unknown, theirs: unknown): ConflictField[] {
  if (!isRecord(mine)) return []
  const current = isRecord(theirs) ? theirs : {}
  return Object.keys(mine)
    .filter((k) => !IGNORED_FIELDS.has(k) && !same(mine[k], current[k]))
    .map((k) => ({ field: k, mine: mine[k], theirs: current[k] }))
}

export function formatConflictValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  let s: string
  if (typeof v === 'string') s = v
  else {
    try {
      s = JSON.stringify(v)
    } catch {
      s = String(v)
    }
  }
  return s.length > MAX_VALUE_CHARS ? `${s.slice(0, MAX_VALUE_CHARS)}…` : s
}

function label(field: string): string {
  const s = field.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export interface ConflictDialogProps {
  open: boolean
  method: 'PUT' | 'PATCH' | 'DELETE'
  /** The body I tried to save. */
  mine: unknown
  /** The server's current copy (`details.current` of the 409). */
  theirs: unknown
  currentVersion?: number
  onReloadTheirs(): void
  onOverwrite(): void
}

export function ConflictDialog({
  open,
  method,
  mine,
  theirs,
  currentVersion,
  onReloadTheirs,
  onOverwrite,
}: ConflictDialogProps) {
  const isDelete = method === 'DELETE'
  const fields = isDelete ? [] : conflictFields(mine, theirs)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Closing without a choice keeps their version.
        if (!next) onReloadTheirs()
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Changed by someone else</DialogTitle>
          <DialogDescription>
            {isDelete
              ? 'This item was changed after you loaded it. Keep the latest version, or delete it anyway?'
              : 'Someone saved this item after you opened it. Review the differences, then keep their version or overwrite it with yours.'}
            {typeof currentVersion === 'number' && (
              <span className="ml-1 text-muted-foreground">(current version {currentVersion})</span>
            )}
          </DialogDescription>
        </DialogHeader>

        {!isDelete &&
          (fields.length > 0 ? (
            <div className="overflow-x-auto rounded-md border border-white/10">
              <table className="w-full text-sm" aria-label="Conflicting fields">
                <thead className="bg-slate-900/60 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left font-medium">Field</th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">Yours</th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">Current</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((f) => (
                    <tr key={f.field} className="border-t border-white/10 align-top">
                      <th scope="row" className="px-3 py-2 text-left font-medium text-foreground">
                        {label(f.field)}
                      </th>
                      <td className="px-3 py-2 break-words text-foreground">{formatConflictValue(f.mine)}</td>
                      <td className="px-3 py-2 break-words text-muted-foreground">{formatConflictValue(f.theirs)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              The fields you edited match the current version; other fields were changed.
            </p>
          ))}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onReloadTheirs}>
            {isDelete ? 'Keep theirs' : 'Reload theirs'}
          </Button>
          <Button variant={isDelete ? 'destructive' : 'default'} onClick={onOverwrite}>
            {isDelete ? 'Delete anyway' : 'Overwrite with mine'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ConflictDialog
