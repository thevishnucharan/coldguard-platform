import { describe, expect, it } from 'vitest'
import { HOME, NAV, navFor } from '../app/navigation'

const flat = (role: keyof typeof NAV, perms: string[]) => navFor(role, perms).flatMap((s) => s.items.map((i) => i.to))

describe('role-based navigation', () => {
  it('gives every role its own home and structure', () => {
    expect(new Set(Object.values(HOME)).size).toBe(5)
    const titles = (r: keyof typeof NAV) => NAV[r].map((s) => s.title).join('|')
    expect(new Set((Object.keys(NAV) as (keyof typeof NAV)[]).map(titles)).size).toBe(5)
  })

  it('operator menu has no platform administration entries', () => {
    const items = flat('OPERATOR', ['facilities.view', 'monitoring.view', 'incidents.view', 'inventory.view', 'maintenance.view', 'reports.view'])
    expect(items).toContain('/inventory')
    expect(items.some((p) => p.startsWith('/admin'))).toBe(false)
    expect(items).not.toContain('/audit')
  })

  it('filters entries the user lacks permission for', () => {
    const items = flat('ADMIN', ['platform.view', 'users.view'])
    expect(items).toContain('/admin')
    expect(items).not.toContain('/admin/config')
    expect(items).not.toContain('/admin/devices')
  })

  it('auditor navigation is records-oriented', () => {
    const items = flat('AUDITOR', [])
    expect(items).toEqual(expect.arrayContaining(['/auditor', '/audit', '/incidents', '/inventory', '/calibration', '/reports']))
    expect(items.some((p) => p.startsWith('/admin'))).toBe(false)
  })
})
