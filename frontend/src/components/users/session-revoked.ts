/**
 * `session:revoked` (socket, room `user_<id>`): an admin disabled the
 * account, forced a logout or reset the password / MFA, so every token of
 * this user is dead. Clear the local session and land on the login page with
 * a notice. The single handler for this event, registered by SocketProvider
 * (W2-RT-FE + W2-LIFE-UI).
 */
import { toast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/lib/store'

export const SESSION_REVOKED_EVENT = 'session:revoked'
export const SESSION_REVOKED_LOGIN = '/login?reason=session_revoked'

/** Copy for `session:revoked` reasons (backend services/token_revocation.py). */
export const SESSION_REVOKED_COPY: Record<string, string> = {
  disabled: 'Your account was disabled.',
  deleted: 'Your account was removed.',
  force_logout: 'An administrator signed you out.',
  password_reset: 'Your password was reset. Sign in again.',
  mfa_reset: 'Your MFA was reset. Sign in again.',
}
export const SESSION_REVOKED_DEFAULT_COPY = 'Your session was ended. Sign in again.'

/** sessionStorage key carrying the reason across the full navigation to /login. */
const REASON_STORAGE_KEY = 'sheetstorm.session_revoked_reason'

export function sessionRevokedMessage(reason: string | null | undefined): string {
  return (reason && SESSION_REVOKED_COPY[reason]) || SESSION_REVOKED_DEFAULT_COPY
}

/** Reads the reason stored by `handleSessionRevoked` (null when absent or unreadable). */
export function readSessionRevokedReason(): string | null {
  try {
    return window.sessionStorage.getItem(REASON_STORAGE_KEY) || null
  } catch {
    return null
  }
}

/** Full navigation (drops all in-memory state of the dead session). Replaceable in tests. */
export const sessionNavigation = {
  assign(url: string) {
    window.location.assign(url)
  },
}

let handling = false

export async function handleSessionRevoked(reason?: unknown): Promise<void> {
  if (handling) return
  handling = true
  const code = typeof reason === 'string' && reason in SESSION_REVOKED_COPY ? reason : ''
  try {
    window.sessionStorage.setItem(REASON_STORAGE_KEY, code)
  } catch {
    // Storage unavailable: the login page falls back to the generic notice.
  }
  toast({ title: 'Signed out', description: sessionRevokedMessage(code) })
  try {
    // logout() tolerates the 401 of the already-revoked session.
    await useAuthStore.getState().logout()
  } finally {
    handling = false
    sessionNavigation.assign(SESSION_REVOKED_LOGIN)
  }
}
