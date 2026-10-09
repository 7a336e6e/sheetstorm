/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import * as React from "react"

/**
 * The app is dark-only (Cyber-Noir). `<html class="dark">` is set statically
 * in `app/layout.tsx`; this provider only removes the stale preference key
 * left behind by builds that had a light/system theme toggle.
 */
const LEGACY_STORAGE_KEY = "sheetstorm-theme"

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    React.useEffect(() => {
        try {
            window.localStorage.removeItem(LEGACY_STORAGE_KEY)
        } catch {
            // Storage unavailable (private mode / blocked) — nothing to clean.
        }
    }, [])

    return <>{children}</>
}

interface ThemeState {
    theme: "light" | "dark" | "system"
    resolvedTheme: "light" | "dark"
    setTheme: (theme: "light" | "dark" | "system") => void
}

const DARK_THEME: ThemeState = {
    theme: "dark",
    resolvedTheme: "dark",
    setTheme: () => {},
}

/** Kept for existing callers; the theme is always dark. */
export function useTheme() {
    return DARK_THEME
}
