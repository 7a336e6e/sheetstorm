"use client"

/**
 * Password rules for form hints (`GET /auth/password-policy`): the signed-in
 * user's organization, otherwise the platform organization (registration).
 * Returns the code defaults until (or if) the server answers. Hints only: the
 * server validates every password write.
 */
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/lib/store'
import { DEFAULT_PASSWORD_RULES, securityPolicy } from '@/lib/endpoints/security'
import type { PasswordRules } from '@/types'

const cache = new Map<string, Promise<PasswordRules>>()

/** Drop cached rules (e.g. after an admin saved the policy). */
export function clearPasswordRulesCache(): void {
  cache.clear()
}

function load(key: string): Promise<PasswordRules> {
  let pending = cache.get(key)
  if (!pending) {
    pending = securityPolicy.passwordRules().catch((err) => {
      cache.delete(key)
      throw err
    })
    cache.set(key, pending)
  }
  return pending
}

export function usePasswordPolicy(enabled = true): PasswordRules {
  const userId = useAuthStore((s) => s.user?.id)
  const key = userId ?? 'anonymous'
  const [rules, setRules] = useState<PasswordRules>(DEFAULT_PASSWORD_RULES)

  useEffect(() => {
    if (!enabled) return
    let active = true
    load(key)
      .then((r) => {
        if (active) setRules({ ...DEFAULT_PASSWORD_RULES, ...r })
      })
      .catch(() => {
        // Keep the defaults; the server still validates.
      })
    return () => {
      active = false
    }
  }, [enabled, key])

  return rules
}
