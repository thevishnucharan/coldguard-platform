import { BrainCircuit, CheckCircle2, Clock, PackageCheck, Route, Snowflake, Truck, XCircle } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, LoadingBlock } from '../../components/common/Feedback'
import { Field } from '../../components/common/Form'
import { ConfirmDialog } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SeverityBadge, SimulatedTag, StatusPill } from '../../components/common/Status'
import { RouteMap } from '../../components/charts/RouteMap'
import { TRIP_COLORS } from '../../components/charts/routeColors'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Logistics } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { cx, fmtDateTime } from '../../utils/format'

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any
interface Excursion {
  incident_id: string; incident_number: string; title: string; severity: string; status: string; created_at: string
  storage_unit_id: string; unit_code: string; facility_name: string; is_simulated: boolean
  batches_at_risk: number; doses_at_risk: number; latest_plan: { id: string; plan_number: string; status: string } | null
}
interface View { id?: string; plan_number?: string; status?: string; result: Any }

const mins = (m: number | null | undefined) => (m === null || m === undefined ? '—' : m >= 90 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`)
const num = (n: number | null | undefined) => (n === null || n === undefined ? '—' : n.toLocaleString())

export default function ExcursionRoutingPage() {
  const can = useAuthStore((s) => s.can)
  const canPlan = can('logistics.plan')
  const model = useApi(() => Logistics.model(), [])
  const excursions = useApi(() => Logistics.excursions(), [], { refreshOn: ['incident.created', 'incident.updated'], interval: 30000 })
  const plans = useApi(() => Logistics.plans(), [])
  const [selected, setSelected] = useState<string | null>(null)
  const [params, setParams] = useState({ max_trip_minutes: 240, vehicle_capacity_litres: 60, vehicles: 1 })
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<View | null>(null)
  const [cancelOpen, setCancelOpen] = useState(false)

  const sel = (excursions.data as Excursion[] | null)?.find((e) => e.incident_id === selected) || null
  const reloadLists = () => { excursions.reload(); plans.reload() }

  const optimise = async () => {
    if (!sel) return
    setBusy(true)
    try {
      const r = await Logistics.optimise({ incident_id: sel.incident_id, ...params })
      setView({ id: r.id, plan_number: r.plan_number, status: r.status, result: r })
      toast.success(`${r.plan_number} generated`)
      reloadLists()
    } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  const openPlan = async (id: string) => {
    try { const p = await Logistics.plan(id); setView({ id: p.id, plan_number: p.plan_number, status: p.status, result: p.plan }) }
    catch (e) { toast.error(errorMessage(e)) }
  }
  const decide = async (approve: boolean, note?: string) => {
    if (!view?.id) return
    try {
      const p = approve ? await Logistics.approve(view.id, note) : await Logistics.cancel(view.id, note || '')
      setView({ ...view, status: p.status })
      toast.success(`${p.plan_number} ${p.status.toLowerCase()}`)
      reloadLists()
    } catch (e) { toast.error(errorMessage(e)) }
  }

  const m = model.data
  return (
    <>
      <PageHeader title="Excursion routing"
        subtitle="Relocate stock out of units in a temperature excursion to safe, compatible storage — ML-predicted transit times, optimised trips."
        crumbs={[{ label: 'Platform', to: '/admin' }, { label: 'Excursion routing' }]}
        meta={m && <Pill tone={m.available ? 'brand' : 'warn'} icon={BrainCircuit}
          title={m.available ? `p50 MAE ${m.metrics?.p50_mae_minutes} min vs baseline ${m.metrics?.baseline_mae_minutes} min` : 'Model file missing — physical baseline in use'}>
          {m.available ? m.version : 'Baseline ETA (no model)'}</Pill>} />

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Active excursions" subtitle="Units with stock at risk right now" />
            {excursions.loading && !excursions.data ? <LoadingBlock rows={3} /> : !(excursions.data || []).length
              ? <EmptyState icon={Snowflake} title="No active excursions" description="Every storage unit in scope is inside its approved range." />
              : <ul className="space-y-2" role="listbox" aria-label="Active excursions">
                {(excursions.data as Excursion[]).map((e) => (
                  <li key={e.incident_id}>
                    <button role="option" aria-selected={selected === e.incident_id} onClick={() => setSelected(e.incident_id)}
                      className={cx('w-full text-left rounded-lg border px-3 py-2 transition-colors',
                        selected === e.incident_id ? 'border-brand-500 bg-brand-50' : 'border-line hover:border-brand-200')}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="mono text-[12.5px] font-medium">{e.incident_number}</span>
                        <span className="flex gap-1"><SeverityBadge severity={e.severity} /><SimulatedTag show={e.is_simulated} /></span>
                      </div>
                      <div className="text-xs text-ink-2 mt-0.5">{e.unit_code} · {e.facility_name}</div>
                      <div className="flex items-center justify-between text-xs text-ink-3 mt-1">
                        <span>{num(e.doses_at_risk)} doses · {e.batches_at_risk} batch(es)</span>
                        {e.latest_plan && <StatusPill status={e.latest_plan.status} label={e.latest_plan.plan_number} />}
                      </div>
                    </button>
                  </li>))}
              </ul>}
          </Card>

          {canPlan && (
            <Card>
              <CardHeader title="Constraints" subtitle="Applied to every trip" />
              <div className="grid grid-cols-2 gap-3">
                <Field label="Cold-box hold time (min)" hint="Checked against p90 ETA" className="col-span-2">
                  <input type="number" min={30} max={720} className="input" value={params.max_trip_minutes}
                    onChange={(e) => setParams({ ...params, max_trip_minutes: Number(e.target.value) })} /></Field>
                <Field label="Vehicle capacity (L)"><input type="number" min={5} max={2000} className="input" value={params.vehicle_capacity_litres}
                  onChange={(e) => setParams({ ...params, vehicle_capacity_litres: Number(e.target.value) })} /></Field>
                <Field label="Vehicles"><input type="number" min={1} max={10} className="input" value={params.vehicles}
                  onChange={(e) => setParams({ ...params, vehicles: Number(e.target.value) })} /></Field>
              </div>
              <button className="btn-primary w-full mt-4" disabled={!sel || busy || sel.doses_at_risk === 0} onClick={optimise}>
                <Route size={15} /> {busy ? 'Optimising…' : 'Optimise relocation route'}</button>
              {sel && sel.doses_at_risk === 0 && <p className="text-[11px] text-ink-3 mt-2">No stock left in {sel.unit_code}.</p>}
            </Card>)}
        </div>

        <div className="lg:col-span-2 space-y-4">
          {!view ? (
            <Card><EmptyState icon={Truck} title="No plan selected"
              description={canPlan ? 'Pick an active excursion and optimise, or open a plan from the history below.' : 'Open a plan from the history below.'} /></Card>
          ) : <PlanView view={view} canPlan={canPlan} onApprove={() => decide(true)} onCancel={() => setCancelOpen(true)} />}
        </div>
      </div>

      <Card className="mt-4" pad={false}>
        <div className="card-pad pb-0"><CardHeader title="Plan history" subtitle="Every generated plan is kept with its model version and decision" /></div>
        <DataTable rows={plans.data} loading={plans.loading} error={plans.error} onRetry={plans.reload} onRowClick={(p: Any) => openPlan(p.id)}
          rowKey={(p: Any) => p.id} selectedKey={view?.id} empty={<EmptyState title="No route plans yet" />} columns={[
            { key: 'n', header: 'Plan', render: (p: Any) => <span className="mono font-medium">{p.plan_number}</span> },
            { key: 'i', header: 'Incident', render: (p: Any) => p.incident_number || '—' },
            { key: 'u', header: 'Source', render: (p: Any) => <div><div>{p.unit_code}</div><div className="text-xs text-ink-3">{p.facility_name}</div></div> },
            { key: 'd', header: 'Doses', align: 'right', render: (p: Any) => num(p.total_doses - p.unassigned_doses) },
            { key: 't', header: 'Trips', align: 'right', render: (p: Any) => p.trip_count },
            { key: 'g', header: 'vs baseline', align: 'right', render: (p: Any) => p.improvement_pct === null ? '—' : `${p.improvement_pct > 0 ? '−' : '+'}${Math.abs(p.improvement_pct)}%` },
            { key: 's', header: 'Status', render: (p: Any) => <StatusPill status={p.status} /> },
            { key: 'c', header: 'Created', render: (p: Any) => <span className="text-xs">{fmtDateTime(p.created_at)} · {p.created_by_name}</span> },
          ]} />
      </Card>

      <ConfirmDialog open={cancelOpen} onClose={() => setCancelOpen(false)} danger title={`Cancel ${view?.plan_number || 'plan'}`}
        description="The plan is kept for the audit trail but can no longer be approved." confirmLabel="Cancel plan"
        reasonLabel="Reason" reasonRequired minReason={5} onConfirm={(reason) => decide(false, reason)} />
    </>
  )
}

function PlanView({ view, canPlan, onApprove, onCancel }: { view: View; canPlan: boolean; onApprove: () => void; onCancel: () => void }) {
  const r = view.result
  const s = r.summary
  const improvement = s.improvement_pct
  return (
    <>
      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <KpiCard label="Doses relocated" icon={PackageCheck} tone={s.unassigned_doses ? 'warn' : 'ok'} value={num(s.relocated_doses)}
          sub={s.unassigned_doses ? `${num(s.unassigned_doses)} doses unplaced` : `of ${num(s.total_doses)} at risk`} ratio={s.total_doses ? s.relocated_doses / s.total_doses : 0} />
        <KpiCard label="Trips" icon={Truck} tone="info" value={s.trip_count} sub={`${s.distance_km} km · ${r.on_site_moves.length} on-site move(s)`} />
        <KpiCard label="All stock safe in" icon={Clock} tone="neutral" value={mins(s.completion_minutes)} sub="incl. unloading & returns" />
        <KpiCard label="Exposure vs baseline" icon={BrainCircuit} tone={improvement > 0 ? 'ok' : 'neutral'}
          value={improvement === null ? '—' : `${improvement > 0 ? '−' : '+'}${Math.abs(improvement)}%`}
          sub={`${num(Math.round(s.exposure_dose_minutes))} vs ${num(Math.round(s.baseline_exposure_dose_minutes ?? 0))} dose·min`} />
      </div>

      <Card>
        <CardHeader title={<span className="flex items-center gap-2">{view.plan_number || 'Preview'} {view.status && <StatusPill status={view.status} />}</span>}
          subtitle={`From ${r.source.unit_code} · ${r.source.name} · departs ${fmtDateTime(r.parameters.depart_at)} · ETA model ${r.model.version}`}
          actions={canPlan && view.status === 'PROPOSED' && <>
            <button className="btn-secondary btn-sm" onClick={onCancel}><XCircle size={14} /> Cancel</button>
            <button className="btn-primary btn-sm" onClick={onApprove}><CheckCircle2 size={14} /> Approve & notify</button></>} />
        <RouteMap source={r.source} trips={r.trips} />
        <p className="text-[11px] text-ink-3 mt-2">{r.note}</p>
      </Card>

      {r.trips.map((t: Any, i: number) => (
        <Card key={t.trip}>
          <CardHeader title={<span className="flex items-center gap-2"><span className="h-1.5 w-5 rounded" style={{ background: TRIP_COLORS[i % TRIP_COLORS.length] }} />
            Trip {t.trip} · vehicle {t.vehicle}</span>}
            subtitle={`Leaves at +${mins(t.start_offset_minutes)} · ${t.distance_km} km · ${t.load_litres} L · cold-chain p90 ${mins(t.cold_chain_minutes_p90)} / ${mins(r.parameters.max_trip_minutes)}`} />
          <ol className="space-y-2">
            {t.stops.map((st: Any, k: number) => (
              <li key={st.facility_key} className="rounded-lg border border-line px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
                  <span className="font-medium">{k + 1}. {st.facility_name} <span className="mono text-xs text-ink-3">{st.facility_code}</span></span>
                  <span className="text-xs text-ink-2 tabular-nums">{st.leg_distance_km} km · ETA +{mins(st.arrival_offset_minutes)} <span className="text-ink-3">(p90 +{mins(st.arrival_p90_offset_minutes)})</span></span>
                </div>
                {st.deliveries.map((d: Any) => (
                  <div key={d.storage_unit_id} className="mt-1 text-xs text-ink-2">
                    → <span className="mono">{d.unit_code}</span> ({d.approved_range[0]}…{d.approved_range[1]} °C): {d.batches.map((b: Any) => (
                      <span key={b.batch_id} className="mr-2">{b.batch_number} · {b.product} · {num(b.doses)}{b.segregate && <Pill tone="warn" className="ml-1">keep segregated</Pill>}</span>))}
                  </div>))}
              </li>))}
          </ol>
        </Card>))}

      {(r.on_site_moves.length > 0 || r.unassigned.length > 0 || r.excluded_units.length > 0) && (
        <Card>
          <CardHeader title="Other actions & exclusions" />
          {r.on_site_moves.map((d: Any) => (
            <p key={d.storage_unit_id} className="text-xs mb-1"><Pill tone="ok">On-site</Pill> Move to <span className="mono">{d.unit_code}</span> in the same facility: {d.batches.map((b: Any) => `${b.batch_number} (${num(b.doses)})`).join(', ')}</p>))}
          {r.unassigned.map((u: Any) => (
            <p key={u.batch_id} className="text-xs mb-1"><Pill tone="crit">Unplaced</Pill> {u.batch_number} · {u.product} · {num(u.doses)} doses — {u.reason}</p>))}
          {r.excluded_units.map((u: Any) => (
            <p key={u.unit_code} className="text-xs mb-1 text-ink-3"><Pill>Excluded</Pill> {u.unit_code} ({u.facility_code}) — {u.reason}</p>))}
        </Card>)}
    </>
  )
}
