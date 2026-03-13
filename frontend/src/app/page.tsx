/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useRef, useState, useEffect } from 'react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import {
  Github, ArrowRight, Linkedin, BookOpen as BookIcon,
  GraduationCap, Users, Building2, Trophy, UserCheck, Heart,
} from 'lucide-react'
import { SheetStormLogo } from '@/components/landing/SheetStormLogo'
import { IRPhaseAnimation } from '@/components/landing/IRPhaseAnimation'
import { ExpandingButton } from '@/components/landing/ExpandingButton'
import { FeatureOrbit } from '@/components/landing/FeatureOrbit'
import { FeatureShowcase } from '@/components/landing/FeatureShowcase'
import { CopyButton } from '@/components/landing/CopyButton'
import { StarryBackground } from '@/components/landing/StarryBackground'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ─── Data ────────────────────────────────────────────────────────────────────

const DFIR_AUDIENCES = [
  { icon: GraduationCap, title: 'DFIR Training & Labs', desc: 'Hands-on IR lifecycle practice with a realistic platform — no vendor licenses needed.', color: 'text-blue-400', hex: '#60a5fa' },
  { icon: Users, title: 'Small Security Teams', desc: 'Structured incident management without the overhead of enterprise SOAR tools.', color: 'text-emerald-400', hex: '#34d399' },
  { icon: Building2, title: 'Enterprise SOCs', desc: 'Self-hosted, extensible IR platform with API and MCP integration points.', color: 'text-violet-400', hex: '#a78bfa' },
  { icon: Trophy, title: 'CTF & Blue Team Exercises', desc: 'Collaborative incident tracking purpose-built for blue team competitions.', color: 'text-amber-400', hex: '#fbbf24' },
  { icon: UserCheck, title: 'Solo Analysts', desc: 'Organize investigations with proper evidence handling and timeline tracking.', color: 'text-cyan-400', hex: '#22d3ee' },
  { icon: Heart, title: 'Open Source Community', desc: 'MIT-licensed, fully self-hosted, and built to be extended by the community.', color: 'text-rose-400', hex: '#fb7185' },
]

const QUICK_START_CODE = `git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
chmod +x start.sh && ./start.sh`

// ─── Scroll Fade-In Helper ───────────────────────────────────────────────────────────────

function FadeIn({ children, className, delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={cn(
        'transition-all duration-700 ease-out',
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6',
        className
      )}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="dark force-dark min-h-screen relative">
      <StarryBackground />

      <div className="relative z-10">
      {/* ── Header ── */}
      <header className="border-b border-white/[0.06] sticky top-0 z-50 bg-background/80 backdrop-blur-xl" style={{ WebkitBackdropFilter: 'blur(24px)' }}>
        <div className="container mx-auto px-4 py-4">
          <nav className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5">
              <SheetStormLogo size={28} />
              <span className="text-xl font-semibold">SheetStorm</span>
            </Link>
            <div className="flex items-center gap-2">
              <a
                href="https://github.com/7a336e6e/sheetstorm"
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:inline-flex"
              >
                <Button variant="ghost" size="icon">
                  <Github className="h-5 w-5" />
                </Button>
              </a>
              <Link href="/login">
                <Button variant="ghost">Sign In</Button>
              </Link>
            </div>
          </nav>
        </div>
      </header>

      <main>
        {/* ── Hero ── */}
        <section className="py-20 lg:py-28 relative">
          {/* Subtle hero glow */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center_top,_rgba(99,102,241,0.1)_0%,_transparent_60%)] pointer-events-none" />

          <div className="container mx-auto px-4 text-center relative">
            <FadeIn>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.06] border border-white/[0.08] text-sm mb-8">
                <SheetStormLogo size={16} />
                <span>Free & Open Source — MIT Licensed</span>
              </div>
            </FadeIn>

            <FadeIn delay={100}>
              <h1 className="text-4xl lg:text-6xl font-bold mb-6 tracking-tight">
                Incident Response
                <br />
                <span className="bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500 bg-clip-text text-transparent">
                  Without the Spreadsheet
                </span>
              </h1>
            </FadeIn>

            <FadeIn delay={200}>
              <p className="text-lg text-muted-foreground mb-10 max-w-2xl mx-auto">
                A free, open-source platform for the DFIR community. Track incidents across the full
                response lifecycle with real-time collaboration, evidence integrity, and AI-powered insights.
              </p>
            </FadeIn>

            {/* Expanding buttons */}
            <FadeIn delay={300}>
              <div className="flex justify-center gap-4 mb-16">
                <ExpandingButton
                  icon={<ArrowRight className="h-5 w-5" />}
                  label="Get Started"
                  href="#quick-start"
                  onClick={(e) => {
                    e?.preventDefault()
                    document.getElementById('quick-start')?.scrollIntoView({ behavior: 'smooth' })
                  }}
                  variant="primary"
                />
                <ExpandingButton
                  icon={<Github className="h-5 w-5" />}
                  label="View on GitHub"
                  href="https://github.com/7a336e6e/sheetstorm"
                  variant="outline"
                  external
                />
              </div>
            </FadeIn>

            {/* Animated IR Phase Stepper (replaces hero screenshot) */}
            <FadeIn delay={400}>
              <IRPhaseAnimation />
            </FadeIn>
          </div>
        </section>

        {/* ── Who is this for ── */}
        <section className="py-20 bg-gradient-to-b from-indigo-950/20 via-background/80 to-indigo-950/20 backdrop-blur-sm border-t border-white/[0.03]">
          <div className="container mx-auto px-4">
            <div className="text-center mb-14">
              <h2 className="text-3xl font-bold mb-4">Built for the DFIR Community</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Whether you&apos;re training, competing, or responding to real incidents — SheetStorm gives
                every responder access to structured, collaborative IR for free.
              </p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
              {DFIR_AUDIENCES.map((item, i) => {
                const Icon = item.icon
                return (
                  <FadeIn key={item.title} delay={i * 80}>
                    <div className="group relative h-full rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 transition-all duration-500 hover:border-white/[0.12] hover:bg-white/[0.04] hover:shadow-lg hover:shadow-black/20">
                      {/* Top accent line */}
                      <div
                        className="absolute top-0 left-4 right-4 h-px opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                        style={{ background: `linear-gradient(90deg, transparent, ${item.hex}40, transparent)` }}
                      />
                      <div
                        className="mb-3 inline-flex items-center justify-center w-9 h-9 rounded-lg transition-colors duration-300"
                        style={{ backgroundColor: `${item.hex}12` }}
                      >
                        <Icon className={cn('h-4.5 w-4.5', item.color)} />
                      </div>
                      <h3 className="font-semibold mb-1.5 text-sm">{item.title}</h3>
                      <p className="text-sm text-muted-foreground leading-relaxed">{item.desc}</p>
                    </div>
                  </FadeIn>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Features Orbit (replaces features grid) ── */}
        <FeatureOrbit />

        {/* ── See It in Action — Live Mock Views ── */}
        <section className="py-20 bg-gradient-to-b from-violet-950/20 via-background/80 to-violet-950/20 backdrop-blur-sm border-t border-white/[0.03]">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">See It in Action</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                A closer look at the tools and views that help responders stay organized, thorough, and fast.
              </p>
            </div>

            <FadeIn>
              <FeatureShowcase />
            </FadeIn>
          </div>
        </section>

        {/* ── Quick Start ── */}
        <section id="quick-start" className="py-20 scroll-mt-20">
          <div className="container mx-auto px-4">
            <div className="max-w-3xl mx-auto">
              <div className="text-center mb-10">
                <h2 className="text-3xl font-bold mb-4">Quick Start</h2>
                <p className="text-muted-foreground">
                  Two commands. That&apos;s it. Docker handles the rest.
                </p>
              </div>

              <Card>
                <CardContent className="py-6">
                  <div className="relative">
                    <pre className="bg-muted rounded-lg p-4 pr-12 overflow-x-auto text-sm font-mono">
{QUICK_START_CODE}
                    </pre>
                    <CopyButton text={QUICK_START_CODE} />
                  </div>
                  <p className="text-sm text-muted-foreground mt-4">
                    The start script generates secrets, builds all Docker containers, runs database
                    migrations, and seeds an admin user automatically.
                  </p>
                  <div className="grid sm:grid-cols-3 gap-4 mt-6 text-sm">
                    <div className="flex flex-col items-center p-3 rounded-lg bg-muted">
                      <span className="font-semibold">Frontend</span>
                      <span className="text-muted-foreground">:3000</span>
                    </div>
                    <div className="flex flex-col items-center p-3 rounded-lg bg-muted">
                      <span className="font-semibold">API</span>
                      <span className="text-muted-foreground">:5000</span>
                    </div>
                    <div className="flex flex-col items-center p-3 rounded-lg bg-muted">
                      <span className="font-semibold">MCP Server</span>
                      <span className="text-muted-foreground">:8811</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>

        {/* ── Community Section ── */}
        <section className="py-20 bg-gradient-to-b from-blue-950/20 via-background/80 to-blue-950/20 backdrop-blur-sm border-t border-white/[0.03]">
          <div className="container mx-auto px-4">
            <Card className="max-w-3xl mx-auto bg-card/80 backdrop-blur-sm border-white/[0.06]">
              <CardContent className="py-12 text-center">
                <h2 className="text-2xl lg:text-3xl font-bold mb-4">
                  Join the Community
                </h2>
                <p className="text-muted-foreground mb-8 max-w-xl mx-auto">
                  SheetStorm is free, open source, and built by practitioners.
                  Star the repo, contribute features, or just say hello.
                </p>
                <div className="flex flex-wrap justify-center gap-4">
                  <ExpandingButton
                    icon={<Github className="h-5 w-5" />}
                    label="Star on GitHub"
                    href="https://github.com/7a336e6e/sheetstorm"
                    variant="primary"
                    external
                  />
                  <ExpandingButton
                    icon={<BookIcon className="h-5 w-5" />}
                    label="Documentation"
                    href="https://github.com/7a336e6e/sheetstorm#readme"
                    variant="outline"
                    external
                  />
                  <ExpandingButton
                    icon={<Linkedin className="h-5 w-5" />}
                    label="LinkedIn"
                    href="https://www.linkedin.com/in/cybergeorge/"
                    variant="outline"
                    external
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-white/[0.06] py-8 bg-background/80 backdrop-blur-sm">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <SheetStormLogo size={20} />
              <span className="font-semibold">SheetStorm</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Free & open source. Built for the DFIR community.
            </p>
            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <a
                href="https://github.com/7a336e6e/sheetstorm"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                GitHub
              </a>
              <a
                href="https://www.linkedin.com/in/cybergeorge/"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                LinkedIn
              </a>
              <a href="https://github.com/7a336e6e/sheetstorm/blob/main/LICENSE" target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">MIT License</a>
            </div>
          </div>
        </div>
      </footer>
      </div>
    </div>
  )
}
