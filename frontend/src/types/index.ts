export interface User {
  id: string
  email: string
  name: string
  avatar_url?: string
  roles: string[]
  permissions?: string[]
  organizational_role?: string
  teams?: { id: string; name: string }[]
  organization_id?: string
  auth_provider?: string
  is_active: boolean
  last_login?: string
  created_at: string
}

export interface Team {
  id: string
  name: string
  description?: string
  member_count: number
  members?: TeamMemberEntry[]
  created_at: string
  updated_at?: string
}

export interface TeamMemberEntry {
  id: string
  team_id: string
  user_id: string
  user?: User
  joined_at: string
}

export interface Role {
  id: string
  name: string
  description: string
  permissions: string[]
  is_system: boolean
}

export interface Incident {
  id: string
  incident_number: number
  title: string
  description?: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'contained' | 'eradicated' | 'recovered' | 'closed'
  classification?: string
  phase: number
  phase_name: string
  lead_responder?: User
  creator?: { id: string; name: string }
  teams?: { id: string; name: string | null }[]
  detected_at?: string
  contained_at?: string
  eradicated_at?: string
  recovered_at?: string
  closed_at?: string
  executive_summary?: string
  lessons_learned?: string
  created_at: string
  updated_at?: string
  counts?: {
    timeline_events: number
    compromised_hosts: number
    compromised_accounts: number
    artifacts: number
    tasks: number
  }
}

export interface TimelineEvent {
  id: string
  incident_id: string
  timestamp: string
  host_id?: string
  hostname?: string
  host?: CompromisedHost
  activity: string
  source?: string
  mitre_tactic?: string
  mitre_technique?: string
  kill_chain_phase?: string
  phase?: number
  is_key_event: boolean
  is_ioc: boolean
  metadata?: Record<string, unknown>
  creator?: { id: string; name: string }
  created_at: string
}

export interface CompromisedHost {
  id: string
  incident_id: string
  hostname: string
  ip_address?: string
  mac_address?: string
  system_type?: string
  os_version?: string
  evidence?: string
  first_seen?: string
  last_seen?: string
  containment_status: 'active' | 'isolated' | 'reimaged' | 'decommissioned'
  notes?: string
  metadata?: Record<string, unknown>
  creator?: { id: string; name: string }
  created_at: string
}

export interface CompromisedAccount {
  id: string
  incident_id: string
  host_id?: string
  host?: CompromisedHost
  timeline_event_id?: string
  timeline_event?: { id: string; timestamp: string }
  datetime_seen: string
  account_name: string
  password?: string
  has_password: boolean
  host_system?: string
  sid?: string
  account_type: 'domain' | 'local' | 'ftp' | 'service' | 'application' | 'admin' | 'other'
  domain?: string
  is_privileged: boolean
  status: 'active' | 'disabled' | 'reset' | 'deleted'
  notes?: string
  creator?: { id: string; name: string }
  created_at: string
}

export interface NetworkIndicator {
  id: string
  incident_id: string
  host_id?: string
  host?: CompromisedHost
  timeline_event_id?: string
  timestamp?: string
  protocol?: string
  port?: number
  dns_ip: string
  source_host?: string
  destination_host?: string
  direction?: 'inbound' | 'outbound' | 'lateral'
  description?: string
  is_malicious: boolean
  threat_intel_source?: string
  creator?: { id: string; name: string }
  created_at: string
}

export interface HostBasedIndicator {
  id: string
  incident_id: string
  host_id?: string
  host_ref?: CompromisedHost
  timeline_event_id?: string
  source_event?: TimelineEvent
  artifact_type: 'wmi_event' | 'asep' | 'registry' | 'scheduled_task' | 'service' | 'file' | 'process' | 'other'
  datetime?: string
  artifact_value: string
  host?: string
  notes?: string
  is_malicious: boolean
  remediated: boolean
  creator?: { id: string; name: string }
  created_at: string
}

export interface MalwareTool {
  id: string
  incident_id: string
  host_id?: string
  host_ref?: CompromisedHost
  file_name: string
  file_path?: string
  md5?: string
  sha256?: string
  sha512?: string
  file_size?: number
  creation_time?: string
  modification_time?: string
  host?: string
  description?: string
  malware_family?: string
  threat_actor?: string
  is_tool: boolean
  sandbox_report_url?: string
  creator?: { id: string; name: string }
  created_at: string
}

export interface Artifact {
  id: string
  incident_id: string
  filename: string
  original_filename: string
  storage_type: 'local' | 's3'
  mime_type?: string
  file_size: number
  md5: string
  sha256: string
  sha512: string
  description?: string
  source?: string
  collected_at?: string
  is_verified: boolean
  verification_status: 'verified' | 'mismatch' | 'pending'
  uploader?: { id: string; name: string }
  created_at: string
}

export interface Task {
  id: string
  incident_id: string
  title: string
  description?: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | 'cancelled'
  priority: 'low' | 'medium' | 'high' | 'critical'
  assignee?: User
  due_date?: string
  completed_at?: string
  checklist?: { item: string; completed: boolean }[]
  checklist_progress?: { completed: number; total: number; percentage: number }
  phase?: number
  extra_data?: {
    linked_entities?: { type: string; id: string; label: string }[]
    [key: string]: unknown
  }
  creator?: { id: string; name: string }
  created_at: string
}

export interface AttackGraphNode {
  id: string
  incident_id: string
  node_type: 'workstation' | 'server' | 'domain_controller' | 'attacker' | 'c2_server' | 'cloud_resource' | 'user' | 'service_account' | 'external' | 'unknown' | 'ip_address' | 'malware' | 'host_indicator' | 'database' | 'web_server' | 'file_server'
  label: string
  compromised_host_id?: string
  compromised_account_id?: string
  position_x: number
  position_y: number
  is_initial_access: boolean
  is_objective: boolean
  extra_data?: Record<string, unknown>
  correlation?: {
    accounts: number
    malware: number
    network_iocs: number
    host_iocs: number
    timeline_events: number
  }
  cytoscape?: {
    data: {
      id: string
      label: string
      type: string
      isInitialAccess: boolean
      isObjective: boolean
      containmentStatus?: string
      compromisedHostId?: string
      compromisedAccountId?: string
    }
    position: { x: number; y: number }
  }
  created_at: string
}

export interface AttackGraphEdge {
  id: string
  incident_id: string
  source_node_id: string
  target_node_id: string
  edge_type: 'lateral_movement' | 'credential_theft' | 'data_exfiltration' | 'command_control' | 'initial_access' | 'privilege_escalation' | 'persistence' | 'discovery' | 'execution' | 'defense_evasion' | 'collection' | 'associated_with'
  label?: string
  mitre_tactic?: string
  mitre_technique?: string
  timestamp?: string
  description?: string
  extra_data?: Record<string, unknown>
  cytoscape?: {
    data: {
      id: string
      source: string
      target: string
      label: string
      type: string
    }
  }
  created_at: string
}

export interface Notification {
  id: string
  type: string
  title: string
  message?: string
  is_read: boolean
  action_url?: string
  incident?: { id: string; title: string; incident_number: number }
  created_at: string
}

export interface AuditLog {
  id: string
  event_type: string
  action: string
  resource_type?: string
  resource_id?: string
  user?: { id: string; email: string; name: string }
  user_email?: string
  ip_address?: string
  user_agent?: string
  request_method?: string
  request_path?: string
  status_code?: number
  details?: Record<string, unknown>
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface CaseNote {
  id: string
  incident_id: string
  title: string
  content: string
  category: 'general' | 'finding' | 'question' | 'action_item' | 'handoff' | 'evidence' | 'hypothesis'
  is_pinned: boolean
  author?: { id: string; name: string }
  created_at: string
  updated_at?: string
}

export interface VirusTotalResult {
  found: boolean
  type: string
  value: string
  malicious?: number
  suspicious?: number
  undetected?: number
  harmless?: number
  total_engines?: number
  detection_ratio?: string
  file_name?: string
  file_type?: string
  sha256?: string
  md5?: string
  sha1?: string
  tags?: string[]
  reputation?: number
  message?: string
}

// ---------- Threat Intel Types ----------

export interface CVEResult {
  cve_id: string
  found: boolean
  nvd?: {
    description: string
    published: string
    last_modified: string
    cvss_score: number | null
    cvss_severity: string | null
    cvss_vector: string | null
    cwes: string[]
    references: string[]
  }
  kev?: {
    vendor: string
    product: string
    vulnerability_name: string
    date_added: string
    due_date: string
    short_description: string
    required_action: string
    known_ransomware_use: string
  }
  nvd_error?: string
  kev_error?: string
}

export interface IPReputationResult {
  ip: string
  enriched: boolean
  sources: {
    abuseipdb?: {
      abuse_confidence_score: number
      total_reports: number
      country_code: string
      isp: string
      domain: string
      is_tor: boolean
      is_whitelisted: boolean
      usage_type: string
      last_reported_at: string
    }
    virustotal?: {
      malicious: number
      suspicious: number
      harmless: number
      undetected: number
      reputation: number
      as_owner: string
      country: string
    }
    geo?: {
      country: string
      region: string
      city: string
      isp: string
      org: string
      as: string
    }
  }
}

export interface DomainReputationResult {
  domain: string
  enriched: boolean
  sources: {
    virustotal?: {
      malicious: number
      suspicious: number
      harmless: number
      undetected: number
      reputation: number
      registrar: string
      creation_date: number
      last_analysis_date: number
      categories: Record<string, string>
    }
  }
}

export interface EmailReputationResult {
  email: string
  enriched: boolean
  sources: {
    hibp?: {
      breach_count: number
      breaches: {
        name: string
        domain: string
        breach_date: string
        added_date: string
        pwn_count: number
        data_classes: string[]
        is_verified: boolean
      }[]
    }
  }
}

export interface RansomwareVictimResult {
  query: string
  found: boolean
  items: {
    victim: string
    group: string
    discovered: string
    country: string
    domain: string
    description: string
    activity: string
  }[]
  total: number
}

export interface DefangResult {
  items?: { original: string; defanged: string }[]
  original?: string
  defanged?: string
  total?: number
}

// ---------- Knowledge Base Types ----------

export interface LOLBASEntry {
  name: string
  description: string
  category: string
  mitre_id: string
  path: string
  commands: string[]
  detection: string[]
  os: string
}

export interface WindowsEventID {
  event_id: number
  description: string
  category: string
  provider: string
  severity: 'info' | 'warning' | 'critical'
}

export interface D3FENDTechnique {
  id: string
  name: string
  tactic: string
  description: string
  mitre_attack_mappings: string[]
  examples: string[]
  matched_techniques?: string[]
}

