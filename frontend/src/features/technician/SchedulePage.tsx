import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHeader } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState } from '../../components/common/Feedback'
import { Segmented } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Maintenance } from '../../services/api/endpoints'
import { fmtDate } from '../../utils/format'
import { WorkOrderTable } from '../maintenance/WorkOrdersPage'

const dueTag = (iso: string | null) => {
  if (!iso) return null
  const days = Math.round((new Date(iso).getTime() - Date.now()) / 86400000)
  return days < 0 ? <Pill tone="crit">{-days} d overdue</Pill> : <Pill tone={days <= 14 ? 'warn' : 'neutral'}>in {days} d</Pill>
}

export default function SchedulePage() {
  const [days, setDays] = useState<'30' | '60' | '120'>('60')
  const s = useApi(() => Maintenance.schedule(Number(days)), [days])
  const pm = useApi(() => Maintenance.list({ maintenance_type: 'PREVENTIVE', status: ['OPEN', 'ASSIGNED', 'IN_PROGRESS'], page_size: 50 }), [])
  const cal = useApi(() => Maintenance.list({ maintenance_type: 'CALIBRATION', status: ['OPEN', 'ASSIGNED', 'IN_PROGRESS'], page_size: 50 }), [])
  return (
    <>
      <PageHeader title="Preventive maintenance schedule" subtitle="Upcoming servicing and calibration. Preventive work orders are generated automatically 14 days before due."
        crumbs={[{ label: 'Work' }, { label: 'Schedule' }]}
        actions={<Segmented value={days} onChange={setDays} options={[{ value: '30', label: '30 d' }, { value: '60', label: '60 d' }, { value: '120', label: '120 d' }]} />} />
      <div className="grid xl:grid-cols-2 gap-4 mb-4">
        <Card pad={false}>
          <div className="card-pad pb-0"><CardHeader title="Refrigerator servicing due" /></div>
          <DataTable rows={s.data?.service_due} loading={s.loading} rowKey={(r) => r.storage_unit_id} empty={<EmptyState title="Nothing due in this window" />} columns={[
            { key: 'u', header: 'Unit', render: (r) => <Link className="font-medium text-brand-700" to={`/monitoring/units/${r.storage_unit_id}`}>{r.unit_code}</Link> },
            { key: 'l', header: 'Last service', render: (r) => fmtDate(r.last_service_at) },
            { key: 'n', header: 'Due', render: (r) => <span className="flex gap-1.5 items-center">{fmtDate(r.next_service_due)}{dueTag(r.next_service_due)}</span> },
          ]} />
        </Card>
        <Card pad={false}>
          <div className="card-pad pb-0"><CardHeader title="Sensor calibration due" actions={<Link to="/calibration" className="text-xs text-brand-700">Calibration records</Link>} /></div>
          <DataTable rows={s.data?.calibration_due} loading={s.loading} rowKey={(r) => r.sensor_id} empty={<EmptyState title="Nothing due in this window" />} columns={[
            { key: 's', header: 'Sensor', render: (r) => <span className="mono">{r.sensor_code}</span> },
            { key: 'u', header: 'Unit', render: (r) => r.unit_code },
            { key: 'l', header: 'Last calibrated', render: (r) => fmtDate(r.last_calibrated_at) },
            { key: 'd', header: 'Due', render: (r) => <span className="flex gap-1.5 items-center">{fmtDate(r.calibration_due_at)}{dueTag(r.calibration_due_at)}</span> },
          ]} />
        </Card>
      </div>
      <div className="grid xl:grid-cols-2 gap-4">
        <Card pad={false}><div className="card-pad pb-0"><CardHeader title="Open preventive work orders" /></div><WorkOrderTable rows={pm.data?.items} loading={pm.loading} /></Card>
        <Card pad={false}><div className="card-pad pb-0"><CardHeader title="Open calibration work orders" /></div><WorkOrderTable rows={cal.data?.items} loading={cal.loading} /></Card>
      </div>
    </>
  )
}
