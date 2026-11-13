import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { navFor, ROLE_META } from '../app/navigation'
import { useAuthStore } from '../store/authStore'
import type { Me, Role } from '../types'

const shipment = {
  id: 's1', shipment_number: 'SH-20261113-ABC123-1', plan_number: 'RP-20261113-ABC123', trip_no: 1, status: 'IN_TRANSIT',
  vehicle_code: 'KA01CC1001', sensor_code: 'VDL-KA01CC1001', sensor_state: 'FAULT', facility_name: 'PHC Jayanagar',
  total_doses: 1200, load_litres: 4.2, temperature_range: [2, 8], hold_minutes: 240, minutes_in_transit: 180,
  last_lat: 12.95, last_lon: 77.59, last_temperature: 5.1, last_reading_at: new Date().toISOString(), is_simulated: true,
  stops: [{ facility_code: 'BLR-HEB', facility_name: 'PHC Hebbal', lat: 13.03, lon: 77.59, doses: 1200 }], open_alerts: 1,
  alerts: [{
    id: 'a1', alert_type: 'SENSOR_FAULT', status: 'OPEN', severity: 'HIGH', incident_number: 'INC-2026-0042', notified_users: 4,
    message: 'Data logger reported FAULT. Nearest compatible store: CHC Anekal.', created_at: new Date().toISOString(),
    nearby: [
      { facility_id: 'f-ank', facility_code: 'BLR-ANK', facility_name: 'CHC Anekal', distance_km: 6.2, eta_minutes: 14, eta_p90_minutes: 19,
        reachable_within_hold: true, units: [{ unit_code: 'BLR-ANK-ILR-1', free_litres: 40 }] },
      { facility_id: 'f-mys', facility_code: 'MYS-DVS', facility_name: 'DVS Mysuru', distance_km: 128, eta_minutes: 170, eta_p90_minutes: 215,
        reachable_within_hold: false, units: [{ unit_code: 'MYS-DVS-WIC-1', free_litres: 300 }] },
    ],
  }],
}

vi.mock('../services/api/endpoints', () => ({
  Logistics: {
    shipments: vi.fn(), divert: vi.fn(), deliver: vi.fn(), acknowledgeAlert: vi.fn(), telemetry: vi.fn(),
    transitAlerts: vi.fn().mockResolvedValue([{ id: 'a1' }]),
  },
  Auth: { login: vi.fn(), me: vi.fn(), logout: vi.fn() },
  Incidents: { list: vi.fn().mockResolvedValue({ items: [], total: 3 }) },
  Maintenance: { list: vi.fn().mockResolvedValue({ items: [], total: 0 }) },
  Notifications: { list: vi.fn().mockResolvedValue({ items: [], unread: 0 }), read: vi.fn(), readAll: vi.fn() },
}))

import { Auth, Logistics } from '../services/api/endpoints'
import { TransitMonitor } from '../features/logistics/TransitMonitor'
import { AppShell } from '../app/AppShell'
import LoginPage from '../features/authentication/LoginPage'

const me = (role: Role, perms: string[]): Me => ({ id: 'u', name: 'Ravi Kumar', email: 'r@x.io', role, role_label: `${role} label`,
  permissions: perms, global_scope: false, facility_ids: ['f1', 'f2'], region_ids: [] })

beforeEach(() => {
  vi.mocked(Logistics.shipments).mockReset().mockResolvedValue([shipment])
  vi.mocked(Logistics.divert).mockReset().mockResolvedValue({ ...shipment, status: 'DIVERTED' })
  vi.mocked(Logistics.acknowledgeAlert).mockReset().mockResolvedValue({})
  vi.mocked(Logistics.telemetry).mockReset().mockResolvedValue({})
})

describe('TransitMonitor (in-transit sensor failure)', () => {
  it('shows the failed logger, the hold-time budget and ranked nearby stores', async () => {
    useAuthStore.setState({ me: me('OPERATOR', ['logistics.view', 'logistics.operate']) })
    render(<MemoryRouter><TransitMonitor /></MemoryRouter>)
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Data logger fault')).toBeInTheDocument()
    expect(within(alert).getByText(/INC-2026-0042 · 4 people alerted/)).toBeInTheDocument()
    expect(screen.getByText('Logger fault')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Cold-box hold time used' })).toHaveAttribute('aria-valuenow', '75')
    const stores = within(screen.getByRole('list', { name: 'Nearest compatible cold-chain stores' })).getAllByRole('listitem')
    expect(stores[0]).toHaveTextContent('CHC Anekal')
    expect(stores[0]).toHaveTextContent('Recommended')
    expect(stores[1]).toHaveTextContent('Beyond hold time')
  })

  it('lets the operator divert to the recommended store and acknowledge', async () => {
    useAuthStore.setState({ me: me('OPERATOR', ['logistics.view', 'logistics.operate']) })
    render(<MemoryRouter><TransitMonitor /></MemoryRouter>)
    await screen.findByRole('alert')
    fireEvent.click(screen.getAllByRole('button', { name: /Divert here/ })[0])
    await waitFor(() => expect(Logistics.divert).toHaveBeenCalledWith('s1', 'f-ank', 'Diverted after SENSOR_FAULT'))
    fireEvent.click(screen.getByRole('button', { name: /Acknowledge/ }))
    await waitFor(() => expect(Logistics.acknowledgeAlert).toHaveBeenCalledWith('a1'))
  })

  it('can simulate a logger failure for demo vehicles', async () => {
    useAuthStore.setState({ me: me('ADMIN', ['logistics.view', 'logistics.operate']) })
    vi.mocked(Logistics.shipments).mockResolvedValue([{ ...shipment, sensor_state: 'OK', alerts: [], open_alerts: 0 }])
    render(<MemoryRouter><TransitMonitor /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /Simulate logger failure/ }))
    await waitFor(() => expect(Logistics.telemetry).toHaveBeenCalledWith('s1', expect.objectContaining({ temperature: null, sensor_status: 'FAULT' })))
  })

  it('is read-only without logistics.operate', async () => {
    useAuthStore.setState({ me: me('AUDITOR', ['logistics.view']) })
    render(<MemoryRouter><TransitMonitor /></MemoryRouter>)
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: /Divert here/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Mark delivered/ })).not.toBeInTheDocument()
  })

  it('shows an empty state when nothing is moving', async () => {
    useAuthStore.setState({ me: me('OPERATOR', ['logistics.view']) })
    vi.mocked(Logistics.shipments).mockResolvedValue([])
    render(<MemoryRouter><TransitMonitor /></MemoryRouter>)
    expect(await screen.findByText('No vehicles in transit')).toBeInTheDocument()
  })
})

describe('navigation and sidebar', () => {
  it('gives operators, supervisors and admins the in-transit page', () => {
    for (const role of ['ADMIN', 'OPERATOR', 'SUPERVISOR'] as Role[]) {
      const items = navFor(role, ['logistics.view', 'inventory.view', 'users.view', 'facilities.view', 'devices.view']).flatMap((s) => s.items)
      expect(items.map((i) => i.to)).toContain('/logistics/transit')
    }
    expect(navFor('TECHNICIAN', []).flatMap((s) => s.items).map((i) => i.to)).not.toContain('/logistics/transit')
    for (const role of ['ADMIN', 'OPERATOR', 'SUPERVISOR', 'TECHNICIAN', 'AUDITOR'] as Role[]) {
      expect(ROLE_META[role].accent).toMatch(/^#[0-9a-f]{6}$/)
    }
  })

  it('renders the role profile card, badges, home greeting and collapses to icons', async () => {
    useAuthStore.setState({ me: me('OPERATOR', ['incidents.view', 'logistics.view', 'inventory.view', 'incidents.acknowledge']), accessToken: 't' })
    render(<MemoryRouter initialEntries={['/operator']}><Routes><Route element={<AppShell />}><Route path="/operator" element={<p>dash</p>} /></Route></Routes></MemoryRouter>)
    const side = screen.getAllByLabelText('Sidebar')[0]
    expect(within(side).getByText('Ravi Kumar')).toBeInTheDocument()
    expect(within(side).getByText('2 facilities in scope')).toBeInTheDocument()
    expect(await within(side).findByText('3')).toBeInTheDocument()            // active incidents badge
    expect(await screen.findByRole('region', { name: 'Welcome' })).toHaveTextContent(/Good (morning|afternoon|evening), Ravi/)
    fireEvent.click(within(side).getByRole('button', { name: 'Collapse sidebar' }))
    const mini = screen.getAllByLabelText('Sidebar')[0]
    expect(within(mini).queryByText('Ravi Kumar')).not.toBeInTheDocument()
    expect(within(mini).getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument()
  })
})

describe('LoginPage', () => {
  it('signs in with a demo role card and toggles password visibility', async () => {
    useAuthStore.setState({ me: null, accessToken: null, refreshToken: null })
    vi.mocked(Auth.login).mockResolvedValue({ access_token: 'acc', refresh_token: 'ref' })
    vi.mocked(Auth.me).mockResolvedValue(me('SUPERVISOR', []))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    const pw = screen.getByLabelText('Password')
    expect(pw).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(pw).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: /Regional Supervisor/ }))
    await waitFor(() => expect(Auth.login).toHaveBeenCalledWith('supervisor@coldguard.local', 'ColdGuard#2026'))
  })
})
