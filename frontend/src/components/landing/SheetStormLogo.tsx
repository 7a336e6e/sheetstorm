/**
 * SheetStorm logo — matches the favicon SVG.
 * Indigo-to-violet gradient rounded rect with terminal chevron + underscore.
 */
import { cn } from '@/lib/utils'

interface SheetStormLogoProps {
  className?: string
  size?: number
}

export function SheetStormLogo({ className, size = 28 }: SheetStormLogoProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="url(#logo-grad)" />
      <path
        d="M9 11 l3 3 l-3 3 M15 17 h6"
        stroke="#fff"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <rect x="8" y="21" width="16" height="2" rx="1" fill="rgba(255,255,255,0.4)" />
    </svg>
  )
}
