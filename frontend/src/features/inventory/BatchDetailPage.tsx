import { ArrowRightLeft, ClipboardList, PackageMinus, ShieldAlert, ShieldCheck, Trash2 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Link, useParams } from 'react-router-dom'
import { Card, CardHeader, KpiCard } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { Field } from '../../components/common/Form'
import { ConfirmDialog, Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { SeverityBadge, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Inventory, Monitoring } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { Movement } from '../../types'
import { fmtDate, fmtDateTime, fmtTemp, humanize } from '../../utils/format'
import { ExpiryCell } from './InventoryPage'

type Act = null | 'issue' | 'adjust' | 'reconcile' | 'transfer' | 'quarantine' | 'release' | 'dispose'

export default function BatchDetailPage() {
  const { id = '' } = useParams()
  const can = useAuthStore((s) => s.can)
  const q = useApi(() => Inventory.batch(id), [id])
  const [act, setAct] = useState<Act>(null)
  const b = q.data
  if (q.loading && !b) return <PageSkeleton />
  if (q.error || !b) return <ErrorState message={q.error || 'Batch not found'} onRetry={q.reload} />
  const run = async (action: string, body: Record<string, unknown>, ok: string) => {
    try { await Inventory.action(id, action, body); toast.success(ok); q.reload() } catch (e) { toast.error(errorMessage(e)); throw e }
  }
  const manage = can('inventory.manage') && b.status === 'ACTIVE'

  return (
    <>
      <PageHeader title={`Batch ${b.batch_number}`} subtitle={`${b.product_name} · ${b.facility_name} · ${b.storage_unit_code}`}
        crumbs={[{ label: 'Inventory', to: '/inventory' }, { label: b.batch_number }]} meta={<StatusPill status={b.status} />}
        actions={<>
          {manage && <button className="btn-secondary" onClick={() => setAct('issue')}><PackageMinus size={15} /> Issue</button>}
          {manage && <button className="btn-secondary" onClick={() => setAct('transfer')}><ArrowRightLeft size={15} /> Transfer</button>}
          {can('inventory.manage') && b.current_quantity > 0 && <button className="btn-secondary" onClick={() => setAct('reconcile')}><ClipboardList size={15} /> Stock count</button>}
          {b.status === 'ACTIVE' && can('batches.quarantine') && <button className="btn-secondary text-serious-ink" onClick={() => setAct('quarantine')}><ShieldAlert size={15} /> Quarantine</button>}
          {b.status === 'QUARANTINED' && can('batches.release') && <button className="btn-primary" onClick={() => setAct('release')}><ShieldCheck size={15} /> Release</button>}
          {(b.status === 'QUARANTINED' || b.status === 'EXPIRED') && can('batches.dispose') && <button className="btn-danger" onClick={() => setAct('dispose')}><Trash2 size={15} /> Record disposal</button>}
        </>} />
      {b.status === 'QUARANTINED' && (
        <div className="mb-4 rounded-xl border border-serious/40 bg-serious-bg px-4 py-3 text-[13px] text-serious-ink">
          <b>Quarantined:</b> {b.quarantine_reason}. Release or disposal requires an authorised supervisor / clinical decision with documented justification.
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Current quantity" value={b.current_quantity.toLocaleString()} sub={`of ${b.quantity_received.toLocaleString()} received (${b.unit_of_measure})`} />
        <KpiCard label="Expiry" value={<span className="text-xl"><ExpiryCell b={b} /></span>} />
        <KpiCard label="Temperature incidents" value={b.incidents.length} tone={b.incidents.length ? 'serious' : 'ok'} />
        <KpiCard label="Movements" value={b.movements.length} />
      </div>
      <div className="grid xl:grid-cols-[1fr_340px] gap-4">
        <div className="space-y-4 min-w-0">
          <Card pad={false}>
            <div className="card-pad pb-0"><CardHeader title="Movement history" subtitle="Append-only ledger — entries are never edited or deleted." /></div>
            <DataTable<Movement> rows={b.movements} columns={[
              { key: 't', header: 'When', render: (m) => <span className="text-xs">{fmtDateTime(m.created_at)}</span> },
              { key: 'ty', header: 'Movement', render: (m) => <StatusPill status={m.movement_type} label={humanize(m.movement_type)} /> },
              { key: 'c', header: 'Change', align: 'right', render: (m) => <span className={m.quantity_change < 0 ? 'text-crit' : m.quantity_change > 0 ? 'text-ok' : ''}>{m.quantity_change > 0 ? '+' : ''}{m.quantity_change}</span> },
              { key: 'a', header: 'Balance', align: 'right', render: (m) => m.quantity_after.toLocaleString() },
              { key: 's', header: 'Status', render: (m) => <span className="text-xs">{m.status_before === m.status_after ? humanize(m.status_after) : `${humanize(m.status_before)} → ${humanize(m.status_after)}`}</span> },
              { key: 'r', header: 'Reason', render: (m) => <span className="text-xs">{m.reason}{m.reference && <span className="text-ink-3"> · {m.reference}</span>}</span> },
              { key: 'u', header: 'By', render: (m) => <span className="text-xs">{m.performed_by_name}</span> },
            ]} />
          </Card>
          <Card pad={false}>
            <div className="card-pad pb-0"><CardHeader title="Related temperature excursions" /></div>
            {b.incidents.length ? (
              <DataTable rows={b.incidents} columns={[
                { key: 'n', header: 'Incident', render: (i) => <Link to={`/incidents/${i.id}`} className="text-brand-700 font-medium">{i.incident_number}</Link> },
                { key: 's', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
                { key: 'st', header: 'Status', render: (i) => <StatusPill status={i.status} /> },
                { key: 'p', header: 'Peak', align: 'right', render: (i) => fmtTemp(i.peak_temperature) },
                { key: 'w', header: 'Window', render: (i) => <span className="text-xs">{fmtDateTime(i.excursion_start)} → {i.excursion_end ? fmtDateTime(i.excursion_end) : 'ongoing'}</span> },
                { key: 'd', header: 'Disposition', render: (i) => <span className="text-xs">{i.vaccine_disposition || '—'}</span> },
              ]} />
            ) : <EmptyState title="No excursions recorded while this batch was stored" />}
          </Card>
        </div>
        <Card>
          <CardHeader title="Batch record" />
          <dl className="text-[13px] space-y-2">
            {[['Product', b.product_name], ['Manufacturer', b.manufacturer], ['Manufactured', fmtDate(b.manufacturing_date)], ['Received', fmtDate(b.receipt_date)],
              ['Supplier', b.supplier], ['Facility', b.facility_name], ['Storage unit', b.storage_unit_code]].map(([k, v]) => (
              <div key={k as string} className="flex justify-between gap-2 border-b border-line pb-2 last:border-0"><dt className="text-ink-3">{k}</dt><dd className="text-right">{v || '—'}</dd></div>
            ))}
          </dl>
        </Card>
      </div>

      <QtyDialog open={act === 'issue'} onClose={() => setAct(null)} title="Issue stock" fefo
        onSubmit={(qty, reason, override) => run('issue', { quantity: qty, reason, override_fefo_reason: override || undefined }, 'Stock issued')} />
      <QtyDialog open={act === 'reconcile'} onClose={() => setAct(null)} title="Physical stock count" label="Counted quantity" allowZero
        onSubmit={(qty, reason) => run('reconcile', { counted_quantity: qty, reason }, 'Reconciliation recorded')} />
      <TransferDialog open={act === 'transfer'} onClose={() => setAct(null)} productRange={null}
        onSubmit={(unit, reason) => run('transfer', { to_storage_unit_id: unit, reason }, 'Batch transferred')} />
      <ConfirmDialog open={act === 'quarantine'} onClose={() => setAct(null)} title="Quarantine batch" reasonLabel="Reason (e.g. incident number)" reasonRequired minReason={3}
        confirmLabel="Quarantine" danger onConfirm={(r) => run('quarantine', { reason: r }, 'Batch quarantined')} />
      <ConfirmDialog open={act === 'release'} onClose={() => setAct(null)} title="Release from quarantine"
        description="Authorised disposition: document the evidence (e.g. stability data, manufacturer guidance) supporting release."
        reasonLabel="Release justification" reasonRequired minReason={10} confirmLabel="Release batch" onConfirm={(r) => run('release', { reason: r }, 'Batch released')} />
      <ConfirmDialog open={act === 'dispose'} onClose={() => setAct(null)} title="Record disposal" danger typeToConfirm={b.batch_number}
        description="All remaining doses are written off. This cannot be undone."
        reasonLabel="Disposal justification" reasonRequired minReason={10} confirmLabel="Record disposal" onConfirm={(r) => run('dispose', { reason: r }, 'Disposal recorded')} />
    </>
  )
}

function QtyDialog({ open, onClose, onSubmit, title, label = 'Quantity', fefo, allowZero }: {
  open: boolean; onClose: () => void; title: string; label?: string; fefo?: boolean; allowZero?: boolean
  onSubmit: (qty: number, reason: string, override?: string) => Promise<unknown>
}) {
  const [qty, setQty] = useState('')
  const [reason, setReason] = useState('')
  const [override, setOverride] = useState('')
  const [needOverride, setNeedOverride] = useState(false)
  const ok = allowZero ? qty !== '' && Number(qty) >= 0 : Number(qty) > 0
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!ok || (needOverride && override.length < 5)} onClick={async () => {
          try { await onSubmit(Number(qty), reason, needOverride ? override : undefined); onClose() }
          catch (e) { if (fefo && errorMessage(e).includes('FEFO')) setNeedOverride(true) } }}>Confirm</button></>}>
      <div className="space-y-3">
        <Field label={label} required><input type="number" className="input" value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {needOverride && <Field label="FEFO override justification" required hint="An earlier-expiring batch exists. Overrides are audited.">
          <input className="input" value={override} onChange={(e) => setOverride(e.target.value)} /></Field>}
      </div>
    </Modal>
  )
}

function TransferDialog({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; productRange: null; onSubmit: (unit: string, reason: string) => Promise<unknown> }) {
  const units = useApi(() => Monitoring.units({ status: 'ACTIVE' }), [], { enabled: open })
  const [unit, setUnit] = useState('')
  const [reason, setReason] = useState('')
  return (
    <Modal open={open} onClose={onClose} title="Transfer batch" size="sm"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!unit} onClick={async () => { try { await onSubmit(unit, reason); onClose() } catch { /* */ } }}>Transfer</button></>}>
      <div className="space-y-3">
        <Field label="Destination storage unit" required><select className="input" value={unit} onChange={(e) => setUnit(e.target.value)}>
          <option value="">Select…</option>{(units.data || []).map((u) => <option key={u.id} value={u.id}>{u.unit_code} — {u.name}</option>)}</select></Field>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
