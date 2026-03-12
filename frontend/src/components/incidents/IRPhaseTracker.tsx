"use client"

import { useState, useRef, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import {
  CheckCircle2,
  ChevronUp,
  Shield,
  BookOpen,
} from 'lucide-react'

// --- Phase definitions ---

const PHASE_INFO = [
  { number: 1, name: 'Preparation', color: 'from-blue-500 to-cyan-500', accent: 'blue' },
  { number: 2, name: 'Identification', color: 'from-cyan-500 to-teal-500', accent: 'cyan' },
  { number: 3, name: 'Containment', color: 'from-teal-500 to-green-500', accent: 'teal' },
  { number: 4, name: 'Eradication', color: 'from-green-500 to-yellow-500', accent: 'green' },
  { number: 5, name: 'Recovery', color: 'from-yellow-500 to-orange-500', accent: 'yellow' },
  { number: 6, name: 'Lessons Learned', color: 'from-orange-500 to-red-500', accent: 'orange' },
] as const

// --- Generic IR recommendations per phase ---

const PHASE_RECOMMENDATIONS: Record<number, { title: string; subtitle: string; steps: { action: string; detail: string; d3fend?: string }[] }> = {
  1: {
    title: 'Preparation',
    subtitle: 'Establish readiness before incidents occur',
    steps: [
      { action: 'Verify IR team roster and communication channels', detail: 'Ensure all responders have current contact info and access to secure comms (war room, encrypted chat).', d3fend: 'D3-OAM · Operational Activity Mapping' },
      { action: 'Validate detection and logging infrastructure', detail: 'Confirm SIEM, EDR, network monitoring, and centralized logging are operational and ingesting data.', d3fend: 'D3-NTA · Network Traffic Analysis' },
      { action: 'Review and update response playbooks', detail: 'Ensure runbooks are current for common incident types (ransomware, phishing, insider threat, supply chain).', d3fend: 'D3-PM · Platform Monitoring' },
      { action: 'Test backup integrity and restoration', detail: 'Verify backups are complete, accessible, and can be restored within target RTO/RPO windows.', d3fend: 'D3-BA · Backup' },
      { action: 'Prepare forensic toolkit and jump kits', detail: 'Stage disk imaging tools, memory capture utilities, chain-of-custody forms, and clean media.' },
      { action: 'Conduct tabletop exercises', detail: 'Simulate attack scenarios with the IR team to identify procedural gaps before real incidents occur.' },
    ],
  },
  2: {
    title: 'Identification',
    subtitle: 'Detect, validate, and scope the incident',
    steps: [
      { action: 'Triage alerts — confirm true positive', detail: 'Correlate alerts across data sources. Eliminate false positives before escalating.', d3fend: 'D3-DA · Dynamic Analysis' },
      { action: 'Determine scope of compromise', detail: 'Identify affected systems, users, data, and network segments. Map the blast radius.', d3fend: 'D3-AM · Asset Inventory' },
      { action: 'Collect and preserve IOCs', detail: 'Gather file hashes, IPs, domains, registry keys, and suspicious process names. Log everything.', d3fend: 'D3-FAPA · File Analysis' },
      { action: 'Establish an event timeline', detail: 'Chronologically order all evidence from earliest known attacker activity to present.', d3fend: 'D3-OAM · Operational Activity Mapping' },
      { action: 'Classify incident type and severity', detail: 'Determine if this is malware, phishing, lateral movement, data exfiltration, etc. Assign TLP and severity.' },
      { action: 'Notify stakeholders and begin documentation', detail: 'Open formal incident ticket, notify management chain, and begin the incident log.' },
    ],
  },
  3: {
    title: 'Containment',
    subtitle: 'Limit damage and prevent lateral spread',
    steps: [
      { action: 'Isolate compromised hosts', detail: 'Network-isolate affected endpoints via EDR or firewall rules. Do not power off — preserve volatile data.', d3fend: 'D3-NI · Network Isolation' },
      { action: 'Block attacker infrastructure at perimeter', detail: 'Add C2 IPs, domains, and malware hashes to blocklists across firewalls, proxies, and DNS sinkhole.', d3fend: 'D3-ITF · Inbound Traffic Filtering' },
      { action: 'Disable compromised accounts', detail: 'Lock or disable breached user/service accounts. Force password resets for potentially exposed credentials.', d3fend: 'D3-AL · Account Locking' },
      { action: 'Preserve forensic evidence', detail: 'Capture full disk images, memory dumps, and network PCAPs before any remediation changes.' },
      { action: 'Segment the network', detail: 'Apply micro-segmentation or VLAN changes to prevent attacker pivot to unaffected zones.', d3fend: 'D3-NI · Network Isolation' },
      { action: 'Deploy enhanced monitoring on adjacent systems', detail: 'Increase logging verbosity and deploy canary tokens on systems adjacent to compromised assets.', d3fend: 'D3-HD · Decoy Environment' },
    ],
  },
  4: {
    title: 'Eradication',
    subtitle: 'Remove the attacker and all persistence',
    steps: [
      { action: 'Remove malware and backdoors', detail: 'Delete malicious binaries, scripts, scheduled tasks, and registry persistence. Verify complete removal.', d3fend: 'D3-FE · File Eviction' },
      { action: 'Patch exploited vulnerabilities', detail: 'Apply security updates for the specific CVEs the attacker used for initial access and privilege escalation.', d3fend: 'D3-SU · Software Update' },
      { action: 'Rotate all compromised credentials', detail: 'Reset passwords, revoke tokens/API keys, and rotate certificates for all compromised identities.', d3fend: 'D3-CRO · Credential Rotation' },
      { action: 'Sever all C2 channels', detail: 'Confirm no remaining network connections to attacker infrastructure. Check for DNS tunneling or covert channels.', d3fend: 'D3-OTF · Outbound Traffic Filtering' },
      { action: 'Scan for residual IOCs', detail: 'Run full-environment sweeps with updated signatures/YARA rules to find any remaining artifacts.', d3fend: 'D3-FAPA · File Analysis' },
      { action: 'Verify clean state', detail: 'Perform integrity checks on critical system files, configurations, and startup items. Confirm no lingering access.' },
    ],
  },
  5: {
    title: 'Recovery',
    subtitle: 'Restore operations with confidence',
    steps: [
      { action: 'Restore from clean backups', detail: 'Rebuild affected systems from verified clean backups. Restore data in priority order (business-critical first).', d3fend: 'D3-RFS · Restore from Backup' },
      { action: 'Reconnect systems incrementally', detail: 'Bring systems back online one at a time with enhanced monitoring before proceeding to the next.', d3fend: 'D3-NI · Network Isolation' },
      { action: 'Verify data integrity', detail: 'Validate restored data against checksums. Ensure no tampered or encrypted files persist from the attack.', d3fend: 'D3-FV · File Verification' },
      { action: 'Monitor for re-compromise', detail: 'Deploy targeted detection rules for the same TTPs/IOCs. Watch for the attacker attempting to regain access.', d3fend: 'D3-NTA · Network Traffic Analysis' },
      { action: 'Return to normal operations', detail: 'Gradually lower heightened alerting thresholds once monitoring confirms no suspicious activity.' },
      { action: 'Confirm business services operational', detail: 'Validate all user-facing services, integrations, and workflows are functioning normally.' },
    ],
  },
  6: {
    title: 'Lessons Learned',
    subtitle: 'Improve defenses based on what happened',
    steps: [
      { action: 'Conduct post-incident review', detail: 'Hold a blameless retrospective within 1-2 weeks. Include all responders and key stakeholders.' },
      { action: 'Document full incident timeline', detail: 'Produce a comprehensive timeline from initial compromise through recovery, including decisions and outcomes.' },
      { action: 'Identify detection gaps', detail: 'Analyze what TTPs were not detected, which alerts were missed, and where visibility was insufficient.', d3fend: 'D3-DE · Detection' },
      { action: 'Update detection rules and playbooks', detail: 'Create new SIEM rules, YARA signatures, and update response procedures based on findings.' },
      { action: 'Assess training and tooling needs', detail: 'Determine if additional training, tools, or staffing is needed to prevent similar incidents.' },
      { action: 'Produce executive summary', detail: 'Create a concise report for leadership covering impact, root cause, response effectiveness, and recommended investments.' },
    ],
  },
}

// --- Component ---

interface IRPhaseTrackerProps {
  currentPhase: number
  context?: 'incident' | 'dashboard'
  incidents?: unknown[]
}

export function IRPhaseTracker({ currentPhase }: IRPhaseTrackerProps) {
  const [selectedPhase, setSelectedPhase] = useState<number | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const handlePhaseClick = (phaseNum: number) => {
    setSelectedPhase(selectedPhase === phaseNum ? null : phaseNum)
  }

  useEffect(() => {
    if (selectedPhase !== null && panelRef.current) {
      panelRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [selectedPhase])

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 lg:p-6 relative">
        {/* Background grid */}
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
          {PHASE_INFO.map((phase, index) => {
            const isCompleted = phase.number < currentPhase
            const isCurrent = phase.number === currentPhase
            const isSelected = selectedPhase === phase.number

            return (
              <div key={phase.number} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center z-10 relative">
                  <button
                    onClick={() => handlePhaseClick(phase.number)}
                    className={`relative w-10 h-10 lg:w-12 lg:h-12 rounded-full flex items-center justify-center font-semibold text-sm transition-all duration-300 cursor-pointer group
                      ${isCompleted
                        ? `bg-gradient-to-r ${phase.color} text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/40 hover:scale-110`
                        : isCurrent
                          ? `bg-gradient-to-r ${phase.color} text-white animate-phase-pulse hover:scale-110`
                          : 'bg-black/[0.06] dark:bg-white/[0.06] text-black/30 dark:text-white/30 border border-white/[0.08] hover:bg-black/[0.1] dark:hover:bg-white/[0.1] hover:scale-105'
                      }
                      ${isSelected ? 'ring-2 ring-cyan-400/50 ring-offset-2 ring-offset-transparent' : ''}
                    `}
                    title={`Phase ${phase.number}: ${phase.name} — Click for recommendations`}
                  >

                    {isCompleted ? (
                      <CheckCircle2 className="h-5 w-5" />
                    ) : (
                      <span className={isCurrent ? 'drop-shadow-[0_0_6px_rgba(255,255,255,0.5)]' : ''}>
                        {phase.number}
                      </span>
                    )}
                  </button>

                  <span
                    className={`text-[10px] lg:text-xs mt-2 text-center font-medium transition-colors duration-300 max-w-[80px] lg:max-w-[100px] leading-tight ${
                      isCompleted ? 'text-cyan-400' : isCurrent ? 'text-cyan-300' : 'text-black/30 dark:text-white/30'
                    }`}
                  >
                    {phase.name}
                  </span>
                </div>

                {/* Connector line */}
                {index < PHASE_INFO.length - 1 && (
                  <div className="flex-1 mx-1 lg:mx-2 relative" style={{ height: '2px', marginBottom: '36px' }}>
                    <div className="absolute inset-0 bg-black/[0.06] dark:bg-white/[0.06] rounded-full" />
                    {(isCompleted || isCurrent) && (
                      <div
                        className={`absolute inset-y-0 left-0 rounded-full animate-line-fill ${
                          isCompleted
                            ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 w-full shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                            : 'bg-gradient-to-r from-cyan-500/80 to-cyan-500/20 w-full'
                        }`}
                      />
                    )}
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

        {/* Recommendations panel — below bubbles when a phase is clicked */}
        {selectedPhase !== null && (
          <div ref={panelRef} className="relative mt-5 pt-4 border-t border-black/5 dark:border-white/5 animate-in slide-in-from-top-2 fade-in duration-300">
            <RecommendationsPanel
              phase={selectedPhase}
              phaseInfo={PHASE_INFO.find(p => p.number === selectedPhase)!}
              isCurrent={selectedPhase === currentPhase}
              isCompleted={selectedPhase < currentPhase}
              onClose={() => setSelectedPhase(null)}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// --- Recommendations Panel ---

function RecommendationsPanel({
  phase,
  phaseInfo,
  isCurrent,
  isCompleted,
  onClose,
}: {
  phase: number
  phaseInfo: typeof PHASE_INFO[number]
  isCurrent: boolean
  isCompleted: boolean
  onClose: () => void
}) {
  const recs = PHASE_RECOMMENDATIONS[phase]

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${phaseInfo.color} flex items-center justify-center text-white text-xs font-bold`}>
            {phase}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              {recs.title}
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
