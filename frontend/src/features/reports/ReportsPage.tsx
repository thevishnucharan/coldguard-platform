import { Download, FileSpreadsheet, FileText } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader } from '../../components/common/Card'
import { EmptyState, LoadingBlock } from '../../components/common/Feedback'
import { DAY_RANGES, Field, Segmented, Select } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { useApi } from '../../hooks/useApi'
import { downloadFile, errorMessage } from '../../services/api/client'
import { Org, Reports } from '../../services/api/endpoints'

const DESCRIPTIONS: Record<string, string> = {
  temperature: 'Every reading with quality flag and source; simulated readings are marked.',
  incidents: 'Incidents, root cause, corrective actions, review decisions and vaccine disposition.',
  inventory_movements: 'Immutable stock ledger: receipts, issues, transfers, quarantine, release, disposal.',
  stock: 'Current batch status, quantities and expiry by facility.',
  maintenance: 'Work orders with trigger, assignee, repairs and verification.',
  calibration: 'Calibration results, offsets, due dates and certificates.',
  compliance: 'Per-facility compliance %, excursions, MTTA / MTTR and equipment work orders.',
  device_reliability: 'Sensor availability over 24 h, battery and status.',
  audit: 'Platform audit trail: who did what, when, from where, with what outcome.',
}

export default function ReportsPage() {
  const types = useApi(() => Reports.types(), [])
  const facilities = useApi(() => Org.facilities(), [])
  const [days, setDays] = useState('7')
  const [facility, setFacility] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const download = async (key: string, format: 'csv' | 'pdf') => {
    setBusy(`${key}-${format}`)
    try { await downloadFile('/reports/export', { type: key, format, days: Number(days), facility_id: facility || undefined }); toast.success('Report downloaded') }
    catch (e) { toast.error(errorMessage(e, 'Export failed')) } finally { setBusy(null) }
  }
  return (
    <>
      <PageHeader title="Reports & exports" subtitle="Only data within your authorised scope is included. Every export is recorded in the audit trail."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Reports' }]} />
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Period"><Segmented value={days} onChange={setDays} options={DAY_RANGES} /></Field>
          <Field label="Facility"><Select value={facility} onChange={setFacility} placeholder="All facilities in scope" className="w-64"
            options={(facilities.data || []).map((f) => ({ value: f.id, label: f.name }))} /></Field>
        </div>
      </Card>
      {types.loading ? <LoadingBlock /> : !types.data?.reports.length ? <div className="card"><EmptyState title="No reports available for your role" /></div> : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {types.data.reports.map((r) => (
            <Card key={r.key}>
              <CardHeader title={<span className="flex items-center gap-2"><FileText size={15} className="text-brand-600" />{r.label}</span>} subtitle={DESCRIPTIONS[r.key]} />
              {types.data!.can_export ? (
                <div className="flex gap-2">
                  <button className="btn-secondary btn-sm" disabled={!!busy} onClick={() => download(r.key, 'csv')}><FileSpreadsheet size={14} /> {busy === `${r.key}-csv` ? 'Preparing…' : 'CSV'}</button>
                  <button className="btn-secondary btn-sm" disabled={!!busy} onClick={() => download(r.key, 'pdf')}><Download size={14} /> {busy === `${r.key}-pdf` ? 'Preparing…' : 'PDF'}</button>
                </div>
              ) : <p className="text-xs text-ink-3">Export not permitted for your role.</p>}
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
