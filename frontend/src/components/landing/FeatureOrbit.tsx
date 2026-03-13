"use client"

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  Activity,
  FileText,
  Users,
  BarChart3,
  Lock,
  Zap,
  Search,
  BookOpen,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface Feature {
  icon: LucideIcon
  title: string
  description: string
  color: string     // tailwind text class
  hex: string       // hex for SVG
}

const features: Feature[] = [
  { icon: Activity,  title: 'Timeline Tracking',      description: 'Chronological event tracking with MITRE ATT&CK mapping and kill-chain phase tagging.',             color: 'text-blue-500',    hex: '#3b82f6' },
  { icon: FileText,  title: 'Evidence Management',    description: 'Secure artifact storage with hash verification and complete chain of custody.',                     color: 'text-emerald-500', hex: '#10b981' },
  { icon: Users,     title: 'Real-time Collaboration', description: 'WebSocket-powered live updates so your entire team sees changes as they happen.',                  color: 'text-violet-500',  hex: '#8b5cf6' },
  { icon: BarChart3, title: 'Attack Visualization',   description: 'Auto-generated interactive attack graphs with 11 node types and 12 edge types.',                   color: 'text-orange-500',  hex: '#f97316' },
  { icon: Lock,      title: 'RBAC Security',          description: '6 roles with 40+ granular permissions, MFA/TOTP, SSO, and full audit trail.',                      color: 'text-rose-500',    hex: '#f43f5e' },
  { icon: Zap,       title: 'AI-Powered Reports',     description: 'Generate executive summaries, IOC analysis, and trend reports via GPT-4 or Gemini.',               color: 'text-amber-500',   hex: '#f59e0b' },
  { icon: Search,    title: 'Threat Intelligence',    description: 'CVE lookup, IP/domain/email reputation, ransomware victim search, and IOC defanging.',              color: 'text-cyan-500',    hex: '#06b6d4' },
  { icon: BookOpen,  title: 'Knowledge Base',         description: 'Built-in LOLBAS, Windows Event IDs, and MITRE D3FEND defensive countermeasures.',                   color: 'text-indigo-500',  hex: '#6366f1' },
]

const TOTAL = features.length
const FEATURE_INTERVAL = 3500

// ─── Geometry helpers ────────────────────────────────────────────────────────

const ORBIT_R = 130
const CENTER = 170          // viewBox is 340×340
const ICON_R = 22           // radius of each icon circle

function posFor(index: number) {
  const angle = (index / TOTAL) * Math.PI * 2 - Math.PI / 2   // start at top
  return {
    x: CENTER + Math.cos(angle) * ORBIT_R,
    y: CENTER + Math.sin(angle) * ORBIT_R,
    angle,
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export function FeatureOrbit() {
  const [activeIndex, setActiveIndex] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const [spokeActiveIndex, setSpokeActiveIndex] = useState(0)
  const prevIndex = useRef(0)
  // Track cumulative rotation so the hand always goes clockwise (never reverses)
  const cumulativeAngle = useRef(-90) // start at top (index 0 → -90°)

  const advance = useCallback(() => {
    setActiveIndex((prev) => {
      prevIndex.current = prev
      const next = (prev + 1) % TOTAL
      // Always add one step clockwise (positive direction)
      cumulativeAngle.current += 360 / TOTAL
      return next
    })
  }, [])

  useEffect(() => {
    if (isPaused) return
    const timer = setInterval(advance, FEATURE_INTERVAL)
    return () => clearInterval(timer)
  }, [isPaused, advance])

  // Turn off spoke immediately when hand starts moving, light up after arrival
  useEffect(() => {
    setSpokeActiveIndex(-1)
    const timeout = setTimeout(() => {
      setSpokeActiveIndex(activeIndex)
    }, 800)
    return () => clearTimeout(timeout)
  }, [activeIndex])

  const active = features[activeIndex]
  const activePos = posFor(activeIndex)

  // Pre-compute all positions once
  const positions = useMemo(() => features.map((_, i) => posFor(i)), [])

  // Use cumulative angle so hand always rotates clockwise
  const handAngle = cumulativeAngle.current

  // When user clicks a feature, compute shortest clockwise jump
  const jumpTo = useCallback((target: number) => {
    setActiveIndex((prev) => {
      prevIndex.current = prev
      // Calculate clockwise steps from current to target
      const steps = (target - prev + TOTAL) % TOTAL
      cumulativeAngle.current += steps * (360 / TOTAL)
      return target
    })
  }, [])

  return (
    <section className="py-20">
      <div className="container mx-auto px-4">
        <div
          className="flex flex-col lg:flex-row items-center gap-12 lg:gap-16 max-w-5xl mx-auto"
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={() => setIsPaused(false)}
        >
          {/* ── Left: Orbit SVG ── */}
          <div className="relative flex-shrink-0" style={{ width: 340, height: 340 }}>
            <svg
              viewBox="0 0 340 340"
              className="w-full h-full"
              xmlns="http://www.w3.org/2000/svg"
            >
              <defs>
                {/* Glow filter for active node */}
                <filter id="orbit-glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>

                {/* Gradient for the clock hand */}
                <linearGradient id="hand-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="white" stopOpacity="0" />
                  <stop offset="60%" stopColor={active.hex} stopOpacity="0.5" />
                  <stop offset="100%" stopColor={active.hex} stopOpacity="1" />
                </linearGradient>

                {/* Flowing particle gradient */}
                <linearGradient id="flow-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="white" stopOpacity="0" />
                  <stop offset="50%" stopColor="white" stopOpacity="0.7" />
                  <stop offset="100%" stopColor="white" stopOpacity="0" />
                </linearGradient>
              </defs>

              {/* ── Outer orbit ring ── */}
              <circle cx={CENTER} cy={CENTER} r={ORBIT_R} fill="none" stroke="white" strokeOpacity="0.06" strokeWidth="1" />

              {/* ── Decorative inner rings ── */}
              <circle cx={CENTER} cy={CENTER} r={70} fill="none" stroke="white" strokeOpacity="0.03" strokeWidth="0.5" strokeDasharray="4 6" />
              <circle cx={CENTER} cy={CENTER} r={40} fill="none" stroke="white" strokeOpacity="0.03" strokeWidth="0.5" strokeDasharray="3 8" />

              {/* ── Connection lines: center → edge of each node circle ── */}
              {positions.map((pos, i) => {
                // Stop at the border of the icon circle, not its center
                const scale = (ORBIT_R - ICON_R) / ORBIT_R
                const edgeX = CENTER + (pos.x - CENTER) * scale
                const edgeY = CENTER + (pos.y - CENTER) * scale
                const isLit = i === spokeActiveIndex
                return (
                  <line
                    key={`spoke-${i}`}
                    x1={CENTER}
                    y1={CENTER}
                    x2={edgeX}
                    y2={edgeY}
                    stroke={isLit ? features[i].hex : 'white'}
                    strokeOpacity={isLit ? 0.5 : 0.04}
                    strokeWidth={isLit ? 1.5 : 0.5}
                    className="transition-all duration-700"
                  />
                )
              })}

              {/* ── Connection lines between adjacent nodes ── */}
              {positions.map((pos, i) => {
                const next = positions[(i + 1) % TOTAL]
                return (
                  <line
                    key={`arc-${i}`}
                    x1={pos.x}
                    y1={pos.y}
                    x2={next.x}
                    y2={next.y}
                    stroke="white"
                    strokeOpacity="0.05"
                    strokeWidth="0.5"
                  />
                )
              })}

              {/* ── Flowing particles along the orbit ── */}
              <circle r="2" fill="white" opacity="0.5">
                <animateMotion
                  dur="12s"
                  repeatCount="indefinite"
                  path={`M ${CENTER + ORBIT_R} ${CENTER} A ${ORBIT_R} ${ORBIT_R} 0 1 1 ${CENTER + ORBIT_R - 0.01} ${CENTER}`}
                />
                <animate attributeName="opacity" values="0;0.6;0" dur="12s" repeatCount="indefinite" />
              </circle>
              <circle r="1.5" fill="white" opacity="0.3">
                <animateMotion
                  dur="18s"
                  repeatCount="indefinite"
                  path={`M ${CENTER - ORBIT_R} ${CENTER} A ${ORBIT_R} ${ORBIT_R} 0 1 1 ${CENTER - ORBIT_R + 0.01} ${CENTER}`}
                />
                <animate attributeName="opacity" values="0;0.4;0" dur="18s" repeatCount="indefinite" />
              </circle>

              {/* ── Clock hand: rotates to active node ── */}
              <g
                style={{
                  transform: `rotate(${handAngle}deg)`,
                  transformOrigin: `${CENTER}px ${CENTER}px`,
                  transition: 'transform 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
                }}
              >
                <line
                  x1={CENTER}
                  y1={CENTER}
                  x2={CENTER + ORBIT_R - ICON_R}
                  y2={CENTER}
                  stroke="url(#hand-grad)"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                {/* Hand tip glow dot */}
                <circle
                  cx={CENTER + ORBIT_R - ICON_R - 2}
                  cy={CENTER}
                  r="3"
                  fill={active.hex}
                  opacity="0.8"
                >
                  <animate attributeName="r" values="2;4;2" dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.6;1;0.6" dur="2s" repeatCount="indefinite" />
                </circle>
              </g>

              {/* ── Center hub ── */}
              <circle cx={CENTER} cy={CENTER} r="6" fill={active.hex} opacity="0.15" className="transition-all duration-700" />
              <circle cx={CENTER} cy={CENTER} r="3" fill={active.hex} opacity="0.6" className="transition-all duration-700" />

              {/* ── Active node pulse rings ── */}
              <circle cx={activePos.x} cy={activePos.y} r={ICON_R + 4} fill="none" stroke={active.hex} strokeWidth="1" opacity="0.3">
                <animate attributeName="r" values={`${ICON_R + 2};${ICON_R + 14};${ICON_R + 2}`} dur="2.5s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.4;0;0.4" dur="2.5s" repeatCount="indefinite" />
              </circle>
              <circle cx={activePos.x} cy={activePos.y} r={ICON_R + 8} fill="none" stroke={active.hex} strokeWidth="0.5" opacity="0.15">
                <animate attributeName="r" values={`${ICON_R + 6};${ICON_R + 20};${ICON_R + 6}`} dur="3s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.2;0;0.2" dur="3s" repeatCount="indefinite" />
              </circle>

              {/* ── Feature icon circles ── */}
              {features.map((f, i) => {
                const pos = positions[i]
                const isActive = i === activeIndex
                return (
                  <g
                    key={f.title}
                    className="cursor-pointer"
                    onClick={() => {
                      jumpTo(i)
                    }}
                    role="button"
                    aria-label={f.title}
                  >
                    {/* Background circle */}
                    <circle
                      cx={pos.x}
                      cy={pos.y}
                      r={ICON_R}
                      fill={isActive ? f.hex : 'hsl(240 5% 12%)'}
                      fillOpacity={isActive ? 0.15 : 0.9}
                      stroke={isActive ? f.hex : 'white'}
                      strokeOpacity={isActive ? 0.6 : 0.08}
                      strokeWidth={isActive ? 1.5 : 0.5}
                      className="transition-all duration-500"
                    />
                    {/* Hover expand - invisible larger hit area */}
                    <circle
                      cx={pos.x}
                      cy={pos.y}
                      r={ICON_R + 6}
                      fill="transparent"
                    />
                  </g>
                )
              })}
            </svg>

            {/* ── Icon overlays (HTML for Lucide icons) ── */}
            {features.map((f, i) => {
              const pos = positions[i]
              const isActive = i === activeIndex
              const Icon = f.icon
              return (
                <button
                  key={`icon-${f.title}`}
                  onClick={() => {
                    jumpTo(i)
                  }}
                  className={cn(
                    'absolute flex items-center justify-center pointer-events-auto',
                    'transition-all duration-500',
                    isActive ? 'scale-110' : 'opacity-50 hover:opacity-80 hover:scale-105',
                  )}
                  style={{
                    width: ICON_R * 2,
                    height: ICON_R * 2,
                    left: `${(pos.x / 340) * 100}%`,
                    top: `${(pos.y / 340) * 100}%`,
                    transform: 'translate(-50%, -50%)',
                  }}
                  aria-label={f.title}
                >
                  <Icon className={cn('h-5 w-5', isActive ? f.color : 'text-slate-500')} />
                </button>
              )
            })}

            {/* Center logo */}
            <div
              className="absolute flex items-center justify-center pointer-events-none"
              style={{
                width: 40,
                height: 40,
                left: '50%',
                top: '50%',
                transform: 'translate(-50%, -50%)',
              }}
            >
              <div
                className="w-2.5 h-2.5 rounded-full transition-colors duration-700"
                style={{ backgroundColor: active.hex, boxShadow: `0 0 12px ${active.hex}40` }}
              />
            </div>
          </div>

          {/* ── Right: Feature description ── */}
          <div className="flex-1 text-center lg:text-left">
            <h2 className="text-3xl font-bold mb-4 text-white">
              Everything You Need for Incident Response
            </h2>
            <p className="text-slate-400 mb-8">
              Purpose-built by security practitioners. Every feature designed to
              accelerate your response workflow.
            </p>

            {/* Active feature card */}
            <div key={activeIndex} className="animate-phase-slide-in">
              <div className="flex items-start gap-4 p-5 rounded-xl border border-white/[0.08] bg-[hsl(240,5%,12%)]/80 backdrop-blur-sm">
                <div
                  className="p-2.5 rounded-lg shrink-0 transition-colors duration-500"
                  style={{ backgroundColor: `${active.hex}15` }}
                >
                  <active.icon className={cn('h-5 w-5', active.color)} />
                </div>
                <div>
                  <h3 className="font-semibold mb-1 text-white">{active.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    {active.description}
                  </p>
                </div>
              </div>
            </div>

            {/* Feature dots indicator */}
            <div className="flex gap-1.5 mt-6 justify-center lg:justify-start">
              {features.map((f, i) => (
                <button
                  key={i}
                  onClick={() => jumpTo(i)}
                  className={cn(
                    'h-1.5 rounded-full transition-all duration-300',
                    i === activeIndex
                      ? 'w-6'
                      : 'w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/50'
                  )}
                  style={i === activeIndex ? { backgroundColor: f.hex } : undefined}
                  aria-label={`Feature ${i + 1}: ${f.title}`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
