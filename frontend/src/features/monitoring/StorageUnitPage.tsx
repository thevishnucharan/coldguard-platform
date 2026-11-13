import { AlertTriangle, Wrench } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { TemperatureChart } from '../../components/charts/TemperatureChart'
import { Card, CardHeader, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { ErrorState, LoadingBlock, PageSkeleton } from '../../components/common/Feedback'
import { Field, Segmented } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { HealthBadge, SeverityBadge, SimulatedTag, StatusPill } from '../../components/common/Status'
import { useApi, useNow } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Devices, Incidents, Inventory, Maintenance, Monitoring } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { ago, fmtDate, fmtDateTime, fmtTemp } from '../../utils/format'

export function ReportIssueModal({ open, onClose, unit }: { open: boolean; onClose: () => void; unit: { id: string; unit_code: string; facility_id: string } }) {
  const can = useAuthStore((s) => s.can)
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [kind, setKind] = useState<'workorder' | 'incident'>(can('maintenance.create') ? 'workorder' : 'incident')
  const [priority, setPriority] = useState('MEDIUM')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const submit = async () => {
    setBusy(true)
    try {
      if (kind === 'workorder') {
        const t = await Maintenance.create({ facility_id: unit.facility_id, storage_unit_id: unit.id, title, description: desc, priority })
        toast.success(`Work order ${t.ticket_number} raised`)
        navigate(`/maintenance/${t.id}`)
      } else {
        const i = await Incidents.report({ storage_unit_id: unit.id, title, description: desc })
        toast.success(`Incident ${i.incident_number} reported`)
        navigate(`/incidents/${i.id}`)
      }
      onClose()
    } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title={`Report equipment issue · ${unit.unit_code}`}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || title.length < 5 || desc.length < 5} onClick={submit}>Submit</button></>}>
      <div className="space-y-3">
        {can('maintenance.create') && can('incidents.investigate') && (
          <Segmented value={kind} onChange={setKind} options={[{ value: 'workorder', label: 'Maintenance request' }, { value: 'incident', label: 'Equipment incident' }]} />
        )}
        <Field label="Title" required hint="Minimum 5 characters"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Description" required><textarea className="input h-24 py-2" value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
        {kind === 'workorder' && (
          <Field label="Priority"><select className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
            {['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((p) => <option key={p}>{p}</option>)}</select></Field>
        )}
      </div>
    </Modal>
  )
}

export default function StorageUnitPage() {
  const { id = '' } = useParams()
  const can = useAuthStore((s) => s.can)
  const [hours, setHours] = useState<'6' | '24' | '168'>('24')
  const [reportOpen, setReportOpen] = useState(false)
  const now = useNow(5000)
  const live = useApi(() => Monitoring.live().then((us) => us.find((u) => u.id === id) || null), [id], { refreshOn: ['reading', 'sensor.status'], interval: 20000 })
  const readings = useApi(() => Monitoring.unitReadings(id, Number(hours)), [id, hours], { refreshOn: ['reading'] })
  const sensors = useApi(() => Devices.list({ storage_unit_id: id }), [id], { refreshOn: ['sensor.status'] })
  const incidents = useApi(() => Incidents.list({ storage_unit_id: id, page_size: 10 }), [id], { refreshOn: ['incident.created', 'incident.updated'] })
  const batches = useApi(() => Inventory.batches({ storage_unit_id: id, status: ['ACTIVE', 'QUARANTINED'], page_size: 50 }), [id], { enabled: can('inventory.view') })
  const u = live.data
  if (live.loading && !u) return <PageSkeleton />
  if (live.error) return <ErrorState message={live.error} onRetry={live.reload} />
  if (!u) return <ErrorState message="Storage unit not found or outside your scope" />

  return (
    <>
      <PageHeader title={`${u.unit_code} · ${u.name}`} subtitle={`${u.unit_type} at ${u.facility_name}${u.policy_name ? ` · Policy: ${u.policy_name}` : ''}`}
        crumbs={[{ label: 'Live monitoring', to: '/monitoring' }, { label: u.unit_code }]}
        meta={<><HealthBadge health={u.health} /><SimulatedTag show={u.is_simulated} /></>}
        actions={(can('maintenance.create') || can('incidents.investigate')) &&
          <button className="btn-secondary" onClick={() => setReportOpen(true)}><Wrench size={15} /> Report equipment issue</button>} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Current temperature" value={fmtTemp(u.latest_temperature)} tone={u.health === 'NORMAL' ? 'ok' : u.health === 'WARNING' ? 'warn' : 'crit'}
          sub={u.stale ? <span className="text-serious-ink font-medium">Stale — last reading {ago(u.last_reading_at, now)}</span> : `Updated ${ago(u.last_reading_at, now)}`} />
        <KpiCard label="Approved range" value={`${u.min_temperature} – ${u.max_temperature}°C`} sub={`Warning margin ±${u.warning_margin}°C`} />
        <KpiCard label={`${hours}h min / max`} value={readings.data?.stats ? `${readings.data.stats.min.toFixed(1)} / ${readings.data.stats.max.toFixed(1)}` : '—'}
          sub={readings.data ? `${readings.data.count} readings${readings.data.downsampled ? ' (chart downsampled)' : ''}` : ''} />
        <KpiCard label="Active incidents" value={u.active_incidents} tone={u.active_incidents ? 'crit' : 'ok'} icon={AlertTriangle} />
      </div>
      <Card className="mb-4">
        <CardHeader title="Temperature history" subtitle="Shaded green: approved range · amber: warning margin · red markers: out-of-range readings"
          actions={<Segmented value={hours} onChange={setHours} options={[{ value: '6', label: '6 h' }, { value: '24', label: '24 h' }, { value: '168', label: '7 d' }]} />} />
        {readings.error ? <ErrorState message={readings.error} onRetry={readings.reload} /> : !readings.data ? <LoadingBlock rows={5} /> :
          <TemperatureChart points={readings.data.points.map((p: { t: string; v: number; sim: boolean }) => ({ t: p.t, v: p.v, sim: p.sim }))}
            min={readings.data.min_limit} max={readings.data.max_limit} margin={readings.data.warning_margin} height={300} />}
      </Card>
      <div className="grid xl:grid-cols-2 gap-4">
        <Card pad={false}>
          <div className="card-pad pb-0"><CardHeader title="Sensors" subtitle="Connectivity, battery and calibration" /></div>
          <DataTable rows={sensors.data} loading={sensors.loading} error={sensors.error} columns={[
            { key: 'c', header: 'Sensor', render: (s) => <span className="mono">{s.sensor_code}</span> },
            { key: 's', header: 'Status', render: (s) => <StatusPill status={s.status} /> },
            { key: 'b', header: 'Battery', align: 'right', render: (s) => s.battery_level !== null ? `${Math.round(s.battery_level)}%` : '—' },
            { key: 'l', header: 'Last reading', render: (s) => ago(s.last_reading_at, now) },
            { key: 'cal', header: 'Calibration due', render: (s) => fmtDate(s.calibration_due_at) },
          ]} />
        </Card>
        <Card pad={false}>
          <div className="card-pad pb-0"><CardHeader title="Incident history" actions={<Link className="text-xs text-brand-700" to={`/incidents?unit=${u.id}`}>View all</Link>} /></div>
          <DataTable rows={incidents.data?.items} loading={incidents.loading} error={incidents.error} columns={[
            { key: 'n', header: 'Incident', render: (i) => <Link className="font-medium text-brand-700" to={`/incidents/${i.id}`}>{i.incident_number}</Link> },
            { key: 'sv', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
            { key: 'st', header: 'Status', render: (i) => <StatusPill status={i.status} /> },
            { key: 'd', header: 'Detected', render: (i) => fmtDateTime(i.created_at) },
          ]} />
        </Card>
        {can('inventory.view') && (
          <Card pad={false} className="xl:col-span-2">
            <div className="card-pad pb-0"><CardHeader title="Vaccine batches stored in this unit" /></div>
            <DataTable rows={batches.data?.items} loading={batches.loading} columns={[
              { key: 'b', header: 'Batch', render: (b) => <Link className="font-medium text-brand-700" to={`/inventory/batches/${b.id}`}>{b.batch_number}</Link> },
              { key: 'p', header: 'Product', render: (b) => b.product_name },
              { key: 's', header: 'Status', render: (b) => <StatusPill status={b.status} /> },
              { key: 'q', header: 'Quantity', align: 'right', render: (b) => b.current_quantity.toLocaleString() },
              { key: 'e', header: 'Expiry', render: (b) => fmtDate(b.expiry_date) },
            ]} />
          </Card>
        )}
      </div>
      <ReportIssueModal open={reportOpen} onClose={() => setReportOpen(false)} unit={{ id: u.id, unit_code: u.unit_code, facility_id: u.facility_id }} />
    </>
  )
}
