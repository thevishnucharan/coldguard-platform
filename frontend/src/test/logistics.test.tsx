import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { navFor } from '../app/navigation'
import { useAuthStore } from '../store/authStore'
import type { Me } from '../types'

vi.mock('../components/charts/RouteMap', () => ({
  RouteMap: ({ trips }: { trips: unknown[] }) => <div data-testid="route-map">{trips.length} trip(s)</div>,
}))

const plan = {
  id: 'p1', plan_number: 'RP-20261113-ABC123', status: 'PROPOSED',
  source: { key: 'f1', code: 'F1', name: 'PHC One', lat: 12.9, lon: 77.5, unit_code: 'U1' },
  trips: [{ trip: 1, vehicle: 1, start_offset_minutes: 0, duration_minutes: 52, cold_chain_minutes_p90: 24, distance_km: 14.2, load_litres: 7, doses: 2000,
    stops: [{ facility_key: 'f2', facility_code: 'F2', facility_name: 'PHC Two', lat: 13, lon: 77.6, leg_distance_km: 7.1, leg_eta_minutes: 19,
      leg_eta_p90_minutes: 24, arrival_offset_minutes: 19, arrival_p90_offset_minutes: 24, doses: 2000, load_litres: 7,
      deliveries: [{ storage_unit_id: 'u2', unit_code: 'U2', approved_range: [2, 8], batches: [{ batch_id: 'b1', batch_number: 'PENTA-1', product: 'Penta', doses: 2000, segregate: false }] }] }] }],
  on_site_moves: [], unassigned: [{ batch_id: 'b9', batch_number: 'MRNA-1', product: 'mRNA', doses: 50, reason: 'No compatible storage unit in scope' }],
  excluded_units: [],
  summary: { batches: 2, total_doses: 2050, relocated_doses: 2000, unassigned_doses: 50, trip_count: 1, distance_km: 14.2, completion_minutes: 52,
    exposure_dose_minutes: 38000, baseline_exposure_dose_minutes: 61000, improvement_pct: 37.7 },
  parameters: { max_trip_minutes: 240, vehicle_capacity_litres: 60, vehicles: 1, depart_at: '2026-11-13T09:00:00Z' },
  model: { available: true, version: 'route-eta-gbr-v1-sim-2026.11' },
  note: 'Decision support only.',
}

vi.mock('../services/api/endpoints', () => ({
  Logistics: {
    model: vi.fn().mockResolvedValue({ available: true, version: 'route-eta-gbr-v1-sim-2026.11', metrics: { p50_mae_minutes: 6.4, baseline_mae_minutes: 16.2 } }),
    excursions: vi.fn().mockResolvedValue([{ incident_id: 'i1', incident_number: 'INC-2026-0007', title: 'Excursion', severity: 'CRITICAL', status: 'OPEN',
      created_at: '2026-11-13T08:50:00Z', storage_unit_id: 'u1', unit_code: 'U1', facility_name: 'PHC One', is_simulated: false,
      batches_at_risk: 2, doses_at_risk: 2050, latest_plan: null }]),
    plans: vi.fn().mockResolvedValue([]),
    plan: vi.fn(),
    optimise: vi.fn(),
    approve: vi.fn(),
    cancel: vi.fn(),
  },
}))

import { Logistics } from '../services/api/endpoints'
import ExcursionRoutingPage from '../features/admin/ExcursionRoutingPage'

const me = (perms: string[]): Me => ({ id: 'a', name: 'Admin', email: 'a@x.io', role: 'ADMIN', role_label: 'System Administrator',
  permissions: perms, global_scope: true, facility_ids: [], region_ids: [] })

beforeEach(() => {
  vi.mocked(Logistics.optimise).mockReset().mockResolvedValue(plan)
  vi.mocked(Logistics.approve).mockReset().mockResolvedValue({ ...plan, status: 'APPROVED' })
})

describe('ExcursionRoutingPage', () => {
  it('optimises the selected excursion with the chosen constraints and shows the result', async () => {
    useAuthStore.setState({ me: me(['logistics.view', 'logistics.plan']) })
    render(<MemoryRouter><ExcursionRoutingPage /></MemoryRouter>)
    const option = await screen.findByRole('option', { name: /INC-2026-0007/ })
    const button = screen.getByRole('button', { name: /Optimise relocation route/ })
    expect(button).toBeDisabled()
    fireEvent.click(option)
    fireEvent.change(screen.getByLabelText('Vehicles'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText(/Cold-box hold time/), { target: { value: '180' } })
    fireEvent.click(button)
    await waitFor(() => expect(Logistics.optimise).toHaveBeenCalledWith(
      { incident_id: 'i1', max_trip_minutes: 180, vehicle_capacity_litres: 60, vehicles: 2, allow_on_site: true }))
    expect(await screen.findByText('−37.7%')).toBeInTheDocument()
    expect(screen.getByTestId('route-map')).toHaveTextContent('1 trip(s)')
    expect(screen.getByText(/PHC Two/)).toBeInTheDocument()
    expect(screen.getByText(/No compatible storage unit in scope/)).toBeInTheDocument()
  })

  it('approves a proposed plan', async () => {
    useAuthStore.setState({ me: me(['logistics.view', 'logistics.plan']) })
    render(<MemoryRouter><ExcursionRoutingPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('option', { name: /INC-2026-0007/ }))
    fireEvent.click(screen.getByRole('button', { name: /Optimise relocation route/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Approve & notify/ }))
    await waitFor(() => expect(Logistics.approve).toHaveBeenCalledWith('p1', undefined))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Approve & notify/ })).not.toBeInTheDocument())
  })

  it('is read-only without logistics.plan', async () => {
    useAuthStore.setState({ me: me(['logistics.view']) })
    render(<MemoryRouter><ExcursionRoutingPage /></MemoryRouter>)
    expect(await screen.findByRole('option', { name: /INC-2026-0007/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Optimise relocation route/ })).not.toBeInTheDocument()
  })
})

describe('admin navigation', () => {
  it('shows Excursion routing only with logistics.view', () => {
    const labels = (perms: string[]) => navFor('ADMIN', perms).flatMap((s) => s.items.map((i) => i.label))
    expect(labels(['logistics.view'])).toContain('Excursion routing')
    expect(labels([])).not.toContain('Excursion routing')
  })
})
