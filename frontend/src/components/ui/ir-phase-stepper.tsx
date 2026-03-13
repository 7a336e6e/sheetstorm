"use client"

import React, { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/lib/utils"
import {
  ShieldAlert,
  Crosshair,
  ShieldOff,
  Bug,
  RefreshCw,
  ClipboardCheck,
} from "lucide-react"

const phases = [
  {
    id: 1,
    title: "Preparation",
    short: "Prepare",
    icon: ShieldAlert,
    color: "from-cyan-400 to-cyan-500",
    glow: "rgba(6,182,212,0.5)",
    ring: "border-cyan-400/40",
    bg: "bg-cyan-500",
    desc: "Establish procedures, train teams, configure tools & monitoring.",
  },
  {
    id: 2,
    title: "Identification",
    short: "Identify",
    icon: Crosshair,
    color: "from-blue-400 to-blue-500",
    glow: "rgba(59,130,246,0.5)",
    ring: "border-blue-400/40",
    bg: "bg-blue-500",
    desc: "Detect & validate events, triage alerts, classify severity.",
  },
  {
    id: 3,
    title: "Containment",
    short: "Contain",
    icon: ShieldOff,
    color: "from-emerald-400 to-emerald-500",
    glow: "rgba(52,211,153,0.5)",
    ring: "border-emerald-400/40",
    bg: "bg-emerald-500",
    desc: "Isolate hosts, block threats, preserve forensic evidence.",
  },
  {
    id: 4,
    title: "Eradication",
    short: "Eradicate",
    icon: Bug,
    color: "from-amber-400 to-amber-500",
    glow: "rgba(251,191,36,0.5)",
    ring: "border-amber-400/40",
    bg: "bg-amber-500",
    desc: "Remove root cause, patch vulnerabilities, revoke access.",
  },
  {
    id: 5,
    title: "Recovery",
    short: "Recover",
    icon: RefreshCw,
    color: "from-orange-400 to-orange-500",
    glow: "rgba(251,146,60,0.5)",
    ring: "border-orange-400/40",
    bg: "bg-orange-500",
    desc: "Restore systems, validate integrity, increase monitoring.",
  },
  {
    id: 6,
    title: "Lessons Learned",
    short: "Review",
    icon: ClipboardCheck,
    color: "from-rose-400 to-rose-500",
    glow: "rgba(251,113,133,0.5)",
    ring: "border-rose-400/40",
    bg: "bg-rose-500",
    desc: "Document findings, update procedures & detection rules.",
  },
]

export function IRPhaseStepper() {
  const [active, setActive] = useState(0)
  const [auto, setAuto] = useState(true)

  useEffect(() => {
    if (!auto) return
    const timer = setInterval(() => {
      setActive((prev) => (prev + 1) % phases.length)
    }, 3000)
    return () => clearInterval(timer)
  }, [auto])

  const handleClick = (index: number) => {
    setActive(index)
    setAuto(false)
    setTimeout(() => setAuto(true), 10000)
  }

  return (
    <div className="w-full max-w-5xl mx-auto">
      {/* Phase nodes — horizontal timeline */}
      <div className="relative flex items-center justify-between px-4 md:px-0">
        {/* Connecting line */}
        <div className="absolute top-5 left-[8%] right-[8%] h-px bg-white/10" />
        <div
          className="absolute top-5 left-[8%] h-px bg-gradient-to-r from-cyan-500/60 to-cyan-500/20 transition-all duration-500"
          style={{ width: `${(active / (phases.length - 1)) * 84}%` }}
        />

        {phases.map((phase, index) => {
          const isActive = index === active
          const isPast = index < active
          const Icon = phase.icon

          return (
            <button
              key={phase.id}
              className="relative flex flex-col items-center gap-2.5 cursor-pointer group z-10"
              onClick={() => handleClick(index)}
            >
              {/* Node */}
              <div className="relative">
                {isActive && (
                  <motion.div
                    className={cn("absolute -inset-2 rounded-full border", phase.ring)}
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.3 }}
                  />
                )}
                {isActive && (
                  <motion.div
                    className="absolute -inset-3 rounded-full border border-white/10"
                    initial={{ scale: 0.6, opacity: 0 }}
                    animate={{ scale: [1, 1.5], opacity: [0.4, 0] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                )}

                <motion.div
                  className={cn(
                    "relative w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300",
                    isActive
                      ? cn(phase.bg, "text-white")
                      : isPast
                        ? "bg-white/15 text-cyan-300"
                        : "bg-white/5 text-slate-500 group-hover:bg-white/10 group-hover:text-slate-400",
                  )}
                  style={isActive ? { boxShadow: `0 0 20px -4px ${phase.glow}` } : {}}
                  animate={isActive ? { scale: [1, 1.05, 1] } : { scale: 1 }}
                  transition={{ duration: 2, repeat: isActive ? Infinity : 0 }}
                >
                  <Icon className="h-4 w-4" />
                </motion.div>
              </div>

              {/* Label */}
              <span
                className={cn(
                  "text-xs font-medium transition-colors whitespace-nowrap",
                  isActive ? "text-white" : isPast ? "text-slate-400" : "text-slate-600",
                )}
              >
                <span className="hidden sm:inline">{phase.title}</span>
                <span className="sm:hidden">{phase.short}</span>
              </span>
            </button>
          )
        })}
      </div>

      {/* Active phase detail card */}
      <div className="mt-6 px-4 md:px-0">
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
            className="bg-white/[0.06] backdrop-blur-sm border border-white/10 rounded-xl px-5 py-4 flex items-center gap-4"
          >
            <div
              className={cn(
                "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
                phases[active].bg,
              )}
              style={{ boxShadow: `0 0 16px -4px ${phases[active].glow}` }}
            >
              {React.createElement(phases[active].icon, { className: "h-4 w-4 text-white" })}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-widest text-slate-500">
                  Phase {phases[active].id}
                </span>
                <h4 className="text-sm font-semibold text-white">{phases[active].title}</h4>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                {phases[active].desc}
              </p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
