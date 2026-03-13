"use client"

import React, { createContext, useContext, useEffect, useState } from 'react'

interface AnimationContextType {
  isAnimationPaused: boolean
  toggleAnimation: () => void
}

const AnimationContext = createContext<AnimationContextType | undefined>(undefined)

export function AnimationProvider({ children }: { children: React.ReactNode }) {
  const [isAnimationPaused, setIsAnimationPaused] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem('animation-paused')
    if (stored === 'true') {
      setIsAnimationPaused(true)
    }
  }, [])

  const toggleAnimation = () => {
    setIsAnimationPaused((prev) => {
      const newValue = !prev
      localStorage.setItem('animation-paused', String(newValue))
      return newValue
    })
  }

  return (
    <AnimationContext.Provider value={{ isAnimationPaused, toggleAnimation }}>
      {children}
    </AnimationContext.Provider>
  )
}

export function useAnimation() {
  const context = useContext(AnimationContext)
  if (context === undefined) {
    throw new Error('useAnimation must be used within an AnimationProvider')
  }
  return context
}
