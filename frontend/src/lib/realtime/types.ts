/**
 * Realtime wire types (backend contract: assets/docs/websocket-events.md).
 *
 * Every incident-entity change arrives as one `entity:changed` envelope in a
 * per-(incident, scope) room; bulk changes arrive as `incident:resync`. User
 * room events (`session:revoked`, `incident:access_revoked`, …) go to
 * `user_<id>`.
 */

export const REALTIME_EVENTS = {
  join: 'incident:join',
  leave: 'incident:leave',
  joined: 'incident:joined',
  changed: 'entity:changed',
  resync: 'incident:resync',
  accessRevoked: 'incident:access_revoked',
  presenceUpdate: 'presence:update',
  presenceState: 'presence:state',
  nodeDrag: 'graph:node_drag',
  error: 'rt:error',
  sessionRevoked: 'session:revoked',
  permissionsChanged: 'permissions_changed',
  notification: 'notification',
} as const

export type RealtimeScope =
  | 'incident'
  | 'timeline'
  | 'hosts'
  | 'accounts'
  | 'network_iocs'
  | 'host_iocs'
  | 'malware'
  | 'artifacts'
  | 'tasks'
  | 'attack_graph'
  | 'notes'
  | 'playbook'
  | 'questions'
  | 'decisions'
  | 'decisions_privileged'
  | 'response_actions'
  | 'review'
  | 'improvements'

/** entity → scope room, as registered server-side (`realtime.register_entity`). */
export const ENTITY_SCOPES: Record<string, RealtimeScope> = {
  incident: 'incident',
  assignment: 'incident',
  timeline_event: 'timeline',
  host: 'hosts',
  account: 'accounts',
  network_ioc: 'network_iocs',
  host_ioc: 'host_iocs',
  malware: 'malware',
  artifact: 'artifacts',
  evidence_item: 'artifacts',
  custody_entry: 'artifacts',
  task: 'tasks',
  task_comment: 'tasks',
  graph_node: 'attack_graph',
  graph_edge: 'attack_graph',
  case_note: 'notes',
  playbook: 'playbook',
  question: 'questions',
  decision: 'decisions',
  decision_privileged: 'decisions_privileged',
  response_action: 'response_actions',
  review: 'review',
  improvement_action: 'improvements',
}

export type RealtimeEntity = keyof typeof ENTITY_SCOPES | string

export function scopeForEntity(entity: string): RealtimeScope | undefined {
  return ENTITY_SCOPES[entity]
}

export function entitiesForScope(scope: string): string[] {
  return Object.keys(ENTITY_SCOPES).filter((e) => ENTITY_SCOPES[e] === scope)
}

export type EntityOp = 'created' | 'updated' | 'deleted'

/** `entity:changed` envelope. `data` is omitted for `deleted`. */
export interface EntityChange<T = Record<string, unknown>> {
  incident_id: string
  entity: string
  op: EntityOp
  id: string
  version?: number | null
  scope?: string
  /** Per-(incident, scope) counter; null when the server has no Redis. */
  seq?: number | null
  actor?: { id: string; name?: string } | null
  at?: string
  data?: T
}

export interface ResyncEvent {
  incident_id: string
  scopes: string[]
  reason?: string
}

export interface AccessRevokedEvent {
  incident_id: string
  reason?: string
}

export type PresenceMode = 'viewing' | 'editing'

export interface PresenceFocus {
  entity: string
  id: string
}

/** One socket's presence in an incident. `pid` is opaque (never a socket id). */
export interface PresenceUser {
  pid: string
  user_id: string
  name: string
  focus: PresenceFocus | null
  mode: PresenceMode
  since?: string
}

export interface PresenceState {
  incident_id: string
  users: PresenceUser[]
}

export interface JoinAck {
  incident_id: string
  scopes: string[]
  seq?: Record<string, number | null> | null
  presence?: PresenceUser[]
}

export interface NodeDragEvent {
  incident_id: string
  node_id: string
  x: number
  y: number
  user_id?: string
}

export interface SessionRevokedEvent {
  reason?: 'disabled' | 'deleted' | 'force_logout' | 'password_reset' | 'mfa_reset' | string
}

/** Live connection state shown by `LiveStatusDot`. */
export type LiveStatus = 'live' | 'connecting' | 'offline'

/** Runtime check for an `entity:changed` payload (socket data is untrusted input). */
export function isEntityChange(v: unknown): v is EntityChange {
  if (!v || typeof v !== 'object') return false
  const c = v as Record<string, unknown>
  return (
    typeof c.incident_id === 'string' &&
    typeof c.entity === 'string' &&
    typeof c.id === 'string' &&
    (c.op === 'created' || c.op === 'updated' || c.op === 'deleted') &&
    (c.data === undefined || c.data === null || (typeof c.data === 'object' && !Array.isArray(c.data)))
  )
}
