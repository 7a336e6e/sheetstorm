"use client"

import React, { useState, useRef, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/lib/utils"

interface TimelineNode {
  id: number
  title: string
  description: string
  icon: React.ReactNode
  color?: string
}

interface OrbitalTimelineProps {
  nodes: TimelineNode[]
  className?: string
  title?: string
  subtitle?: string
}

export function OrbitalTimeline({
  nodes,
  className,
  title,
  subtitle,
}: OrbitalTimelineProps) {
  const [activeNode, setActiveNode] = useState(0)
  const [autoRotate, setAutoRotate] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    if (!autoRotate) return
    timerRef.current = setInterval(() => {
      setActiveNode((prev) => (prev + 1) % nodes.length)
    }, 3500)
    return () => clearInterval(timerRef.current)
  }, [autoRotate, nodes.length])

  const handleNodeClick = (index: number) => {
    setActiveNode(index)
    setAutoRotate(false)
    // Resume auto-rotate after 8 seconds of inactivity
    clearInterval(timerRef.current)
    timerRef.current = setTimeout(() => setAutoRotate(true), 8000) as unknown as ReturnType<typeof setInterval>
  }

  const radius = 140

  return (
    <div className={cn("relative py-16", className)} ref={containerRef}>
      {title && (
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">{title}</h2>
          {subtitle && (
            <p className="text-muted-foreground leading-relaxed max-w-2xl mx-auto">{subtitle}</p>
          )}
        </div>
      )}

      <div className="flex flex-col lg:flex-row items-center gap-10 lg:gap-16 max-w-5xl mx-auto px-4">
        {/* Orbital visualization */}
        <div className="relative w-[340px] h-[340px] md:w-[380px] md:h-[380px] shrink-0">
          {/* Orbit ring */}
          <div className="absolute inset-8 rounded-full border border-primary/15" />
          <div className="absolute inset-14 rounded-full border border-primary/10" />

          {/* Subtle glow at center */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-20 h-20 rounded-full bg-primary/5 blur-xl" />
            <div className="absolute w-12 h-12 rounded-full bg-primary/10 blur-md" />
          </div>

          {/* Center label */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center z-10">
              <div className="text-xs uppercase tracking-widest text-muted-foreground mb-1">Phase</div>
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeNode}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="text-lg font-bold text-primary"
                >
                  {activeNode + 1}/{nodes.length}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>

          {/* Orbital nodes */}
          {nodes.map((node, index) => {
            const angle = (2 * Math.PI * index) / nodes.length - Math.PI / 2
            const x = Math.cos(angle) * radius
            const y = Math.sin(angle) * radius
            const isActive = index === activeNode

            return (
              <motion.button
                key={node.id}
                className="absolute flex items-center justify-center cursor-pointer z-20"
                style={{
                  left: `calc(50% + ${x}px - 22px)`,
                  top: `calc(50% + ${y}px - 22px)`,
                }}
                onClick={() => handleNodeClick(index)}
                whileHover={{ scale: 1.15 }}
                whileTap={{ scale: 0.95 }}
              >
                {/* Pulse ring for active */}
                {isActive && (
                  <motion.div
                    className="absolute inset-0 rounded-full border-2 border-primary/40"
                    initial={{ scale: 1, opacity: 0.6 }}
                    animate={{ scale: 1.8, opacity: 0 }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                )}

                {/* Connection line to center */}
                {isActive && (
                  <motion.div
                    className="absolute w-px bg-gradient-to-b from-primary/40 to-transparent"
                    style={{
                      height: radius - 30,
                      transformOrigin: "top center",
                      transform: `rotate(${angle + Math.PI / 2}rad)`,
                      left: "50%",
                      top: "50%",
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.3 }}
                  />
                )}

                <div
                  className={cn(
                    "w-11 h-11 rounded-full flex items-center justify-center transition-all duration-300 text-sm",
                    isActive
                      ? "bg-primary text-primary-foreground shadow-[0_0_20px_-4px_hsl(var(--primary))]"
                      : "bg-muted/80 text-muted-foreground border border-border/50 hover:border-primary/30 hover:text-primary",
                  )}
                >
                  {node.icon}
                </div>
              </motion.button>
            )
          })}
        </div>

        {/* Detail panel */}
        <div className="flex-1 min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeNode}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.35 }}
              className="glass rounded-xl p-6 md:p-8"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                  {nodes[activeNode].icon}
                </div>
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wider">
                    Phase {nodes[activeNode].id}
                  </div>
                  <h3 className="text-xl font-bold tracking-tight">{nodes[activeNode].title}</h3>
                </div>
              </div>
              <p className="text-muted-foreground leading-relaxed">
                {nodes[activeNode].description}
              </p>
            </motion.div>
          </AnimatePresence>

          {/* Phase dots navigation */}
          <div className="flex gap-2 mt-4">
            {nodes.map((_, index) => (
              <button
                key={index}
                onClick={() => handleNodeClick(index)}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-300",
                  index === activeNode
                    ? "w-8 bg-primary"
                    : "w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/50",
                )}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
