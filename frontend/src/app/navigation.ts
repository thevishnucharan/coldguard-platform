import {
  Activity, BarChart3, Boxes, Building2, CalendarCheck, ClipboardCheck, ClipboardList, Cpu, FileText, FlaskConical,
  Gauge, LayoutDashboard, Map, ScrollText, Settings2, ShieldAlert, ShieldCheck, Thermometer, Users, Wrench,
} from 'lucide-react'
import type { Role } from '../types'

export interface NavItem { label: string; to: string; icon: React.ComponentType<{ size?: number; className?: string }>; perm?: string[]; badge?: 'incidents' | 'approvals' | 'workorders' }
export interface NavSection { title: string; items: NavItem[] }

/** Each role gets its own information architecture — not one menu with items hidden. */
export const NAV: Record<Role, NavSection[]> = {
  ADMIN: [
    { title: 'Platform', items: [
      { label: 'Global overview', to: '/admin', icon: LayoutDashboard },
      { label: 'Facilities', to: '/admin/facilities', icon: Building2, perm: ['facilities.view'] },
      { label: 'Users & access', to: '/admin/users', icon: Users, perm: ['users.view'] },
      { label: 'Device registry', to: '/admin/devices', icon: Cpu, perm: ['devices.view'] },
    ] },
    { title: 'Oversight', items: [
      { label: 'Live monitoring', to: '/monitoring', icon: Thermometer, perm: ['monitoring.view'] },
      { label: 'Incidents', to: '/incidents', icon: ShieldAlert, perm: ['incidents.view'], badge: 'incidents' },
      { label: 'Reports', to: '/reports', icon: FileText, perm: ['reports.view'] },
      { label: 'Audit logs', to: '/audit', icon: ScrollText, perm: ['audit.view'] },
    ] },
    { title: 'Configuration', items: [
      { label: 'System configuration', to: '/admin/config', icon: Settings2, perm: ['platform.configure'] },
      { label: 'Demo simulation', to: '/admin/simulation', icon: FlaskConical, perm: ['simulation.control'] },
    ] },
  ],
  OPERATOR: [
    { title: 'My facility', items: [
      { label: 'Facility dashboard', to: '/operator', icon: LayoutDashboard },
      { label: 'Live monitoring', to: '/monitoring', icon: Thermometer, perm: ['monitoring.view'] },
      { label: 'Incidents', to: '/incidents', icon: ShieldAlert, perm: ['incidents.view'], badge: 'incidents' },
    ] },
    { title: 'Operations', items: [
      { label: 'Vaccine inventory', to: '/inventory', icon: Boxes, perm: ['inventory.view'] },
      { label: 'Maintenance requests', to: '/maintenance', icon: Wrench, perm: ['maintenance.view'] },
      { label: 'Facility reports', to: '/reports', icon: FileText, perm: ['reports.view'] },
    ] },
  ],
  SUPERVISOR: [
    { title: 'Region', items: [
      { label: 'Regional overview', to: '/supervisor', icon: Map },
      { label: 'Approval queue', to: '/supervisor/approvals', icon: ClipboardCheck, badge: 'approvals' },
      { label: 'Incident review', to: '/incidents', icon: ShieldAlert, perm: ['incidents.view'], badge: 'incidents' },
      { label: 'Compliance analytics', to: '/supervisor/compliance', icon: BarChart3 },
    ] },
    { title: 'Monitoring', items: [
      { label: 'Live monitoring', to: '/monitoring', icon: Thermometer },
      { label: 'Stock & quarantine', to: '/inventory', icon: Boxes, perm: ['inventory.view'] },
      { label: 'Maintenance', to: '/maintenance', icon: Wrench, perm: ['maintenance.view'] },
    ] },
    { title: 'Records', items: [
      { label: 'Reports', to: '/reports', icon: FileText },
      { label: 'Audit trail', to: '/audit', icon: ScrollText, perm: ['audit.view'] },
    ] },
  ],
  TECHNICIAN: [
    { title: 'Work', items: [
      { label: 'My work orders', to: '/technician', icon: LayoutDashboard },
      { label: 'All work orders', to: '/maintenance', icon: ClipboardList, badge: 'workorders' },
      { label: 'Preventive schedule', to: '/technician/schedule', icon: CalendarCheck },
    ] },
    { title: 'Equipment', items: [
      { label: 'Equipment health', to: '/technician/equipment', icon: Activity },
      { label: 'Sensor calibration', to: '/calibration', icon: Gauge },
      { label: 'Live monitoring', to: '/monitoring', icon: Thermometer },
      { label: 'Reports', to: '/reports', icon: FileText },
    ] },
  ],
  AUDITOR: [
    { title: 'Compliance', items: [
      { label: 'Compliance overview', to: '/auditor', icon: ShieldCheck },
      { label: 'Audit trail', to: '/audit', icon: ScrollText },
      { label: 'Incident history', to: '/incidents', icon: ShieldAlert },
    ] },
    { title: 'Records', items: [
      { label: 'Temperature records', to: '/monitoring', icon: Thermometer },
      { label: 'Batch traceability', to: '/inventory', icon: Boxes },
      { label: 'Calibration records', to: '/calibration', icon: Gauge },
      { label: 'Exports', to: '/reports', icon: FileText },
    ] },
  ],
}

export const HOME: Record<Role, string> = {
  ADMIN: '/admin', OPERATOR: '/operator', SUPERVISOR: '/supervisor', TECHNICIAN: '/technician', AUDITOR: '/auditor',
}

export function navFor(role: Role, perms: string[]): NavSection[] {
  return NAV[role]
    .map((s) => ({ ...s, items: s.items.filter((i) => !i.perm || i.perm.every((p) => perms.includes(p))) }))
    .filter((s) => s.items.length)
}
