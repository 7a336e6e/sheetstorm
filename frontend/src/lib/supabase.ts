import { createClient, SupabaseClient } from '@supabase/supabase-js'

let _supabase: SupabaseClient | null = null

export function getSupabase(): SupabaseClient | null {
  if (_supabase) return _supabase

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!supabaseUrl || !supabaseAnonKey) {
    return null
  }

  _supabase = createClient(supabaseUrl, supabaseAnonKey)
  return _supabase
}

/** @deprecated Use getSupabase() which handles missing env vars gracefully */
export const supabase = (() => {
  const client = getSupabase()
  if (client) return client
  // Return a proxy that throws only when actually used, not at import time
  return new Proxy({} as SupabaseClient, {
    get(_, prop) {
      if (prop === 'then') return undefined // prevent Promise-like behavior
      throw new Error(
        'Supabase client is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY environment variables.'
      )
    },
  })
})()
