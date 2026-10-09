import type { TimeMode } from '@/lib/time'

/** `users.preferences` (server allowlist: `display_timezone`). */
export interface UserPreferences {
  display_timezone?: TimeMode
}
