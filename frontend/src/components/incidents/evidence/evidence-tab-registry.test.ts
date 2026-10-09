import { describe, expect, it } from '@jest/globals'
import { checkPermission } from '@/components/auth/permission-gate'
import { TAB_ALIASES, TAB_REGISTRY, resolveTab } from '@/app/dashboard/incidents/[id]/tabs'
import { EvidenceTab } from './EvidenceTab'
import { ADMIN, READ, RESPONDER } from './test-fixtures'

// System role sets, backend permissions.py: Viewer holds no artifacts:* at all.
const VIEWER = ['incidents:read', 'incidents:read_tlp_white', 'decisions:read']

describe('Evidence entry in TAB_REGISTRY', () => {
  const entry = TAB_REGISTRY.find((t) => t.id === 'evidence')!

  it('replaces the Artifacts tab: same id, new label and component', () => {
    expect(entry).toBeDefined()
    expect(entry.label).toBe('Evidence')
    expect(entry.component).toBe(EvidenceTab)
    expect(entry.permission).toBe('artifacts:read')
    expect(entry.keepMounted).toBe(true)
    expect(TAB_REGISTRY.filter((t) => t.id === 'evidence')).toHaveLength(1)
  })

  it('keeps ?tab=artifacts working', () => {
    expect(TAB_ALIASES.artifacts).toBe('evidence')
  })

  it('is hidden from a Viewer, visible to read-only users, responders and admins', () => {
    const can = (granted: string[]) => (p: string | string[]) => checkPermission(granted, p)
    expect(resolveTab('evidence', can(VIEWER))).toBe('overview')
    expect(resolveTab('artifacts', can(VIEWER))).toBe('overview')
    for (const granted of [READ, RESPONDER, ADMIN]) {
      expect(resolveTab('evidence', can(granted))).toBe('evidence')
      expect(resolveTab('artifacts', can(granted))).toBe('evidence')
    }
  })
})
