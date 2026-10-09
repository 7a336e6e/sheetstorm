"use client"

/**
 * Repeatable "algorithm + value + source" rows for acquisition hashes.
 *
 * Validation mirrors the server (`evidence.py::_hex_hash`): the value must be
 * hexadecimal of exactly the algorithm's length (MD5 32, SHA-1 40, SHA-256 64,
 * SHA-512 128), compared lower-cased, and an algorithm may appear once. The
 * server re-validates; this just says why before the request.
 */
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { HASH_ALGORITHMS, HASH_LENGTHS, HASH_SOURCES, type HashAlgorithm, type HashSource, type NewHashInput } from '@/types'
import { HASH_LABELS, HASH_SOURCE_LABELS, guessAlgorithm, normalizeHash, validateHash } from './evidence-helpers'
import { NativeSelect, optionsFrom } from './form-parts'

export interface HashRow {
  key: string
  algorithm: HashAlgorithm
  value: string
  source: HashSource
}

let seq = 0
export const newHashRow = (algorithm: HashAlgorithm = 'sha256'): HashRow => ({
  key: `h${++seq}`,
  algorithm,
  value: '',
  source: 'tool_reported',
})

/** Per-row problem (null = fine). Empty rows are ignored by `hashRowsToInput`. */
export function hashRowProblem(row: HashRow, all: HashRow[]): string | null {
  if (!normalizeHash(row.value)) return null
  const own = validateHash(row.algorithm, row.value)
  if (own) return own
  const dup = all.some((r) => r.key !== row.key && r.algorithm === row.algorithm && normalizeHash(r.value))
  return dup ? `Only one ${HASH_LABELS[row.algorithm]} value per item. Correct a recorded one by superseding it.` : null
}

export function hashRowsInvalid(rows: HashRow[]): boolean {
  return rows.some((r) => hashRowProblem(r, rows) !== null)
}

export function hashRowsToInput(rows: HashRow[]): NewHashInput[] {
  return rows
    .filter((r) => normalizeHash(r.value))
    .map((r) => ({ algorithm: r.algorithm, value: normalizeHash(r.value), source: r.source }))
}

const SOURCE_OPTIONS = optionsFrom(HASH_SOURCE_LABELS).filter((o) => HASH_SOURCES.includes(o.value))
const ALGORITHM_OPTIONS = HASH_ALGORITHMS.map((a) => ({ value: a, label: HASH_LABELS[a] }))

export function HashEntry({
  rows,
  onChange,
  showErrors,
  max = 4,
  disabled,
}: {
  rows: HashRow[]
  onChange: (rows: HashRow[]) => void
  /** Show problems of rows that have a value (and empty-row hints after a submit attempt). */
  showErrors?: boolean
  max?: number
  disabled?: boolean
}) {
  const update = (key: string, patch: Partial<HashRow>) =>
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))

  const onValue = (row: HashRow, value: string) => {
    // A pasted value whose length identifies exactly one algorithm selects it.
    const guessed = guessAlgorithm(value)
    const taken = guessed && rows.some((r) => r.key !== row.key && r.algorithm === guessed && normalizeHash(r.value))
    update(row.key, guessed && !taken && guessed !== row.algorithm ? { value, algorithm: guessed } : { value })
  }

  return (
    <div className="space-y-3">
      {rows.map((row, i) => {
        const problem = hashRowProblem(row, rows)
        const errId = `${row.key}-err`
        const len = normalizeHash(row.value).length
        return (
          <div key={row.key} className="space-y-1">
            <div className="grid gap-2 sm:grid-cols-[130px_1fr_170px_auto]">
              <NativeSelect
                aria-label={`Hash ${i + 1} algorithm`}
                value={row.algorithm}
                onValueChange={(v) => update(row.key, { algorithm: v as HashAlgorithm })}
                options={ALGORITHM_OPTIONS}
                disabled={disabled}
              />
              <Input
                aria-label={`Hash ${i + 1} value`}
                aria-invalid={(showErrors && !!problem) || undefined}
                aria-describedby={showErrors && problem ? errId : undefined}
                value={row.value}
                onChange={(e) => onValue(row, e.target.value)}
                placeholder={`${HASH_LENGTHS[row.algorithm]} hexadecimal characters`}
                className={cn('font-mono text-xs', showErrors && problem && 'border-destructive')}
                spellCheck={false}
                autoComplete="off"
                disabled={disabled}
              />
              <NativeSelect
                aria-label={`Hash ${i + 1} source`}
                value={row.source}
                onValueChange={(v) => update(row.key, { source: v as HashSource })}
                options={SOURCE_OPTIONS}
                disabled={disabled}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove hash ${i + 1}`}
                onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
                disabled={disabled}
                className="self-center"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <p
              id={errId}
              className={cn('text-xs', showErrors && problem ? 'text-destructive' : 'text-muted-foreground')}
              aria-live="polite"
            >
              {showErrors && problem
                ? problem
                : len
                  ? `${len} / ${HASH_LENGTHS[row.algorithm]} characters`
                  : ' '}
            </p>
          </div>
        )
      })}
      {rows.length < max && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const used = new Set(rows.map((r) => r.algorithm))
            onChange([...rows, newHashRow(HASH_ALGORITHMS.find((a) => !used.has(a)) ?? 'sha256')])
          }}
          disabled={disabled}
        >
          <Plus className="h-4 w-4" />
          Add hash
        </Button>
      )}
    </div>
  )
}
