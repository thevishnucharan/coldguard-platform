import { ClipboardCheck, ShieldAlert } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Card, CardHeader } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SeverityBadge } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Dashboards } from '../../services/api/endpoints'
import { ago } from '../../utils/format'

export default function ApprovalQueue() {
  const q = useApi(() => Dashboards.supervisor(), [], { refreshOn: ['incident.updated', 'incident.created'] })
  const navigate = useNavigate()
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'No data'} onRetry={q.reload} />
  const d = q.data
  return (
    <>
      <PageHeader title="Approval queue" subtitle="Decisions only an authorised supervisor can make. Open an item to review evidence before deciding."
        crumbs={[{ label: 'Regional overview', to: '/supervisor' }, { label: 'Approval queue' }]} />
      <Card pad={false} className="mb-4">
        <div className="card-pad pb-0"><CardHeader title={`Incident decisions (${d.approval_queue.length})`} /></div>
        <DataTable rows={d.approval_queue} rowKey={(r) => r.kind + r.incident_id + (r.corrective_action_id || '')}
          onRowClick={(r) => navigate(`/incidents/${r.incident_id}`)} empty={<EmptyState icon={ClipboardCheck} title="Queue is clear" />} columns={[
            { key: 'k', header: 'Decision', render: (r) => <Pill tone={r.kind === 'CORRECTIVE_ACTION' ? 'info' : 'brand'}>{r.kind === 'CORRECTIVE_ACTION' ? 'Approve corrective action' : 'Review & resolve incident'}</Pill> },
            { key: 'i', header: 'Incident', render: (r) => <span className="font-medium text-brand-700">{r.incident_number}</span> },
            { key: 'd', header: 'Proposal / summary', render: (r) => <span className="text-xs line-clamp-2 max-w-md">{r.title}</span> },
            { key: 'p', header: 'Proposed by', render: (r) => r.proposed_by || '—' },
            { key: 'f', header: 'Facility', render: (r) => <span className="text-xs">{r.facility_name}</span> },
            { key: 's', header: 'Severity', render: (r) => <SeverityBadge severity={r.severity} /> },
            { key: 'w', header: 'Waiting', render: (r) => <span className="text-xs">{ago(r.at)}</span> },
          ]} />
      </Card>
      <Card pad={false}>
        <div className="card-pad pb-0"><CardHeader title={<span className="flex items-center gap-2"><ShieldAlert size={15} className="text-serious-ink" />Quarantined batches awaiting disposition ({d.quarantined_batches.length})</span>}
          subtitle="Release or disposal must be documented on the batch record." /></div>
        <DataTable rows={d.quarantined_batches} onRowClick={(b) => navigate(`/inventory/batches/${b.id}`)} empty={<EmptyState title="No quarantined stock" />} columns={[
          { key: 'b', header: 'Batch', render: (b) => <Link to={`/inventory/batches/${b.id}`} className="font-medium text-brand-700">{b.batch_number}</Link> },
          { key: 'p', header: 'Product', render: (b) => b.product },
          { key: 'q', header: 'Doses', align: 'right', render: (b) => b.quantity.toLocaleString() },
          { key: 'r', header: 'Quarantine reason', render: (b) => <span className="text-xs">{b.reason}</span> },
        ]} />
      </Card>
    </>
  )
}
