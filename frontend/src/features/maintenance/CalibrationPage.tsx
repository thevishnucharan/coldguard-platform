import { Plus } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { DataTable } from '../../components/common/DataTable'
import { Field, FilterBar, Select } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Devices, Maintenance } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { fmtDate, fmtTemp } from '../../utils/format'

export function RecordCalibrationModal({ open, onClose, onDone, sensorId }: { open: boolean; onClose: () => void; onDone?: () => void; sensorId?: string }) {
  const sensors = useApi(() => Devices.list(), [], { enabled: open })
  const [f, setF] = useState({ sensor_id: sensorId || '', calibrated_at: new Date().toISOString().slice(0, 10), result: 'PASS', reference_temperature: '5.0',
    measured_temperature: '', offset_applied: '0', certificate_reference: '', interval_days: '365', notes: '' })
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }))
  const submit = async () => {
    try {
      await Maintenance.recordCalibration({ ...f, calibrated_at: new Date(f.calibrated_at).toISOString(),
        reference_temperature: f.reference_temperature ? Number(f.reference_temperature) : undefined,
        measured_temperature: f.measured_temperature ? Number(f.measured_temperature) : undefined,
        offset_applied: Number(f.offset_applied || 0), interval_days: Number(f.interval_days), notes: f.notes || undefined,
        certificate_reference: f.certificate_reference || undefined })
      toast.success('Calibration recorded'); onDone?.(); onClose()
    } catch (e) { toast.error(errorMessage(e)) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Record sensor calibration" size="lg" description="An ADJUSTED result applies the offset to all future readings from this sensor."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={!f.sensor_id} onClick={submit}>Save record</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Sensor" required><select className="input" value={f.sensor_id} onChange={(e) => set('sensor_id', e.target.value)}>
          <option value="">Select…</option>{(sensors.data || []).map((s) => <option key={s.id} value={s.id}>{s.sensor_code}</option>)}</select></Field>
        <Field label="Calibration date" required><input type="date" className="input" value={f.calibrated_at} onChange={(e) => set('calibrated_at', e.target.value)} /></Field>
        <Field label="Result" required><select className="input" value={f.result} onChange={(e) => set('result', e.target.value)}>{['PASS', 'ADJUSTED', 'FAIL'].map((r) => <option key={r}>{r}</option>)}</select></Field>
        <Field label="Interval (days)" hint="Next due date = calibration date + interval"><input type="number" className="input" value={f.interval_days} onChange={(e) => set('interval_days', e.target.value)} /></Field>
        <Field label="Reference °C"><input type="number" step="0.01" className="input" value={f.reference_temperature} onChange={(e) => set('reference_temperature', e.target.value)} /></Field>
        <Field label="Measured °C"><input type="number" step="0.01" className="input" value={f.measured_temperature} onChange={(e) => set('measured_temperature', e.target.value)} /></Field>
        <Field label="Offset applied (°C)" hint="Required for ADJUSTED"><input type="number" step="0.01" className="input" value={f.offset_applied} onChange={(e) => set('offset_applied', e.target.value)} /></Field>
        <Field label="Certificate reference"><input className="input" value={f.certificate_reference} onChange={(e) => set('certificate_reference', e.target.value)} /></Field>
        <Field label="Notes" className="sm:col-span-2"><textarea className="input h-20 py-2" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></Field>
      </div>
    </Modal>
  )
}

export default function CalibrationPage() {
  const can = useAuthStore((s) => s.can)
  const [result, setResult] = useState('')
  const [open, setOpen] = useState(false)
  const q = useApi(() => Maintenance.calibrations({ limit: 500 }), [])
  const rows = (q.data || []).filter((r) => !result || r.result === result)
  const now = Date.now()
  return (
    <>
      <PageHeader title="Sensor calibration" subtitle="Calibration history, results, due dates and certificate references."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Calibration' }]}
        actions={can('calibration.record') && <button className="btn-primary" onClick={() => setOpen(true)}><Plus size={15} /> Record calibration</button>} />
      <FilterBar><Select ariaLabel="Result" value={result} onChange={setResult} placeholder="All results" className="w-40" options={['PASS', 'ADJUSTED', 'FAIL'].map((r) => ({ value: r, label: r }))} /></FilterBar>
      <div className="card p-0">
        <DataTable rows={rows} loading={q.loading} error={q.error} columns={[
          { key: 's', header: 'Sensor', render: (r) => <span className="mono">{r.sensor_code}</span> },
          { key: 'c', header: 'Calibrated', render: (r) => fmtDate(r.calibrated_at) },
          { key: 'r', header: 'Result', render: (r) => <StatusPill status={r.result} /> },
          { key: 'm', header: 'Reference / measured', render: (r) => `${fmtTemp(r.reference_temperature, 2)} / ${fmtTemp(r.measured_temperature, 2)}` },
          { key: 'o', header: 'Offset', align: 'right', render: (r) => r.offset_applied ? `${r.offset_applied > 0 ? '+' : ''}${r.offset_applied}°C` : '—' },
          { key: 'd', header: 'Next due', render: (r) => <span className="flex items-center gap-1.5">{fmtDate(r.due_date)}
            {new Date(r.due_date).getTime() < now && <Pill tone="crit">Overdue</Pill>}</span> },
          { key: 'cert', header: 'Certificate', render: (r) => <span className="text-xs">{r.certificate_reference || '—'}</span> },
          { key: 'b', header: 'Performed by', render: (r) => <span className="text-xs">{r.performed_by_name}</span> },
        ]} />
      </div>
      <RecordCalibrationModal open={open} onClose={() => setOpen(false)} onDone={q.reload} />
    </>
  )
}
