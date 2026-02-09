"use client"

import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  onReset?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
    this.props.onReset?.()
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex flex-col items-center justify-center p-8 rounded-xl border border-white/10 bg-white/5">
          <AlertTriangle className="h-10 w-10 text-yellow-400 mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-1">Something went wrong</h3>
          <p className="text-sm text-muted-foreground text-center max-w-md mb-4">
            {this.state.error?.message || 'An unexpected error occurred in this section.'}
          </p>
          <Button variant="outline" onClick={this.handleReset}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Try again
          </Button>
        </div>
      )
    }

    return this.props.children
  }
}

/** Wrapper for tab-level error boundaries */
export function TabErrorBoundary({ children, onReset }: { children: React.ReactNode; onReset?: () => void }) {
  return <ErrorBoundary onReset={onReset}>{children}</ErrorBoundary>
}

/** Wrapper for page-level error boundaries */
export function PageErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary
      fallback={
        <div className="flex flex-col items-center justify-center min-h-[60vh] p-8">
          <AlertTriangle className="h-16 w-16 text-yellow-400 mb-6" />
          <h2 className="text-2xl font-bold text-foreground mb-2">Page Error</h2>
          <p className="text-muted-foreground text-center max-w-md mb-6">
            This page encountered an unexpected error. Try refreshing the page.
          </p>
          <Button onClick={() => window.location.reload()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh Page
          </Button>
        </div>
      }
    >
      {children}
    </ErrorBoundary>
  )
}
