import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AxiosError, AxiosHeaders } from 'axios'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { errorMessage } from '../services/api/client'
import { useAuthStore } from '../store/authStore'

vi.mock('../services/api/endpoints', () => ({
  Auth: {
    login: vi.fn(),
    me: vi.fn(),
    changePassword: vi.fn(),
  },
  Dashboards: {
    technician: vi.fn().mockResolvedValue({
      kpis: { open_requests: 4, my_assigned: 2, in_progress: 1, completed_30d: 7, overdue: 3, pm_due_30d: 5, calibration_due_30d: 2, sensors_offline: 1, low_battery: 0 },
      overdue_gauge: { overdue: 3, active: 9 },
      work_orders_over_time: [{ week: '2026-10-01', preventive: 1, corrective: 2, completed: 1 }],
      active_by_type: [{ type: 'CORRECTIVE', count: 4 }], active_by_trigger: [{ trigger: 'RULE', count: 2 }],
      my_work_orders: [{ id: 'w1', ticket_number: 'WO-2026-00001', title: 'Replace door gasket', status: 'IN_PROGRESS', priority: 'HIGH',
        due_date: '2026-11-20T00:00:00Z', is_overdue: false, unit_code: 'BLR-HEB-ILR-1', facility_name: 'PHC Hebbal' }],
      unassigned: [], equipment: [],
    }),
  },
}))

import { Auth } from '../services/api/endpoints'
import LoginPage from '../features/authentication/LoginPage'
import TechnicianDashboard from '../features/technician/TechnicianDashboard'
import ProfilePage from '../features/authentication/ProfilePage'

beforeEach(() => {
  useAuthStore.setState({ me: null, accessToken: null, refreshToken: null })
  vi.mocked(Auth.login).mockReset()
  vi.mocked(Auth.me).mockReset()
})

describe('LoginPage', () => {
  it('validates required fields before calling the API', async () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter your email and password')
    expect(Auth.login).not.toHaveBeenCalled()
  })

  it('stores the session and profile on success', async () => {
    vi.mocked(Auth.login).mockResolvedValue({ access_token: 'acc', refresh_token: 'ref' })
    vi.mocked(Auth.me).mockResolvedValue({ id: 'u', name: 'Ravi', email: 'r@x.io', role: 'OPERATOR', role_label: 'Facility Operator',
      permissions: ['incidents.view'], global_scope: false, facility_ids: [], region_ids: [] })
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'r@x.io' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Secret-123x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(useAuthStore.getState().accessToken).toBe('acc'))
    expect(useAuthStore.getState().me?.role).toBe('OPERATOR')
  })

  it('shows the API error message on failure', async () => {
    vi.mocked(Auth.login).mockRejectedValue(new AxiosError('x', '401', undefined, undefined,
      { status: 401, data: { detail: 'Incorrect email or password' }, statusText: '', headers: {}, config: { headers: new AxiosHeaders() } }))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'r@x.io' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'bad' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password')
  })
})

describe('ProfilePage password form validation', () => {
  it('flags weak and mismatched passwords and disables submit', () => {
    useAuthStore.setState({ me: { id: 'u', name: 'A', email: 'a@x.io', role: 'AUDITOR', role_label: 'Auditor', permissions: [], global_scope: true, facility_ids: [], region_ids: [] } })
    render(<MemoryRouter><ProfilePage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'whatever1' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'short' } })
    expect(screen.getByText(/Too weak/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'LongEnough123' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'Different123' } })
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Update password' })).toBeDisabled()
  })
})

describe('TechnicianDashboard', () => {
  it('renders API data: hero numbers, gauge and work queue', async () => {
    render(<MemoryRouter><TechnicianDashboard /></MemoryRouter>)
    expect(await screen.findByText('WO-2026-00001')).toBeInTheDocument()
    expect(screen.getByText('Overdue work orders', { selector: 'div' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'overdue: 3 of 9' })).toBeInTheDocument()
  })
})

describe('errorMessage', () => {
  it('formats validation errors from the API', () => {
    const err = new AxiosError('x', '422', undefined, undefined, { status: 422, statusText: '', headers: {}, config: { headers: new AxiosHeaders() },
      data: { detail: 'Validation failed', errors: [{ loc: ['body', 'quantity'], msg: 'must be > 0' }] } })
    expect(errorMessage(err)).toBe('quantity: must be > 0')
    expect(errorMessage(new AxiosError('net'))).toBe('Cannot reach the ColdGuard API')
  })
})
