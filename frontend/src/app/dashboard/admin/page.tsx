/**
 * `/dashboard/admin`: lands on the first admin page the user may open
 * (the Overview for `organizations:manage` holders), else the dashboard.
 */

"use client"

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store'
import { adminLandingHref } from '@/components/layout/nav-config'

export default function AdminIndexPage() {
  const router = useRouter()
  const user = useAuthStore((s) => s.user)
  const isLoading = useAuthStore((s) => s.isLoading)

  useEffect(() => {
    if (isLoading || !user) return
    router.replace(adminLandingHref(user.permissions))
  }, [isLoading, user, router])

  return null
}
