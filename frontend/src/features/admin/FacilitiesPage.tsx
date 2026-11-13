import { Plus } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { LoadingBlock } from '../../components/common/Feedback'
import { Field, FilterBar, SearchInput } from '../../components/common/Form'
import { ConfirmDialog, Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { HealthBadge, Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Org } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { FacilitySummary } from '../../types'
import { humanize } from '../../utils/format'

function FacilityForm({ open, onClose, initial, onDone }: { open: boolean; onClose: () => void; initial?: FacilitySummary | null; onDone: () => void }) {
  const regions = useApi(() => Org.regions(), [], { enabled: open })
  const [f, setF] = useState(() => ({ code: initial?.code || '', name: initial?.name || '', facility_type: initial?.facility_type || 'Primary Health Centre',
    region_id: initial?.region_id || '', address: initial?.address || '', latitude: initial?.latitude?.toString() || '', longitude: initial?.longitude?.toString() || '',
    contact_name: initial?.contact_name || '', contact_phone: initial?.contact_phone || '' }))
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }))
  const save = async () => {
    const body = { ...f, latitude: f.latitude ? Number(f.latitude) : null, longitude: f.longitude ? Number(f.longitude) : null }
    try {
      if (initial) { const { code: _c, ...rest } = body; void _c; await Org.updateFacility(initial.id, rest) } else await Org.createFacility(body)
      toast.success('Facility saved'); onDone(); onClose()
    } catch (e) { toast.error(errorMessage(e)) }
  }
  return (
    <Modal open={open} onClose={onClose} title={initial ? `Edit ${initial.name}` : 'Register facility'} size="lg"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={!f.code || !f.name || !f.region_id} onClick={save}>Save</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Code" required hint="Uppercase letters, digits, - or _"><input className="input" disabled={!!initial} value={f.code} onChange={(e) => set('code', e.target.value.toUpperCase())} /></Field>
        <Field label="Name" required><input className="input" value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="Type"><select className="input" value={f.facility_type} onChange={(e) => set('facility_type', e.target.value)}>
          {['District Vaccine Store', 'Community Health Centre', 'Primary Health Centre', 'Hospital', 'Regional Store'].map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Region" required><select className="input" value={f.region_id} onChange={(e) => set('region_id', e.target.value)}>
          <option value="">Select…</option>{(regions.data || []).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
        <Field label="Address" className="sm:col-span-2"><input className="input" value={f.address} onChange={(e) => set('address', e.target.value)} /></Field>
        <Field label="Latitude"><input type="number" step="0.0001" className="input" value={f.latitude} onChange={(e) => set('latitude', e.target.value)} /></Field>
        <Field label="Longitude"><input type="number" step="0.0001" className="input" value={f.longitude} onChange={(e) => set('longitude', e.target.value)} /></Field>
        <Field label="Contact person"><input className="input" value={f.contact_name} onChange={(e) => set('contact_name', e.target.value)} /></Field>
        <Field label="Contact phone"><input className="input" value={f.contact_phone} onChange={(e) => set('contact_phone', e.target.value)} /></Field>
      </div>
    </Modal>
  )
}

function FacilityDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useApi(() => Org.facility(id), [id])
  return (
    <Modal open onClose={onClose} title={q.data?.name || 'Facility'} description={q.data ? `${q.data.facility_type} · ${q.data.region_name}` : ''} size="lg">
      {!q.data ? <LoadingBlock /> : (
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <p className="label">Equipment</p>
            <ul className="divide-y divide-line border border-line rounded-lg">{q.data.equipment.map((u: { id: string; unit_code: string; unit_type: string; status: string; sensors: number }) => (
              <li key={u.id} className="flex justify-between px-3 py-2 text-xs"><span>{u.unit_code} · {u.unit_type}</span><span className="flex gap-1.5">{u.sensors} sensor(s) <StatusPill status={u.status} /></span></li>))}</ul>
          </div>
          <div>
            <p className="label">Assigned staff (facility & region)</p>
            <ul className="divide-y divide-line border border-line rounded-lg">{q.data.staff.map((u: { id: string; name: string; role: string; is_active: boolean }) => (
              <li key={u.id} className="flex justify-between px-3 py-2 text-xs"><span>{u.name}</span><Pill>{humanize(u.role)}</Pill></li>))}</ul>
            <p className="text-[11px] text-ink-3 mt-2">Assign operators, technicians and supervisors from Users & access.</p>
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function FacilitiesPage() {
  const can = useAuthStore((s) => s.can)
  const [search, setSearch] = useState('')
  const [edit, setEdit] = useState<FacilitySummary | null | undefined>(undefined)
  const [view, setView] = useState<string | null>(null)
  const [deact, setDeact] = useState<FacilitySummary | null>(null)
  const [regionOpen, setRegionOpen] = useState(false)
  const q = useApi(() => Org.facilities({ include_inactive: true }), [])
  const regions = useApi(() => Org.regions(), [])
  const rows = (q.data || []).filter((f) => !search || `${f.code} ${f.name} ${f.region_name}`.toLowerCase().includes(search.toLowerCase()))
  return (
    <>
      <PageHeader title="Facilities" subtitle="Registered facilities, regions and their equipment." crumbs={[{ label: 'Platform', to: '/admin' }, { label: 'Facilities' }]}
        actions={<>
          {can('regions.manage') && <button className="btn-secondary" onClick={() => setRegionOpen(true)}><Plus size={15} /> Region</button>}
          {can('facilities.create') && <button className="btn-primary" onClick={() => setEdit(null)}><Plus size={15} /> Register facility</button>}</>} />
      <FilterBar><SearchInput value={search} onChange={setSearch} placeholder="Search facilities" className="w-72" /></FilterBar>
      <div className="card p-0">
        <DataTable<FacilitySummary> rows={rows} loading={q.loading} error={q.error} onRowClick={(f) => setView(f.id)} columns={[
          { key: 'c', header: 'Code', render: (f) => <span className="mono font-medium">{f.code}</span> },
          { key: 'n', header: 'Facility', render: (f) => <div><div className="font-medium">{f.name}</div><div className="text-xs text-ink-3">{f.facility_type}</div></div> },
          { key: 'r', header: 'Region', render: (f) => f.region_name },
          { key: 'h', header: 'Health', render: (f) => f.is_active ? <HealthBadge health={f.health} /> : <Pill>Deactivated</Pill> },
          { key: 'u', header: 'Units', align: 'right', render: (f) => f.storage_units },
          { key: 's', header: 'Sensors online', align: 'right', render: (f) => `${f.sensors_online}/${f.sensors_total}` },
          { key: 'i', header: 'Incidents', align: 'right', render: (f) => f.active_incidents || '—' },
          { key: 'x', header: '', render: (f) => can('facilities.update') && <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <button className="btn-ghost btn-sm" onClick={() => setEdit(f)}>Edit</button>
            {f.is_active ? <button className="btn-ghost btn-sm text-crit" onClick={() => setDeact(f)}>Deactivate</button>
              : <button className="btn-ghost btn-sm" onClick={async () => { await Org.updateFacility(f.id, { is_active: true }); q.reload() }}>Reactivate</button>}
          </div> },
        ]} />
      </div>
      <Card className="mt-4"><CardHeader title="Regions" />
        <div className="flex flex-wrap gap-2">{(regions.data || []).map((r) => <Pill key={r.id}>{r.code} · {r.name}</Pill>)}</div></Card>
      {edit !== undefined && <FacilityForm open onClose={() => setEdit(undefined)} initial={edit} onDone={q.reload} />}
      {view && <FacilityDrawer id={view} onClose={() => setView(null)} />}
      <ConfirmDialog open={!!deact} onClose={() => setDeact(null)} danger title={`Deactivate ${deact?.name}`}
        description="Historical data is retained. Users keep their assignments but the facility is hidden from operational views."
        typeToConfirm={deact?.code} confirmLabel="Deactivate"
        onConfirm={async () => { try { await Org.updateFacility(deact!.id, { is_active: false }); toast.success('Facility deactivated'); q.reload() } catch (e) { toast.error(errorMessage(e)) } }} />
      <RegionModal open={regionOpen} onClose={() => setRegionOpen(false)} onDone={regions.reload} />
    </>
  )
}

function RegionModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  return (
    <Modal open={open} onClose={onClose} title="Create region" size="sm"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={code.length < 2 || name.length < 2}
        onClick={async () => { try { await Org.createRegion({ code, name }); toast.success('Region created'); onDone(); onClose() } catch (e) { toast.error(errorMessage(e)) } }}>Create</button></>}>
      <div className="space-y-3">
        <Field label="Code" required><input className="input" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} /></Field>
        <Field label="Name" required><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
