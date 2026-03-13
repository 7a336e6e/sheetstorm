"use client"

import { Skeleton } from '@/components/ui/skeleton'

// ─── Stat Card ───────────────────────────────────────────────────────────

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  description?: string
}

export function StatCard({ title, value, icon, description }: StatCardProps) {
  return (
    <div className="px-3 py-2.5 rounded-lg bg-muted/50 border border-border">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{title}</span>
        <div className="text-primary">{icon}</div>
      </div>
      <div className="text-xl font-bold text-foreground">{value}</div>
      {description && <div className="text-[11px] text-muted-foreground mt-0.5">{description}</div>}
    </div>
  )
}

export function SkeletonStatCard() {
  return (
    <div className="rounded-lg border border-border bg-muted/50 px-3 py-2.5 space-y-2">
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="h-6 w-1/2" />
    </div>
  )
}
