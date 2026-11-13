import { useState } from 'react'
import { Card, CardHeader } from '../../components/common/Card'
import { BarList } from '../../components/charts/Mini'
import { DataTable } from '../../components/common/DataTable'
import { ErrorState, LoadingBlock } from '../../components/common/Feedback'
import { Segmented } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Analytics } from '../../services/api/endpoints'
import { ComplianceTrend, IncidentsPerDay } from './charts'

export default function CompliancePage() {
  const [days, setDays] = useState<'14' | '30' | '90'>('30')
  const comp = useApi(() => Analytics.facilityComparison(Number(days)), [days])
  const trend = useApi(() => Analytics.complianceTrend(Math.min(Number(days), 90)), [days])
  const perDay = useApi(() => Analytics.incidentsPerDay(Math.min(Number(days), 90)), [days])
  const rows = comp.data || []
  return (
    <>
      <PageHeader title="Compliance analytics" subtitle="Facility-wise temperature compliance, excursion frequency, response and resolution time."
        crumbs={[{ label: 'Regional overview', to: '/supervisor' }, { label: 'Compliance' }]}
        actions={<Segmented value={days} onChange={setDays} options={[{ value: '14', label: '14 d' }, { value: '30', label: '30 d' }, { value: '90', label: '90 d' }]} />} />
      <div className="grid xl:grid-cols-2 gap-4 mb-4">
        <Card><CardHeader title="Temperature compliance trend" subtitle="% of readings in approved range per day" />
          {trend.error ? <ErrorState message={trend.error} /> : trend.data ? <ComplianceTrend data={trend.data} /> : <LoadingBlock />}</Card>
        <Card><CardHeader title="Incident frequency" subtitle="Incidents opened per day by severity" />
          {perDay.data ? <IncidentsPerDay data={perDay.data} height={240} /> : <LoadingBlock />}</Card>
        <Card><CardHeader title="Mean time to acknowledge" subtitle="Minutes from detection to acknowledgement" />
          <BarList items={rows.filter((r) => r.mtta_min !== null).sort((a, b) => b.mtta_min - a.mtta_min).map((r) => ({ label: r.facility_name, value: r.mtta_min }))} unit=" min" color="var(--color-series-2)" /></Card>
        <Card><CardHeader title="Repeated equipment failures" subtitle="Corrective / inspection work orders in period" />
          <BarList items={rows.sort((a, b) => b.equipment_failures - a.equipment_failures).slice(0, 8).map((r) => ({ label: r.facility_name, value: r.equipment_failures }))} color="var(--color-series-3)" /></Card>
      </div>
      <Card pad={false}>
        <div className="card-pad pb-0"><CardHeader title="Facility comparison" subtitle="Compliance uses the last 14 days of readings; incident metrics use the selected period." /></div>
        <DataTable rows={rows} loading={comp.loading} error={comp.error} rowKey={(r) => r.facility_id} columns={[
          { key: 'f', header: 'Facility', render: (r) => <span className="font-medium">{r.facility_name}</span> },
          { key: 'c', header: 'Compliance', align: 'right', render: (r) => r.compliance === null ? '—' : <span className="flex items-center justify-end gap-1.5">{r.compliance}%
            {r.compliance < 95 && <Pill tone={r.compliance < 90 ? 'crit' : 'warn'}>{r.compliance < 90 ? 'Below 90%' : 'Below 95%'}</Pill>}</span> },
          { key: 'r', header: 'Readings', align: 'right', render: (r) => r.readings.toLocaleString() },
          { key: 'e', header: 'Excursions', align: 'right', render: (r) => r.excursions },
          { key: 'i', header: 'Incidents', align: 'right', render: (r) => r.incidents },
          { key: 'a', header: 'MTTA', align: 'right', render: (r) => r.mtta_min === null ? '—' : `${r.mtta_min} min` },
          { key: 'm', header: 'MTTR', align: 'right', render: (r) => r.mttr_h === null ? '—' : `${r.mttr_h} h` },
          { key: 'w', header: 'Equipment WOs', align: 'right', render: (r) => r.equipment_failures },
        ]} />
      </Card>
    </>
  )
}
