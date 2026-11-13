import { BatteryLow, Clock, LayoutGrid, Rows3, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Sparkline } from '../../components/charts/Mini'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, ErrorState, LoadingBlock } from '../../components/common/Feedback'
import { FilterBar, SearchInput, Segmented, Select } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { HealthBadge, healthColor, SimulatedTag } from '../../components/common/Status'
import { useApi, useNow, useRealtimeEvent } from '../../hooks/useApi'
import { Monitoring, Org } from '../../services/api/endpoints'
import type { LiveUnit } from '../../types'
import { ago, cx, fmtTemp } from '../../utils/format'

export function useLiveUnits(facilityId?: string) {
  const q = useApi(() => Monitoring.live(facilityId || undefined), [facilityId],
    { refreshOn: ['sensor.status', 'incident.created', 'incident.updated'], interval: 20000 })
  // Patch readings in place as they stream in; health is re-derived server-side on the next refresh.
  useRealtimeEvent('reading', (e) => {
    const d = e.data as { storage_unit_id: string; temperature: number; timestamp: string }
    q.setData((units) => units?.map((u) => u.id !== d.storage_unit_id ? u : {
      ...u, latest_temperature: d.temperature, last_reading_at: d.timestamp, seconds_since_reading: 0, stale: false,
      sparkline: [...u.sparkline.slice(-59), { t: d.timestamp, v: d.temperature }],
    }) ?? null)
  })
  return q
}

export function UnitCard({ u, now, onClick, selected }: { u: LiveUnit; now: number; onClick?: () => void; selected?: boolean }) {
  const secs = u.last_reading_at ? (now - new Date(u.last_reading_at).getTime()) / 1000 : null
  const out = u.latest_temperature !== null && (u.latest_temperature > u.max_temperature || u.latest_temperature < u.min_temperature)
  const lowBattery = u.sensors.some((s) => (s.battery_level ?? 100) < 20)
  return (
    <button onClick={onClick} className={cx('card text-left p-4 w-full hover:border-brand-200 transition-colors border-l-4', selected && 'ring-2 ring-brand-200')}
      style={{ borderLeftColor: healthColor(u.health) }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13px] font-semibold truncate">{u.unit_code}</div>
          <div className="text-xs text-ink-3 truncate">{u.name} · {u.facility_name}</div>
        </div>
        <HealthBadge health={u.health} />
      </div>
      <div className="flex items-end justify-between mt-3">
        <div>
          <div className={cx('text-[26px] font-semibold tabular-nums leading-none', u.stale ? 'text-ink-3' : out ? 'text-crit' : 'text-ink')}>
            {fmtTemp(u.latest_temperature)}
          </div>
          <div className="text-[11px] text-ink-3 mt-1">Range {u.min_temperature}–{u.max_temperature}°C</div>
        </div>
        <Sparkline points={u.sparkline} min={u.min_temperature} max={u.max_temperature} stale={u.stale} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 pt-3 border-t border-line text-[11.5px]">
        <span className={cx('flex items-center gap-1', u.stale ? 'text-serious-ink font-medium' : 'text-ink-3')}>
          <Clock size={12} /> {u.stale ? 'Stale · last ' : ''}{ago(u.last_reading_at, now)}{secs !== null && secs < 0 ? '' : ''}
        </span>
        {u.active_incidents > 0 && <span className="flex items-center gap-1 text-crit font-medium"><ShieldAlert size={12} />{u.active_incidents} incident{u.active_incidents > 1 ? 's' : ''}</span>}
        {lowBattery && <span className="flex items-center gap-1 text-warn-ink"><BatteryLow size={12} /> Low battery</span>}
        <SimulatedTag show={u.is_simulated} />
      </div>
    </button>
  )
}

export default function LiveMonitoringPage() {
  const [params, setParams] = useSearchParams()
  const facility = params.get('facility') || ''
  const [health, setHealth] = useState<'all' | 'attention' | 'normal'>('all')
  const [search, setSearch] = useState('')
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const facilities = useApi(() => Org.facilities(), [])
  const { data, error, loading, reload } = useLiveUnits(facility)
  const now = useNow(5000)
  const navigate = useNavigate()
  const rows = useMemo(() => (data || []).filter((u) =>
    (health === 'all' || (health === 'normal' ? u.health === 'NORMAL' : u.health !== 'NORMAL')) &&
    (!search || `${u.unit_code} ${u.name} ${u.facility_name}`.toLowerCase().includes(search.toLowerCase()))), [data, health, search])
  const attention = (data || []).filter((u) => u.health !== 'NORMAL').length

  return (
    <>
      <PageHeader title="Live monitoring" subtitle="Current temperature of every storage unit in your scope. Stale readings are flagged, never shown as current."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Live monitoring' }]} />
      <FilterBar>
        <Select ariaLabel="Facility" value={facility} onChange={(v) => setParams(v ? { facility: v } : {})} placeholder="All facilities"
          options={(facilities.data || []).map((f) => ({ value: f.id, label: f.name }))} className="w-60" />
        <Segmented value={health} onChange={setHealth} options={[
          { value: 'all', label: `All (${data?.length ?? 0})` }, { value: 'attention', label: `Needs attention (${attention})` },
          { value: 'normal', label: 'Normal' }]} />
        <SearchInput value={search} onChange={setSearch} placeholder="Search units…" className="w-56" />
        <div className="flex-1" />
        <Segmented value={view} onChange={setView} options={[{ value: 'cards', label: 'Cards' }, { value: 'table', label: 'Table' }]} />
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <LoadingBlock rows={6} /> : view === 'cards' ? (
        rows.length ? (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
            {rows.map((u) => <UnitCard key={u.id} u={u} now={now} onClick={() => navigate(`/monitoring/units/${u.id}`)} />)}
          </div>
        ) : <div className="card"><EmptyState title="No storage units match" /></div>
      ) : (
        <div className="card p-0">
          <DataTable rows={rows} onRowClick={(u) => navigate(`/monitoring/units/${u.id}`)} columns={[
            { key: 'u', header: 'Unit', render: (u) => <Link to={`/monitoring/units/${u.id}`} className="font-medium text-brand-700">{u.unit_code}</Link> },
            { key: 'f', header: 'Facility', render: (u) => u.facility_name },
            { key: 'h', header: 'Status', render: (u) => <HealthBadge health={u.health} /> },
            { key: 't', header: 'Temperature', align: 'right', render: (u) => <span className={u.stale ? 'text-ink-3' : ''}>{fmtTemp(u.latest_temperature)}</span> },
            { key: 'r', header: 'Approved range', render: (u) => `${u.min_temperature} to ${u.max_temperature}°C` },
            { key: 'l', header: 'Last reading', render: (u) => <span className={u.stale ? 'text-serious-ink font-medium' : ''}>{ago(u.last_reading_at, now)}</span> },
            { key: 's', header: 'Sensors', render: (u) => u.sensors.map((s) => s.sensor_code).join(', ') },
            { key: 'i', header: 'Incidents', align: 'right', render: (u) => u.active_incidents || '—' },
          ]} />
        </div>
      )}
      <p className="text-[11px] text-ink-3 mt-3 flex items-center gap-1.5">
        <LayoutGrid size={12} /> Readings update live; health is re-evaluated by the server every 20 s. <Rows3 size={12} /> A table view is available for screen readers.
      </p>
    </>
  )
}
