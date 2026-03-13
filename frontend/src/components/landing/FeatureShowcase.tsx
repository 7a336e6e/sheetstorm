"use client"

import { useState, useEffect, useCallback, useRef } from 'react'
import { cn } from '@/lib/utils'
import {
  Activity,
  Server,
  CheckSquare,
  Shield,
  User,
  Globe,
  Fingerprint,
  Bug,
  FileText,
  StickyNote,
  BarChart3,
  ChevronRight,
  Star,
  Clock,
  Circle,
  CheckCircle2,
  Crown,
  Eye,
  ArrowUpRight,
  ArrowDownLeft,
  ArrowLeftRight,
  Copy,
  Wrench,
  Monitor,
  Cloud,
  HardDrive,
  Pin,
  FileSearch,
  Lightbulb,
  Calendar,
  Key,
  Link2,
  ShieldCheck,
  Upload,
} from 'lucide-react'

// ─── Types & Data ────────────────────────────────────────────────────────────

interface ShowcaseFeature {
  id: string
  title: string
  description: string
  icon: React.ElementType
  color: string
  hex: string
}

const features: ShowcaseFeature[] = [
  {
    id: 'overview',
    title: 'Overview',
    description: 'Dashboard view with stats, progress tracking, and host containment status.',
    icon: BarChart3,
    color: 'text-blue-400',
    hex: '#60a5fa',
  },
  {
    id: 'events',
    title: 'Events',
    description: 'Chronological timeline with MITRE ATT&CK mapping and D3FEND countermeasures.',
    icon: Activity,
    color: 'text-cyan-400',
    hex: '#22d3ee',
  },
  {
    id: 'hosts',
    title: 'Hosts',
    description: 'Compromised host tracking with containment status and system classification.',
    icon: Server,
    color: 'text-emerald-400',
    hex: '#34d399',
  },
  {
    id: 'tasks',
    title: 'Tasks',
    description: 'Response task management with priority, assignments, and linked entities.',
    icon: CheckSquare,
    color: 'text-violet-400',
    hex: '#a78bfa',
  },
  {
    id: 'accounts',
    title: 'Accounts',
    description: 'Compromised account tracking with credential management and privilege flags.',
    icon: User,
    color: 'text-amber-400',
    hex: '#fbbf24',
  },
  {
    id: 'network',
    title: 'Network IOCs',
    description: 'Network indicators of compromise with direction, protocol, and host correlation.',
    icon: Globe,
    color: 'text-orange-400',
    hex: '#fb923c',
  },
  {
    id: 'hostiocs',
    title: 'Host IOCs',
    description: 'Host-based indicators including registry, services, processes, and persistence.',
    icon: Fingerprint,
    color: 'text-rose-400',
    hex: '#fb7185',
  },
  {
    id: 'malware',
    title: 'Malware',
    description: 'Malware samples and tools with file hashes, threat actors, and classification.',
    icon: Bug,
    color: 'text-red-400',
    hex: '#f87171',
  },
  {
    id: 'artifacts',
    title: 'Artifacts',
    description: 'Evidence storage with hash verification, chain of custody, and cloud integration.',
    icon: FileText,
    color: 'text-teal-400',
    hex: '#2dd4bf',
  },
  {
    id: 'notes',
    title: 'Notes',
    description: 'Case notes with categories, pinning, and collaborative annotations.',
    icon: StickyNote,
    color: 'text-indigo-400',
    hex: '#818cf8',
  },
]

const CYCLE_MS = 5000
const PANEL_HEIGHT = 'h-[420px]'

// ─── Shared mock table primitives ─────────────────────────────────────────

function MockTableHead({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn('h-10 px-4 text-left align-middle font-medium text-muted-foreground text-[10px] uppercase tracking-wider', className)}>
      {children}
    </th>
  )
}

function MockTableCell({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <td className={cn('px-4 py-2.5 align-middle', className)}>
      {children}
    </td>
  )
}

function MockBadge({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium', className)}>
      {children}
    </span>
  )
}

// ─── Overview Panel ──────────────────────────────────────────────────────

function OverviewPanel() {
  const stats = [
    { title: 'Events', value: '23', icon: Activity, desc: '5 key events pinned' },
    { title: 'Hosts', value: '4', icon: Server, desc: '2 contained' },
    { title: 'Network IOCs', value: '12', icon: Globe, desc: '8 malicious' },
    { title: 'Host IOCs', value: '9', icon: Fingerprint, desc: '3 remediated' },
    { title: 'Tasks', value: '8', icon: CheckSquare, desc: '3 completed' },
    { title: 'Accounts', value: '3', icon: User, desc: '1 privileged' },
    { title: 'Malware', value: '3', icon: Bug, desc: '2 families' },
    { title: 'Artifacts', value: '6', icon: FileText, desc: '5 verified' },
  ]

  const containment = [
    { status: 'Active', count: 1, color: 'text-red-400 bg-red-500/10 border-red-500/20' },
    { status: 'Monitoring', count: 1, color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
    { status: 'Isolated', count: 0, color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
    { status: 'Reimaged', count: 1, color: 'text-green-400 bg-green-500/10 border-green-500/20' },
    { status: 'Decommissioned', count: 1, color: 'text-gray-400 bg-gray-500/10 border-gray-500/20' },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-2">
        {stats.map((s) => {
          const Icon = s.icon
          return (
            <div key={s.title} className="px-3 py-2.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-muted-foreground">{s.title}</span>
                <Icon className="h-3.5 w-3.5 text-muted-foreground/60" />
              </div>
              <div className="text-xl font-bold">{s.value}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">{s.desc}</div>
            </div>
          )
        })}
      </div>

      <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-muted-foreground">Task Progress</span>
          <span className="text-xs font-medium">38%</span>
        </div>
        <div className="bg-white/[0.06] rounded-full h-2 mb-2">
          <div className="bg-gradient-to-r from-blue-500 to-cyan-400 h-2 rounded-full" style={{ width: '38%' }} />
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div><span className="text-sm font-semibold">3</span><span className="text-[10px] text-muted-foreground block">Pending</span></div>
          <div><span className="text-sm font-semibold text-blue-400">2</span><span className="text-[10px] text-muted-foreground block">In Progress</span></div>
          <div><span className="text-sm font-semibold text-emerald-400">3</span><span className="text-[10px] text-muted-foreground block">Completed</span></div>
        </div>
      </div>

      <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
        <span className="text-xs font-medium text-muted-foreground block mb-2">Host Containment</span>
        <div className="grid grid-cols-5 gap-2">
          {containment.map((c) => (
            <div key={c.status} className={cn('rounded-lg border px-2 py-2 text-center', c.color)}>
              <div className="text-lg font-bold">{c.count}</div>
              <div className="text-[9px]">{c.status}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Events Panel ────────────────────────────────────────────────────────

function EventsPanel() {
  const events = [
    { time: 'Jan 15, 14:23', host: 'WS-PC042', activity: 'Initial access via spear-phishing attachment', tactic: 'Initial Access', technique: 'T1566.001', isKey: true },
    { time: 'Jan 15, 14:25', host: 'WS-PC042', activity: 'PowerShell execution \u2014 encoded command detected', tactic: 'Execution', technique: 'T1059.001', isKey: true },
    { time: 'Jan 15, 14:28', host: 'DC-01', activity: 'LSASS memory credential dumping observed', tactic: 'Credential Access', technique: 'T1003.001', isKey: true },
    { time: 'Jan 15, 14:31', host: 'DC-01', activity: 'Lateral movement to DC01 via SMB', tactic: 'Lateral Movement', technique: 'T1021.002', isKey: false },
    { time: 'Jan 15, 14:35', host: 'WS-PC042', activity: 'Scheduled task created for persistence', tactic: 'Persistence', technique: 'T1053.005', isKey: false },
    { time: 'Jan 15, 14:42', host: 'SRV-WEB03', activity: 'Web shell deployed to public directory', tactic: 'Persistence', technique: 'T1505.003', isKey: true },
  ]

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-white/[0.06]">
          <tr>
            <MockTableHead className="w-[32px]">{' '}</MockTableHead>
            <MockTableHead className="w-[40px]"><Star className="h-3.5 w-3.5 text-muted-foreground" /></MockTableHead>
            <MockTableHead>Time</MockTableHead>
            <MockTableHead>Host</MockTableHead>
            <MockTableHead>Activity</MockTableHead>
            <MockTableHead>MITRE Tactic / Technique</MockTableHead>
          </tr>
        </thead>
        <tbody>
          {events.map((ev, i) => (
            <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
              <MockTableCell className="w-[32px] px-2">
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </MockTableCell>
              <MockTableCell className="w-[40px]">
                <Star className={cn('h-4 w-4', ev.isKey ? 'text-amber-400 fill-amber-400' : 'text-muted-foreground/30')} />
              </MockTableCell>
              <MockTableCell className="whitespace-nowrap text-xs text-muted-foreground">{ev.time}</MockTableCell>
              <MockTableCell>
                <div className="flex items-center gap-1">
                  <Server className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs">{ev.host}</span>
                </div>
              </MockTableCell>
              <MockTableCell className="max-w-[260px] truncate text-xs">{ev.activity}</MockTableCell>
              <MockTableCell>
                <div className="flex flex-col gap-1 items-start">
                  <MockBadge className="border-white/[0.1] bg-white/[0.04] text-foreground/80">{ev.tactic}</MockBadge>
                  <span className="text-[10px] font-mono text-muted-foreground">{ev.technique}</span>
                </div>
              </MockTableCell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Hosts Panel ─────────────────────────────────────────────────────────

function HostsPanel() {
  const hosts = [
    { hostname: 'WS-PC042', ip: '10.1.5.42', type: 'Workstation', typeIcon: Monitor, os: 'Windows 11', status: 'active', statusColor: 'bg-red-500/20 text-red-400 border-red-400/30', firstSeen: 'Jan 15, 14:23' },
    { hostname: 'DC-01', ip: '10.1.1.10', type: 'Domain Controller', typeIcon: Shield, os: 'Win Server 2022', status: 'monitoring', statusColor: 'bg-amber-500/20 text-amber-400 border-amber-400/30', firstSeen: 'Jan 15, 14:28' },
    { hostname: 'SRV-WEB03', ip: '10.1.3.20', type: 'Web Server', typeIcon: Cloud, os: 'Ubuntu 22.04', status: 'reimaged', statusColor: 'bg-green-500/20 text-green-400 border-green-400/30', firstSeen: 'Jan 15, 14:42' },
    { hostname: 'WS-PC108', ip: '10.1.5.108', type: 'Workstation', typeIcon: Monitor, os: 'Windows 10', status: 'monitoring', statusColor: 'bg-amber-500/20 text-amber-400 border-amber-400/30', firstSeen: 'Jan 15, 15:10' },
    { hostname: 'FS-01', ip: '10.1.2.5', type: 'File Server', typeIcon: HardDrive, os: 'Win Server 2019', status: 'decommissioned', statusColor: 'bg-gray-500/20 text-gray-400 border-gray-400/30', firstSeen: 'Jan 16, 09:15' },
  ]

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-white/[0.06]">
          <tr>
            <MockTableHead>Hostname</MockTableHead>
            <MockTableHead>IP</MockTableHead>
            <MockTableHead>Type</MockTableHead>
            <MockTableHead>OS</MockTableHead>
            <MockTableHead>Containment</MockTableHead>
            <MockTableHead>First Seen</MockTableHead>
          </tr>
        </thead>
        <tbody>
          {hosts.map((h, i) => {
            const TypeIcon = h.typeIcon
            return (
              <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                <MockTableCell className="font-medium text-sm">{h.hostname}</MockTableCell>
                <MockTableCell className="font-mono text-xs text-muted-foreground">{h.ip}</MockTableCell>
                <MockTableCell>
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded bg-white/[0.05]"><TypeIcon className="h-3.5 w-3.5 text-muted-foreground" /></div>
                    <span className="text-xs">{h.type}</span>
                  </div>
                </MockTableCell>
                <MockTableCell className="text-xs text-muted-foreground">{h.os}</MockTableCell>
                <MockTableCell>
                  <MockBadge className={h.statusColor}>{h.status}</MockBadge>
                </MockTableCell>
                <MockTableCell className="text-xs text-muted-foreground">{h.firstSeen}</MockTableCell>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Tasks Panel ─────────────────────────────────────────────────────────

function TasksPanel() {
  const tasks = [
    { title: 'Isolate WS-PC042 from network', desc: 'Disconnect patient zero from corporate LAN immediately', priority: 'critical', prColor: 'border-red-500/20 bg-red-500/10 text-red-400', status: 'completed', assignee: 'Sarah Chen', due: 'Jan 15', linked: [{ type: 'host', label: 'WS-PC042' }] },
    { title: 'Capture forensic image of DC-01', desc: 'Full disk image before any remediation steps', priority: 'high', prColor: 'border-amber-500/20 bg-amber-500/10 text-amber-400', status: 'in_progress', assignee: 'Mike Torres', due: 'Jan 16', linked: [{ type: 'host', label: 'DC-01' }] },
    { title: 'Reset all compromised credentials', desc: 'Force password reset for identified compromised accounts', priority: 'high', prColor: 'border-amber-500/20 bg-amber-500/10 text-amber-400', status: 'pending', assignee: 'Alex Kim', due: 'Jan 16', linked: [{ type: 'account', label: 'svc_backup' }, { type: 'account', label: 'admin_j.smith' }] },
    { title: 'Scan for lateral movement artifacts', desc: 'Check for evidence of SMB/WMI/RDP lateral movement activity', priority: 'medium', prColor: 'border-yellow-500/20 bg-yellow-500/10 text-yellow-400', status: 'pending', assignee: 'Sarah Chen', due: 'Jan 17', linked: [] },
  ]

  const statusInfo: Record<string, { icon: React.ElementType; color: string; label: string }> = {
    pending: { icon: Circle, color: 'text-muted-foreground', label: 'Pending' },
    in_progress: { icon: Clock, color: 'text-blue-400', label: 'In Progress' },
    completed: { icon: CheckCircle2, color: 'text-emerald-400', label: 'Completed' },
  }

  const entityIcons: Record<string, React.ElementType> = {
    host: Server,
    account: Key,
    malware: Bug,
    host_indicator: Fingerprint,
  }

  return (
    <div className="space-y-2.5">
      {tasks.map((task, i) => {
        const st = statusInfo[task.status]
        const StatusIcon = st.icon
        return (
          <div key={i} className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3.5">
            <div className="flex gap-3">
              <div className={cn('mt-0.5', st.color)}>
                <StatusIcon className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h4 className={cn('text-sm font-medium', task.status === 'completed' ? 'line-through text-muted-foreground' : 'text-foreground')}>{task.title}</h4>
                  <MockBadge className={cn('border', task.prColor)}>{task.priority}</MockBadge>
                  <MockBadge className={cn('border-white/[0.1] bg-white/[0.04]', st.color)}>{st.label}</MockBadge>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{task.desc}</p>
                <div className="flex items-center gap-3 mt-2 flex-wrap">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1"><User className="w-3 h-3" /> {task.assignee}</span>
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1"><Calendar className="w-3 h-3" /> {task.due}</span>
                </div>
                {task.linked.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    <Link2 className="w-3 h-3 text-muted-foreground" />
                    {task.linked.map((ent, j) => {
                      const EntIcon = entityIcons[ent.type] || Server
                      return (
                        <span key={j} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                          <EntIcon className="w-3 h-3" />{ent.label}
                        </span>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Compromised Accounts Panel ──────────────────────────────────────────

function AccountsPanel() {
  const accounts = [
    { domain: 'CORP', name: 'admin_j.smith', sid: 'S-1-5-21-...1001', type: 'domain', isPrivileged: true, host: 'DC-01', status: 'active', dateSeen: 'Jan 15, 14:28' },
    { domain: 'CORP', name: 'svc_backup', sid: 'S-1-5-21-...2105', type: 'service', isPrivileged: true, host: 'FS-01', status: 'active', dateSeen: 'Jan 15, 15:01' },
    { domain: '', name: 'Administrator', sid: 'S-1-5-21-...500', type: 'local', isPrivileged: true, host: 'WS-PC042', status: 'reset', dateSeen: 'Jan 15, 14:30' },
    { domain: 'CORP', name: 'j.doe', sid: 'S-1-5-21-...1042', type: 'domain', isPrivileged: false, host: 'WS-PC108', status: 'disabled', dateSeen: 'Jan 15, 15:10' },
  ]

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-white/[0.06]">
          <tr>
            <MockTableHead>Account Name</MockTableHead>
            <MockTableHead>Type</MockTableHead>
            <MockTableHead>Host System</MockTableHead>
            <MockTableHead>Password</MockTableHead>
            <MockTableHead>Date Seen</MockTableHead>
            <MockTableHead>Status</MockTableHead>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a, i) => (
            <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
              <MockTableCell>
                <div className="flex items-center gap-2">
                  <div className={cn('p-1 rounded', a.isPrivileged ? 'bg-red-500/20 text-red-400' : 'bg-white/[0.05] text-muted-foreground')}>
                    {a.isPrivileged ? <Crown className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                  </div>
                  <div>
                    <span className="text-sm font-medium">{a.domain ? `${a.domain}\\${a.name}` : a.name}</span>
                    <span className="block text-[10px] text-muted-foreground font-mono">{a.sid}</span>
                  </div>
                </div>
              </MockTableCell>
              <MockTableCell>
                <MockBadge className="border-white/[0.1] bg-white/[0.04] text-foreground/80">{a.type}</MockBadge>
              </MockTableCell>
              <MockTableCell className="text-xs">{a.host}</MockTableCell>
              <MockTableCell>
                <div className="flex items-center gap-1">
                  <span className="text-xs text-muted-foreground font-mono">{'\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}</span>
                  <Eye className="h-3 w-3 text-muted-foreground/50" />
                </div>
              </MockTableCell>
              <MockTableCell className="text-xs text-muted-foreground">{a.dateSeen}</MockTableCell>
              <MockTableCell>
                <MockBadge className={cn(
                  a.status === 'active' ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                )}>
                  {a.status}
                </MockBadge>
              </MockTableCell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Network IOCs Panel ──────────────────────────────────────────────────

function NetworkIOCsPanel() {
  const indicators = [
    { direction: 'outbound', dirIcon: ArrowUpRight, dirColor: 'text-red-400', value: '185.220.101.34', protocol: 'TCP', port: '443', srcHost: 'WS-PC042', dstHost: 'External', desc: 'C2 beacon traffic to known malicious IP' },
    { direction: 'outbound', dirIcon: ArrowUpRight, dirColor: 'text-red-400', value: 'malware-c2[.]xyz', protocol: 'HTTPS', port: '443', srcHost: 'WS-PC042', dstHost: 'External', desc: 'DNS resolution to C2 domain' },
    { direction: 'lateral', dirIcon: ArrowLeftRight, dirColor: 'text-yellow-400', value: '10.1.1.10', protocol: 'SMB', port: '445', srcHost: 'WS-PC042', dstHost: 'DC-01', desc: 'SMB lateral movement to domain controller' },
    { direction: 'inbound', dirIcon: ArrowDownLeft, dirColor: 'text-orange-400', value: '45.77.65.211', protocol: 'HTTP', port: '80', srcHost: 'External', dstHost: 'SRV-WEB03', desc: 'Web shell callback from attacker IP' },
    { direction: 'lateral', dirIcon: ArrowLeftRight, dirColor: 'text-yellow-400', value: '10.1.2.5', protocol: 'RDP', port: '3389', srcHost: 'DC-01', dstHost: 'FS-01', desc: 'RDP session to file server' },
  ]

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-white/[0.06]">
          <tr>
            <MockTableHead className="w-[40px]">Dir</MockTableHead>
            <MockTableHead>Value (IP/DNS)</MockTableHead>
            <MockTableHead>Protocol/Port</MockTableHead>
            <MockTableHead>Source Host</MockTableHead>
            <MockTableHead>Dest Host</MockTableHead>
            <MockTableHead>Description</MockTableHead>
          </tr>
        </thead>
        <tbody>
          {indicators.map((ioc, i) => {
            const DirIcon = ioc.dirIcon
            return (
              <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                <MockTableCell className="w-[40px]">
                  <div className="p-1 rounded bg-white/[0.05]">
                    <DirIcon className={cn('h-3.5 w-3.5', ioc.dirColor)} />
                  </div>
                </MockTableCell>
                <MockTableCell className="font-mono text-xs">{ioc.value}</MockTableCell>
                <MockTableCell className="text-xs">{ioc.protocol}:{ioc.port}</MockTableCell>
                <MockTableCell className="text-xs">{ioc.srcHost}</MockTableCell>
                <MockTableCell className="text-xs">{ioc.dstHost}</MockTableCell>
                <MockTableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{ioc.desc}</MockTableCell>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Host-Based IOCs Panel ───────────────────────────────────────────────

function HostIOCsPanel() {
  const iocs = [
    { type: 'Registry', typeIcon: Fingerprint, value: 'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\svchost_update', host: 'WS-PC042', status: 'Active', notes: 'Persistence mechanism \u2014 auto-start registry key' },
    { type: 'Process', typeIcon: Activity, value: 'svchost_update.exe (PID 4892)', host: 'WS-PC042', status: 'Remediated', notes: 'Masquerading as legitimate svchost process' },
    { type: 'Service', typeIcon: Server, value: 'WindowsUpdateHelper (display: Windows Update)', host: 'DC-01', status: 'Active', notes: 'Malicious service installed for persistence' },
    { type: 'Scheduled Task', typeIcon: Clock, value: '\\Microsoft\\Windows\\Maintenance\\BackupTask', host: 'WS-PC042', status: 'Remediated', notes: 'Scheduled task runs encoded PowerShell every 30m' },
    { type: 'File', typeIcon: FileText, value: 'C:\\inetpub\\wwwroot\\upload.aspx', host: 'SRV-WEB03', status: 'Remediated', notes: 'Web shell \u2014 ASP.NET file upload capability' },
  ]

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-white/[0.06]">
          <tr>
            <MockTableHead>Type</MockTableHead>
            <MockTableHead>Value</MockTableHead>
            <MockTableHead>Host</MockTableHead>
            <MockTableHead>Status</MockTableHead>
            <MockTableHead>Notes</MockTableHead>
          </tr>
        </thead>
        <tbody>
          {iocs.map((ioc, i) => {
            const TypeIcon = ioc.typeIcon
            return (
              <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                <MockTableCell>
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded bg-white/[0.05]"><TypeIcon className="h-3.5 w-3.5 text-muted-foreground" /></div>
                    <span className="text-xs">{ioc.type}</span>
                  </div>
                </MockTableCell>
                <MockTableCell className="font-mono text-xs max-w-[260px] truncate">{ioc.value}</MockTableCell>
                <MockTableCell className="text-xs">{ioc.host}</MockTableCell>
                <MockTableCell>
                  <MockBadge className={cn(
                    ioc.status === 'Active' ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-green-500/20 text-green-400 border-green-500/30'
                  )}>
                    {ioc.status}
                  </MockBadge>
                </MockTableCell>
                <MockTableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{ioc.notes}</MockTableCell>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Malware Panel ───────────────────────────────────────────────────────

function MalwarePanel() {
  const items = [
    { name: 'svchost_update.exe', path: 'C:\\Windows\\Temp\\', isTool: false, md5: 'a3f2d1c4e7b9', host: 'WS-PC042', size: '284 KB', time: 'Jan 14, 23:45', family: 'BlackCat/ALPHV', actor: 'UNC4466' },
    { name: 'beacon_x64.dll', path: 'C:\\ProgramData\\', isTool: false, md5: 'f9c841e20b73', host: 'DC-01', size: '312 KB', time: 'Jan 15, 02:12', family: 'Cobalt Strike', actor: 'UNC4466' },
    { name: 'mimikatz.exe', path: 'C:\\Users\\admin\\Desktop\\', isTool: true, md5: '84c208a15fd2', host: 'DC-01', size: '1.2 MB', time: 'Jan 15, 14:28', family: 'Mimikatz', actor: '-' },
    { name: 'upload.aspx', path: 'C:\\inetpub\\wwwroot\\', isTool: false, md5: '7e2f9a31b048', host: 'SRV-WEB03', size: '4.7 KB', time: 'Jan 15, 14:42', family: 'Web Shell', actor: 'UNC4466' },
  ]

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-white/[0.06]">
          <tr>
            <MockTableHead>Name / Path</MockTableHead>
            <MockTableHead>Type</MockTableHead>
            <MockTableHead>Hash</MockTableHead>
            <MockTableHead>Host</MockTableHead>
            <MockTableHead>Size / Time</MockTableHead>
            <MockTableHead>Threat Info</MockTableHead>
          </tr>
        </thead>
        <tbody>
          {items.map((m, i) => (
            <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
              <MockTableCell>
                <div className="text-sm font-medium">{m.name}</div>
                <div className="text-[10px] text-muted-foreground truncate max-w-[180px]">{m.path}</div>
              </MockTableCell>
              <MockTableCell>
                <MockBadge className={cn(
                  m.isTool
                    ? 'border-white/[0.1] bg-white/[0.04] text-foreground/80'
                    : 'bg-red-500/10 text-red-400 border-red-500/20'
                )}>
                  {m.isTool ? <><Wrench className="w-3 h-3 mr-1" />Tool</> : <><Bug className="w-3 h-3 mr-1" />Malware</>}
                </MockBadge>
              </MockTableCell>
              <MockTableCell>
                <div className="flex items-center gap-1 text-[10px] font-mono bg-white/[0.04] px-1.5 py-0.5 rounded w-fit">
                  MD5: {m.md5.substring(0, 8)}{'\u2026'}
                  <Copy className="w-3 h-3 text-muted-foreground/50" />
                </div>
              </MockTableCell>
              <MockTableCell className="text-xs">{m.host}</MockTableCell>
              <MockTableCell>
                <div className="text-xs">{m.size}</div>
                <div className="text-[10px] text-muted-foreground">{m.time}</div>
              </MockTableCell>
              <MockTableCell>
                <div className="text-xs">{m.family}</div>
                <div className="text-[10px] text-muted-foreground">{m.actor}</div>
              </MockTableCell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Artifacts Panel ─────────────────────────────────────────────────────

function ArtifactsPanel() {
  const artifacts = [
    { name: 'invoice_q4_2024.docm', desc: 'Phishing attachment \u2014 initial access vector', size: '248 KB', sha256: 'a7f3d2c8e91c4b', storage: 'Google Drive', storageColor: 'border-blue-500/30 text-blue-400', status: 'verified', uploaded: 'Jan 15, 14:45' },
    { name: 'lsass_dump.dmp', desc: 'LSASS memory dump from DC-01', size: '1.2 GB', sha256: 'c4e891f23bf7a2', storage: 'S3', storageColor: 'border-amber-500/30 text-amber-400', status: 'verified', uploaded: 'Jan 15, 15:02' },
    { name: 'upload.aspx', desc: 'Web shell recovered from SRV-WEB03', size: '4.7 KB', sha256: '9d2f1a065ec803', storage: 'Local', storageColor: 'border-white/20 text-muted-foreground', status: 'verified', uploaded: 'Jan 15, 16:30' },
    { name: 'schtask_export.xml', desc: 'Exported malicious scheduled task XML', size: '12 KB', sha256: 'f1b8c3d07a4d09', storage: 'Google Drive', storageColor: 'border-blue-500/30 text-blue-400', status: 'unverified', uploaded: 'Jan 15, 17:15' },
    { name: 'pcap_capture.pcapng', desc: 'Network capture \u2014 C2 communication', size: '847 MB', sha256: 'b2e7f4a19c0d53', storage: 'S3', storageColor: 'border-amber-500/30 text-amber-400', status: 'verified', uploaded: 'Jan 16, 08:30' },
  ]

  return (
    <div className="space-y-3">
      <div className="rounded-xl border-2 border-dashed border-white/[0.08] p-3 flex items-center justify-center gap-2 text-muted-foreground/60">
        <Upload className="h-4 w-4" />
        <span className="text-xs">Drag & drop evidence files or click to upload</span>
      </div>

      <div className="rounded-lg border border-white/[0.06] overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-white/[0.06]">
            <tr>
              <MockTableHead>File</MockTableHead>
              <MockTableHead>Size</MockTableHead>
              <MockTableHead>SHA-256</MockTableHead>
              <MockTableHead>Storage</MockTableHead>
              <MockTableHead>Status</MockTableHead>
              <MockTableHead>Uploaded</MockTableHead>
            </tr>
          </thead>
          <tbody>
            {artifacts.map((a, i) => (
              <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                <MockTableCell>
                  <div className="text-sm font-medium">{a.name}</div>
                  <div className="text-[10px] text-muted-foreground">{a.desc}</div>
                </MockTableCell>
                <MockTableCell className="text-xs text-muted-foreground">{a.size}</MockTableCell>
                <MockTableCell>
                  <code className="text-[10px] font-mono text-muted-foreground bg-white/[0.04] px-1.5 py-0.5 rounded">
                    {a.sha256.substring(0, 16)}{'\u2026'}
                  </code>
                </MockTableCell>
                <MockTableCell>
                  <MockBadge className={a.storageColor}>{a.storage}</MockBadge>
                </MockTableCell>
                <MockTableCell>
                  <div className="flex items-center gap-1">
                    {a.status === 'verified' ? (
                      <ShieldCheck className="h-3.5 w-3.5 text-green-400" />
                    ) : (
                      <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                    <span className={cn('text-[10px]', a.status === 'verified' ? 'text-green-400' : 'text-muted-foreground')}>{a.status}</span>
                  </div>
                </MockTableCell>
                <MockTableCell className="text-xs text-muted-foreground">{a.uploaded}</MockTableCell>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Case Notes Panel ────────────────────────────────────────────────────

function NotesPanel() {
  const notes = [
    { title: 'Initial triage findings', category: 'finding', catColor: 'bg-blue-500/15 text-blue-400 border-blue-500/20', catIcon: FileSearch, content: 'Phishing email delivered via spoofed HR address. Attachment exploited macro to download second-stage payload from malware-c2[.]xyz.', author: 'Sarah Chen', time: '2h ago', isPinned: true },
    { title: 'Password spray hypothesis', category: 'hypothesis', catColor: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20', catIcon: Lightbulb, content: 'The svc_backup account may have been compromised prior to phishing. Checking auth logs for password spray activity from external IPs.', author: 'Mike Torres', time: '1h ago', isPinned: false },
    { title: 'Escalation to legal team', category: 'handoff', catColor: 'bg-orange-500/15 text-orange-400 border-orange-500/20', catIcon: ArrowUpRight, content: 'Notified legal about potential data exfiltration. PII may have been accessed on FS-01. Awaiting guidance on notification requirements.', author: 'Alex Kim', time: '45m ago', isPinned: false },
    { title: 'Check EDR timeline gap', category: 'action_item', catColor: 'bg-green-500/15 text-green-400 border-green-500/20', catIcon: CheckSquare, content: 'EDR agent on WS-PC042 was disabled 14:24\u201314:26. Need to cross-reference with Windows event logs to fill timeline gap.', author: 'Sarah Chen', time: '30m ago', isPinned: true },
  ]

  return (
    <div className="space-y-2.5">
      {notes.map((note, i) => {
        const CatIcon = note.catIcon
        return (
          <div key={i} className={cn(
            'rounded-xl bg-white/[0.03] border p-3.5',
            note.isPinned ? 'border-yellow-500/30 bg-yellow-500/[0.02]' : 'border-white/[0.06]'
          )}>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                {note.isPinned && <Pin className="h-3.5 w-3.5 text-yellow-400 -rotate-45" />}
                <h4 className="text-sm font-medium">{note.title}</h4>
              </div>
              <MockBadge className={cn('border shrink-0', note.catColor)}>
                <CatIcon className="w-3 h-3 mr-1" />{note.category.replace('_', ' ')}
              </MockBadge>
            </div>
            <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">{note.content}</p>
            <div className="flex items-center gap-3 mt-2 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1"><User className="w-3 h-3" /> {note.author}</span>
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {note.time}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Panel registry ──────────────────────────────────────────────────────

const PANELS: Record<string, () => React.ReactNode> = {
  overview: () => <OverviewPanel />,
  events: () => <EventsPanel />,
  hosts: () => <HostsPanel />,
  tasks: () => <TasksPanel />,
  accounts: () => <AccountsPanel />,
  network: () => <NetworkIOCsPanel />,
  hostiocs: () => <HostIOCsPanel />,
  malware: () => <MalwarePanel />,
  artifacts: () => <ArtifactsPanel />,
  notes: () => <NotesPanel />,
}

// ─── Component ───────────────────────────────────────────────────────────

export function FeatureShowcase() {
  const [activeId, setActiveId] = useState(features[0].id)
  const [isPaused, setIsPaused] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const advance = useCallback(() => {
    setActiveId((prev) => {
      const idx = features.findIndex((f) => f.id === prev)
      return features[(idx + 1) % features.length].id
    })
  }, [])

  useEffect(() => {
    if (isPaused) return
    timerRef.current = setInterval(advance, CYCLE_MS)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isPaused, advance, activeId])

  const active = features.find((f) => f.id === activeId)!

  return (
    <div
      className="max-w-6xl mx-auto"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Left: Feature selector tabs */}
        <div className="lg:w-56 shrink-0">
          <nav className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-x-visible pb-2 lg:pb-0">
            {features.map((f) => {
              const isActive = f.id === activeId
              const Icon = f.icon
              return (
                <button
                  key={f.id}
                  onClick={() => setActiveId(f.id)}
                  className={cn(
                    'flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all duration-300 shrink-0',
                    'border',
                    isActive
                      ? 'bg-white/[0.06] border-white/[0.1] shadow-lg'
                      : 'border-transparent hover:bg-white/[0.03] hover:border-white/[0.05]'
                  )}
                >
                  <div
                    className={cn(
                      'p-1.5 rounded-md transition-colors duration-300',
                      isActive ? 'bg-white/[0.08]' : 'bg-transparent'
                    )}
                  >
                    <Icon className={cn('h-4 w-4 transition-colors duration-300', isActive ? f.color : 'text-muted-foreground')} />
                  </div>
                  <span className={cn(
                    'text-sm font-medium transition-colors duration-300 hidden lg:block',
                    isActive ? 'text-foreground' : 'text-muted-foreground'
                  )}>
                    {f.title}
                  </span>
                  {isActive && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground ml-auto hidden lg:block" />}
                </button>
              )
            })}
          </nav>
        </div>

        {/* Right: Mock panel */}
        <div className="flex-1 min-w-0">
          <div className="rounded-xl border border-white/[0.06] bg-card/60 backdrop-blur-sm overflow-hidden">
            {/* Panel header bar */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
              <active.icon className={cn('h-4 w-4', active.color)} />
              <span className="text-sm font-medium">{active.title}</span>
              <span className="text-xs text-muted-foreground hidden sm:block">{active.description}</span>
              {/* Dot timer indicator */}
              <div className="ml-auto flex gap-1 shrink-0">
                {features.map((f) => (
                  <div
                    key={f.id}
                    className={cn(
                      'h-1 rounded-full transition-all duration-300',
                      f.id === activeId ? 'w-4' : 'w-1 bg-white/[0.1]',
                    )}
                    style={f.id === activeId ? { backgroundColor: active.hex } : undefined}
                  />
                ))}
              </div>
            </div>

            {/* Panel content - fixed height to prevent layout shift */}
            <div key={activeId} className={cn('p-4 animate-phase-slide-in overflow-y-auto', PANEL_HEIGHT)}>
              {PANELS[activeId]?.()}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
