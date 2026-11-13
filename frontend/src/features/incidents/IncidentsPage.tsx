import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { DataTable, Pagination } from '../../components/common/DataTable'
import { FilterBar, SearchInput, Segmented, Select } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { SeverityBadge, SimulatedTag, SourceTag, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { Incidents, Org } from '../../services/api/endpoints'
import type { Incident } from '../../types'
import { ago, fmtDateTime, fmtDuration, humanize } from '../../utils/format'

const TYPES = ['TEMPERATURE_EXCURSION', 'SENSOR_OFFLINE', 'MISSING_TELEMETRY', 'ABNORMAL_PATTERN', 'EQUIPMENT_FAILURE']

export default function IncidentsPage() {
  const [params, setParams] = useSearchParams()
  const [scope, setScope] = useState<'active' | 'review' | 'all' | 'closed'>((params.get('view') as 'active') || 'active')
  const [severity, setSeverity] = useState('')
  const [type, setType] = useState('')
  const [facility, setFacility] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const navigate = useNavigate()
  const unit = params.get('unit') || undefined
  const facilities = useApi(() => Org.facilities(), [])
  const q = useApi(() => Incidents.list({
    page, page_size: 20, severity: severity || undefined, incident_type: type || undefined, facility_id: facility || undefined,
    search: search || undefined, storage_unit_id: unit,
    ...(scope === 'active' ? { active: true } : scope === 'closed' ? { active: false } : scope === 'review' ? { status: ['CORRECTIVE_ACTION_PENDING', 'UNDER_REVIEW'] } : {}),
  }), [page, scope, severity, type, facility, search, unit], { refreshOn: ['incident.created', 'incident.updated'] })

  return (
    <>
      <PageHeader title="Incidents" subtitle="Temperature excursions, connectivity loss, equipment failures and decision-support signals."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Incidents' }]} />
      <FilterBar>
        <Segmented value={scope} onChange={(v) => { setScope(v); setPage(1); setParams({}) }} options={[
          { value: 'active', label: 'Active' }, { value: 'review', label: 'Awaiting review' }, { value: 'closed', label: 'Resolved / closed' }, { value: 'all', label: 'All' }]} />
        <Select ariaLabel="Severity" value={severity} onChange={(v) => { setSeverity(v); setPage(1) }} placeholder="All severities" className="w-40"
          options={['CRITICAL', 'HIGH', 'WARNING'].map((s) => ({ value: s, label: humanize(s) }))} />
        <Select ariaLabel="Type" value={type} onChange={(v) => { setType(v); setPage(1) }} placeholder="All types" className="w-52"
          options={TYPES.map((t) => ({ value: t, label: humanize(t) }))} />
        <Select ariaLabel="Facility" value={facility} onChange={(v) => { setFacility(v); setPage(1) }} placeholder="All facilities" className="w-56"
          options={(facilities.data || []).map((f) => ({ value: f.id, label: f.name }))} />
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Incident # or title" className="w-56" />
      </FilterBar>
      <div className="card p-0">
        <DataTable<Incident> rows={q.data?.items} loading={q.loading} error={q.error} onRetry={q.reload}
          onRowClick={(i) => navigate(`/incidents/${i.id}`)} columns={[
            { key: 'n', header: 'Incident', render: (i) => (
              <div><Link to={`/incidents/${i.id}`} className="font-medium text-brand-700">{i.incident_number}</Link>
                <div className="text-xs text-ink-3 max-w-72 truncate">{i.title}</div></div>) },
            { key: 'sv', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
            { key: 'st', header: 'Status', render: (i) => <StatusPill status={i.status} /> },
            { key: 'ty', header: 'Type', render: (i) => <span className="text-xs whitespace-nowrap">{humanize(i.incident_type)}</span> },
            { key: 'src', header: 'Source', render: (i) => <div className="flex gap-1"><SourceTag source={i.source} /><SimulatedTag show={i.is_simulated} /></div> },
            { key: 'f', header: 'Facility / unit', render: (i) => <div className="text-xs max-w-52"><div className="truncate" title={i.facility_name || ''}>{i.facility_name}</div><div className="text-ink-3 whitespace-nowrap">{i.storage_unit_code}</div></div> },
            { key: 'a', header: 'Assignee', render: (i) => i.assignee_name || <span className="text-ink-3">Unassigned</span> },
            { key: 'e', header: 'Esc.', align: 'center', render: (i) => i.escalation_level ? <span className="font-semibold text-crit">L{i.escalation_level}</span> : '—' },
            { key: 'd', header: 'Detected', render: (i) => <span title={fmtDateTime(i.created_at)} className="text-xs whitespace-nowrap">{ago(i.created_at)}</span> },
            { key: 'du', header: 'Duration', align: 'right', render: (i) => <span className="text-xs">{fmtDuration(i.duration_seconds)}</span> },
          ]} />
        <div className="px-4 pb-3"><Pagination page={page} pageSize={20} total={q.data?.total || 0} onPage={setPage} /></div>
      </div>
    </>
  )
}
