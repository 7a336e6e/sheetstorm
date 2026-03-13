/**
 * Redirect /register to /login?tab=register
 */

"use client"

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function RegisterPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/login?tab=register')
  }, [router])

  return null
}
