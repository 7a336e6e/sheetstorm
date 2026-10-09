/**
 * `session:revoked` (socket, room `user_<id>`): an admin disabled the
 * account, forced a logout or reset the password / MFA, so every token of
 * this user is dead. Clear the local session and land on the login page with
 * a notice. Registered by SocketProvider.
 */
import { useAuthStore } from '@/lib/store'

export const SESSION_REVOKED_EVENT = 'session:revoked'
export const SESSION_REVOKED_LOGIN = '/login?reason=session_revoked'

/** Full navigation (drops all in-memory state of the dead session). Replaceable in tests. */
export const sessionNavigation = {
  assign(url: string) {
    window.location.assign(url)
  },
}

let handling = false

export async function handleSessionRevoked(): Promise<void> {
  if (handling) return
  handling = true
  try {
    // logout() tolerates the 401 of the already-revoked session.
    await useAuthStore.getState().logout()
  } finally {
    handling = false
    sessionNavigation.assign(SESSION_REVOKED_LOGIN)
  }
}
