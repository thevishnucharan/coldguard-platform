import { Activity, Cpu, Database, Radio, Server, ShieldAlert, Thermometer, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BarList } from '../../components/charts/Mini'
import { FacilityMap, FacilityMapCard, type MapLayer } from '../../components/charts/FacilityMap'
import { LegendChips, StackedBars } from '../../components/charts/Trends'
import { Card, CardHeader, Delta, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { Segmented } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Dashboards } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { FacilitySummary } from '../../types'
import { ago, humanize } from '../../utils/format'
import { IncidentsPerDay } from '../supervisor/charts'

function Health({ label, value, icon: Icon }: { label: string; value: string; icon: React.ComponentType<{ size?: number }> }) {
  const ok = ['ok', 'connected'].includes(value)
  const off = value === 'disabled'
  return (
    <div className="flex items-center justify-between rounded-xl border border-line bg-surface-2/60 px-3 py-2.5">
      <span className="flex items-center gap-2.5 text-[13px] text-ink"><span className="grid place-items-center size-7 rounded-lg bg-surface text-ink-2 border border-line"><Icon size={14} /></span>{label}</span>
      <Pill tone={ok ? 'ok' : off ? 'neutral' : 'crit'}>{off ? 'Not configured' : ok ? 'Operational' : humanize(value)}</Pill>
    </div>
  )
}

export default function AdminOverview() {
  const me = useAuthStore((s) => s.me)
  const [sel, setSel] = useState<FacilitySummary | null>(null)
  const [layer, setLayer] = useState<MapLayer>('status')
  const q = useApi(() => Dashboards.admin(), [], { refreshOn: ['incident.created', 'sensor.status'], interval: 30000 })
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'No data'} onRetry={q.reload} />
  const d = q.data
  const k = d.kpis
  const s = d.system
  const dl = d.deltas
  const ingestion = (d.ingestion as { hour: string; device: number; simulated: number }[]).map((r) => ({ ...r, h: new Date(r.hour).getHours().toString().padStart(2, '0') + 'h' }))
  const first = (me?.name || '').replace(/^Dr\.\s*/, '').split(' ')[0]

  return (
    <>
      <PageHeader title="Global overview" subtitle={`Welcome back, ${first}. Platform-wide infrastructure, devices, users and incident load.`}
        crumbs={[{ label: 'Platform' }, { label: 'Overview' }]}
        meta={<><Pill tone={s.demo_mode ? 'info' : 'neutral'}>{s.environment}{s.demo_mode ? ' · demo mode' : ''}</Pill><Pill>v{s.version}</Pill></>}
        actions={<><Link to="/admin/facilities" className="btn-secondary">Facilities</Link><Link to="/admin/devices" className="btn-primary">Device registry</Link></>} />

      <div className="grid xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-4 mb-4">
        <div className="grid grid-cols-2 gap-4">
          <KpiCard label="Sensors online" value={`${k.sensors_online}/${k.sensors_total}`} icon={Cpu} tone={k.sensors_offline ? 'warn' : 'ok'} badge="Live"
            ratio={k.sensors_total ? k.sensors_online / k.sensors_total : 0} sub={`${k.sensors_offline} offline / error`} />
          <KpiCard label="Readings (24 h)" value={dl.readings_24h.toLocaleString()} icon={Thermometer} tone="info" badge="24 h"
            delta={<Delta value={dl.readings_change_pct} label="vs previous 24 h" />} />
          <KpiCard label="Platform incidents" value={k.active_incidents} icon={ShieldAlert} tone={k.critical_incidents ? 'crit' : k.active_incidents ? 'warn' : 'ok'} badge="7 d"
            delta={<Delta value={dl.incidents_change_pct} goodWhen="down" label={`${dl.incidents_7d} opened this week`} />} sub={`${k.critical_incidents} critical active`} />
          <KpiCard label="Users & facilities" value={k.users_active} icon={Users} tone="brand" badge="Platform"
            sub={`${k.users_total} accounts · ${k.facilities} facilities · ${k.storage_units} units`} />
        </div>
        <Card>
          <CardHeader title="Telemetry ingestion" subtitle={`Readings per hour · ${s.ingested_last_hour.toLocaleString()} in the last hour · ${s.quarantined_last_24h} quarantined (24 h)`}
            actions={<LegendChips items={[{ name: 'Device', color: 'var(--color-series-1)' }, { name: 'Simulated', color: 'color-mix(in srgb, var(--color-series-1) 45%, transparent)' }]} />} />
          <StackedBars data={ingestion} x="h" height={250}
            series={[{ key: 'device', name: 'Device telemetry', color: 'var(--color-series-1)' }, { key: 'simulated', name: 'Simulated', color: 'color-mix(in srgb, var(--color-series-1) 45%, transparent)' }]} />
        </Card>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4 mb-4">
        <Card>
          <CardHeader title="Facility network" subtitle="Registered facilities by district and current cold-chain status"
            actions={<Segmented value={layer} onChange={setLayer} options={[{ value: 'status', label: 'Status' }, { value: 'region', label: 'Regions' }]} />} />
          <FacilityMap facilities={d.facilities} height={460} selectedId={sel?.id} onSelect={setSel} layer={layer}>
            {sel && <FacilityMapCard facility={sel} onClose={() => setSel(null)} to={`/monitoring?facility=${sel.id}`} action="Open live monitoring"
              rows={[['Storage units', sel.storage_units], ['Sensors online', `${sel.sensors_online}/${sel.sensors_total}`], ['Active incidents', sel.active_incidents]]} />}
          </FacilityMap>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader title="System health" subtitle={`Worker heartbeat ${ago(s.worker_heartbeat)}`} />
            <div className="space-y-2">
              <Health label="API service" value={s.api} icon={Server} />
              <Health label="Database" value={s.database} icon={Database} />
              <Health label="Background worker" value={s.worker} icon={Activity} />
              <Health label="MQTT broker" value={s.mqtt} icon={Radio} />
              <Health label="Redis (real-time bus)" value={s.redis} icon={Server} />
            </div>
          </Card>
          <Card>
            <CardHeader title="Incidents per day" subtitle="Platform-wide, 14 days" />
            <IncidentsPerDay data={d.incidents_per_day} height={170} />
          </Card>
        </div>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-4">
        <Card>
          <CardHeader title="Least reliable devices" subtitle="Received vs expected readings, 24 h" actions={<Link to="/admin/devices" className="text-xs text-brand-700">Registry</Link>} />
          <BarList items={d.device_reliability.map((r: { sensor_code: string; availability: number | null; status: string }) => ({ label: `${r.sensor_code} · ${r.status.toLowerCase()}`, value: r.availability }))} max={100} unit="%" />
        </Card>
        <Card pad={false}>
          <div className="card-pad pb-0"><CardHeader title="Security & configuration events" actions={<Link to="/audit" className="btn-secondary btn-sm">Audit logs</Link>} /></div>
          <DataTable dense rows={d.recent_security_events} rowKey={(e) => e.timestamp + e.action} columns={[
            { key: 'a', header: 'Action', render: (e) => <span className="mono">{e.action}</span> },
            { key: 'u', header: 'Actor', render: (e) => e.actor },
            { key: 'o', header: 'Outcome', render: (e) => <StatusPill status={e.outcome} /> },
            { key: 't', header: 'When', render: (e) => <span className="text-xs">{ago(e.timestamp)}</span> },
          ]} />
        </Card>
      </div>
    </>
  )
}
