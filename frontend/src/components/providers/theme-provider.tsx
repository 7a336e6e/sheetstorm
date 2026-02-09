/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import * as React from "react"

type Theme = "light" | "dark" | "system"

interface ThemeProviderProps {
    children: React.ReactNode
    defaultTheme?: Theme
    storageKey?: string
}

interface ThemeProviderState {
    theme: Theme
    setTheme: (theme: Theme) => void
    resolvedTheme: "light" | "dark"
}

const ThemeProviderContext = React.createContext<ThemeProviderState | undefined>(
    undefined
)

export function ThemeProvider({
    children,
    defaultTheme = "system",
    storageKey = "sheetstorm-theme",
}: ThemeProviderProps) {
    const [theme, setThemeState] = React.useState<Theme>(defaultTheme)
    const [resolvedTheme, setResolvedTheme] = React.useState<"light" | "dark">("light")

    // Initialize theme from localStorage on mount
    React.useEffect(() => {
        const stored = localStorage.getItem(storageKey) as Theme | null
        if (stored) {
            setThemeState(stored)
        }
    }, [storageKey])

    // Handle theme changes and system preference
    React.useEffect(() => {
        const root = window.document.documentElement

        const applyTheme = (resolvedValue: "light" | "dark") => {
            root.classList.remove("light", "dark")
            root.classList.add(resolvedValue)
            setResolvedTheme(resolvedValue)
        }

        if (theme === "system") {
            const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
                ? "dark"
                : "light"
            applyTheme(systemTheme)

            // Listen for system theme changes
            const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)")
            const handler = (e: MediaQueryListEvent) => {
                applyTheme(e.matches ? "dark" : "light")
            }
            mediaQuery.addEventListener("change", handler)
            return () => mediaQuery.removeEventListener("change", handler)
        } else {
            applyTheme(theme)
        }
    }, [theme])

    const setTheme = React.useCallback(
        (newTheme: Theme) => {
            localStorage.setItem(storageKey, newTheme)
            setThemeState(newTheme)
        },
        [storageKey]
    )

    const value = React.useMemo(
        () => ({
            theme,
            setTheme,
            resolvedTheme,
        }),
        [theme, setTheme, resolvedTheme]
    )

    return (
        <ThemeProviderContext.Provider value={value}>
            {children}
        </ThemeProviderContext.Provider>
    )
}

export function useTheme() {
    const context = React.useContext(ThemeProviderContext)
    if (context === undefined) {
        throw new Error("useTheme must be used within a ThemeProvider")
    }
    return context
}
