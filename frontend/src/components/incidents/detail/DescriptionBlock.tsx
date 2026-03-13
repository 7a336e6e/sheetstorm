"use client"

import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

// ─── Collapsible Description Block ───────────────────────────────────────

const DESCRIPTION_COLLAPSE_THRESHOLD = 300

interface DescriptionBlockProps {
  text: string
}

export function DescriptionBlock({ text }: DescriptionBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const isLong = text.length > DESCRIPTION_COLLAPSE_THRESHOLD

  return (
    <div className="max-w-full">
      <div
        className={`text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap break-words ${
          !expanded && isLong ? 'line-clamp-4' : ''
        }`}
      >
        {text}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center gap-1 mt-1.5 text-xs text-primary hover:text-primary/80 transition-colors"
        >
          {expanded ? (
            <>Show less <ChevronUp className="h-3 w-3" /></>
          ) : (
            <>Show more <ChevronDown className="h-3 w-3" /></>
          )}
        </button>
      )}
    </div>
  )
}
