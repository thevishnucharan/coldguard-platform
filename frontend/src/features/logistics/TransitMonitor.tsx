import { AlertOctagon, CheckCircle2, Clock, MapPin, Navigation, PackageCheck, Radio, Thermometer, Truck, Zap } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader } from '../../components/common/Card'
import { EmptyState, LoadingBlock } from '../../components/common/Feedback'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SimulatedTag, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Logistics } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { ago, cx, fmtTemp } from '../../utils/format'

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any

const ALERT_LABEL: Record<string, string> = {
  SENSOR_FAULT: 'Data logger fault', SENSOR_OFFLINE: 'Data logger silent', TEMPERATURE_EXCURSION: 'Cargo temperature excursion',
}
const SENSOR_TONE: Record<string, 'ok' | 'crit' | 'serious'> = { OK: 'ok', FAULT: 'crit', OFFLINE: 'serious' }

function HoldBar({ used, hold }: { used: number; hold: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(hold, 1)) * 100))
  const tone = pct >= 85 ? 'bg-crit' : pct >= 60 ? 'bg-warn' : 'bg-ok'
  return (
    <div className="mt-1" title={`${Math.round(used)} of ${Math.round(hold)} min cold-box hold time used`}>
      <div className="h-1.5 rounded-full bg-line overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
        aria-label="Cold-box hold time used"><div className={cx('h-full rounded-full', tone)} style={{ width: `${pct}%` }} /></div>
      <p className="text-[11px] text-ink-3 mt-1">{Math.round(used)} / {Math.round(hold)} min hold time · {Math.max(0, Math.round(hold - used))} min left</p>
    </div>
  )
}

function NearbyStores({ alert, canOperate, onDivert }: { alert: Any; canOperate: boolean; onDivert: (facilityId: string, name: string) => void }) {
  if (!alert.nearby?.length) return <p className="text-xs text-crit-ink mt-2">No compatible cold-chain store with free capacity found — escalate to the supervisor.</p>
  return (
    <ol className="mt-2 space-y-1.5" aria-label="Nearest compatible cold-chain stores">
      {alert.nearby.map((n: Any, i: number) => (
        <li key={n.facility_id} className={cx('flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2',
          i === 0 && n.reachable_within_hold ? 'border-brand-500 bg-brand-50' : 'border-line')}>
          <div className="min-w-0">
            <p className="text-[13px] font-medium flex items-center gap-1.5">
              <MapPin size={13} className="text-ink-3" />{n.facility_name}
              {i === 0 && n.reachable_within_hold && <Pill tone="brand">Recommended</Pill>}
              {!n.reachable_within_hold && <Pill tone="crit">Beyond hold time</Pill>}
            </p>
            <p className="text-[11.5px] text-ink-3 tabular-nums">
              {n.distance_km.toFixed(1)} km · ETA ~{Math.round(n.eta_minutes)} min (p90 {Math.round(n.eta_p90_minutes)}) · {n.units[0]?.unit_code} free {n.units[0]?.free_litres} L
            </p>
          </div>
          {canOperate && <button className="btn-secondary btn-sm" onClick={() => onDivert(n.facility_id, n.facility_name)}><Navigation size={13} /> Divert here</button>}
        </li>
      ))}
    </ol>
  )
}

/** Vehicles carrying relocated stock: live logger state, hold-time budget, transit alerts with
 *  the nearest compatible stores (ML ETA) and the divert / deliver / acknowledge actions. */
export function TransitMonitor({ compact = false }: { compact?: boolean }) {
  const can = useAuthStore((s) => s.can)
  const canOperate = can('logistics.operate')
  const q = useApi(() => Logistics.shipments({ status: 'IN_TRANSIT' }), [],
    { refreshOn: ['transit.alert', 'notification'], interval: 20000 })
  const [busy, setBusy] = useState<string | null>(null)
  const act = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key)
    try { await fn(); toast.success(ok); q.reload() } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(null) }
  }
  const simulateFault = (s: Any) => act(`sim-${s.id}`, () => Logistics.telemetry(s.id, {
    lat: s.last_lat + (s.stops[0]?.lat - s.last_lat) * 0.3, lon: s.last_lon + (s.stops[0]?.lon - s.last_lon) * 0.3,
    temperature: null, sensor_status: 'FAULT',
  }), 'Logger fault reported — nearby stores alerted')

  return (
    <Card>
      <CardHeader title={<span className="flex items-center gap-2"><Truck size={16} /> Vehicles in transit</span>}
        subtitle="Data-logger health and cargo temperature for relocation vehicles. Failures alert the vehicle's operator and the nearest compatible cold-chain stores." />
      {q.loading && !q.data ? <LoadingBlock rows={2} /> : !(q.data || []).length ? (
        <EmptyState icon={Truck} title="No vehicles in transit" description="Dispatch an approved relocation plan to start in-transit monitoring." />
      ) : (
        <ul className="space-y-3">
          {(q.data as Any[]).map((s) => {
            const open = (s.alerts || []).filter((a: Any) => a.status !== 'RESOLVED')
            return (
              <li key={s.id} className={cx('rounded-xl border p-3', open.length ? 'border-crit/40 bg-crit-bg/30' : 'border-line')}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-[14px] flex items-center gap-2"><Truck size={15} />{s.vehicle_code}
                      <span className="mono text-xs text-ink-3">{s.shipment_number}</span><SimulatedTag show={s.is_simulated} /></p>
                    <p className="text-xs text-ink-2 mt-0.5">{s.facility_name} → {s.stops.map((x: Any) => x.facility_name).join(' → ')} · {s.total_doses.toLocaleString()} doses ({s.temperature_range[0]}–{s.temperature_range[1]} °C)</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill tone={SENSOR_TONE[s.sensor_state] || 'neutral'} icon={Radio}>Logger {s.sensor_state.toLowerCase()}</Pill>
                    <Pill icon={Thermometer}>{fmtTemp(s.last_temperature)}</Pill>
                    <Pill icon={Clock}>{ago(s.last_reading_at)}</Pill>
                  </div>
                </div>
                <HoldBar used={s.minutes_in_transit} hold={s.hold_minutes} />
                {open.map((a: Any) => (
                  <div key={a.id} className="mt-3 rounded-lg border border-crit/30 bg-surface p-3" role="alert">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[13px] font-semibold text-crit-ink flex items-center gap-1.5"><AlertOctagon size={15} />{ALERT_LABEL[a.alert_type] || a.alert_type}
                        <StatusPill status={a.status} /></p>
                      <span className="text-[11px] text-ink-3">{a.incident_number && `${a.incident_number} · `}{a.notified_users} people alerted · {ago(a.created_at)}</span>
                    </div>
                    {!compact && <p className="text-xs text-ink-2 mt-1">{a.message}</p>}
                    <NearbyStores alert={a} canOperate={canOperate}
                      onDivert={(fid, name) => act(`div-${s.id}`, () => Logistics.divert(s.id, fid, `Diverted after ${a.alert_type}`), `${s.vehicle_code} diverting to ${name}`)} />
                    {canOperate && a.status === 'OPEN' && (
                      <button className="btn-ghost btn-sm mt-2" disabled={busy === a.id} onClick={() => act(a.id, () => Logistics.acknowledgeAlert(a.id), 'Alert acknowledged')}>
                        <CheckCircle2 size={13} /> Acknowledge</button>)}
                  </div>
                ))}
                {canOperate && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="btn-secondary btn-sm" disabled={busy === `del-${s.id}`} onClick={() => act(`del-${s.id}`, () => Logistics.deliver(s.id, 'Received at destination'), `${s.vehicle_code} delivered`)}>
                      <PackageCheck size={13} /> Mark delivered</button>
                    {s.is_simulated && !open.length && (
                      <button className="btn-ghost btn-sm" disabled={busy === `sim-${s.id}`} onClick={() => simulateFault(s)}>
                        <Zap size={13} /> Simulate logger failure</button>)}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

export default function TransitPage() {
  return (
    <>
      <PageHeader title="In-transit cold chain" crumbs={[{ label: 'Logistics' }, { label: 'In transit' }]}
        subtitle="Relocation vehicles, their data loggers and the nearest compatible stores if something fails on the road." />
      <TransitMonitor />
    </>
  )
}
