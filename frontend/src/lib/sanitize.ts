/**
 * Input sanitization utilities to prevent XSS and injection attacks.
 * Used as a defense-in-depth measure alongside server-side sanitization.
 */

/**
 * Escape HTML entities in a string to prevent XSS.
 */
export function escapeHtml(str: string): string {
  const escapeMap: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '/': '&#x2F;',
  }
  return str.replace(/[&<>"'/]/g, (char) => escapeMap[char])
}

/**
 * Strip HTML tags from a string.
 */
export function stripHtml(str: string): string {
  return str.replace(/<[^>]*>/g, '')
}

/**
 * Sanitize a string by stripping HTML and trimming whitespace.
 * Use for plain-text fields like titles, names, descriptions.
 */
export function sanitizeText(str: string): string {
  return stripHtml(str).trim()
}

/**
 * Sanitize a URL string — only allow http(s) protocols.
 * Returns empty string if the URL is suspicious.
 */
export function sanitizeUrl(url: string): string {
  const trimmed = url.trim()
  if (!trimmed) return ''
  try {
    const parsed = new URL(trimmed)
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return ''
    }
    return trimmed
  } catch {
    return ''
  }
}

/**
 * Sanitize an object's string values recursively (shallow — one level).
 * For use before sending form data to the API.
 */
export function sanitizeFormData<T extends Record<string, unknown>>(data: T): T {
  const sanitized = { ...data }
  for (const key of Object.keys(sanitized)) {
    const val = sanitized[key]
    if (typeof val === 'string') {
      ;(sanitized as any)[key] = sanitizeText(val)
    }
  }
  return sanitized
}

/**
 * CSP nonce helper — generates a nonce for inline scripts.
 */
export function generateNonce(): string {
  const array = new Uint8Array(16)
  crypto.getRandomValues(array)
  return Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('')
}
