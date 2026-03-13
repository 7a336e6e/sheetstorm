"use client"

import React, { useEffect, useRef, useState, useCallback } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { Shield, Github, ArrowRight, Pause, Play } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAnimation } from '@/components/providers/animation-provider'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
}

export function AnimatedNavbar({ className }: { className?: string }) {
  const [scrolled, setScrolled] = useState(false)
  const { isAnimationPaused, toggleAnimation } = useAnimation()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const navRef = useRef<HTMLElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const mouseRef = useRef({ x: 0, y: 0, active: false })
  const animRef = useRef<number>(0)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const spawnParticles = useCallback((x: number, y: number, count: number = 3) => {
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2
      const speed = Math.random() * 1.5 + 0.5
      particlesRef.current.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 0.5,
        life: 0,
        maxLife: Math.random() * 40 + 20,
        size: Math.random() * 2 + 0.5,
      })
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    const nav = navRef.current
    if (!canvas || !nav) return

    const handleResize = () => {
      const rect = nav.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
      const ctx = canvas.getContext("2d")
      if (ctx) ctx.scale(dpr, dpr)
    }
    handleResize()
    window.addEventListener("resize", handleResize)

    const handleMouseMove = (e: MouseEvent) => {
      const rect = nav.getBoundingClientRect()
      mouseRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        active: true,
      }
      if (Math.random() > 0.6) {
        spawnParticles(mouseRef.current.x, mouseRef.current.y, 1)
      }
    }

    const handleMouseLeave = () => {
      mouseRef.current.active = false
    }

    nav.addEventListener("mousemove", handleMouseMove)
    nav.addEventListener("mouseleave", handleMouseLeave)

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const render = () => {
      const rect = nav.getBoundingClientRect()
      ctx.clearRect(0, 0, rect.width, rect.height)

      particlesRef.current = particlesRef.current.filter((p) => {
        p.x += p.vx
        p.y += p.vy
        p.vy += 0.02 // slight gravity
        p.life++

        const progress = p.life / p.maxLife
        const alpha = 1 - progress

        if (alpha <= 0) return false

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size * (1 - progress * 0.5), 0, Math.PI * 2)
        ctx.fillStyle = `rgba(6,182,212,${alpha * 0.8})`
        ctx.fill()

        return true
      })

      animRef.current = requestAnimationFrame(render)
    }

    animRef.current = requestAnimationFrame(render)

    return () => {
      cancelAnimationFrame(animRef.current)
      window.removeEventListener("resize", handleResize)
      nav.removeEventListener("mousemove", handleMouseMove)
      nav.removeEventListener("mouseleave", handleMouseLeave)
    }
  }, [spawnParticles])

  return (
    <header
      ref={navRef}
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-500",
        scrolled
          ? "border-b border-white/[0.06] bg-[#0a0e1a]/60 backdrop-blur-xl"
          : "bg-transparent",
        className,
      )}
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none"
        aria-hidden="true"
      />
      <div className="container mx-auto px-4 py-3 relative z-10">
        <nav className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <Shield className="h-6 w-6 text-primary transition-transform group-hover:scale-110 group-hover:rotate-6" />
            <span className="text-lg font-semibold tracking-tight">SheetStorm</span>
          </Link>
          <div className="flex items-center gap-2">
            <a
              href="https://github.com/7a336e6e/sheetstorm"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex"
            >
              <Button variant="ghost" size="icon-sm">
                <Github className="h-4 w-4" />
              </Button>
            </a>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleAnimation}
              title={isAnimationPaused ? "Play animations" : "Pause animations"}
            >
              {isAnimationPaused ? (
                <Play className="h-4 w-4" />
              ) : (
                <Pause className="h-4 w-4" />
              )}
            </Button>
            <Link
              href="/login"
              className="group relative h-9 px-4 rounded-full flex items-center justify-center bg-white/10 border border-white/10 hover:border-transparent transition-all duration-500 overflow-hidden"
              style={{ '--gradient-from': '#a855f7', '--gradient-to': '#ec4899' } as React.CSSProperties}
            >
              <span className="absolute inset-0 rounded-full bg-[linear-gradient(135deg,var(--gradient-from),var(--gradient-to))] opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <span className="relative z-10 text-sm font-medium text-white/80 group-hover:text-white transition-colors">Sign In</span>
            </Link>
            <Link
              href="/register"
              className="group relative h-9 px-4 rounded-full flex items-center justify-center bg-white/10 border border-white/10 hover:border-transparent transition-all duration-500 overflow-hidden"
              style={{ '--gradient-from': '#06b6d4', '--gradient-to': '#3b82f6' } as React.CSSProperties}
            >
              <span className="absolute inset-0 rounded-full bg-[linear-gradient(135deg,var(--gradient-from),var(--gradient-to))] opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <span className="absolute inset-x-0 top-[10px] h-full rounded-full bg-[linear-gradient(135deg,var(--gradient-from),var(--gradient-to))] blur-[12px] opacity-0 -z-10 group-hover:opacity-30 transition-opacity duration-500" />
              <span className="relative z-10 text-sm font-medium text-white/80 group-hover:text-white transition-colors flex items-center gap-1.5">
                Get Started
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          </div>
        </nav>
      </div>
    </header>
  )
}
