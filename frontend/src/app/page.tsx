/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 *
 * Architecture: Fixed StarsBackground (z-0) + ShootingStars (z-1) persist
 * behind all content. Every section is transparent / glass — the cosmic
 * atmosphere continues unbroken as the user scrolls.
 */

"use client"

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useTheme } from '@/components/providers/theme-provider'
import { AnimatedNavbar } from '@/components/ui/animated-navbar'
import { FeatureSteps } from '@/components/ui/feature-steps'
import { OrbitalTimeline } from '@/components/ui/orbital-timeline'
import { IRPhaseStepper } from '@/components/ui/ir-phase-stepper'
import { ShootingStars } from '@/components/ui/shooting-stars'
import { StarsBackground } from '@/components/ui/stars-background'
import { SocialLinks } from '@/components/ui/social-links'
import { GradientMenu } from '@/components/ui/gradient-menu'
import { CopyCode } from '@/components/ui/copy-code-button'
import { ScrollReveal } from '@/components/ui/scroll-reveal'
import { AnimationProvider } from '@/components/providers/animation-provider'
import {
  Shield,
  Activity,
  FileText,
  Users,
  BarChart3,
  Lock,
  ArrowRight,
  Zap,
  Search,
  BookOpen,
  Github,
  GraduationCap,
  ShieldCheck,
  Building2,
  Flag,
  User,
  Code2,
  Terminal,
  ChevronDown,
  Crosshair,
  ShieldAlert,
  ShieldOff,
  Bug,
  RefreshCw,
  ClipboardCheck,
} from 'lucide-react'

/* ─── Data ────────────────────────────────────────────────────────── */

const phaseNodes = [
  {
    id: 1,
    title: 'Preparation',
    description: 'Establish incident response procedures, team training, and communication plans. Configure tools, define asset inventories, and set up monitoring before incidents occur.',
    icon: <ShieldAlert className="h-5 w-5" />,
  },
  {
    id: 2,
    title: 'Identification',
    description: 'Detect and validate security events. Triage alerts, gather initial evidence, classify severity, and determine whether an incident has occurred.',
    icon: <Crosshair className="h-5 w-5" />,
  },
  {
    id: 3,
    title: 'Containment',
    description: 'Limit the spread of the incident. Isolate affected hosts, block malicious IPs, preserve forensic evidence, and implement short- and long-term containment strategies.',
    icon: <ShieldOff className="h-5 w-5" />,
  },
  {
    id: 4,
    title: 'Eradication',
    description: 'Remove the root cause. Clean compromised systems, patch vulnerabilities, eliminate persistence mechanisms, and verify threat actor access is fully revoked.',
    icon: <Bug className="h-5 w-5" />,
  },
  {
    id: 5,
    title: 'Recovery',
    description: 'Restore systems to normal operation. Rebuild from known-good images, validate system integrity, increase monitoring, and phase services back into production.',
    icon: <RefreshCw className="h-5 w-5" />,
  },
  {
    id: 6,
    title: 'Lessons Learned',
    description: 'Conduct a post-incident review. Document what happened, what was effective, and what needs improvement. Update procedures, detection rules, and training materials.',
    icon: <ClipboardCheck className="h-5 w-5" />,
  },
]

const features = [
  {
    icon: Activity,
    title: 'Timeline Tracking',
    description: 'Chronological event tracking with MITRE ATT&CK mapping and kill-chain phase tagging.',
  },
  {
    icon: FileText,
    title: 'Evidence Management',
    description: 'Secure artifact storage with hash verification and complete chain of custody.',
  },
  {
    icon: Users,
    title: 'Real-time Collaboration',
    description: 'WebSocket-powered live updates so your entire team sees changes as they happen.',
  },
  {
    icon: BarChart3,
    title: 'Attack Visualization',
    description: 'Auto-generated interactive attack graphs with 11 node types and 12 edge types.',
  },
  {
    icon: Lock,
    title: 'RBAC Security',
    description: '6 roles with 40+ granular permissions, MFA/TOTP, SSO, and full audit trail.',
  },
  {
    icon: Zap,
    title: 'AI-Powered Reports',
    description: 'Generate executive summaries, IOC analysis, and trend reports via GPT-4 or Gemini.',
  },
  {
    icon: Search,
    title: 'Threat Intelligence',
    description: 'CVE lookup, IP/domain/email reputation, ransomware victim search, and IOC defanging.',
  },
  {
    icon: BookOpen,
    title: 'Knowledge Base',
    description: 'Built-in LOLBAS, Windows Event IDs, and MITRE D3FEND defensive countermeasures.',
  },
]

const audiences = [
  { icon: GraduationCap, title: 'DFIR Training & Labs', desc: 'Hands-on IR lifecycle practice with a realistic platform — no vendor licenses needed.' },
  { icon: ShieldCheck, title: 'Small Security Teams', desc: 'Structured incident management without the overhead of enterprise SOAR tools.' },
  { icon: Building2, title: 'Enterprise SOCs', desc: 'Self-hosted, extensible IR platform with API and MCP integration points.' },
  { icon: Flag, title: 'CTF & Blue Team Exercises', desc: 'Collaborative incident tracking purpose-built for blue team competitions.' },
  { icon: User, title: 'Solo Analysts', desc: 'Organize investigations with proper evidence handling and timeline tracking.' },
  { icon: Code2, title: 'Open Source Community', desc: 'MIT-licensed, fully self-hosted, and built to be extended by the community.' },
]

/* ─── Helpers ─────────────────────────────────────────────────────── */


function useThemedFeatureSteps() {
  const { resolvedTheme } = useTheme()
  const mode = resolvedTheme === 'light' ? 'light_mode' : 'dark_mode'

  return [
    {
      step: 'Incident Phase Management',
      title: 'Track every phase of your response',
      content: 'Manage incidents across all six IR lifecycle phases with structured data collection, team assignment, and severity classification.',
      image: `/screenshots/${mode}/incident_phases.png`,
    },
    {
      step: 'Host & Account Tracking',
      title: 'Map compromised assets instantly',
      content: 'Document compromised hosts and accounts with detailed containment status, forensic notes, and MITRE ATT&CK technique mapping.',
      image: `/screenshots/${mode}/host_tracking.png`,
    },
    {
      step: 'Timeline Analysis',
      title: 'Build the story of the attack',
      content: 'Construct chronological timelines with kill-chain phase tagging, evidence source tracking, and expandable event details.',
      image: `/screenshots/${mode}/expanded_event_entry.png`,
    },
    {
      step: 'MITRE ATT&CK Coverage',
      title: 'Visualize adversary behavior',
      content: 'Map detection coverage across MITRE ATT&CK tactics and techniques, identify gaps, and track adversary behavior patterns.',
      image: `/screenshots/${mode}/mitre_att%26ck_coverage.png`,
    },
    {
      step: 'Threat Intelligence',
      title: 'Enrich IOCs in real time',
      content: 'Query CVEs with CISA KEV + CVSS scoring, check IP/domain/email reputation, and search ransomware victim databases.',
      image: `/screenshots/${mode}/threat_intelligence.png`,
    },
    {
      step: 'Knowledge Base',
      title: 'Instant reference at your fingertips',
      content: 'Reference LOLBAS binaries, 65+ Windows Event IDs, and MITRE D3FEND defensive countermeasures with a built-in suggestion engine.',
      image: `/screenshots/${mode}/knowledge_base.png`,
    },
    {
      step: 'Evidence Storage',
      title: 'Preserve chain of custody',
      content: 'Upload and manage forensic artifacts with hash verification, chain of custody tracking, and optional S3 or Google Drive integration.',
      image: `/screenshots/${mode}/artifact_storage.png`,
    },
    {
      step: 'Malware Tracking',
      title: 'Catalog discovered threats',
      content: 'Document malware samples with file hashes, classification, and links to external threat intelligence — all tied to the incident.',
      image: `/screenshots/${mode}/malware_tracking.png`,
    },
  ]
}

/* ─── Reusable section-glow: subtle radial gradient for visual separation ── */

function SectionGlow({ color = 'cyan' }: { color?: 'cyan' | 'purple' | 'blue' }) {
  const colors = {
    cyan: 'radial-gradient(ellipse 80% 50% at 50% 0%, rgba(6,182,212,0.08) 0%, transparent 70%)',
    purple: 'radial-gradient(ellipse 80% 50% at 50% 0%, rgba(139,92,246,0.06) 0%, transparent 70%)',
    blue: 'radial-gradient(ellipse 80% 50% at 50% 0%, rgba(59,130,246,0.06) 0%, transparent 70%)',
  }
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{ background: colors[color] }}
      aria-hidden="true"
    />
  )
}

/* ─── Page ────────────────────────────────────────────────────────── */

export default function LandingPage() {
  const featureSteps = useThemedFeatureSteps()

  return (
    <AnimationProvider>
      <div className="dark min-h-screen overflow-x-hidden text-white" style={{ background: '#0a0e1a' }}>
        {/* === Fixed background layers === */}
        <StarsBackground className="fixed z-[1]" />
        {/* Cyber-themed shooting stars: cyan data streams + matrix green traces + purple threat alerts */}
        <ShootingStars
          starColor="#06b6d4"
          trailColor="#0e7490"
          minSpeed={12}
          maxSpeed={28}
          minDelay={1500}
          maxDelay={4500}
          starWidth={12}
          starHeight={1}
          className="fixed z-[2]"
        />
        <ShootingStars
          starColor="#00ff41"
          trailColor="#065f46"
          minSpeed={8}
          maxSpeed={22}
          minDelay={2500}
          maxDelay={6000}
          starWidth={8}
          starHeight={1}
          className="fixed z-[2]"
        />
        <ShootingStars
          starColor="#9333ea"
          trailColor="#6b21a8"
          minSpeed={15}
          maxSpeed={35}
          minDelay={3000}
          maxDelay={7000}
          starWidth={6}
          starHeight={1}
          className="fixed z-[2]"
        />

      {/* === Navbar (fixed, z-50) === */}
      <AnimatedNavbar />

      {/* === Scrollable content (z-10, above background layers) === */}
      <main className="relative z-10">

        {/* ═══════════════ ACT 1: THE HERO ═══════════════ */}
        <section className="relative min-h-screen flex flex-col items-center justify-center px-4 pt-20">
          <SectionGlow color="cyan" />

          <div className="relative z-10 max-w-4xl mx-auto text-center space-y-8">
            {/* Trust badge */}
            <ScrollReveal>
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 bg-white/5 backdrop-blur-sm text-sm text-slate-300">
                <Shield className="h-4 w-4 text-cyan-400" />
                Free &amp; Open Source — MIT Licensed
              </div>
            </ScrollReveal>

            {/* Headline */}
            <ScrollReveal delay={0.1}>
              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1]">
                <span className="block">Incident Response</span>
                <span className="block bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                  Without the Spreadsheet
                </span>
              </h1>
            </ScrollReveal>

            {/* Subtitle */}
            <ScrollReveal delay={0.2}>
              <p className="max-w-2xl mx-auto text-lg text-slate-400 leading-relaxed">
                A free, open-source platform for the DFIR community. Track incidents across the full
                response lifecycle with real-time collaboration, evidence integrity, and AI-powered insights.
              </p>
            </ScrollReveal>

            {/* CTA */}
            <ScrollReveal delay={0.3}>
              <div className="mt-10">
                <GradientMenu />
              </div>
            </ScrollReveal>

            <div className="mt-16 flex flex-col items-center gap-1 text-white/30">
              <span className="text-xs uppercase tracking-widest">Scroll</span>
              <ChevronDown className="h-4 w-4 animate-bounce" />
            </div>
          </div>
        </section>

        {/* IR Phase Stepper — integrated into hero flow */}
        <section className="relative -mt-8 pb-24 pt-0">
          <div className="container mx-auto px-4">
            <ScrollReveal>
              <IRPhaseStepper />
            </ScrollReveal>
          </div>
        </section>

        {/* ═══════════════ ACT 2: WHO IS THIS FOR ═══════════════ */}
        <section className="relative py-28">
          <SectionGlow color="purple" />
          <div className="container mx-auto px-4 relative z-10">
            <ScrollReveal>
              <div className="max-w-2xl mx-auto text-center mb-14">
                <h2 className="text-3xl font-bold mb-4 tracking-tight">Built for the DFIR Community</h2>
                <p className="text-slate-400 leading-relaxed">
                  Whether you&apos;re training, competing, or responding to real incidents — SheetStorm gives
                  every responder access to structured, collaborative IR for free.
                </p>
              </div>
            </ScrollReveal>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5 max-w-5xl mx-auto">
              {audiences.map((item, i) => (
                <ScrollReveal key={item.title} delay={i * 0.08}>
                  <Card variant="glass" className="group h-full hover:border-cyan-500/30 transition-all duration-300">
                    <CardContent className="pt-6">
                      <div className="p-2.5 rounded-lg bg-cyan-500/10 w-fit mb-4 group-hover:bg-cyan-500/20 transition-colors">
                        <item.icon className="h-5 w-5 text-cyan-400" />
                      </div>
                      <h3 className="font-semibold mb-2 text-white">{item.title}</h3>
                      <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
                    </CardContent>
                  </Card>
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* ═══════════════ ACT 3: FEATURES ═══════════════ */}
        <section className="relative py-28">
          <SectionGlow color="blue" />
          <div className="container mx-auto px-4 relative z-10">
            <ScrollReveal>
              <div className="max-w-2xl mx-auto text-center mb-14">
                <h2 className="text-3xl font-bold mb-4 tracking-tight">
                  Everything You Need for Incident Response
                </h2>
                <p className="text-slate-400 leading-relaxed">
                  Purpose-built by security practitioners. Every feature designed to
                  accelerate your response workflow.
                </p>
              </div>
            </ScrollReveal>

            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5 max-w-6xl mx-auto">
              {features.map((feature, i) => (
                <ScrollReveal key={feature.title} delay={i * 0.06}>
                  <Card variant="glass" className="group h-full hover:border-cyan-500/30 transition-all duration-300">
                    <CardContent className="pt-6">
                      <div className="p-2.5 rounded-lg bg-cyan-500/10 w-fit mb-4 group-hover:bg-cyan-500/20 transition-colors">
                        <feature.icon className="h-5 w-5 text-cyan-400" />
                      </div>
                      <h3 className="font-semibold mb-2 text-white">{feature.title}</h3>
                      <p className="text-sm text-slate-400 leading-relaxed">{feature.description}</p>
                    </CardContent>
                  </Card>
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* ═══════════════ ACT 4: SEE IT IN ACTION — FEATURE STEPS ═══════════════ */}
        <section className="relative py-28 overflow-hidden">
          <SectionGlow color="cyan" />
          <div className="relative z-10">
            <FeatureSteps
              features={featureSteps}
              title="See It in Action"
              autoPlayInterval={5000}
            />
          </div>
        </section>

        {/* ═══════════════ ACT 5: IR LIFECYCLE — ORBITAL TIMELINE ═══════════════ */}
        <section className="relative py-28 overflow-hidden">
          <SectionGlow color="purple" />
          <div className="relative z-10">
            <OrbitalTimeline
              nodes={phaseNodes}
              title="Full Incident Response Lifecycle"
              subtitle="Built-in support for all six phases of the incident response lifecycle, following NIST 800-61 best practices."
            />
          </div>
        </section>

        {/* ═══════════════ ACT 6: QUICK START ═══════════════ */}
        <section className="relative py-28 overflow-hidden">
          <SectionGlow color="blue" />
          <div className="container mx-auto px-4 relative z-10">
            <ScrollReveal>
              <div className="max-w-3xl mx-auto">
                <div className="text-center mb-10">
                  <h2 className="text-3xl font-bold mb-4 tracking-tight">Quick Start</h2>
                  <p className="text-slate-400">
                    Two commands. That&apos;s it. Docker handles the rest.
                  </p>
                </div>

                <Card variant="glass">
                  <CardContent className="py-6">
                    <div className="relative">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <Terminal className="h-3.5 w-3.5" />
                          <span className="font-mono">terminal</span>
                        </div>
                        <CopyCode
                          code={`git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
chmod +x start.sh && ./start.sh`}
                        />
                      </div>
                      <pre className="bg-black/40 rounded-lg p-5 overflow-x-auto text-sm font-mono text-slate-300 border border-white/5">
{`git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
chmod +x start.sh && ./start.sh`}
                      </pre>
                    </div>
                    <p className="text-sm text-slate-400 mt-5">
                      The start script generates secrets, builds all Docker containers, runs database
                      migrations, and seeds an admin user automatically.
                    </p>
                    <div className="grid sm:grid-cols-3 gap-3 mt-6 text-sm">
                      {[
                        { label: 'Frontend', port: ':3000' },
                        { label: 'API', port: ':5000' },
                        { label: 'MCP Server', port: ':8811' },
                      ].map((svc) => (
                        <div key={svc.label} className="flex flex-col items-center p-3 rounded-lg bg-white/5 border border-white/10">
                          <span className="font-semibold text-white">{svc.label}</span>
                          <span className="text-slate-400 font-mono text-xs">{svc.port}</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </ScrollReveal>
          </div>
        </section>

        {/* ═══════════════ ACT 7: CTA ═══════════════ */}
        <section className="py-28">
          <div className="container mx-auto px-4">
            <ScrollReveal>
              <Card variant="glass" className="max-w-3xl mx-auto border-cyan-500/20 shadow-[0_0_40px_-12px_rgba(6,182,212,0.15)]">
                <CardContent className="py-14 text-center">
                  <h2 className="text-2xl lg:text-3xl font-bold mb-4 tracking-tight text-white">
                    Ready to modernize your IR workflow?
                  </h2>
                  <p className="text-slate-400 mb-8 max-w-xl mx-auto leading-relaxed">
                    SheetStorm is free, open source, and self-hosted. Start using it today —
                    no sign-ups, no vendor lock-in.
                  </p>
                  <div className="flex justify-center">
                    <GradientMenu />
                  </div>
                </CardContent>
              </Card>
            </ScrollReveal>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/10 py-10">
        <div className="container mx-auto px-4">
          <div className="flex flex-col items-center gap-6">
            {/* Logo + tagline */}
            <div className="flex flex-col items-center gap-2">
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-cyan-400" />
                <span className="font-heading font-semibold text-white tracking-tight">SheetStorm</span>
              </div>
              <p className="text-xs text-slate-500 text-center max-w-xs">
                Free &amp; open-source incident response platform. Built for the DFIR community.
              </p>
            </div>

            {/* Social links */}
            <SocialLinks />

            {/* Divider + copyright */}
            <div className="w-full max-w-xs border-t border-white/5 pt-4">
              <p className="text-[11px] text-slate-600 text-center">
                &copy; {new Date().getFullYear()} SheetStorm &middot; MIT License
              </p>
            </div>
          </div>
        </div>
      </footer>
      </div>
    </AnimationProvider>
  )
}
