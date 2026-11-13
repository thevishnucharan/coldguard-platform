export type Role = 'ADMIN' | 'OPERATOR' | 'SUPERVISOR' | 'TECHNICIAN' | 'AUDITOR'
export type Severity = 'WARNING' | 'HIGH' | 'CRITICAL'
export type IncidentStatus =
  | 'DETECTED' | 'OPEN' | 'ACKNOWLEDGED' | 'INVESTIGATING' | 'CORRECTIVE_ACTION_PENDING'
  | 'UNDER_REVIEW' | 'RESOLVED' | 'CLOSED'
export type IncidentType =
  | 'TEMPERATURE_EXCURSION' | 'SENSOR_OFFLINE' | 'MISSING_TELEMETRY' | 'ABNORMAL_PATTERN'
  | 'EQUIPMENT_FAILURE' | 'SENSOR_FAULT'
export type UnitHealth = 'NORMAL' | 'WARNING' | 'CRITICAL' | 'OFFLINE' | 'MISSING_TELEMETRY' | 'NO_DATA' | 'INACTIVE'
export type BatchStatus = 'ACTIVE' | 'QUARANTINED' | 'EXPIRED' | 'DEPLETED' | 'DISCARDED' | 'COMPLETED'
export type WorkOrderStatus = 'OPEN' | 'ASSIGNED' | 'IN_PROGRESS' | 'RESOLVED' | 'VERIFIED' | 'CLOSED'
export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface Me {
  id: string; name: string; email: string; role: Role; role_label: string; title?: string | null
  permissions: string[]; global_scope: boolean; facility_ids: string[]; region_ids: string[]
  last_login_at?: string | null
}

export interface SensorBrief {
  id: string; sensor_code: string; status: string; battery_level: number | null
  last_reading_at: string | null; last_temperature: number | null; is_simulated: boolean
}

export interface LiveUnit {
  id: string; unit_code: string; name: string; unit_type: string; status: string
  facility_id: string; facility_name: string | null; min_temperature: number; max_temperature: number
  warning_margin: number; policy_name: string | null; health: UnitHealth; latest_temperature: number | null
  last_reading_at: string | null; seconds_since_reading: number | null; stale: boolean
  active_incidents: number; sensors: SensorBrief[]; is_simulated: boolean
  sparkline: { t: string; v: number }[]
}

export interface Incident {
  id: string; incident_number: string; incident_type: IncidentType; severity: Severity; status: IncidentStatus
  title: string | null; description: string | null; source: string; is_simulated: boolean
  facility_id: string | null; facility_name: string | null; storage_unit_id: string | null
  storage_unit_code: string | null; sensor_code: string | null; assigned_to: string | null; assignee_name: string | null
  root_cause: string | null; corrective_action: string | null; investigation_notes: string | null
  ai_summary: string | null; escalation_level: number; escalation_reason: string | null
  review_decision: string | null; review_notes: string | null; closure_evidence: string | null
  vaccine_disposition: string | null; peak_temperature: number | null
  excursion_start: string | null; excursion_end: string | null
  created_at: string; acknowledged_at: string | null; resolved_at: string | null; closed_at: string | null
  duration_seconds: number | null; limit_min: number | null; limit_max: number | null
}

export interface IncidentEvent {
  id: string; event_type: string; from_status: string | null; to_status: string | null
  actor_name: string; note: string | null; data: Record<string, unknown> | null; created_at: string
}

export interface CorrectiveAction {
  id: string; action_type: string; description: string; root_cause: string | null; status: string
  proposer_name: string | null; reviewer_name: string | null; review_comment: string | null
  reviewed_at: string | null; due_date: string | null; implemented_at: string | null
  implementation_notes: string | null; created_at: string
}

export interface IncidentDetail extends Incident {
  events: IncidentEvent[]; corrective_actions: CorrectiveAction[]; affected_batch_count: number
  available_actions: string[]
}

export interface Batch {
  id: string; batch_number: string; product_id: string; product_name: string | null
  storage_unit_id: string; storage_unit_code: string | null; facility_id: string | null; facility_name: string | null
  status: BatchStatus; manufacturer: string | null; manufacturing_date: string | null; expiry_date: string
  receipt_date: string | null; supplier: string | null; quantity_received: number; current_quantity: number
  unit_of_measure: string; quarantine_reason: string | null; expiry_bucket: string; days_to_expiry: number
  excursion_count: number
}

export interface Movement {
  id: string; batch_id: string; batch_number: string | null; movement_type: string; quantity_change: number
  quantity_after: number; status_before: string | null; status_after: string | null; reason: string | null
  reference: string | null; performed_by_name: string; created_at: string
}

export interface WorkOrder {
  id: string; ticket_number: string; facility_id: string; facility_name: string | null
  storage_unit_id: string | null; storage_unit_code: string | null; sensor_id: string | null; sensor_code: string | null
  incident_id: string | null; title: string; description: string; maintenance_type: string; priority: Priority
  status: WorkOrderStatus; trigger: string; trigger_rule: string | null; assigned_to: string | null
  assignee_name: string | null; due_date: string | null; inspection_results: string | null
  repair_notes: string | null; next_maintenance_due: string | null; created_at: string; resolved_at: string | null
  verified_at: string | null; closed_at: string | null; is_overdue: boolean
  notes?: { id: string; kind: string; body: string; evidence_reference: string | null; author_name: string; created_at: string }[]
}

export interface FacilitySummary {
  id: string; code: string; name: string; facility_type: string; region_id: string; region_name: string | null
  latitude: number | null; longitude: number | null; is_active: boolean; storage_units: number
  sensors_total: number; sensors_online: number; active_incidents: number; critical_incidents: number
  health: UnitHealth; address?: string | null; contact_name?: string | null; contact_phone?: string | null
}

export interface Notification {
  id: string; level: 'INFO' | 'WARNING' | 'CRITICAL'; category: string; title: string; message: string
  link: string | null; created_at: string; read_at: string | null
}

export interface ApiErrorShape { detail?: string; errors?: { loc: string[]; msg: string }[] }
