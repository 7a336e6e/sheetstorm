// Shared E2E identities: seeded role users, their passwords and storage-state
// files. Passwords are never stored: they are derived from ADMIN_PASSWORD (or
// taken from E2E_SEED_PASSWORD), so nothing secret is committed and reruns
// against the same stack can log the existing users back in.
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

export const ROLES = {
  admin: 'Administrator',
  responder: 'Incident Responder',
  analyst: 'Analyst',
  manager: 'Manager',
  operator: 'Operator',
  viewer: 'Viewer',
} as const

export type RoleKey = keyof typeof ROLES
export type OrgKey = 'a' | 'b'

export const ROLE_KEYS = Object.keys(ROLES) as RoleKey[]

export const AUTH_DIR = process.env.E2E_AUTH_DIR || path.join(__dirname, '.auth')

/** Reuse storage states younger than this (the app refreshes the session itself). */
export const AUTH_MAX_AGE_MS = Number(process.env.E2E_AUTH_MAX_AGE_MIN || 30) * 60_000

export function seedEmail(role: RoleKey, org: OrgKey): string {
  return `e2e.${role}@org-${org}.e2e.sheetstorm.test`
}

/** Deterministic, policy-compliant password for a seeded user, or null when no key is configured. */
export function seedPassword(email: string): string | null {
  if (process.env.E2E_SEED_PASSWORD) return process.env.E2E_SEED_PASSWORD
  const key = process.env.ADMIN_PASSWORD
  if (!key) return null
  const digest = crypto.createHmac('sha256', key).update(`sheetstorm-e2e:${email}`).digest('base64url')
  return `${digest.slice(0, 24)}Aa1!`
}

export function storageStatePath(role: RoleKey, org: OrgKey = 'a'): string {
  return path.join(AUTH_DIR, `${org}-${role}.json`)
}

export function hasStorageState(role: RoleKey, org: OrgKey = 'a'): boolean {
  return fs.existsSync(storageStatePath(role, org))
}

export function isFresh(file: string): boolean {
  try {
    return Date.now() - fs.statSync(file).mtimeMs < AUTH_MAX_AGE_MS
  } catch {
    return false
  }
}
