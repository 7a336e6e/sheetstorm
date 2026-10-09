/**
 * Incident detail tab registry (shared module §1 #28, created by W1-TBL).
 *
 * One entry per tab. New tabs add one entry here (hot file: merges are the
 * union of entries); the page renders triggers and panels from this list.
 *
 * - `permission`: needed to see the tab at all (cosmetic; the API enforces).
 * - `keepMounted`: mount on first visit, then keep the panel mounted while
 *   hidden so its list state, scroll and cache subscriptions survive tab
 *   switches. Use `false` for canvases that cannot measure while hidden
 *   (React Flow): they unmount and read cached data when shown again.
 * - URL: `?tab=<id>&row=<uuid>`; `row` is passed to the active tab as
 *   `focusRowId` (deep links from global search). Unknown or forbidden tabs
 *   fall back to `overview`; `TAB_ALIASES` keeps old links working.
 */
import type { ComponentType } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Archive,
  BookOpen,
  Bug,
  CheckSquare,
  ClipboardCheck,
  Fingerprint,
  Globe,
  Key,
  LayoutList,
  MessageSquare,
  Network,
  Server,
  Target,
} from 'lucide-react'
import type { Incident, Versioned } from '@/types'
import type { IncidentTabBaseProps } from '@/components/incidents/table-helpers'
import { HostsTab } from '@/components/incidents/HostsTab'
import { CompromisedAccountsTab } from '@/components/incidents/CompromisedAccountsTab'
import { NetworkIOCsTab } from '@/components/incidents/NetworkIOCsTab'
import { HostBasedIOCsTab } from '@/components/incidents/HostBasedIOCsTab'
import { MalwareToolsTab } from '@/components/incidents/MalwareToolsTab'
import { EvidenceTab } from '@/components/incidents/evidence/EvidenceTab'
import { CaseNotesTab } from '@/components/incidents/CaseNotesTab'
import { TasksTab } from '@/components/incidents/detail/TasksTab'
import { IncidentPlaybookTab } from '@/components/incidents/detail/IncidentPlaybookTab'
import { PostIncidentReviewTab } from '@/components/incidents/detail/PostIncidentReviewTab'
import { EventsPanel, GraphPanel, MitrePanel, OverviewPanel } from './panels'

export interface IncidentTabProps extends IncidentTabBaseProps {
  incident: Incident & Versioned
  /** Switch to another tab, optionally landing on a row there. */
  onNavigate: (tab: string, row?: string | null) => void
  /** The incident itself (header, counts, lead) changed: refetch it. */
  onIncidentChanged: () => void
}

export interface IncidentTabDef {
  id: string
  label: string
  icon: LucideIcon
  permission: string | string[]
  component: ComponentType<IncidentTabProps>
  keepMounted: boolean
}

export const DEFAULT_TAB = 'overview'

export const TAB_REGISTRY: IncidentTabDef[] = [
  { id: 'overview', label: 'Overview', icon: Activity, permission: 'incidents:read', component: OverviewPanel, keepMounted: true },
  { id: 'events', label: 'Events', icon: LayoutList, permission: 'timeline:read', component: EventsPanel, keepMounted: true },
  { id: 'hosts', label: 'Hosts', icon: Server, permission: 'hosts:read', component: HostsTab, keepMounted: true },
  { id: 'tasks', label: 'Tasks', icon: CheckSquare, permission: 'tasks:read', component: TasksTab, keepMounted: true },
  { id: 'playbook', label: 'Playbook', icon: BookOpen, permission: 'incidents:read', component: IncidentPlaybookTab, keepMounted: true },
  { id: 'graph', label: 'Attack Graph', icon: Network, permission: 'attack_graph:read', component: GraphPanel, keepMounted: false },
  { id: 'mitre-matrix', label: 'MITRE Matrix', icon: Target, permission: 'timeline:read', component: MitrePanel, keepMounted: true },
  { id: 'accounts', label: 'Accounts', icon: Key, permission: 'accounts:read', component: CompromisedAccountsTab, keepMounted: true },
  { id: 'network', label: 'Network IOCs', icon: Globe, permission: 'network_iocs:read', component: NetworkIOCsTab, keepMounted: true },
  { id: 'host-iocs', label: 'Host IOCs', icon: Fingerprint, permission: 'host_iocs:read', component: HostBasedIOCsTab, keepMounted: true },
  { id: 'malware', label: 'Malware', icon: Bug, permission: 'malware:read', component: MalwareToolsTab, keepMounted: true },
  { id: 'evidence', label: 'Evidence', icon: Archive, permission: 'artifacts:read', component: EvidenceTab, keepMounted: true },
  { id: 'notes', label: 'Notes', icon: MessageSquare, permission: 'incidents:read', component: CaseNotesTab, keepMounted: true },
  { id: 'review', label: 'Post-Incident Review', icon: ClipboardCheck, permission: 'incidents:read', component: PostIncidentReviewTab, keepMounted: true },
]

/** Old tab ids that still resolve (links, bookmarks, search results). */
export const TAB_ALIASES: Record<string, string> = {
  artifacts: 'evidence',
}

/**
 * The tab to show for a `?tab=` value: aliases are followed; an unknown tab,
 * or one the user may not see, falls back to `overview`.
 */
export function resolveTab(
  param: string | null | undefined,
  canSee: (permission: string | string[]) => boolean,
  registry: IncidentTabDef[] = TAB_REGISTRY
): string {
  const id = param ? TAB_ALIASES[param] ?? param : DEFAULT_TAB
  const def = registry.find((t) => t.id === id)
  return def && canSee(def.permission) ? def.id : DEFAULT_TAB
}
