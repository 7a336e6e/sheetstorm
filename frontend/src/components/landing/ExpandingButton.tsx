"use client"

import { type ReactNode, type MouseEvent } from 'react'
import { cn } from '@/lib/utils'

type ExpandingButtonVariant = 'primary' | 'outline' | 'ghost'

interface ExpandingButtonProps {
  icon: ReactNode
  label: string
  href?: string
  onClick?: (e?: MouseEvent<HTMLElement>) => void
  variant?: ExpandingButtonVariant
  external?: boolean
  className?: string
}

const variantStyles: Record<ExpandingButtonVariant, string> = {
  primary: [
    'bg-gradient-to-r from-indigo-500 to-violet-500',
    'text-white shadow-lg shadow-indigo-500/25',
    'group-hover:shadow-xl group-hover:shadow-indigo-500/30',
    'group-hover:from-indigo-600 group-hover:to-violet-600',
  ].join(' '),
  outline: [
    'border border-border bg-background text-foreground',
    'group-hover:bg-muted group-hover:border-border/80',
  ].join(' '),
  ghost: [
    'border border-border bg-background text-muted-foreground',
    'group-hover:text-foreground group-hover:bg-muted',
  ].join(' '),
}

export function ExpandingButton({
  icon,
  label,
  href,
  onClick,
  variant = 'primary',
  external = false,
  className,
}: ExpandingButtonProps) {
  const visual = (
    <span
      className={cn(
        'inline-flex items-center justify-center',
        'h-12 min-w-12 rounded-full',
        'px-3.5 group-hover:px-6',
        'transition-all duration-500 ease-[cubic-bezier(0.25,0.46,0.45,0.94)]',
        'overflow-hidden whitespace-nowrap',
        variantStyles[variant],
        className
      )}
    >
      <span className="shrink-0 flex items-center justify-center w-5 h-5">
        {icon}
      </span>
      <span
        className={cn(
          'ml-0 max-w-0 opacity-0 overflow-hidden',
          'group-hover:ml-2.5 group-hover:max-w-[200px] group-hover:opacity-100',
          'transition-all duration-500 ease-[cubic-bezier(0.25,0.46,0.45,0.94)]',
          'text-sm font-medium',
        )}
      >
        {label}
      </span>
    </span>
  )

  // Outer wrapper creates a stable hover zone (p-1.5 -m-1.5)
  // that extends beyond the visual button, preventing edge-hover twitching.
  const wrapperClass = 'group inline-flex rounded-full p-1.5 -m-1.5 cursor-pointer select-none'

  if (href) {
    return (
      <a
        href={href}
        onClick={onClick}
        className={wrapperClass}
        {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      >
        {visual}
      </a>
    )
  }

  return (
    <button type="button" onClick={onClick} className={wrapperClass}>
      {visual}
    </button>
  )
}
