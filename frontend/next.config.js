/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === 'production'

/** Origin (scheme://host:port) of a configured absolute URL, or null. */
function originOf(url) {
  if (!url) return null
  try {
    const u = new URL(url)
    return u.origin
  } catch {
    return null // relative URL (e.g. '/api/v1') — covered by 'self'
  }
}

/** ws(s):// counterpart of an http(s):// origin, for Socket.IO. */
function wsOriginOf(origin) {
  if (!origin) return null
  if (origin.startsWith('https://')) return 'wss://' + origin.slice('https://'.length)
  if (origin.startsWith('http://')) return 'ws://' + origin.slice('http://'.length)
  return null
}

// NEXT_PUBLIC_* values are inlined at build time, so the CSP must be built
// from the same values the bundle will call.
const apiOrigin = originOf(process.env.NEXT_PUBLIC_API_URL)
const wsOrigin = originOf(process.env.NEXT_PUBLIC_WS_URL)
const supabaseOrigin = originOf(process.env.NEXT_PUBLIC_SUPABASE_URL)

const connectSrc = new Set(["'self'"])
for (const o of [apiOrigin, wsOrigin, supabaseOrigin]) {
  if (o) {
    connectSrc.add(o)
    // Socket.IO / Supabase realtime use the ws(s) counterpart of the origin.
    const ws = wsOriginOf(o)
    if (ws) connectSrc.add(ws)
  }
}
// Same-origin Socket.IO (behind the proxy) is covered by 'self': CSP Level 3
// matches ws:/wss: to the page's own host in all current browsers.
if (!isProd) {
  // Local dev: API / Socket.IO on another localhost port over plain http/ws.
  connectSrc.add('http://localhost:*')
  connectSrc.add('ws://localhost:*')
  connectSrc.add('http://127.0.0.1:*')
  connectSrc.add('ws://127.0.0.1:*')
}

// 'unsafe-eval' is only needed by the dev server (React Refresh / eval
// source maps); production bundles run without it.
const scriptSrc = ["'self'", "'unsafe-inline'"]
if (!isProd) scriptSrc.push("'unsafe-eval'")

const securityHeaders = [
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
  {
    key: 'Content-Security-Policy',
    value: [
      "default-src 'self'",
      "img-src 'self' data: blob: https:",
      "style-src 'self' 'unsafe-inline'",
      `script-src ${scriptSrc.join(' ')}`,
      `connect-src ${[...connectSrc].join(' ')}`,
      "font-src 'self' data:",
      "object-src 'none'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; '),
  },
]

const nextConfig = {
  output: 'standalone',
  // The repo root has its own package-lock.json (shadcn CLI); pin the app
  // root so standalone tracing and Turbopack don't infer the wrong workspace.
  outputFileTracingRoot: __dirname,
  turbopack: {
    root: __dirname,
  },
  reactStrictMode: true,
  // Do not emit client source maps in production (avoids leaking source).
  productionBrowserSourceMaps: false,
  // Strip console.* from production bundles (prevents accidental leakage of
  // tokens / API responses / error objects to the browser console).
  compiler: {
    removeConsole: isProd,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }]
  },
}

module.exports = nextConfig
