import { Gauge as GaugeIcon, Replace } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { DataTable } from '../../components/common/DataTable'
import { Field, FilterBar, Segmented } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SimulatedTag, StatusPill } from '../../components/common/Status'
import { useApi, useNow } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Analytics, Devices, Maintenance } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { ago, cx, fmtDate } from '../../utils/format'
import { RecordCalibrationModal } from '../maintenance/CalibrationPage'

function Battery({ v }: { v: number | null }) {
  if (v === null) return <span className="text-ink-3">n/a</span>
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-16 rounded-full bg-canvas overflow-hidden"><span className={cx('block h-full', v < 20 ? 'bg-crit' : v < 40 ? 'bg-warn' : 'bg-ok')} style={{ width: `${v}%` }} /></span>
      <span className={cx('tabular-nums text-xs', v < 20 && 'text-crit font-medium')}>{Math.round(v)}%</span>
    </span>
  )
}

export default function EquipmentHealthPage() {
  const can = useAuthStore((s) => s.can)
  const now = useNow(10000)
  const [filter, setFilter] = useState<'all' | 'attention'>('attention')
  const sensors = useApi(() => Devices.list(), [], { refreshOn: ['sensor.status'] })
  const rel = useApi(() => Analytics.deviceReliability(24), [])
  const [cal, setCal] = useState<string | null>(null)
  const [replace, setReplace] = useState<{ id: string; code: string } | null>(null)
  const relBy = Object.fromEntries((rel.data || []).map((r) => [r.sensor_id, r]))
  const soon = now + 30 * 86400000
  const needs = (s: { status: string; battery_level: number | null; calibration_due_at: string | null }) =>
    s.status !== 'ONLINE' || (s.battery_level ?? 100) < 20 || (s.calibration_due_at && new Date(s.calibration_due_at).getTime() < soon)
  const rows = (sensors.data || []).filter((s) => filter === 'all' || needs(s))
  return (
    <>
      <PageHeader title="Equipment health" subtitle="Sensor connectivity, battery, reporting availability and calibration status."
        crumbs={[{ label: 'Equipment' }, { label: 'Health' }]} />
      <FilterBar><Segmented value={filter} onChange={setFilter} options={[{ value: 'attention', label: 'Needs attention' }, { value: 'all', label: 'All sensors' }]} /></FilterBar>
      <div className="card p-0">
        <DataTable rows={rows} loading={sensors.loading} error={sensors.error} columns={[
          { key: 'c', header: 'Sensor', render: (s) => <div><span className="mono font-medium">{s.sensor_code}</span><div className="text-[11px] text-ink-3">{s.manufacturer || '—'} · fw {s.firmware_version || '—'}</div></div> },
          { key: 'st', header: 'Connectivity', render: (s) => <div className="flex items-center gap-1"><StatusPill status={s.status} /><SimulatedTag show={s.is_simulated} /></div> },
          { key: 'l', header: 'Last reading', render: (s) => <span className="text-xs">{ago(s.last_reading_at, now)}</span> },
          { key: 'a', header: 'Availability 24 h', align: 'right', render: (s) => relBy[s.id]?.availability !== undefined && relBy[s.id]?.availability !== null ? `${relBy[s.id].availability}%` : '—' },
          { key: 'b', header: 'Battery', render: (s) => <Battery v={s.battery_level} /> },
          { key: 'cal', header: 'Calibration due', render: (s) => <span className="flex items-center gap-1.5 text-xs">{fmtDate(s.calibration_due_at)}
            {s.calibration_due_at && new Date(s.calibration_due_at).getTime() < now ? <Pill tone="crit">Overdue</Pill> : s.calibration_due_at && new Date(s.calibration_due_at).getTime() < soon ? <Pill tone="warn">Due soon</Pill> : null}</span> },
          { key: 'x', header: '', render: (s) => <div className="flex gap-1 justify-end">
            {can('calibration.record') && <button className="btn-ghost btn-sm" onClick={() => setCal(s.id)}><GaugeIcon size={14} /> Calibrate</button>}
            {can('equipment.replace') && <button className="btn-ghost btn-sm" onClick={() => setReplace({ id: s.id, code: s.sensor_code })}><Replace size={14} /> Replace</button>}
          </div> },
        ]} />
      </div>
      {cal && <RecordCalibrationModal open onClose={() => setCal(null)} sensorId={cal} onDone={sensors.reload} />}
      {replace && <ReplaceSensorModal sensor={replace} onClose={() => setReplace(null)} onDone={sensors.reload} />}
    </>
  )
}

function ReplaceSensorModal({ sensor, onClose, onDone }: { sensor: { id: string; code: string }; onClose: () => void; onDone: () => void }) {
  const [code, setCode] = useState(`${sensor.code}-R`)
  const [serial, setSerial] = useState('')
  const [reason, setReason] = useState('')
  return (
    <Modal open onClose={onClose} title={`Replace sensor ${sensor.code}`} description="The old device is decommissioned (its telemetry is rejected from now on); the new device inherits the storage-unit association. History is preserved."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={code.length < 3 || reason.length < 3}
        onClick={async () => { try { await Maintenance.replaceSensor({ old_sensor_id: sensor.id, new_sensor_code: code, serial_number: serial || undefined, reason }); toast.success('Sensor replaced'); onDone(); onClose() } catch (e) { toast.error(errorMessage(e)) } }}>Replace</button></>}>
      <div className="space-y-3">
        <Field label="New sensor code" required><input className="input" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
        <Field label="Serial number"><input className="input" value={serial} onChange={(e) => setSerial(e.target.value)} /></Field>
        <Field label="Reason" required><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
