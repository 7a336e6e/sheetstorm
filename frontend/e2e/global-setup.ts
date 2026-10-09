// Seeds one user per system role in up to two orgs via the API and saves a
// storage state (session cookies) per user in e2e/.auth/<org>-<role>.json.
//
// Org A: the org of ADMIN_EMAIL/ADMIN_PASSWORD (the bootstrap admin).
// Org B: the org of E2E_ORG_B_ADMIN_EMAIL/E2E_ORG_B_ADMIN_PASSWORD, if set.
//        There is no API to create organizations; bootstrap it once with
//        e2e/seed-second-org.py (see e2e/README.md).
//
// Without credentials this is a no-op and logged-in specs skip themselves.
// Idempotent: existing users (409) are reused, fresh storage states are kept.
import fs from 'node:fs'
import { chromium, type FullConfig } from '@playwright/test'
import { AUTH_DIR, ROLES, ROLE_KEYS, isFresh, seedEmail, seedPassword, storageStatePath, type OrgKey } from './auth'
import { api, apiLogin } from './fixtures'

interface OrgSeed {
  key: OrgKey
  adminEmail?: string
  adminPassword?: string
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  if (process.env.E2E_SKIP_SEED === '1') return

  const { baseURL, ignoreHTTPSErrors } = config.projects[0].use
  const orgs: OrgSeed[] = [
    { key: 'a', adminEmail: process.env.ADMIN_EMAIL, adminPassword: process.env.ADMIN_PASSWORD },
    { key: 'b', adminEmail: process.env.E2E_ORG_B_ADMIN_EMAIL, adminPassword: process.env.E2E_ORG_B_ADMIN_PASSWORD },
  ]

  if (!orgs[0].adminEmail || !orgs[0].adminPassword) {
    console.warn('[e2e] ADMIN_EMAIL/ADMIN_PASSWORD not set: no users seeded, logged-in specs will be skipped.')
    return
  }

  fs.mkdirSync(AUTH_DIR, { recursive: true, mode: 0o700 })
  const browser = await chromium.launch()
  try {
    for (const org of orgs) {
      if (!org.adminEmail || !org.adminPassword) {
        console.warn(`[e2e] org ${org.key.toUpperCase()}: no admin credentials, skipped.`)
        continue
      }
      const stale = ROLE_KEYS.filter((role) => !isFresh(storageStatePath(role, org.key)))
      if (stale.length === 0) continue

      // 1. Create the role users as the org's admin (409 = already seeded).
      const adminCtx = await browser.newContext({ baseURL, ignoreHTTPSErrors })
      try {
        await apiLogin(adminCtx, org.adminEmail, org.adminPassword)
        for (const role of stale) {
          const email = seedEmail(role, org.key)
          const res = await api.post(adminCtx, '/users', {
            email,
            name: `E2E ${ROLES[role]} ${org.key.toUpperCase()}`,
            password: seedPassword(email),
            roles: [ROLES[role]],
          })
          if (res.status() !== 201 && res.status() !== 409) {
            throw new Error(`[e2e] seeding ${email} failed: HTTP ${res.status()} ${await res.text()}`)
          }
        }
      } finally {
        await adminCtx.close()
      }

      // 2. Log each user in and save its session.
      for (const role of stale) {
        const email = seedEmail(role, org.key)
        const ctx = await browser.newContext({ baseURL, ignoreHTTPSErrors })
        try {
          await apiLogin(ctx, email, seedPassword(email) as string)
          await ctx.storageState({ path: storageStatePath(role, org.key) })
          fs.chmodSync(storageStatePath(role, org.key), 0o600)
        } finally {
          await ctx.close()
        }
      }
    }
  } finally {
    await browser.close()
  }
}
