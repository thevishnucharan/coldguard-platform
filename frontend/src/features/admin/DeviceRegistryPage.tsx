import { KeyRound, Plus } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { DataTable, Pagination } from '../../components/common/DataTable'
import { Field, FilterBar, SearchInput, Select, Tabs } from '../../components/common/Form'
import { ConfirmDialog, Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SimulatedTag, StatusPill } from '../../components/common/Status'
import { useApi, useNow } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Devices, Monitoring } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { ago, fmtDate, fmtDateTime, humanize } from '../../utils/format'

function KeyReveal({ title, deviceKey, onClose }: { title: string; deviceKey: string; onClose: () => void }) {
  return (
    <Modal open onClose={onClose} title={title} size="sm" footer={<button className="btn-primary" onClick={onClose}>I have stored the key</button>}>
      <p className="text-xs text-ink-2 mb-2">This device key is shown <b>once</b> and only its hash is stored. Configure it on the device / gateway now.</p>
      <pre className="mono bg-canvas rounded-lg p-3 break-all whitespace-pre-wrap select-all">{deviceKey}</pre>
    </Modal>
  )
}

function Provision({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (key: string) => void }) {
  const units = useApi(() => Monitoring.units({ status: 'ACTIVE' }), [], { enabled: open })
  const [f, setF] = useState({ sensor_code: '', storage_unit_id: '', sensor_type: 'Temperature', serial_number: '', manufacturer: '', firmware_version: '', is_simulated: false })
  return (
    <Modal open={open} onClose={onClose} title="Register IoT device" size="lg"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={f.sensor_code.length < 3 || !f.storage_unit_id}
        onClick={async () => { try { const r = await Devices.provision(f); onDone(r.device_key); onClose() } catch (e) { toast.error(errorMessage(e)) } }}>Provision</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Sensor code" required hint="Also the MQTT topic suffix: coldguard/telemetry/<facility>/<code>"><input className="input mono" value={f.sensor_code} onChange={(e) => setF({ ...f, sensor_code: e.target.value })} /></Field>
        <Field label="Storage unit" required><select className="input" value={f.storage_unit_id} onChange={(e) => setF({ ...f, storage_unit_id: e.target.value })}>
          <option value="">Select…</option>{(units.data || []).map((u) => <option key={u.id} value={u.id}>{u.unit_code} — {u.name}</option>)}</select></Field>
        <Field label="Serial number"><input className="input" value={f.serial_number} onChange={(e) => setF({ ...f, serial_number: e.target.value })} /></Field>
        <Field label="Manufacturer"><input className="input" value={f.manufacturer} onChange={(e) => setF({ ...f, manufacturer: e.target.value })} /></Field>
        <Field label="Firmware"><input className="input" value={f.firmware_version} onChange={(e) => setF({ ...f, firmware_version: e.target.value })} /></Field>
        <Field label="Simulation"><label className="flex items-center gap-2 h-9 text-[13px]"><input type="checkbox" checked={f.is_simulated} onChange={(e) => setF({ ...f, is_simulated: e.target.checked })} />Simulated device (demo only)</label></Field>
      </div>
    </Modal>
  )
}

export default function DeviceRegistryPage() {
  const can = useAuthStore((s) => s.can)
  const now = useNow(10000)
  const [tab, setTab] = useState<'devices' | 'quarantine'>('devices')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [prov, setProv] = useState(false)
  const [key, setKey] = useState<{ title: string; key: string } | null>(null)
  const [decom, setDecom] = useState<{ id: string; code: string } | null>(null)
  const [hist, setHist] = useState<{ id: string; code: string } | null>(null)
  const [qPage, setQPage] = useState(1)
  const q = useApi(() => Devices.list({ status: status || undefined, include_decommissioned: status === 'DECOMMISSIONED' }), [status], { refreshOn: ['sensor.status'] })
  const quarantine = useApi(() => Monitoring.quarantine({ page: qPage, page_size: 30 }), [qPage, tab], { enabled: tab === 'quarantine' })
  const history = useApi(() => hist ? Devices.history(hist.id) : Promise.resolve([]), [hist?.id], { enabled: !!hist })
  const rows = (q.data || []).filter((s) => !search || s.sensor_code.toLowerCase().includes(search.toLowerCase()))
  return (
    <>
      <PageHeader title="Device registry" subtitle="IoT sensors: provisioning, assignment, connectivity and retirement." crumbs={[{ label: 'Platform', to: '/admin' }, { label: 'Devices' }]}
        actions={can('devices.register') && <button className="btn-primary" onClick={() => setProv(true)}><Plus size={15} /> Register device</button>} />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'devices', label: 'Devices', count: q.data?.length }, { value: 'quarantine', label: 'Rejected telemetry' }]} />
      {tab === 'devices' ? (<>
        <FilterBar>
          <Select ariaLabel="Status" value={status} onChange={setStatus} placeholder="All active statuses" className="w-52"
            options={['ONLINE', 'OFFLINE', 'PROVISIONED', 'ERROR', 'CALIBRATING', 'DECOMMISSIONED'].map((s) => ({ value: s, label: humanize(s) }))} />
          <SearchInput value={search} onChange={setSearch} placeholder="Sensor code" className="w-56" />
        </FilterBar>
        <div className="card p-0">
          <DataTable rows={rows} loading={q.loading} error={q.error} columns={[
            { key: 'c', header: 'Sensor', render: (s) => <div><span className="mono font-medium">{s.sensor_code}</span><div className="text-[11px] text-ink-3">{s.serial_number || 'no serial'} · fw {s.firmware_version || '—'}</div></div> },
            { key: 's', header: 'Status', render: (s) => <div className="flex gap-1"><StatusPill status={s.status} /><SimulatedTag show={s.is_simulated} /></div> },
            { key: 'l', header: 'Last reading', render: (s) => <span className="text-xs">{ago(s.last_reading_at, now)}</span> },
            { key: 'b', header: 'Battery', align: 'right', render: (s) => s.battery_level !== null ? <span className={s.battery_level < 20 ? 'text-crit font-medium' : ''}>{Math.round(s.battery_level)}%</span> : '—' },
            { key: 'cal', header: 'Calibration due', render: (s) => <span className="text-xs">{fmtDate(s.calibration_due_at)}</span> },
            { key: 'p', header: 'Provisioned', render: (s) => <span className="text-xs">{fmtDate(s.provisioned_at || s.created_at)}</span> },
            { key: 'x', header: '', render: (s) => <div className="flex justify-end gap-1">
              <button className="btn-ghost btn-sm" onClick={() => setHist({ id: s.id, code: s.sensor_code })}>History</button>
              {can('devices.register') && s.status !== 'DECOMMISSIONED' && <>
                <button className="btn-ghost btn-sm" onClick={async () => { try { const r = await Devices.rotateKey(s.id); setKey({ title: `New key for ${s.sensor_code}`, key: r.device_key }) } catch (e) { toast.error(errorMessage(e)) } }}><KeyRound size={13} /> Rotate key</button>
                <button className="btn-ghost btn-sm text-crit" onClick={() => setDecom({ id: s.id, code: s.sensor_code })}>Decommission</button></>}
            </div> },
          ]} />
        </div>
      </>) : (
        <div className="card p-0">
          <p className="text-xs text-ink-3 px-4 pt-3">Malformed, unknown-device or failed-validation telemetry is stored here instead of being silently dropped.</p>
          <DataTable rows={quarantine.data?.items} loading={quarantine.loading} error={quarantine.error} columns={[
            { key: 't', header: 'Received', render: (r) => <span className="text-xs">{fmtDateTime(r.received_at)}</span> },
            { key: 'ch', header: 'Channel', render: (r) => <Pill>{r.channel}</Pill> },
            { key: 's', header: 'Sensor', render: (r) => <span className="mono">{r.sensor_code || '—'}</span> },
            { key: 'r', header: 'Reason', render: (r) => <span className="text-xs">{r.reason}</span> },
            { key: 'p', header: 'Payload', render: (r) => <span className="mono text-[11px] text-ink-3 line-clamp-1 max-w-80">{r.raw_payload}</span> },
            { key: 'sim', header: '', render: (r) => <SimulatedTag show={r.is_simulated} /> },
          ]} />
          <div className="px-4 pb-3"><Pagination page={qPage} pageSize={30} total={quarantine.data?.total || 0} onPage={setQPage} /></div>
        </div>
      )}
      <Provision open={prov} onClose={() => setProv(false)} onDone={(k) => { q.reload(); setKey({ title: 'Device provisioned', key: k }) }} />
      {key && <KeyReveal title={key.title} deviceKey={key.key} onClose={() => setKey(null)} />}
      <ConfirmDialog open={!!decom} onClose={() => setDecom(null)} danger title={`Decommission ${decom?.code}`}
        description="Use for retired or compromised devices. All further telemetry from this device is rejected; history is retained."
        reasonLabel="Reason" reasonRequired minReason={3} confirmLabel="Decommission"
        onConfirm={async (r) => { try { await Devices.decommission(decom!.id, r); toast.success('Device decommissioned'); q.reload() } catch (e) { toast.error(errorMessage(e)) } }} />
      <Modal open={!!hist} onClose={() => setHist(null)} title={`Device history · ${hist?.code}`} size="lg">
        <DataTable dense rows={history.data} loading={history.loading} columns={[
          { key: 't', header: 'When', render: (e) => <span className="text-xs">{fmtDateTime(e.created_at)}</span> },
          { key: 'e', header: 'Event', render: (e) => <span className="mono">{e.event_type}</span> },
          { key: 'd', header: 'Details', render: (e) => <span className="text-xs">{JSON.stringify(e.details)}</span> },
          { key: 'a', header: 'By', render: (e) => <span className="text-xs">{e.actor_name}</span> },
        ]} />
      </Modal>
    </>
  )
}
