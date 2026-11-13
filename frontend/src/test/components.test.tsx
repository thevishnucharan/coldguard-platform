import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, beforeEach } from 'vitest'
import { Guard } from '../app/router'
import { DataTable } from '../components/common/DataTable'
import { HealthBadge, SeverityBadge, SimulatedTag } from '../components/common/Status'
import { Gauge } from '../components/charts/Mini'
import { useAuthStore } from '../store/authStore'
import type { Me } from '../types'

const me = (perms: string[]): Me => ({ id: 'u1', name: 'Test User', email: 't@x.io', role: 'OPERATOR', role_label: 'Facility Operator',
  permissions: perms, global_scope: false, facility_ids: ['f1'], region_ids: [] })

describe('status components', () => {
  it('never communicate state by colour alone', () => {
    render(<><HealthBadge health="CRITICAL" /><HealthBadge health="MISSING_TELEMETRY" /><SeverityBadge severity="HIGH" /><SimulatedTag /></>)
    expect(screen.getByText('Critical')).toBeInTheDocument()
    expect(screen.getByText('Missing data')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
    expect(screen.getByText('Simulated')).toBeInTheDocument()
  })

  it('gauge exposes an accessible label', () => {
    render(<Gauge value={3} total={10} label="overdue" />)
    expect(screen.getByRole('img', { name: 'overdue: 3 of 10' })).toBeInTheDocument()
  })
})

describe('DataTable', () => {
  it('renders rows, empty and error states', () => {
    const cols = [{ key: 'a', header: 'Name', render: (r: { id: string; name: string }) => r.name }]
    const { rerender } = render(<DataTable columns={cols} rows={[{ id: '1', name: 'Fridge A' }]} />)
    expect(screen.getByText('Fridge A')).toBeInTheDocument()
    rerender(<DataTable columns={cols} rows={[]} />)
    expect(screen.getByText('No records found')).toBeInTheDocument()
    rerender(<DataTable columns={cols} rows={null} error="boom" />)
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
  })
})

describe('permission guard (UX only — API enforces independently)', () => {
  beforeEach(() => useAuthStore.setState({ me: null, accessToken: null, refreshToken: null }))
  it('blocks pages without the permission', () => {
    useAuthStore.setState({ me: me(['incidents.view']) })
    render(<MemoryRouter><Guard perm={['users.view']}><p>secret</p></Guard></MemoryRouter>)
    expect(screen.queryByText('secret')).toBeNull()
    expect(screen.getByText(/don't have access/i)).toBeInTheDocument()
  })
  it('renders pages with the permission', () => {
    useAuthStore.setState({ me: me(['users.view']) })
    render(<MemoryRouter><Guard perm={['users.view']}><p>secret</p></Guard></MemoryRouter>)
    expect(screen.getByText('secret')).toBeInTheDocument()
  })
  it('store.can requires all permissions', () => {
    useAuthStore.setState({ me: me(['a', 'b']) })
    expect(useAuthStore.getState().can('a', 'b')).toBe(true)
    expect(useAuthStore.getState().can('a', 'c')).toBe(false)
  })
})
