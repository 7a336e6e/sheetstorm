"use client"

import * as React from 'react'
import { Check, ChevronsUpDown, X } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ComboboxOption {
  value: string
  label: string
  description?: string
}

interface ComboboxProps {
  options: ComboboxOption[]
  value: string
  onChange: (value: string) => void
  /** Called when the display label changes (for free-text entries) */
  onLabelChange?: (label: string) => void
  placeholder?: string
  emptyMessage?: string
  allowCustom?: boolean
  className?: string
  variant?: 'default' | 'glass'
  disabled?: boolean
}

export function Combobox({
  options,
  value,
  onChange,
  onLabelChange,
  placeholder = 'Select or type...',
  emptyMessage = 'No results found.',
  allowCustom = true,
  className,
  variant = 'glass',
  disabled = false,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const [inputValue, setInputValue] = React.useState('')
  const [isTyping, setIsTyping] = React.useState(false)
  const inputRef = React.useRef<HTMLInputElement>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)

  // Sync input value with selected value — but NOT while user is actively typing
  React.useEffect(() => {
    if (isTyping) return
    if (value) {
      const found = options.find(o => o.value === value)
      setInputValue(found ? found.label : value)
    } else {
      setInputValue('')
    }
  }, [value, options, isTyping])

  const filtered = React.useMemo(() => {
    if (!inputValue) return options
    const lower = inputValue.toLowerCase()
    return options.filter(
      o => o.label.toLowerCase().includes(lower) || o.value.toLowerCase().includes(lower) || o.description?.toLowerCase().includes(lower)
    )
  }, [options, inputValue])

  // Close on outside click
  React.useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setIsTyping(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (opt: ComboboxOption) => {
    setIsTyping(false)
    onChange(opt.value)
    setInputValue(opt.label)
    onLabelChange?.(opt.label)
    setOpen(false)
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setIsTyping(true)
    setInputValue(val)
    setOpen(true)
    if (allowCustom) {
      // For custom input, pass raw text as both value and label
      onChange(val)
      onLabelChange?.(val)
    }
  }

  const handleClear = () => {
    setIsTyping(false)
    onChange('')
    setInputValue('')
    onLabelChange?.('')
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setOpen(false)
    }
    if (e.key === 'Enter' && !open) {
      setOpen(true)
    }
    if (e.key === 'Enter' && open && filtered.length > 0) {
      e.preventDefault()
      handleSelect(filtered[0])
    }
  }

  const isGlass = variant === 'glass'

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      <div
        className={cn(
          'flex h-10 items-center rounded-md border px-3 text-sm',
          isGlass
            ? 'bg-black/5 dark:bg-white/5 border-black/10 dark:border-white/10 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 backdrop-blur-sm'
            : 'bg-background border-input focus-within:ring-1 focus-within:ring-ring',
          disabled && 'opacity-50 pointer-events-none'
        )}
      >
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="flex-1 bg-transparent outline-none placeholder:text-muted-foreground text-sm text-foreground"
        />
        {inputValue && (
          <button
            type="button"
            onClick={handleClear}
            className="ml-1 p-0.5 hover:bg-white/10 rounded text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-lg max-h-[200px] overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="py-3 px-3 text-sm text-muted-foreground text-center">
              {allowCustom && inputValue ? (
                <span>Press Enter to use "<span className="text-foreground font-medium">{inputValue}</span>"</span>
              ) : (
                emptyMessage
              )}
            </div>
          ) : (
            <div className="py-1">
              {filtered.map(opt => {
                const isSelected = opt.value === value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => handleSelect(opt)}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-sm text-left hover:bg-accent/10 transition-colors',
                      isSelected && 'bg-accent/15 text-accent-foreground'
                    )}
                  >
                    <Check className={cn('h-3.5 w-3.5 shrink-0', isSelected ? 'opacity-100 text-primary' : 'opacity-0')} />
                    <div className="flex flex-col min-w-0">
                      <span className="truncate text-foreground">{opt.label}</span>
                      {opt.description && (
                        <span className="text-[11px] text-muted-foreground truncate">{opt.description}</span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
