import { describe, expect, it } from '@jest/globals'
import { TOURS, tourForPath, visibleSteps } from './tours'

describe('tours', () => {
  it('maps pages to tours', () => {
    expect(tourForPath('/dashboard')?.id).toBe('dashboard')
    expect(tourForPath('/dashboard/incidents')?.id).toBe('incidents')
    expect(tourForPath('/dashboard/incidents/0b2a6a3e-1111-4222-8333-944445555666')?.id).toBe('incident-detail')
    expect(tourForPath('/dashboard/incidents/new')).toBeNull()
    expect(tourForPath('/dashboard/admin/users')?.id).toBe('admin-users')
    expect(tourForPath(null)).toBeNull()
  })

  it('has unique ids that the backend accepts', () => {
    const ids = TOURS.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) expect(id).toMatch(/^[a-z0-9][a-z0-9-]{0,63}$/)
  })

  it('skips steps whose anchor is not on the page', () => {
    document.body.innerHTML = '<div data-tour="search"></div>'
    const tour = tourForPath('/dashboard')!
    const steps = visibleSteps(tour)
    expect(steps.map((s) => s.target ?? 'centred')).toEqual(['centred', 'search'])
  })
})
