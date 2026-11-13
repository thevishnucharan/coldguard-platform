import { api } from './client'
import type {
  Batch, FacilitySummary, Incident, IncidentDetail, IncidentEvent, LiveUnit, Me, Movement, Notification, Page,
  WorkOrder,
} from '../../types'

type Params = Record<string, unknown>
const get = <T,>(url: string, params?: Params) => api.get<T>(url, { params, paramsSerializer: { indexes: null } }).then((r) => r.data)
const post = <T,>(url: string, body?: unknown, params?: Params) => api.post<T>(url, body ?? {}, { params }).then((r) => r.data)
const put = <T,>(url: string, body?: unknown) => api.put<T>(url, body ?? {}).then((r) => r.data)

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any

export const Auth = {
  login: (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password })
    return api.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      .then((r) => r.data as { access_token: string; refresh_token: string })
  },
  me: () => get<Me>('/auth/me'),
  logout: (refresh_token: string) => post('/auth/logout', { refresh_token }),
  changePassword: (current_password: string, new_password: string) =>
    post('/auth/change-password', { current_password, new_password }),
}

export const Dashboards = {
  admin: () => get<Any>('/dashboards/admin'),
  operator: (facility_id?: string) => get<Any>('/dashboards/operator', { facility_id }),
  supervisor: () => get<Any>('/dashboards/supervisor'),
  technician: () => get<Any>('/dashboards/technician'),
  auditor: () => get<Any>('/dashboards/auditor'),
}

export const Analytics = {
  complianceTrend: (days = 14, facility_id?: string) => get<Any[]>('/analytics/compliance-trend', { days, facility_id }),
  facilityComparison: (days = 30) => get<Any[]>('/analytics/facility-comparison', { days }),
  deviceReliability: (hours = 24) => get<Any[]>('/analytics/device-reliability', { hours }),
  incidentsPerDay: (days = 14) => get<Any[]>('/analytics/incidents-per-day', { days }),
}

export const Org = {
  regions: () => get<Any[]>('/regions'),
  createRegion: (b: Any) => post('/regions', b),
  facilities: (params?: Params) => get<FacilitySummary[]>('/facilities', params),
  facility: (id: string) => get<Any>(`/facilities/${id}`),
  createFacility: (b: Any) => post('/facilities', b),
  updateFacility: (id: string, b: Any) => put(`/facilities/${id}`, b),
  policies: () => get<Any[]>('/policies'),
  createPolicy: (b: Any) => post('/policies', b),
  updatePolicy: (id: string, b: Any) => put(`/policies/${id}`, b),
}

export const Users = {
  list: (params: Params) => get<Page<Any>>('/users', params),
  get: (id: string) => get<Any>(`/users/${id}`),
  create: (b: Any) => post<Any>('/users', b),
  update: (id: string, b: Any) => put<Any>(`/users/${id}`, b),
  setAssignments: (id: string, b: Any) => put<Any>(`/users/${id}/assignments`, b),
  activity: (id: string) => get<Any[]>(`/users/${id}/activity`),
  roles: () => get<Any>('/users/roles'),
  assignable: (role: string, facility_id: string) => get<Any[]>('/users/assignable', { role, facility_id }),
}

export const Monitoring = {
  live: (facility_id?: string) => get<{ units: LiveUnit[] }>('/monitoring/live', { facility_id }).then((r) => r.units),
  unitReadings: (id: string, hours = 24) => get<Any>(`/storage-units/${id}/readings`, { hours }),
  unit: (id: string) => get<Any>(`/storage-units/${id}`),
  units: (params?: Params) => get<Any[]>('/storage-units', params),
  createUnit: (b: Any) => post('/storage-units', b),
  updateUnit: (id: string, b: Any) => put(`/storage-units/${id}`, b),
  anomalies: (params?: Params) => get<Any>('/monitoring/anomalies', params),
  quarantine: (params?: Params) => get<Page<Any>>('/monitoring/quarantine', params),
}

export const Devices = {
  list: (params?: Params) => get<Any[]>('/sensors', params),
  provision: (b: Any) => post<Any>('/sensors', b),
  update: (id: string, b: Any) => put(`/sensors/${id}`, b),
  decommission: (id: string, reason: string) => post(`/sensors/${id}/decommission`, {}, { reason }),
  rotateKey: (id: string) => post<Any>(`/sensors/${id}/rotate-key`),
  history: (id: string) => get<Any[]>(`/sensors/${id}/history`),
  health: (id: string) => get<Any[]>(`/sensors/${id}/health`),
}

export const Incidents = {
  list: (params: Params) => get<Page<Incident>>('/incidents', params),
  get: (id: string) => get<IncidentDetail>(`/incidents/${id}`),
  events: (id: string) => get<IncidentEvent[]>(`/incidents/${id}/events`),
  evidence: (id: string) => get<Any>(`/incidents/${id}/evidence`),
  affectedBatches: (id: string) => get<Any[]>(`/incidents/${id}/affected-batches`),
  report: (b: Any) => post<IncidentDetail>('/incidents', b),
  acknowledge: (id: string, notes?: string) => post<IncidentDetail>(`/incidents/${id}/acknowledge`, { notes }),
  investigate: (id: string, notes?: string) => post<IncidentDetail>(`/incidents/${id}/investigate`, { notes }),
  note: (id: string, note: string) => post<IncidentDetail>(`/incidents/${id}/notes`, { note }),
  escalate: (id: string, reason: string) => post<IncidentDetail>(`/incidents/${id}/escalate`, { reason }),
  proposeCA: (id: string, b: Any) => post(`/incidents/${id}/corrective-actions`, b),
  reviewCA: (id: string, caId: string, decision: string, comment?: string) =>
    post(`/incidents/${id}/corrective-actions/${caId}/review`, { decision, comment }),
  implementCA: (id: string, caId: string, notes?: string) => post(`/incidents/${id}/corrective-actions/${caId}/implement`, { notes }),
  verifyRecovery: (id: string, notes?: string) => post<IncidentDetail>(`/incidents/${id}/verify-recovery`, { notes }),
  review: (id: string, decision: string, notes?: string) => post<IncidentDetail>(`/incidents/${id}/review`, { decision, notes }),
  close: (id: string, b: Any) => post<IncidentDetail>(`/incidents/${id}/close`, b),
  assign: (id: string, assignee_id: string) => post<IncidentDetail>(`/incidents/${id}/assign`, { assignee_id }),
  aiSummary: (id: string) => post<{ ai_summary: string }>(`/incidents/${id}/ai-summary`),
}

export const Inventory = {
  products: () => get<Any[]>('/products'),
  createProduct: (b: Any) => post('/products', b),
  batches: (params: Params) => get<Page<Batch>>('/batches', params),
  batch: (id: string) => get<Batch & { movements: Movement[]; incidents: Any[] }>(`/batches/${id}`),
  receive: (b: Any) => post<Batch>('/batches/receive', b),
  action: (id: string, action: string, b: Any) => post<Batch>(`/batches/${id}/${action}`, b),
  fefo: (product_id: string, facility_id: string) => get<Batch[]>('/inventory/fefo', { product_id, facility_id }),
  issueFefo: (b: Any) => post<Movement[]>('/inventory/issue-fefo', b),
  movements: (params: Params) => get<Page<Movement>>('/inventory/movements', params),
  summary: (facility_id?: string) => get<Any>('/inventory/summary', { facility_id }),
}

export const Maintenance = {
  list: (params: Params) => get<Page<WorkOrder>>('/maintenance/tickets', params),
  get: (id: string) => get<WorkOrder>(`/maintenance/tickets/${id}`),
  create: (b: Any) => post<WorkOrder>('/maintenance/tickets', b),
  act: (id: string, action: string, b?: Any) => post<WorkOrder>(`/maintenance/tickets/${id}/${action}`, b),
  schedule: (days = 60) => get<Any>('/maintenance/schedule', { days }),
  calibrations: (params?: Params) => get<Any[]>('/calibration', params),
  recordCalibration: (b: Any) => post('/calibration', b),
  replaceSensor: (b: Any) => post<Any>('/equipment/replace-sensor', b),
  replaceUnit: (b: Any) => post<Any>('/equipment/replace-storage-unit', b),
  equipmentHistory: (params?: Params) => get<Any[]>('/equipment/history', params),
}

export const Notifications = {
  list: (params?: Params) => get<{ unread: number; items: Notification[] }>('/notifications', params),
  read: (id: string) => post(`/notifications/${id}/read`),
  readAll: () => post('/notifications/read-all'),
}

export const Reports = {
  types: () => get<{ reports: { key: string; label: string }[]; can_export: boolean }>('/reports/types'),
}

export const Audit = {
  list: (params: Params) => get<Page<Any>>('/audit-logs', params),
}

export const System = {
  status: () => get<Any>('/system/status'),
  escalation: () => get<Any>('/system/escalation-rules'),
  setEscalation: (b: Any) => put<Any>('/system/escalation-rules', b),
  configs: () => get<Any[]>('/configurations'),
  setConfig: (key: string, value: unknown) => put(`/configurations/${key}`, { value }),
  simulation: () => get<Any>('/demo/simulation'),
  startSim: (interval_seconds: number) => post('/demo/simulation/start', { interval_seconds }),
  stopSim: () => post('/demo/simulation/stop'),
  setScenario: (sensor_id: string, scenario: string) => post('/demo/simulation/scenario', { sensor_id, scenario }),
  resetDemo: () => post<Any>('/demo/reset', { confirm: 'RESET DEMO DATA' }),
}
