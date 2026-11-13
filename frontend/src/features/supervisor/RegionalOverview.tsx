import { Building2, ClipboardCheck, Layers, ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FacilityMap, FacilityMapCard, type MapLayer } from '../../components/charts/FacilityMap'
import { CoverageBars, LegendChips, MiniLine, MiniMatrix, SurveillanceChart } from '../../components/charts/Trends'
import { Card, CardHeader, Delta, InsightCard, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { Segmented } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SeverityBadge, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Dashboards } from '../../services/api/endpoints'
import type { FacilitySummary } from '../../types'
import { ago, humanize } from '../../utils/format'

const CHANGE = (v: number | null | undefined) => v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v}%`
const RAMP = ['#14a294', '#2a78d6', '#6250d6', '#eb6834', '#e87ba4', '#1baf7a']

export default function RegionalOverview() {
  const q = useApi(() => Dashboards.supervisor(), [], { refreshOn: ['incident.created', 'incident.updated'], interval: 30000 })
  const [sel, setSel] = useState<FacilitySummary | null>(null)
  const [layer, setLayer] = useState<MapLayer>('status')
  const navigate = useNavigate()
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'No data'} onRetry={q.reload} />
  const d = q.data
  const k = d.kpis
  const dl = d.deltas
  const ins = d.insights
  const comp = (d.facility_comparison as { facility_id: string; facility_name: string; compliance: number | null; excursions: number; mtta_min: number | null }[])
  const selComp = sel && comp.find((c) => c.facility_id === sel.id)
  const exc = ins.excursions.series as { x: string; v: number }[]
  const avg = exc.length ? Math.round((exc.reduce((s, r) => s + r.v, 0) / exc.length) * 10) / 10 : 0
  const surveillance = exc.map((r) => ({ day: r.x, excursions: r.v, baseline: avg }))

  return (
    <>
      <PageHeader title="Regional overview" subtitle={`Monitor cold-chain compliance, excursions and approvals across ${k.facilities} facilities in ${d.regions.map((r: { name: string }) => r.name).join(', ')}.`}
        crumbs={[{ label: 'Region' }, { label: 'Overview' }]}
        actions={<Link to="/reports" className="btn-secondary">Export reports</Link>} />

      <div className="grid xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.4fr)] gap-4 mb-4">
        <div className="grid grid-cols-2 gap-4">
          <KpiCard label="Healthy facilities" value={`${k.healthy}/${k.facilities}`} icon={ShieldCheck} tone="ok" ratio={k.facilities ? k.healthy / k.facilities : 0}
            sub={`${k.warning} warning · ${k.critical} critical`} />
          <KpiCard label="Temperature compliance" value={k.compliance_7d === null ? '—' : `${k.compliance_7d}%`} icon={Building2} tone="brand"
            ratio={(k.compliance_7d ?? 0) / 100} delta={<Delta value={dl.compliance_change_pts} suffix=" pts" label="vs previous 7 d" />} />
          <KpiCard label="Unresolved incidents" value={k.unresolved_incidents} icon={ShieldAlert} tone={k.critical ? 'crit' : k.unresolved_incidents ? 'warn' : 'ok'}
            ratio={Math.min(1, k.unresolved_incidents / 10)} onClick={() => navigate('/incidents')}
            delta={<Delta value={dl.incidents_change_pct} goodWhen="down" label={`${dl.incidents_7d} opened this week`} />} />
          <KpiCard label="Awaiting your decision" value={k.approvals_pending} icon={ClipboardCheck} tone={k.approvals_pending ? 'info' : 'ok'}
            ratio={Math.min(1, k.approvals_pending / 5)} onClick={() => navigate('/supervisor/approvals')}
            sub={`${k.escalated} escalated · ${k.quarantined_batches} quarantined batch(es)`} />
        </div>
        <Card>
          <CardHeader title="Excursion surveillance" subtitle="Temperature excursions per day vs 14-day baseline"
            actions={<LegendChips items={[{ name: 'Excursions', color: '#e34948' }, { name: 'Baseline (avg)', color: '#1baf7a' }]} />} />
          <SurveillanceChart data={surveillance} x="day" height={258} markerEvery={2}
            series={[{ key: 'excursions', name: 'Excursions', color: '#e34948' }, { key: 'baseline', name: 'Baseline', color: '#1baf7a' }]} />
        </Card>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.4fr)] gap-4 mb-4">
        <Card className="xl:row-span-2">
          <CardHeader title="Live risk map" subtitle="Facility cold-chain status by district"
            actions={<span className="flex items-center gap-2 text-xs text-ink-3"><Layers size={14} /><Segmented value={layer} onChange={setLayer} options={[{ value: 'status', label: 'Status' }, { value: 'region', label: 'Regions' }]} /></span>} />
          <FacilityMap facilities={d.facilities} selectedId={sel?.id} onSelect={setSel} height={600} layer={layer}>
            {sel && <FacilityMapCard facility={sel} onClose={() => setSel(null)} to={`/monitoring?facility=${sel.id}`} action="Inspect facility"
              rows={[['Compliance (14 d)', selComp?.compliance !== undefined && selComp?.compliance !== null ? `${selComp.compliance}%` : '—'],
                ['Active incidents', sel.active_incidents], ['Sensors online', `${sel.sensors_online}/${sel.sensors_total}`]]} />}
          </FacilityMap>
        </Card>
        <div className="grid md:grid-cols-3 gap-4">
          <InsightCard title="Excursion trend" subtitle="Excursions per day, 14 days"
            chart={<MiniLine data={ins.excursions.series} color="#6250d6" />}
            facts={[['Most affected', ins.excursions.facility], ['Change (7 d)', CHANGE(ins.excursions.change_pct)], ['Confidence', ins.excursions.confidence]]} />
          <InsightCard title="Telemetry volume" subtitle="Readings per hour, 24 h"
            chart={<MiniMatrix data={ins.availability.series} color="#14a294" />}
            facts={[['Lowest availability', ins.availability.facility], ['Availability', ins.availability.facility_availability === null ? '—' : `${ins.availability.facility_availability}%`], ['Confidence', ins.availability.confidence]]} />
          <InsightCard title="Calibration readiness" subtitle="Sensors due (cumulative), next 8 weeks"
            chart={<MiniLine data={ins.calibration.series} color="#eb6834" step />}
            facts={[['Most due', ins.calibration.facility], ['Due in 8 weeks', ins.calibration.due_8w], ['Overdue now', ins.calibration.overdue]]} />
        </div>
        <div className="grid md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-4">
          <Card pad={false}>
            <div className="card-pad pb-0"><CardHeader title="Approval board" subtitle="Corrective actions and incident reviews awaiting a supervisor decision"
              actions={<Link to="/supervisor/approvals" className="btn-secondary btn-sm">Open queue</Link>} /></div>
            <DataTable rows={d.approval_queue} rowKey={(r) => r.kind + r.incident_id} onRowClick={(r) => navigate(`/incidents/${r.incident_id}`)}
              empty={<EmptyState icon={ClipboardCheck} title="Nothing awaiting approval" />} columns={[
                { key: 'i', header: 'Item', render: (r) => <div className="min-w-0"><div className="font-medium text-ink">{r.incident_number}</div><div className="text-xs text-ink-3 truncate max-w-56">{r.title}</div></div> },
                { key: 'f', header: 'Facility', render: (r) => <span className="text-xs">{r.facility_name}</span> },
                { key: 's', header: 'Severity', render: (r) => <SeverityBadge severity={r.severity} /> },
                { key: 'k', header: 'Status', render: (r) => <Pill tone={r.kind === 'CORRECTIVE_ACTION' ? 'warn' : 'ok'}>{r.kind === 'CORRECTIVE_ACTION' ? 'Approval' : 'Ready for review'}</Pill> },
              ]} />
          </Card>
          <Card>
            <CardHeader title="Compliance gap" subtitle="% readings in range by facility, 14 days" />
            <CoverageBars items={comp.slice(0, 6).map((c, i) => ({ label: c.facility_name.replace(/^(Urban |District Vaccine Store, )/, ''), value: c.compliance, color: RAMP[i % RAMP.length] }))} />
          </Card>
        </div>
      </div>

      <Card pad={false}>
        <div className="card-pad pb-0"><CardHeader title={<span className="flex items-center gap-2"><TriangleAlert size={16} className="text-crit" />Critical & escalated incidents</span>}
          subtitle="Highest-priority items across your region" /></div>
        <DataTable rows={d.escalated_incidents} onRowClick={(i) => navigate(`/incidents/${i.id}`)} empty={<EmptyState title="No critical or escalated incidents" />} columns={[
          { key: 'n', header: 'Incident', render: (i) => <span className="font-medium text-brand-700">{i.incident_number}</span> },
          { key: 'f', header: 'Facility / unit', render: (i) => <span className="text-xs">{i.facility_name} · {i.unit_code}</span> },
          { key: 't', header: 'Type', render: (i) => <span className="text-xs">{humanize(i.incident_type)}</span> },
          { key: 's', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
          { key: 'st', header: 'Status', render: (i) => <StatusPill status={i.status} /> },
          { key: 'e', header: 'Escalation', render: (i) => i.escalation_level ? <span className="font-semibold text-crit-ink">L{i.escalation_level}</span> : '—' },
          { key: 'a', header: 'Age', render: (i) => <span className="text-xs">{ago(i.created_at)}</span> },
        ]} />
      </Card>
    </>
  )
}
