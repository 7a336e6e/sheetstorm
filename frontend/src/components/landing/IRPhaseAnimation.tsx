"use client"

import { useState, useEffect, useCallback, useRef } from 'react'
import { CheckCircle2, ChevronUp, Shield, BookOpen } from 'lucide-react'
import { cn } from '@/lib/utils'

// ─── Phase definitions (matches IRPhaseTracker on the incidents page) ────────

const PHASES = [
  { number: 1, name: 'Preparation', color: 'from-blue-500 to-cyan-500' },
  { number: 2, name: 'Identification', color: 'from-cyan-500 to-teal-500' },
  { number: 3, name: 'Containment', color: 'from-teal-500 to-green-500' },
  { number: 4, name: 'Eradication', color: 'from-green-500 to-yellow-500' },
  { number: 5, name: 'Recovery', color: 'from-yellow-500 to-orange-500' },
  { number: 6, name: 'Lessons Learned', color: 'from-orange-500 to-red-500' },
] as const

const PHASE_DESCRIPTIONS: Record<number, { subtitle: string; steps: { action: string; detail: string; d3fend?: string }[] }> = {
  1: {
    subtitle: 'Establish readiness before incidents occur',
    steps: [
      { action: 'Verify IR team roster and communication channels', detail: 'Ensure all responders have current contact info and access to secure comms.', d3fend: 'D3-OAM · Operational Activity Mapping' },
      { action: 'Validate detection and logging infrastructure', detail: 'Confirm SIEM, EDR, and centralized logging are operational and ingesting data.', d3fend: 'D3-NTA · Network Traffic Analysis' },
      { action: 'Review and update response playbooks', detail: 'Ensure runbooks are current for common incident types (ransomware, phishing, insider threat).', d3fend: 'D3-PM · Platform Monitoring' },
      { action: 'Test backup integrity and restoration', detail: 'Verify backups are complete, accessible, and can be restored within RTO/RPO.', d3fend: 'D3-BA · Backup' },
    ],
  },
  2: {
    subtitle: 'Detect, validate, and scope the incident',
    steps: [
      { action: 'Triage alerts — confirm true positive', detail: 'Correlate alerts across data sources. Eliminate false positives before escalating.', d3fend: 'D3-DA · Dynamic Analysis' },
      { action: 'Determine scope of compromise', detail: 'Identify affected systems, users, data, and network segments.', d3fend: 'D3-AM · Asset Inventory' },
      { action: 'Collect and preserve IOCs', detail: 'Gather file hashes, IPs, domains, registry keys, and suspicious process names.', d3fend: 'D3-FAPA · File Analysis' },
      { action: 'Establish an event timeline', detail: 'Chronologically order all evidence from earliest known attacker activity.', d3fend: 'D3-OAM · Operational Activity Mapping' },
    ],
  },
  3: {
    subtitle: 'Limit damage and prevent lateral spread',
    steps: [
      { action: 'Isolate compromised hosts', detail: 'Network-isolate affected endpoints via EDR or firewall rules.', d3fend: 'D3-NI · Network Isolation' },
      { action: 'Block attacker infrastructure at perimeter', detail: 'Add C2 IPs, domains, and malware hashes to blocklists.', d3fend: 'D3-ITF · Inbound Traffic Filtering' },
      { action: 'Disable compromised accounts', detail: 'Lock or disable breached accounts. Force password resets.', d3fend: 'D3-AL · Account Locking' },
      { action: 'Preserve forensic evidence', detail: 'Capture disk images, memory dumps, and network PCAPs before remediation.' },
    ],
  },
  4: {
    subtitle: 'Remove the attacker and all persistence mechanisms',
    steps: [
      { action: 'Remove malware and backdoors', detail: 'Delete malicious binaries, scripts, scheduled tasks, and persistence.', d3fend: 'D3-FE · File Eviction' },
      { action: 'Patch exploited vulnerabilities', detail: 'Apply security updates for the CVEs used for initial access.', d3fend: 'D3-SU · Software Update' },
      { action: 'Rotate all compromised credentials', detail: 'Reset passwords, revoke tokens/API keys, and rotate certificates.', d3fend: 'D3-CRO · Credential Rotation' },
      { action: 'Scan for residual IOCs', detail: 'Run full-environment sweeps with updated signatures/YARA rules.', d3fend: 'D3-FAPA · File Analysis' },
    ],
  },
  5: {
    subtitle: 'Restore operations with confidence',
    steps: [
      { action: 'Restore from clean backups', detail: 'Rebuild affected systems from verified clean backups.', d3fend: 'D3-RFS · Restore from Backup' },
      { action: 'Reconnect systems incrementally', detail: 'Bring systems online one at a time with enhanced monitoring.', d3fend: 'D3-NI · Network Isolation' },
      { action: 'Monitor for re-compromise', detail: 'Deploy targeted detection rules for the same TTPs/IOCs.', d3fend: 'D3-NTA · Network Traffic Analysis' },
      { action: 'Verify data integrity', detail: 'Validate restored data against checksums for tampering.', d3fend: 'D3-FV · File Verification' },
    ],
  },
  6: {
    subtitle: 'Improve defenses based on what happened',
    steps: [
      { action: 'Conduct post-incident review', detail: 'Hold a blameless retrospective within 1-2 weeks with all responders.' },
      { action: 'Document full incident timeline', detail: 'Produce comprehensive timeline from initial compromise through recovery.' },
      { action: 'Identify detection gaps', detail: 'Analyze which TTPs were not detected and where visibility was lacking.', d3fend: 'D3-DE · Detection' },
      { action: 'Update detection rules and playbooks', detail: 'Create new SIEM rules, YARA signatures, and update response procedures.' },
    ],
  },
}

const CYCLE_INTERVAL = 3800

// ─── Component ───────────────────────────────────────────────────────────────

export function IRPhaseAnimation() {
  // Simulated "current phase" that auto-cycles
  const [currentPhase, setCurrentPhase] = useState(1)
  const [isPaused, setIsPaused] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  const advance = useCallback(() => {
    setCurrentPhase((prev) => (prev % 6) + 1)
  }, [])

  useEffect(() => {
    if (isPaused) return
    const timer = setInterval(advance, CYCLE_INTERVAL)
    return () => clearInterval(timer)
  }, [isPaused, advance])

  // Click jumps to that phase and continues cycling from there
  const handlePhaseClick = (num: number) => {
    setCurrentPhase(num)
  }

  return (
    <div
      className="w-full max-w-3xl mx-auto"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <div className="rounded-xl border border-border bg-card p-4 lg:p-6 relative overflow-hidden">
        {/* Subtle grid background — matches incidents page */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(6,182,212,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.5) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />

        {/* Phase bubbles row */}
        <div className="relative flex items-center w-full">
          {PHASES.map((phase, index) => {
            const isCompleted = phase.number < currentPhase
            const isCurrent = phase.number === currentPhase
            const isSelected = currentPhase === phase.number

            return (
              <div key={phase.number} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center z-10 relative">
                  <button
                    onClick={() => handlePhaseClick(phase.number)}
                    className={cn(
                      'relative w-10 h-10 lg:w-12 lg:h-12 rounded-full flex items-center justify-center',
                      'font-semibold text-sm transition-all duration-300 cursor-pointer group',
                      isCompleted && `bg-gradient-to-r ${phase.color} text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/40 hover:scale-110`,
                      isCurrent && `bg-gradient-to-r ${phase.color} text-white hover:scale-110`,
                      !isCompleted && !isCurrent && 'bg-black/[0.06] dark:bg-white/[0.06] text-black/30 dark:text-white/30 border border-white/[0.08] hover:bg-black/[0.1] dark:hover:bg-white/[0.1] hover:scale-105',
                      isSelected && 'ring-2 ring-cyan-400/50 ring-offset-2 ring-offset-transparent',
                    )}
                    title={`Phase ${phase.number}: ${phase.name} — Click for recommendations`}
                  >
                    {/* Pulse ring on current phase */}
                    {isCurrent && (
                      <span className="absolute inset-0 rounded-full animate-ping bg-gradient-to-r from-cyan-400/40 to-transparent pointer-events-none" style={{ animationDuration: '2s' }} />
                    )}

                    {isCompleted ? (
                      <CheckCircle2 className="h-5 w-5" />
                    ) : (
                      <span className={isCurrent ? 'drop-shadow-[0_0_6px_rgba(255,255,255,0.5)]' : ''}>
                        {phase.number}
                      </span>
                    )}
                  </button>

                  <span
                    className={cn(
                      'text-[10px] lg:text-xs mt-2 text-center font-medium transition-colors duration-300',
                      'max-w-[80px] lg:max-w-[100px] leading-tight',
                      isCompleted && 'text-cyan-400',
                      isCurrent && 'text-cyan-300',
                      !isCompleted && !isCurrent && 'text-black/30 dark:text-white/30',
                    )}
                  >
                    {phase.name}
                  </span>
                </div>

                {/* Connector line */}
                {index < PHASES.length - 1 && (
                  <div className="flex-1 mx-1 lg:mx-2 relative" style={{ height: '2px', marginBottom: '36px' }}>
                    <div className="absolute inset-0 bg-black/[0.06] dark:bg-white/[0.06] rounded-full" />
                    {(isCompleted || isCurrent) && (
                      <div
                        className={cn(
                          'absolute inset-y-0 left-0 rounded-full w-full',
                          isCompleted
                            ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                            : 'bg-gradient-to-r from-cyan-500/80 to-cyan-500/20',
                        )}
                      />
                    )}
                    {/* Data flow particle */}
                    {isCompleted && (
                      <div className="absolute inset-0 overflow-hidden rounded-full">
                        <div
                          className="absolute w-2 h-full bg-gradient-to-r from-transparent via-white/60 to-transparent rounded-full animate-data-flow"
                          style={{ animationDelay: `${index * 0.4}s` }}
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Recommendations panel — always visible, follows current phase */}
        <div
          key={currentPhase}
          ref={panelRef}
          className="relative mt-5 pt-4 border-t border-black/5 dark:border-white/5 animate-in slide-in-from-top-2 fade-in duration-300"
        >
          <PhasePanel
            phase={currentPhase}
            phaseInfo={PHASES.find(p => p.number === currentPhase)!}
            isCurrent={true}
            isCompleted={false}
            onClose={() => setIsPaused((p) => !p)}
          />
        </div>
      </div>
    </div>
  )
}

// ─── Recommendations Panel (matches incidents page) ─────────────────────────

function PhasePanel({
  phase,
  phaseInfo,
  isCurrent,
  isCompleted,
  onClose,
}: {
  phase: number
  phaseInfo: typeof PHASES[number]
  isCurrent: boolean
  isCompleted: boolean
  onClose: () => void
}) {
  const recs = PHASE_DESCRIPTIONS[phase]

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${phaseInfo.color} flex items-center justify-center text-white text-xs font-bold`}>
            {phase}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              {phaseInfo.name}
              {isCurrent && (
                <span className="text-[10px] font-normal bg-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded-full">
                  Current Phase
                </span>
              )}
              {isCompleted && (
                <span className="text-[10px] font-normal bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full">
                  Completed
                </span>
              )}
            </h3>
            <p className="text-[11px] text-muted-foreground">{recs.subtitle}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronUp className="h-4 w-4" />
        </button>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {recs.steps.map((step, i) => (
          <div
            key={i}
            className="group flex gap-3 p-3 rounded-lg border border-black/5 dark:border-white/5 hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors"
          >
            <div className={`shrink-0 w-6 h-6 rounded-full bg-gradient-to-r ${phaseInfo.color} flex items-center justify-center text-white text-[10px] font-bold mt-0.5 opacity-70 group-hover:opacity-100 transition-opacity`}>
              {i + 1}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-foreground leading-snug">{step.action}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{step.detail}</p>
              {step.d3fend && (
                <span className="inline-flex items-center gap-1 mt-1 text-[9px] text-cyan-400/70 font-mono">
                  <Shield className="h-2.5 w-2.5" />
                  {step.d3fend}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 pt-2 border-t border-black/5 dark:border-white/5 flex items-center gap-4 text-[10px] text-muted-foreground/50">
        <span className="flex items-center gap-1">
          <Shield className="h-3 w-3" /> MITRE D3FEND aligned
        </span>
        <span className="flex items-center gap-1">
          <BookOpen className="h-3 w-3" /> NIST SP 800-61r2
        </span>
      </div>
    </div>
  )
}
