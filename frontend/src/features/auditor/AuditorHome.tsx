import { Boxes, FileCheck2, FlaskConical, Gauge, ScrollText, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { SurveillanceChart } from '../../components/charts/Trends'
import { Card, CardHeader, Delta, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Dashboards } from '../../services/api/endpoints'
import { fmtDateTime, humanize } from '../../utils/format'

export default function AuditorHome() {
  const q = useApi(() => Dashboards.auditor(), [])
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'No data'} onRetry={q.reload} />
  const d = q.data
  const k = d.kpis
  return (
    <>
      <PageHeader title="Compliance overview" subtitle="Read-only oversight across all facilities (last 30 days)." crumbs={[{ label: 'Compliance' }]}
        meta={<Pill tone="info" icon={ShieldCheck}>Read-only access</Pill>} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Audit events" value={k.audit_events_30d.toLocaleString()} icon={ScrollText} sub={`${k.security_events_30d} security events`} />
        <KpiCard label="Incidents closed" value={k.incidents_closed_30d} icon={ShieldAlert} tone="brand" delta={<Delta value={d.deltas.incidents_change_pct} goodWhen="down" label={`${d.deltas.incidents_7d} opened this week`} />} />
        <KpiCard label="Vaccine dispositions" value={k.dispositions_30d} icon={FileCheck2} sub="Release / disposal decisions" />
        <KpiCard label="Stock movements" value={k.movements_30d.toLocaleString()} icon={Boxes} />
        <KpiCard label="Calibrations" value={k.calibrations_30d} icon={Gauge} />
        <KpiCard label="Quarantined telemetry" value={k.quarantined_telemetry_30d} icon={FlaskConical} tone={k.quarantined_telemetry_30d ? 'warn' : 'ok'} sub="Rejected / malformed messages" />
        <KpiCard label="Anomaly signals" value={k.anomalies_30d} icon={Sparkles} sub="Decision support only" />
        <KpiCard label="Event categories" value={Object.keys(d.events_by_category).length} sub={Object.entries(d.events_by_category).map(([c, n]) => `${humanize(c)} ${n}`).join(' · ')} />
      </div>
      <div className="grid xl:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Temperature compliance (14 days)" subtitle="% of valid readings within each unit's approved range" />
          <SurveillanceChart data={d.compliance_trend.map((r: { date: string; compliance: number | null }) => ({ day: r.date.slice(5), compliance: r.compliance }))} x="day" unit="%" height={250}
            domain={[90, 100]} series={[{ key: 'compliance', name: 'Compliance', color: 'var(--color-series-1)' }]} />
        </Card>
        <Card pad={false}>
          <div className="card-pad pb-0"><CardHeader title="Facility compliance (30 days)" actions={<Link to="/reports" className="text-xs text-brand-700">Export</Link>} /></div>
          <DataTable dense rows={d.facility_comparison} rowKey={(r) => r.facility_id} columns={[
            { key: 'f', header: 'Facility', render: (r) => r.facility_name },
            { key: 'c', header: 'Compliance', align: 'right', render: (r) => r.compliance === null ? '—' : `${r.compliance}%` },
            { key: 'e', header: 'Excursions', align: 'right', render: (r) => r.excursions },
            { key: 'm', header: 'MTTA', align: 'right', render: (r) => r.mtta_min === null ? '—' : `${r.mtta_min} min` },
          ]} />
        </Card>
        <Card pad={false} className="xl:col-span-2">
          <div className="card-pad pb-0"><CardHeader title="Recent audit events" actions={<Link to="/audit" className="text-xs text-brand-700">Full audit trail</Link>} /></div>
          <DataTable dense rows={d.recent_audit} columns={[
            { key: 't', header: 'Time', render: (a) => <span className="text-xs mono">{fmtDateTime(a.timestamp)}</span> },
            { key: 'u', header: 'Actor', render: (a) => `${a.actor} (${a.role})` },
            { key: 'a', header: 'Action', render: (a) => <span className="mono">{a.action}</span> },
            { key: 'c', header: 'Category', render: (a) => <Pill>{humanize(a.category)}</Pill> },
            { key: 'o', header: 'Outcome', render: (a) => <StatusPill status={a.outcome} /> },
          ]} />
        </Card>
      </div>
    </>
  )
}
