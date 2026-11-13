import { Download } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { DataTable, Pagination } from '../../components/common/DataTable'
import { DAY_RANGES, FilterBar, SearchInput, Segmented, Select } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { downloadFile, errorMessage } from '../../services/api/client'
import { Audit } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { fmtDateTime, humanize } from '../../utils/format'

export default function AuditTrailPage() {
  const can = useAuthStore((s) => s.can)
  const [category, setCategory] = useState('')
  const [outcome, setOutcome] = useState('')
  const [search, setSearch] = useState('')
  const [days, setDays] = useState('7')
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const start = new Date(Date.now() - Number(days) * 86400000).toISOString()
  const q = useApi(() => Audit.list({ page, page_size: 50, category: category || undefined, outcome: outcome || undefined, search: search || undefined, start }),
    [page, category, outcome, search, days])
  return (
    <>
      <PageHeader title="Audit trail" subtitle="Append-only record of security events, configuration changes, operational actions and dispositions."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Audit trail' }]}
        actions={can('reports.export') && <button className="btn-secondary" onClick={() =>
          downloadFile('/reports/export', { type: 'audit', format: 'csv', days: Number(days) }).catch((e) => toast.error(errorMessage(e)))}><Download size={15} /> Export CSV</button>} />
      <FilterBar>
        <Segmented value={days} onChange={(v) => { setDays(v); setPage(1) }} options={DAY_RANGES} />
        <Select ariaLabel="Category" value={category} onChange={(v) => { setCategory(v); setPage(1) }} placeholder="All categories" className="w-44"
          options={['SECURITY', 'CONFIG', 'OPERATIONS', 'DISPOSITION', 'DATA'].map((c) => ({ value: c, label: humanize(c) }))} />
        <Select ariaLabel="Outcome" value={outcome} onChange={(v) => { setOutcome(v); setPage(1) }} placeholder="All outcomes" className="w-40"
          options={['SUCCESS', 'FAILURE', 'DENIED'].map((c) => ({ value: c, label: humanize(c) }))} />
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Action, actor or entity" className="w-64" />
      </FilterBar>
      <div className="card p-0">
        <DataTable rows={q.data?.items} loading={q.loading} error={q.error} onRowClick={(a) => setDetail(a)} dense columns={[
          { key: 't', header: 'Timestamp', render: (a) => <span className="text-xs mono">{fmtDateTime(a.timestamp)}</span> },
          { key: 'u', header: 'Actor', render: (a) => <div className="text-xs"><div className="font-medium">{a.actor_name}</div><div className="text-ink-3">{a.actor_role}</div></div> },
          { key: 'a', header: 'Action', render: (a) => <span className="mono">{a.action}</span> },
          { key: 'c', header: 'Category', render: (a) => <Pill>{humanize(a.category)}</Pill> },
          { key: 'o', header: 'Outcome', render: (a) => <StatusPill status={a.outcome} /> },
          { key: 'e', header: 'Entity', render: (a) => <span className="text-xs">{a.entity_type}</span> },
          { key: 'ip', header: 'Source IP', render: (a) => <span className="text-xs mono">{a.ip_address || '—'}</span> },
        ]} />
        <div className="px-4 pb-3"><Pagination page={page} pageSize={50} total={q.data?.total || 0} onPage={setPage} /></div>
      </div>
      <Modal open={!!detail} onClose={() => setDetail(null)} title={String(detail?.action || '')} description={fmtDateTime(detail?.timestamp as string)} size="lg">
        <pre className="mono text-[11.5px] bg-canvas rounded-lg p-3 overflow-x-auto">{JSON.stringify(detail, null, 2)}</pre>
      </Modal>
    </>
  )
}
