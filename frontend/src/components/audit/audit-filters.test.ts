/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import { listParams, type ListState } from '@/hooks/use-paginated-query'
import {
  AUDIT_DEFAULTS,
  activityHref,
  auditApiFilters,
  countActiveFilters,
  isLiveView,
  migrateLegacyParams,
  parseAuditUrl,
  parseEventTypes,
  serializeAuditUrl,
  toggleEventType,
} from './audit-filters'

const state = (over: Partial<ListState> = {}): ListState => ({ ...AUDIT_DEFAULTS, ...over, filters: { ...over.filters } })

describe('audit filters ↔ URL', () => {
  it('round-trips every filter, sort, search, page and page size', () => {
    const s = state({
      page: 3,
      perPage: 100,
      sort: 'user_email',
      q: 'role',
      filters: {
        event_type: 'admin_action,security_event',
        action_contains: 'update_',
        user_id: '6f1c1d4e-0000-4000-8000-000000000001',
        user_email: 'Ana@Example.test',
        start_date: '2026-10-01T00:00:00.000Z',
        end_date: '2026-10-08T23:59:59.000Z',
        resource_type: 'role',
        resource_id: '6f1c1d4e-0000-4000-8000-000000000002',
        incident_id: '6f1c1d4e-0000-4000-8000-000000000003',
        status: 'denied',
        ip: '10.0.0.0/8',
        has_changes: 'true',
      },
    })
    const qs = serializeAuditUrl(s)
    expect(qs).toContain('audit.f.event_type=admin_action%2Csecurity_event')
    expect(qs).toContain('audit.f.ip=10.0.0.0%2F8')
    expect(qs).toContain('audit.page=3')
    expect(qs).toContain('audit.sort=user_email')
    expect(parseAuditUrl(new URLSearchParams(qs))).toEqual(s)
  })

  it('omits defaults, so the plain view has a clean URL', () => {
    expect(serializeAuditUrl(state())).toBe('')
    expect(parseAuditUrl(new URLSearchParams(''))).toEqual(AUDIT_DEFAULTS)
  })

  it('keeps unrelated params and survives a cleared default sort', () => {
    const qs = serializeAuditUrl(state({ sort: undefined }), new URLSearchParams('tab=x'))
    const parsed = parseAuditUrl(new URLSearchParams(qs))
    expect(new URLSearchParams(qs).get('tab')).toBe('x')
    expect(parsed.sort).toBeUndefined()
  })

  it('sends the URL filters to the API under the backend param names', () => {
    const parsed = parseAuditUrl(new URLSearchParams('audit.f.action_contains=login&audit.f.has_changes=true&audit.sort=-chain_seq'))
    expect(listParams(parsed)).toEqual({
      action_contains: 'login',
      has_changes: 'true',
      page: 1,
      per_page: 50,
      sort: '-chain_seq',
      q: undefined,
    })
  })

  it('builds export params from known filters only (trimmed) plus q', () => {
    expect(
      auditApiFilters(state({ q: ' x ', filters: { ip: ' 10.0.0.1 ', bogus: 'y', status: '' } }))
    ).toEqual({ ip: '10.0.0.1', q: 'x' })
    expect(countActiveFilters(state({ q: 'x', filters: { ip: '1.1.1.1' } }))).toBe(2)
  })

  it('builds shareable activity links', () => {
    const href = activityHref({ event_type: 'admin_action', has_changes: 'true' })
    expect(href).toBe('/dashboard/activity?audit.f.event_type=admin_action&audit.f.has_changes=true')
    const parsed = parseAuditUrl(new URLSearchParams(href.split('?')[1]))
    expect(parsed.filters).toEqual({ event_type: 'admin_action', has_changes: 'true' })
    expect(activityHref()).toBe('/dashboard/activity')
  })

  it('migrates plain legacy params into the audit.* form', () => {
    const qs = migrateLegacyParams(new URLSearchParams('event_type=admin_action&has_changes=true&q=role&tab=keep'))
    expect(qs).not.toBeNull()
    const params = new URLSearchParams(qs!)
    expect(params.get('tab')).toBe('keep')
    expect(params.get('event_type')).toBeNull()
    expect(parseAuditUrl(params)).toEqual(state({ q: 'role', filters: { event_type: 'admin_action', has_changes: 'true' } }))
    expect(migrateLegacyParams(new URLSearchParams('audit.f.ip=1.2.3.4&event_type=x'))).toBeNull()
    expect(migrateLegacyParams(new URLSearchParams('tab=x'))).toBeNull()
  })

  it('filters by user from the user drawer link (and its legacy plain form)', () => {
    const id = '6f1c1d4e-0000-4000-8000-000000000001'
    const href = activityHref({ user_id: id })
    expect(href).toBe(`/dashboard/activity?audit.f.user_id=${id}`)
    expect(parseAuditUrl(new URLSearchParams(href.split('?')[1])).filters).toEqual({ user_id: id })
    const migrated = migrateLegacyParams(new URLSearchParams(`user_id=${id}`))
    expect(parseAuditUrl(new URLSearchParams(migrated!)).filters).toEqual({ user_id: id })
  })

  it('toggles event types in a stable order', () => {
    let v = toggleEventType(undefined, 'security_event')
    v = toggleEventType(v, 'authentication')
    expect(v).toBe('authentication,security_event')
    expect(parseEventTypes(`${v},bogus`)).toEqual(['authentication', 'security_event'])
    expect(toggleEventType(toggleEventType(v, 'authentication'), 'security_event')).toBeUndefined()
  })

  it('applies live updates only to the unfiltered newest-first first page', () => {
    expect(isLiveView(state())).toBe(true)
    expect(isLiveView(state({ sort: undefined }))).toBe(true)
    expect(isLiveView(state({ page: 2 }))).toBe(false)
    expect(isLiveView(state({ sort: 'created_at' }))).toBe(false)
    expect(isLiveView(state({ filters: { ip: '1.1.1.1' } }))).toBe(false)
  })
})
