import { Link, useNavigate } from 'react-router-dom'
import { BarList, Gauge } from '../../components/charts/Mini'
import { LegendChips, TwoLines } from '../../components/charts/Trends'
import { Card, CardHeader, Delta } from '../../components/common/Card'
import { EmptyState, ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, PriorityBadge, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Dashboards } from '../../services/api/endpoints'
import { cx, fmtDate, humanize } from '../../utils/format'

function Tile({ value, label, alert, to, extra }: { value: number; label: string; alert?: boolean; to?: string; extra?: React.ReactNode }) {
  const body = (
    <div className={cx('card px-4 py-4 h-full text-center hover:border-brand-200 transition-colors', alert && value > 0 && 'border-crit/40 bg-crit-bg/40')}>
      <div className={cx('display text-[38px] font-semibold tabular-nums leading-none', alert && value > 0 ? 'text-crit-ink' : 'text-ink')}>{value}</div>
      <div className="text-xs text-ink-2 mt-2">{label}{alert && value > 0 && <span className="sr-only"> (needs attention)</span>}</div>
      {extra && <div className="mt-1.5">{extra}</div>}
    </div>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

export default function TechnicianDashboard() {
  const q = useApi(() => Dashboards.technician(), [], { refreshOn: ['maintenance.updated', 'sensor.status'], interval: 60000 })
  const navigate = useNavigate()
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'No data'} onRetry={q.reload} />
  const d = q.data
  const k = d.kpis
  const wos = [...d.my_work_orders, ...d.unassigned]
  return (
    <>
      <PageHeader title="My work orders" subtitle="Assigned work, preventive maintenance and equipment needing attention in your facilities."
        crumbs={[{ label: 'Work' }]} />
      <div className="grid xl:grid-cols-[300px_1fr] gap-4">
        <Card pad={false} className="xl:row-span-3 h-fit">
          <div className="px-4 py-3 border-b border-line flex items-center justify-between">
            <span className="card-title">Work queue</span><Link to="/maintenance" className="text-xs text-brand-700">All</Link>
          </div>
          {!wos.length ? <EmptyState title="No open work orders" /> : (
            <ul className="divide-y divide-line max-h-[720px] overflow-y-auto">
              {wos.map((t: { id: string; ticket_number: string; title: string; status: string; priority: string; due_date: string; is_overdue: boolean; unit_code: string | null; facility_name: string }) => (
                <li key={t.id}>
                  <button onClick={() => navigate(`/maintenance/${t.id}`)} className="w-full text-left px-4 py-2.5 hover:bg-canvas">
                    <div className="flex items-center justify-between gap-2">
                      <span className="mono font-medium text-brand-700">{t.ticket_number}</span><PriorityBadge priority={t.priority} />
                    </div>
                    <div className="text-[12.5px] mt-0.5 line-clamp-1">{t.title}</div>
                    <div className="flex items-center gap-1.5 mt-1 text-[11px] text-ink-3">
                      <StatusPill status={t.status} /><span>{t.unit_code || t.facility_name}</span>
                      <span className={t.is_overdue ? 'text-crit font-medium' : ''}>· due {fmtDate(t.due_date)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Tile value={k.open_requests} label="Open requests" to="/maintenance" />
          <Tile value={k.my_assigned} label="Assigned to me" />
          <Tile value={k.in_progress} label="In progress" />
          <Tile value={k.overdue} label="Overdue work orders" alert />
          <Tile value={k.pm_due_30d} label="Preventive / calibration due" to="/technician/schedule" />
          <Tile value={k.completed_30d} label="Completed (30 d)" extra={d.deltas && <Delta value={d.deltas.completed_prev_30d ? Math.round(100 * (d.deltas.completed_30d - d.deltas.completed_prev_30d) / d.deltas.completed_prev_30d) : null} />} />
        </div>

        <div className="grid lg:grid-cols-3 gap-4">
          <Card><CardHeader title="Overdue work orders" subtitle="Share of active orders past due" />
            <Gauge value={d.overdue_gauge.overdue} total={Math.max(1, d.overdue_gauge.active)} label="overdue" /></Card>
          <Card><CardHeader title="Equipment alerts" subtitle="Sensors needing technician attention" />
            <div className="space-y-2 text-[13px]">
              {[['Sensors offline / error', k.sensors_offline], ['Battery below 20%', k.low_battery], ['Calibration due ≤ 30 d', k.calibration_due_30d]].map(([l, v]) => (
                <Link key={l as string} to="/technician/equipment" className="flex items-center justify-between rounded-lg border border-line px-3 py-2 hover:bg-canvas">
                  <span>{l}</span><Pill tone={(v as number) > 0 ? 'serious' : 'ok'}>{v as number}</Pill></Link>))}
            </div></Card>
          <Card><CardHeader title="Active orders by type" />
            {d.active_by_type.length ? <BarList items={d.active_by_type.map((t: { type: string; count: number }) => ({ label: humanize(t.type), value: t.count }))} /> : <EmptyState title="No active orders" />}
            <p className="text-[11px] text-ink-3 mt-3">By trigger: {d.active_by_trigger.map((t: { trigger: string; count: number }) => `${humanize(t.trigger)} ${t.count}`).join(' · ') || '—'}</p>
          </Card>
        </div>

        <Card>
          <CardHeader title="Work orders over time" subtitle="Created per week — preventive vs corrective (12 weeks)"
            actions={<LegendChips items={[{ name: 'Preventive', color: 'var(--color-series-1)' }, { name: 'Corrective', color: 'var(--color-series-2)' }]} />} />
          <TwoLines data={d.work_orders_over_time.map((w: { week: string }) => ({ ...w, wk: w.week.slice(5) }))} x="wk" height={260}
            series={[{ key: 'preventive', name: 'Preventive', color: 'var(--color-series-1)' }, { key: 'corrective', name: 'Corrective', color: 'var(--color-series-2)' }]} />
        </Card>
      </div>
    </>
  )
}
