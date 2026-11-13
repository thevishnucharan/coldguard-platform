import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom'
import { PageSkeleton } from '../components/common/Feedback'
import { EmptyState } from '../components/common/Feedback'
import { useAuthStore } from '../store/authStore'
import { AppShell } from './AppShell'
import { HOME } from './navigation'
import { ShieldOff } from 'lucide-react'
import LoginPage from '../features/authentication/LoginPage'

const L = (f: () => Promise<{ default: React.ComponentType }>) => {
  const C = lazy(f)
  return <Suspense fallback={<PageSkeleton />}><C /></Suspense>
}

/** Client-side guard for UX only; the API enforces every permission independently. */
export function RequireAuth() {
  const me = useAuthStore((s) => s.me)
  const token = useAuthStore((s) => s.accessToken)
  const loc = useLocation()
  if (!me || !token) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  return <Outlet />
}

export function Guard({ perm, children }: { perm: string[]; children: ReactNode }) {
  const can = useAuthStore((s) => s.can)
  if (!can(...perm)) {
    return <div className="card mt-6"><EmptyState icon={ShieldOff} title="You don't have access to this page"
      description={`Requires permission: ${perm.join(', ')}. Contact your administrator if you need access.`} /></div>
  }
  return <>{children}</>
}

function RoleHome() {
  const me = useAuthStore((s) => s.me)
  return <Navigate to={me ? HOME[me.role] : '/login'} replace />
}

const g = (perm: string[], el: ReactNode) => <Guard perm={perm}>{el}</Guard>

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [{
      element: <AppShell />,
      children: [
        { index: true, element: <RoleHome /> },
        // Admin
        { path: 'admin', element: g(['platform.view', 'users.view'], L(() => import('../features/admin/AdminOverview'))) },
        { path: 'admin/facilities', element: g(['facilities.view'], L(() => import('../features/admin/FacilitiesPage'))) },
        { path: 'admin/users', element: g(['users.view'], L(() => import('../features/admin/UsersPage'))) },
        { path: 'admin/logistics', element: g(['logistics.view'], L(() => import('../features/admin/ExcursionRoutingPage'))) },
        { path: 'logistics/transit', element: g(['logistics.view'], L(() => import('../features/logistics/TransitMonitor'))) },
        { path: 'admin/devices', element: g(['devices.view'], L(() => import('../features/admin/DeviceRegistryPage'))) },
        { path: 'admin/config', element: g(['platform.configure'], L(() => import('../features/admin/SystemConfigPage'))) },
        { path: 'admin/simulation', element: g(['simulation.control'], L(() => import('../features/admin/SimulationPage'))) },
        // Operator
        { path: 'operator', element: g(['incidents.acknowledge'], L(() => import('../features/operator/FacilityDashboard'))) },
        // Supervisor
        { path: 'supervisor', element: g(['incidents.review'], L(() => import('../features/supervisor/RegionalOverview'))) },
        { path: 'supervisor/approvals', element: g(['incidents.review'], L(() => import('../features/supervisor/ApprovalQueue'))) },
        { path: 'supervisor/compliance', element: g(['reports.view', 'incidents.view'], L(() => import('../features/supervisor/CompliancePage'))) },
        // Technician
        { path: 'technician', element: g(['maintenance.update'], L(() => import('../features/technician/TechnicianDashboard'))) },
        { path: 'technician/equipment', element: g(['devices.view'], L(() => import('../features/technician/EquipmentHealthPage'))) },
        { path: 'technician/schedule', element: g(['maintenance.view'], L(() => import('../features/technician/SchedulePage'))) },
        // Auditor
        { path: 'auditor', element: g(['audit.view'], L(() => import('../features/auditor/AuditorHome'))) },
        { path: 'audit', element: g(['audit.view'], L(() => import('../features/auditor/AuditTrailPage'))) },
        // Shared feature areas
        { path: 'monitoring', element: g(['monitoring.view'], L(() => import('../features/monitoring/LiveMonitoringPage'))) },
        { path: 'monitoring/units/:id', element: g(['monitoring.view'], L(() => import('../features/monitoring/StorageUnitPage'))) },
        { path: 'incidents', element: g(['incidents.view'], L(() => import('../features/incidents/IncidentsPage'))) },
        { path: 'incidents/:id', element: g(['incidents.view'], L(() => import('../features/incidents/IncidentDetailPage'))) },
        { path: 'inventory', element: g(['inventory.view'], L(() => import('../features/inventory/InventoryPage'))) },
        { path: 'inventory/batches/:id', element: g(['inventory.view'], L(() => import('../features/inventory/BatchDetailPage'))) },
        { path: 'maintenance', element: g(['maintenance.view'], L(() => import('../features/maintenance/WorkOrdersPage'))) },
        { path: 'maintenance/:id', element: g(['maintenance.view'], L(() => import('../features/maintenance/WorkOrderDetailPage'))) },
        { path: 'calibration', element: g(['calibration.view'], L(() => import('../features/maintenance/CalibrationPage'))) },
        { path: 'reports', element: g(['reports.view'], L(() => import('../features/reports/ReportsPage'))) },
        { path: 'profile', element: L(() => import('../features/authentication/ProfilePage')) },
        { path: '*', element: <div className="card mt-6"><EmptyState title="Page not found" description="The page you requested does not exist." /></div> },
      ],
    }],
  },
])
