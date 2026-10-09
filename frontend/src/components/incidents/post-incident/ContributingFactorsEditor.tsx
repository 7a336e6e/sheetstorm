"use client"

/**
 * Contributing factors of a review: `[{category, description}]` chips plus an
 * add row. Read-only (no add row, no remove buttons) when `disabled`.
 */
import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CATEGORY_OPTIONS, labelOf } from '@/lib/post-incident'
import type { ContributingCategory, ContributingFactor } from '@/types'

export const MAX_FACTORS = 50

interface Props {
  value: ContributingFactor[]
  onChange(next: ContributingFactor[]): void
  disabled?: boolean
}

export function ContributingFactorsEditor({ value, onChange, disabled }: Props) {
  const [category, setCategory] = useState<ContributingCategory>('process')
  const [description, setDescription] = useState('')

  const add = () => {
    const text = description.trim()
    if (!text || value.length >= MAX_FACTORS) return
    onChange([...value, { category, description: text }])
    setDescription('')
  }

  return (
    <div className="space-y-3">
      {value.length === 0 ? (
        <p className="text-sm text-muted-foreground">No contributing factors recorded.</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label="Contributing factors">
          {value.map((f, i) => (
            <li
              key={`${f.category}-${i}`}
              className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-2 py-1 text-sm"
            >
              <Badge variant="outline">{labelOf(CATEGORY_OPTIONS, f.category)}</Badge>
              <span>{f.description}</span>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => onChange(value.filter((_, j) => j !== i))}
                  aria-label={`Remove factor: ${f.description}`}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!disabled && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select value={category} onValueChange={(v) => setCategory(v as ContributingCategory)}>
            <SelectTrigger aria-label="Factor category" className="sm:w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            aria-label="Factor description"
            placeholder="What contributed?"
            value={description}
            maxLength={2000}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                add()
              }
            }}
          />
          <Button type="button" variant="outline" onClick={add} disabled={!description.trim() || value.length >= MAX_FACTORS}>
            <Plus className="mr-1 h-4 w-4" /> Add factor
          </Button>
        </div>
      )}
    </div>
  )
}
