/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import Link from 'next/link'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useTheme } from '@/components/providers/theme-provider'
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
} from 'lucide-react'

const phases = [
  { number: 1, name: 'Preparation' },
  { number: 2, name: 'Identification' },
  { number: 3, name: 'Containment' },
  { number: 4, name: 'Eradication' },
  { number: 5, name: 'Recovery' },
  { number: 6, name: 'Lessons Learned' },
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

interface ShowcaseItem {
  title: string
  description: string
  image: string
}

const showcaseItems: ShowcaseItem[] = [
  {
    title: 'Incident Phase Management',
    description: 'Track incidents across all six IR lifecycle phases with structured data collection, team assignment, and severity classification.',
    image: 'incident_phases',
  },
  {
    title: 'Host & Account Tracking',
    description: 'Document compromised hosts and accounts with detailed containment status, forensic notes, and MITRE ATT&CK technique mapping.',
    image: 'host_tracking',
  },
  {
    title: 'Timeline & Event Analysis',
    description: 'Build chronological timelines with kill-chain phase tagging, evidence source tracking, and expandable event detail views.',
    image: 'expanded_event_entry',
  },
  {
    title: 'MITRE ATT&CK Coverage',
    description: 'Visualize your detection coverage across MITRE ATT&CK tactics and techniques, identify gaps, and track adversary behavior patterns.',
    image: 'mitre_att&ck_coverage',
  },
  {
    title: 'Threat Intelligence Lookups',
    description: 'Query CVEs with CISA KEV + CVSS scoring, check IP/domain/email reputation, and search ransomware victim databases — all from one interface.',
    image: 'threat_intelligence',
  },
  {
    title: 'Knowledge Base',
    description: 'Reference LOLBAS binaries, 65+ Windows Event IDs, and MITRE D3FEND defensive countermeasures with a built-in suggestion engine.',
    image: 'knowledge_base',
  },
  {
    title: 'Evidence & Artifact Storage',
    description: 'Upload and manage forensic artifacts with hash verification, chain of custody tracking, and optional S3 or Google Drive integration.',
    image: 'artifact_storage',
  },
  {
    title: 'Malware Tracking',
    description: 'Catalog malware samples discovered during investigations with file hashes, classification, and links to external threat intelligence.',
    image: 'malware_tracking',
  },
]

function ThemedScreenshot({ image, alt }: { image: string; alt: string }) {
  const { resolvedTheme } = useTheme()
  const mode = resolvedTheme === 'light' ? 'light_mode' : 'dark_mode'

  return (
    <Image
      src={`/screenshots/${mode}/${image}.png`}
      alt={alt}
      width={1200}
      height={700}
      className="rounded-lg border border-border shadow-lg w-full h-auto"
      priority={image === 'incident_phases'}
    />
  )
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border sticky top-0 z-50 bg-background/80 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-4">
          <nav className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2">
              <Shield className="h-7 w-7 text-foreground" />
              <span className="text-xl font-semibold">SheetStorm</span>
            </Link>
            <div className="flex items-center gap-3">
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
              <ThemeToggle />
              <Link href="/login">
                <Button variant="ghost">Sign In</Button>
              </Link>
              <Link href="/register">
                <Button>
                  Get Started
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero Section */}
        <section className="py-20 lg:py-28">
          <div className="container mx-auto px-4 text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted text-sm mb-8">
              <Shield className="h-4 w-4" />
              <span>Free & Open Source — MIT Licensed</span>
            </div>

            <h1 className="text-4xl lg:text-6xl font-bold mb-6 tracking-tight">
              Incident Response
              <br />
              <span className="text-muted-foreground">Without the Spreadsheet</span>
            </h1>

            <p className="text-lg text-muted-foreground mb-10 max-w-2xl mx-auto">
              A free, open-source platform for the DFIR community. Track incidents across the full
              response lifecycle with real-time collaboration, evidence integrity, and AI-powered insights.
            </p>

            <div className="flex flex-col sm:flex-row justify-center gap-4 mb-16">
              <Link href="/register">
                <Button size="lg">
                  Get Started
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <a
                href="https://github.com/7a336e6e/sheetstorm"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button variant="outline" size="lg">
                  <Github className="mr-2 h-4 w-4" />
                  View on GitHub
                </Button>
              </a>
            </div>

            {/* Hero Screenshot */}
            <div className="max-w-5xl mx-auto">
              <ThemedScreenshot image="incident_phases" alt="SheetStorm incident management dashboard" />
            </div>
          </div>
        </section>

        {/* Who is this for */}
        <section className="py-20 bg-muted/30">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">Built for the DFIR Community</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Whether you&apos;re training, competing, or responding to real incidents — SheetStorm gives
                every responder access to structured, collaborative IR for free.
              </p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
              {[
                { title: 'DFIR Training & Labs', desc: 'Hands-on IR lifecycle practice with a realistic platform — no vendor licenses needed.' },
                { title: 'Small Security Teams', desc: 'Structured incident management without the overhead of enterprise SOAR tools.' },
                { title: 'Enterprise SOCs', desc: 'Self-hosted, extensible IR platform with API and MCP integration points.' },
                { title: 'CTF & Blue Team Exercises', desc: 'Collaborative incident tracking purpose-built for blue team competitions.' },
                { title: 'Solo Analysts', desc: 'Organize investigations with proper evidence handling and timeline tracking.' },
                { title: 'Open Source Community', desc: 'MIT-licensed, fully self-hosted, and built to be extended by the community.' },
              ].map((item) => (
                <Card key={item.title}>
                  <CardContent className="pt-6">
                    <h3 className="font-semibold mb-2">{item.title}</h3>
                    <p className="text-sm text-muted-foreground">{item.desc}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        {/* Features Grid */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">
                Everything You Need for Incident Response
              </h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Purpose-built by security practitioners. Every feature designed to
                accelerate your response workflow.
              </p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
              {features.map((feature) => (
                <Card key={feature.title}>
                  <CardContent className="pt-6">
                    <div className="p-2 rounded-md bg-muted w-fit mb-4">
                      <feature.icon className="h-5 w-5" />
                    </div>
                    <h3 className="font-semibold mb-2">{feature.title}</h3>
                    <p className="text-sm text-muted-foreground">{feature.description}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        {/* Screenshot Showcase */}
        <section className="py-20 bg-muted/30">
          <div className="container mx-auto px-4">
            <div className="text-center mb-16">
              <h2 className="text-3xl font-bold mb-4">See It in Action</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                A closer look at the tools and views that help responders stay organized, thorough, and fast.
              </p>
            </div>

            <div className="max-w-5xl mx-auto space-y-24">
              {showcaseItems.map((item, index) => (
                <div
                  key={item.image}
                  className={`flex flex-col ${
                    index % 2 === 0 ? 'lg:flex-row' : 'lg:flex-row-reverse'
                  } gap-8 items-center`}
                >
                  <div className="lg:w-3/5">
                    <ThemedScreenshot image={item.image} alt={item.title} />
                  </div>
                  <div className="lg:w-2/5">
                    <h3 className="text-xl font-bold mb-3">{item.title}</h3>
                    <p className="text-muted-foreground">{item.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* IR Lifecycle Phases */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">
                Full Incident Response Lifecycle
              </h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Built-in support for all six phases of the incident response lifecycle,
                following industry best practices.
              </p>
            </div>

            <div className="flex flex-wrap justify-center gap-3 max-w-4xl mx-auto">
              {phases.map((phase) => (
                <div
                  key={phase.name}
                  className="flex items-center gap-2 px-4 py-2 rounded-full border border-border bg-background"
                >
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-sm font-semibold">
                    {phase.number}
                  </span>
                  <span className="font-medium">{phase.name}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Quick Start */}
        <section className="py-20 bg-muted/30">
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
                  <pre className="bg-muted rounded-lg p-4 overflow-x-auto text-sm font-mono">
{`git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
chmod +x start.sh && ./start.sh`}
                  </pre>
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

        {/* CTA Section */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <Card className="max-w-3xl mx-auto">
              <CardContent className="py-12 text-center">
                <h2 className="text-2xl lg:text-3xl font-bold mb-4">
                  Ready to modernize your IR workflow?
                </h2>
                <p className="text-muted-foreground mb-8 max-w-xl mx-auto">
                  SheetStorm is free, open source, and self-hosted. Start using it today —
                  no sign-ups, no vendor lock-in.
                </p>
                <div className="flex flex-col sm:flex-row justify-center gap-4">
                  <Link href="/register">
                    <Button size="lg">
                      Get Started
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </Link>
                  <a
                    href="https://github.com/7a336e6e/sheetstorm"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button variant="outline" size="lg">
                      <Github className="mr-2 h-4 w-4" />
                      Star on GitHub
                    </Button>
                  </a>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-8">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
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
              <Link href="#" className="hover:text-foreground transition-colors">MIT License</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
