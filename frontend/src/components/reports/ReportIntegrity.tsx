"use client"

/**
 * Integrity badge of a report row (W3-DFIR-C; surface-dfir §3.10, C34): an
 * issued report is a stored, hashed snapshot (every download returns the same
 * bytes); reports issued before snapshots existed are re-rendered on download.
 */
import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { notifyError } from '@/lib/errors'

export interface ReportIntegrityFields {
    /** Stored, hashed snapshot; false = legacy report re-rendered on download. */
    is_snapshot?: boolean
    sha256?: string | null
    size_bytes?: number | null
}

/** First characters of a SHA-256 for tables; the full value stays in the title and the copy button. */
export function shortHash(sha256: string, length = 12): string {
    return sha256.length > length ? `${sha256.slice(0, length)}…` : sha256
}

export function ReportIntegrityBadge({ report }: { report: ReportIntegrityFields }) {
    const [copied, setCopied] = useState(false)
    if (!report.is_snapshot || !report.sha256) {
        return (
            <Badge variant="outline" title="Issued before snapshots existed: re-rendered from current data on every download">
                Legacy (re-rendered)
            </Badge>
        )
    }
    const sha256 = report.sha256
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(sha256)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
        } catch (err) {
            notifyError(err, 'copy the SHA-256')
        }
    }
    return (
        <div className="flex min-w-0 flex-col gap-1">
            <Badge variant="success" title="Stored when issued; every download returns the same bytes">Snapshot</Badge>
            <div className="flex items-center gap-1">
                <code className="font-mono text-[11px] text-muted-foreground" title={sha256}>
                    SHA-256 {shortHash(sha256)}
                </code>
                <Button variant="ghost" size="icon-sm" className="h-5 w-5" aria-label="Copy SHA-256" onClick={() => void copy()}>
                    {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </Button>
            </div>
        </div>
    )
}
