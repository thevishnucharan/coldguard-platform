import { Plus } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Link, useNavigate } from 'react-router-dom'
import { DataTable, Pagination } from '../../components/common/DataTable'
import { Field, FilterBar, Segmented, Select } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, PriorityBadge, SourceTag, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Maintenance, Monitoring, Org } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { WorkOrder } from '../../types'
import { fmtDate, humanize } from '../../utils/format'

export function WorkOrderTable({ rows, loading, error }: { rows?: WorkOrder[]; loading?: boolean; error?: string | null }) {
  const navigate = useNavigate()
  return (
    <DataTable<WorkOrder> rows={rows} loading={loading} error={error} onRowClick={(t) => navigate(`/maintenance/${t.id}`)} columns={[
      { key: 'n', header: 'Work order', render: (t) => <div><Link to={`/maintenance/${t.id}`} className="font-medium text-brand-700">{t.ticket_number}</Link>
        <div className="text-xs text-ink-3 max-w-72 truncate">{t.title}</div></div> },
      { key: 'p', header: 'Priority', render: (t) => <PriorityBadge priority={t.priority} /> },
      { key: 's', header: 'Status', render: (t) => <StatusPill status={t.status} /> },
      { key: 'ty', header: 'Type', render: (t) => <span className="text-xs">{humanize(t.maintenance_type)}</span> },
      { key: 'tr', header: 'Trigger', render: (t) => <SourceTag source={t.trigger} /> },
      { key: 'eq', header: 'Equipment', render: (t) => <div className="text-xs"><div>{t.storage_unit_code || t.sensor_code || '—'}</div><div className="text-ink-3">{t.facility_name}</div></div> },
      { key: 'a', header: 'Technician', render: (t) => t.assignee_name || <span className="text-ink-3">Unassigned</span> },
      { key: 'd', header: 'Due', render: (t) => <span className="flex items-center gap-1.5 text-xs">{fmtDate(t.due_date)}{t.is_overdue && <Pill tone="crit">Overdue</Pill>}</span> },
    ]} />
  )
}

export function NewWorkOrderModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone?: () => void }) {
  const facilities = useApi(() => Org.facilities(), [], { enabled: open })
  const [f, setF] = useState({ facility_id: '', storage_unit_id: '', title: '', description: '', priority: 'MEDIUM', maintenance_type: 'CORRECTIVE' })
  const units = useApi(() => f.facility_id ? Monitoring.units({ facility_id: f.facility_id }) : Promise.resolve([]), [f.facility_id, open], { enabled: open })
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }))
  const navigate = useNavigate()
  return (
    <Modal open={open} onClose={onClose} title="New maintenance request" size="lg"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!f.facility_id || f.title.length < 5 || f.description.length < 5} onClick={async () => {
          try { const t = await Maintenance.create({ ...f, storage_unit_id: f.storage_unit_id || undefined }); toast.success(`${t.ticket_number} created`); onDone?.(); onClose(); navigate(`/maintenance/${t.id}`) }
          catch (e) { toast.error(errorMessage(e)) } }}>Create</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Facility" required><select className="input" value={f.facility_id} onChange={(e) => set('facility_id', e.target.value)}>
          <option value="">Select…</option>{(facilities.data || []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="Equipment"><select className="input" value={f.storage_unit_id} onChange={(e) => set('storage_unit_id', e.target.value)}>
          <option value="">Facility-level</option>{(units.data || []).map((u) => <option key={u.id} value={u.id}>{u.unit_code} — {u.name}</option>)}</select></Field>
        <Field label="Title" required className="sm:col-span-2"><input className="input" value={f.title} onChange={(e) => set('title', e.target.value)} /></Field>
        <Field label="Issue description" required className="sm:col-span-2"><textarea className="input h-24 py-2" value={f.description} onChange={(e) => set('description', e.target.value)} /></Field>
        <Field label="Priority"><select className="input" value={f.priority} onChange={(e) => set('priority', e.target.value)}>{['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((p) => <option key={p}>{p}</option>)}</select></Field>
        <Field label="Type"><select className="input" value={f.maintenance_type} onChange={(e) => set('maintenance_type', e.target.value)}>
          {['CORRECTIVE', 'INSPECTION', 'PREVENTIVE', 'CALIBRATION', 'REPLACEMENT'].map((p) => <option key={p} value={p}>{humanize(p)}</option>)}</select></Field>
      </div>
    </Modal>
  )
}

export default function WorkOrdersPage() {
  const can = useAuthStore((s) => s.can)
  const [view, setView] = useState<'active' | 'mine' | 'overdue' | 'done' | 'all'>(can('maintenance.update') ? 'mine' : 'active')
  const [priority, setPriority] = useState('')
  const [trigger, setTrigger] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const q = useApi(() => Maintenance.list({
    page, page_size: 20, priority: priority || undefined, trigger: trigger || undefined,
    ...(view === 'active' ? { status: ['OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED'] } : view === 'mine' ? { mine: true, status: ['ASSIGNED', 'IN_PROGRESS', 'RESOLVED'] }
      : view === 'overdue' ? { overdue: true } : view === 'done' ? { status: ['VERIFIED', 'CLOSED'] } : {}),
  }), [view, priority, trigger, page], { refreshOn: ['maintenance.updated'] })
  return (
    <>
      <PageHeader title="Maintenance work orders" subtitle="Repairs, inspections, preventive servicing and calibration. Auto-generated orders show their trigger rule."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Maintenance' }]}
        actions={can('maintenance.create') && <button className="btn-primary" onClick={() => setOpen(true)}><Plus size={15} /> New request</button>} />
      <FilterBar>
        <Segmented value={view} onChange={(v) => { setView(v); setPage(1) }} options={[
          ...(can('maintenance.update') ? [{ value: 'mine' as const, label: 'Assigned to me' }] : []),
          { value: 'active', label: 'Active' }, { value: 'overdue', label: 'Overdue' }, { value: 'done', label: 'Completed' }, { value: 'all', label: 'All' }]} />
        <Select ariaLabel="Priority" value={priority} onChange={(v) => { setPriority(v); setPage(1) }} placeholder="All priorities" className="w-40"
          options={['URGENT', 'HIGH', 'MEDIUM', 'LOW'].map((p) => ({ value: p, label: humanize(p) }))} />
        <Select ariaLabel="Trigger" value={trigger} onChange={(v) => { setTrigger(v); setPage(1) }} placeholder="All triggers" className="w-44"
          options={[{ value: 'MANUAL', label: 'Reported' }, { value: 'RULE', label: 'Rule-based' }, { value: 'PREVENTIVE', label: 'Preventive' }, { value: 'ML', label: 'ML signal' }]} />
      </FilterBar>
      <div className="card p-0">
        <WorkOrderTable rows={q.data?.items} loading={q.loading} error={q.error} />
        <div className="px-4 pb-3"><Pagination page={page} pageSize={20} total={q.data?.total || 0} onPage={setPage} /></div>
      </div>
      <NewWorkOrderModal open={open} onClose={() => setOpen(false)} onDone={q.reload} />
    </>
  )
}
