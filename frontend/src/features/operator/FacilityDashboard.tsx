import { AlertTriangle, Boxes, CheckCircle2, ClipboardList, ShieldAlert, Thermometer, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BarList, Sparkline } from '../../components/charts/Mini'
import { FacilityMap } from '../../components/charts/FacilityMap'
import { TemperatureChart } from '../../components/charts/TemperatureChart'
import { Card, CardHeader, Delta, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, ErrorState, LoadingBlock, PageSkeleton } from '../../components/common/Feedback'
import { Select } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { HealthBadge, healthColor, SeverityBadge, SimulatedTag, StatusPill } from '../../components/common/Status'
import { useApi, useNow, useRealtimeEvent } from '../../hooks/useApi'
import { Dashboards, Monitoring, Org } from '../../services/api/endpoints'
import type { LiveUnit } from '../../types'
import { ago, cx, fmtTemp, humanize } from '../../utils/format'

function UnitPanel({ unit, onClose, now }: { unit: LiveUnit; onClose: () => void; now: number }) {
  const r = useApi(() => Monitoring.unitReadings(unit.id, 6), [unit.id], { refreshOn: ['reading'] })
  return (
    <div className="card p-4 h-full flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[15px] font-semibold">{unit.unit_code}</div>
          <div className="mt-1 flex gap-1.5"><HealthBadge health={unit.health} /><SimulatedTag show={unit.is_simulated} /></div>
        </div>
        <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close panel"><X size={15} /></button>
      </div>
      <dl className="mt-3 grid grid-cols-[110px_1fr] gap-y-1.5 text-[12.5px]">
        <dt className="text-ink-3">Equipment</dt><dd>{unit.name} · {unit.unit_type}</dd>
        <dt className="text-ink-3">Current</dt><dd className={cx('font-semibold', unit.stale && 'text-ink-3')}>{fmtTemp(unit.latest_temperature)}{unit.stale && ' (stale)'}</dd>
        <dt className="text-ink-3">Last reading</dt><dd>{ago(unit.last_reading_at, now)}</dd>
        <dt className="text-ink-3">Approved</dt><dd>{unit.min_temperature} – {unit.max_temperature}°C</dd>
        <dt className="text-ink-3">Sensors</dt><dd>{unit.sensors.map((s) => `${s.sensor_code} (${s.battery_level !== null ? Math.round(s.battery_level) + '%' : 'n/a'})`).join(', ')}</dd>
      </dl>
      <p className="text-xs font-medium text-ink-2 mt-4 mb-1">Temperature — last 6 h</p>
      {r.data ? <TemperatureChart height={190} points={r.data.points} min={r.data.min_limit} max={r.data.max_limit} margin={r.data.warning_margin} /> : <LoadingBlock rows={3} />}
      <div className="mt-auto pt-3 flex gap-2">
        <Link to={`/monitoring/units/${unit.id}`} className="btn-secondary btn-sm flex-1">Open unit</Link>
        {unit.active_incidents > 0 && <Link to={`/incidents?unit=${unit.id}`} className="btn-primary btn-sm flex-1">{unit.active_incidents} incident(s)</Link>}
      </div>
    </div>
  )
}

export default function FacilityDashboard() {
  const [facility, setFacility] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const now = useNow(5000)
  const navigate = useNavigate()
  const facs = useApi(() => Org.facilities(), [], { refreshOn: ['incident.created', 'incident.updated', 'sensor.status'], interval: 30000 })
  const q = useApi(() => Dashboards.operator(facility || undefined), [facility],
    { refreshOn: ['incident.created', 'incident.updated', 'sensor.status', 'maintenance.updated'], interval: 20000 })
  useRealtimeEvent('reading', (e) => {
    const d = e.data as { storage_unit_id: string; temperature: number; timestamp: string }
    q.setData((s: Record<string, unknown> | null) => s && ({ ...s, units: (s.units as LiveUnit[]).map((u) => u.id !== d.storage_unit_id ? u : {
      ...u, latest_temperature: d.temperature, last_reading_at: d.timestamp, stale: false, sparkline: [...u.sparkline.slice(-59), { t: d.timestamp, v: d.temperature }] }) }))
  })
  useEffect(() => { if (!facility && q.data?.facilities?.length === 1) setFacility(q.data.facilities[0].id) }, [q.data, facility])
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'No data'} onRetry={q.reload} />
  const d = q.data
  const units: LiveUnit[] = d.units
  const sel = units.find((u) => u.id === selected) || null
  const counts = d.unit_counts
  const facName = d.facilities.find((f: { id: string }) => f.id === facility)?.name

  return (
    <>
      <PageHeader title={facName || 'Facility dashboard'} subtitle="Cold-chain status of your assigned facilities. Select a unit to inspect it."
        crumbs={[{ label: 'Facility dashboard' }]}
        meta={<HealthBadge health={d.facility_health} />}
        actions={d.facilities.length > 1 && <Select ariaLabel="Facility" value={facility} onChange={setFacility} placeholder="All my facilities" className="w-64"
          options={d.facilities.map((f: { id: string; name: string }) => ({ value: f.id, label: f.name }))} />} />
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
        <KpiCard label="Storage units" value={counts.total} icon={Thermometer} tone="brand" badge="Live" ratio={counts.total ? (counts.NORMAL || 0) / counts.total : 0} sub={`${counts.NORMAL || 0} normal · compliance ${d.deltas.compliance_7d ?? '—'}%`} />
        <KpiCard label="Warning" value={(counts.WARNING || 0) + (counts.MISSING_TELEMETRY || 0)} icon={AlertTriangle} tone={(counts.WARNING || counts.MISSING_TELEMETRY) ? 'warn' : 'ok'} sub="Near limit or data gap" />
        <KpiCard label="Critical / offline" value={(counts.CRITICAL || 0) + (counts.OFFLINE || 0)} icon={ShieldAlert} tone={(counts.CRITICAL || counts.OFFLINE) ? 'crit' : 'ok'} />
        <KpiCard label="Pending actions" value={d.pending_actions.length} icon={ClipboardList} tone={d.pending_actions.length ? 'warn' : 'ok'} ratio={Math.min(1, d.pending_actions.length / 10)} delta={<Delta value={d.deltas.incidents_change_pct} goodWhen="down" label={`${d.deltas.incidents_7d} incidents this week`} />} />
        <KpiCard label="Usable doses" value={d.stock.doses_available.toLocaleString()} icon={Boxes} sub={`${d.stock.expiring_30d} batch(es) expire ≤30 d`} onClick={() => navigate('/inventory')} />
      </div>

      <Card className="mb-4">
        <CardHeader title="Facility map" subtitle="Your facilities and their current cold-chain status. Select a facility to focus the dashboard."
          actions={facility && <button className="btn-secondary btn-sm" onClick={() => setFacility('')}>Show all facilities</button>} />
        <FacilityMap facilities={facs.data || []} selectedId={facility || null} onSelect={(f) => { setFacility(f.id); setSelected(null) }} height={340} layer="status" />
      </Card>

      <div className={cx('grid gap-4 mb-4', sel ? 'xl:grid-cols-[1fr_380px]' : '')}>
        <Card>
          <CardHeader title="Storage units" subtitle="Tile colour = status (with label). Dashed trend = stale data." />
          {!units.length ? <EmptyState title="No storage units in scope" /> : (
            <div className="grid sm:grid-cols-2 2xl:grid-cols-3 gap-3">
              {units.map((u) => (
                <button key={u.id} onClick={() => setSelected(u.id)}
                  className={cx('rounded-xl border p-3 text-left transition-colors hover:border-brand-200 border-l-4', selected === u.id ? 'border-brand-500 bg-brand-50/50' : 'border-line bg-surface')}
                  style={{ borderLeftColor: healthColor(u.health) }}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-semibold truncate">{u.unit_code}</span><HealthBadge health={u.health} />
                  </div>
                  <div className="flex items-end justify-between mt-2">
                    <span className={cx('text-2xl font-semibold tabular-nums', u.stale && 'text-ink-3')}>{fmtTemp(u.latest_temperature)}</span>
                    <Sparkline points={u.sparkline} min={u.min_temperature} max={u.max_temperature} stale={u.stale} width={110} height={30} />
                  </div>
                  <div className="text-[11px] text-ink-3 mt-1">{u.facility_name} · {ago(u.last_reading_at, now)}</div>
                </button>
              ))}
            </div>
          )}
        </Card>
        {sel && <UnitPanel unit={sel} onClose={() => setSelected(null)} now={now} />}
      </div>

      <div className="grid xl:grid-cols-3 gap-4">
        <Card pad={false} className="xl:col-span-2">
          <div className="card-pad pb-0"><CardHeader title="Active incidents" actions={<Link to="/incidents" className="text-xs text-brand-700">All incidents</Link>} /></div>
          <DataTable rows={d.active_incidents} empty={<EmptyState icon={CheckCircle2} title="No active incidents" />} onRowClick={(i) => navigate(`/incidents/${i.id}`)} columns={[
            { key: 'n', header: 'Incident', render: (i) => <span className="font-medium text-brand-700">{i.incident_number}</span> },
            { key: 's', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
            { key: 'st', header: 'Status', render: (i) => <StatusPill status={i.status} /> },
            { key: 't', header: 'Detail', render: (i) => <span className="text-xs">{humanize(i.incident_type)} · {i.unit_code}</span> },
            { key: 'a', header: 'Detected', render: (i) => <span className="text-xs">{ago(i.created_at, now)}</span> },
          ]} />
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader title="Pending actions" subtitle="What needs you now" />
            {!d.pending_actions.length ? <EmptyState icon={CheckCircle2} title="Nothing pending" /> : (
              <ul className="divide-y divide-line -my-2">
                {d.pending_actions.slice(0, 8).map((p: { kind: string; title: string; detail: string; link: string; severity: string }, i: number) => (
                  <li key={i}><Link to={p.link} className="flex items-start gap-2 py-2.5 hover:bg-canvas -mx-2 px-2 rounded-lg">
                    <span className={cx('mt-1.5 size-2 rounded-full shrink-0', p.severity === 'CRITICAL' ? 'bg-crit' : p.severity === 'INFO' ? 'bg-series-1' : 'bg-warn')} />
                    <span className="min-w-0"><span className="block text-[13px] font-medium">{p.title}</span><span className="block text-xs text-ink-3 truncate">{p.detail}</span></span>
                  </Link></li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Stock by product" subtitle="Usable doses (ACTIVE batches)" actions={<Link to="/inventory" className="text-xs text-brand-700">Inventory</Link>} />
            {d.stock.by_product.length ? <BarList items={d.stock.by_product.slice(0, 6).map((p: { product: string; doses: number }) => ({ label: p.product, value: p.doses }))} format={(v) => v.toLocaleString()} />
              : <EmptyState title="No stock" />}
          </Card>
        </div>
      </div>
    </>
  )
}
