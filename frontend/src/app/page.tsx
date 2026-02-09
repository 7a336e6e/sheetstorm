/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import {
  Shield,
  Activity,
  FileText,
  Users,
  BarChart3,
  Lock,
  ArrowRight,
  Zap,
  CheckCircle,
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
    description: 'Chronological event tracking with MITRE ATT&CK mapping for complete incident visibility.',
  },
  {
    icon: FileText,
    title: 'Evidence Management',
    description: 'Secure artifact storage with hash verification and complete chain of custody.',
  },
  {
    icon: Users,
    title: 'Real-time Collaboration',
    description: 'Work together with live updates, presence indicators, and instant notifications.',
  },
  {
    icon: BarChart3,
    title: 'Attack Visualization',
    description: 'Interactive attack graphs to visualize lateral movement and threat progression.',
  },
  {
    icon: Lock,
    title: 'RBAC Security',
    description: 'Role-based access control with granular permissions and audit logging.',
  },
  {
    icon: Zap,
    title: 'AI-Powered Reports',
    description: 'Generate executive summaries and detailed reports with AI assistance.',
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border">
        <div className="container mx-auto px-4 py-4">
          <nav className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2">
              <Shield className="h-7 w-7 text-foreground" />
              <span className="text-xl font-semibold">SheetStorm</span>
            </Link>
            <div className="flex items-center gap-3">
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

      {/* Hero Section */}
      <main>
        <section className="py-20 lg:py-28">
          <div className="container mx-auto px-4 text-center">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted text-sm mb-8">
              <Zap className="h-4 w-4" />
              <span>Powered by MITRE ATT&CK Framework</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl lg:text-6xl font-bold mb-6 tracking-tight">
              Incident Response
              <br />
              <span className="text-muted-foreground">Made Intelligent</span>
            </h1>

            <p className="text-lg text-muted-foreground mb-10 max-w-2xl mx-auto">
              Full-stack incident response platform with structured incident response lifecycle
              with real-time collaboration, evidence integrity, and AI-powered insights.
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row justify-center gap-4">
              <Link href="/register">
                <Button size="lg">
                  Start Free Trial
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <Link href="/login">
                <Button size="lg" variant="outline">
                  View Demo
                </Button>
              </Link>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-8 max-w-xl mx-auto mt-16 pt-8 border-t border-border">
              <div className="text-center">
                <div className="text-2xl lg:text-3xl font-bold">99.9%</div>
                <div className="text-sm text-muted-foreground mt-1">Uptime SLA</div>
              </div>
              <div className="text-center">
                <div className="text-2xl lg:text-3xl font-bold">&lt;5min</div>
                <div className="text-sm text-muted-foreground mt-1">Setup Time</div>
              </div>
              <div className="text-center">
                <div className="text-2xl lg:text-3xl font-bold">SOC 2</div>
                <div className="text-sm text-muted-foreground mt-1">Compliant</div>
              </div>
            </div>
          </div>
        </section>

        {/* Features Grid */}
        <section className="py-20 bg-muted/30">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">
                Everything you need for incident response
              </h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Built by security professionals for security teams. Every feature designed
                to accelerate your response and protect your organization.
              </p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
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

        {/* IR Lifecycle Phases */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">
                Incident Response Lifecycle
              </h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Follow industry best practices with built-in support for the complete
                incident response lifecycle.
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

        {/* CTA Section */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <Card className="max-w-3xl mx-auto">
              <CardContent className="py-12 text-center">
                <h2 className="text-2xl lg:text-3xl font-bold mb-4">
                  Ready to transform your incident response?
                </h2>
                <p className="text-muted-foreground mb-8 max-w-xl mx-auto">
                  Join security teams worldwide who trust SheetStorm for their most critical incidents.
                </p>
                <div className="flex flex-col sm:flex-row justify-center gap-4">
                  <Link href="/register">
                    <Button size="lg">
                      Start Free Trial
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </Link>
                  <Link href="/login">
                    <Button size="lg" variant="outline">
                      Contact Sales
                    </Button>
                  </Link>
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
              Built for security teams. Powered by MITRE ATT&CK. Made with care.
            </p>
            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <Link href="#" className="hover:text-foreground transition-colors">Privacy</Link>
              <Link href="#" className="hover:text-foreground transition-colors">Terms</Link>
              <Link href="#" className="hover:text-foreground transition-colors">Security</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
