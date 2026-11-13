import { AlertTriangle, Boxes, PackagePlus, PackageMinus, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Link, useNavigate } from 'react-router-dom'
import { KpiCard } from '../../components/common/Card'
import { DataTable, Pagination } from '../../components/common/DataTable'
import { Field, FilterBar, SearchInput, Select, Tabs } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Inventory, Monitoring, Org } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { Batch, Movement } from '../../types'
import { fmtDate, fmtDateTime, humanize } from '../../utils/format'

export function ExpiryCell({ b }: { b: Batch }) {
  const tone = b.expiry_bucket === 'EXPIRED' ? 'crit' : b.expiry_bucket === 'EXPIRES_30D' ? 'serious' : b.expiry_bucket === 'EXPIRES_90D' ? 'warn' : null
  return (
    <span className="flex items-center gap-1.5">
      {fmtDate(b.expiry_date)}
      {tone && <Pill tone={tone}>{b.days_to_expiry < 0 ? 'Expired' : `${b.days_to_expiry} d`}</Pill>}
    </span>
  )
}

function ReceiveModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const products = useApi(() => Inventory.products(), [], { enabled: open })
  const units = useApi(() => Monitoring.units({ status: 'ACTIVE' }), [], { enabled: open })
  const [f, setF] = useState({ batch_number: '', product_id: '', storage_unit_id: '', quantity: '', expiry_date: '', manufacturing_date: '', supplier: '', reference: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }))
  const valid = f.batch_number.length >= 2 && f.product_id && f.storage_unit_id && Number(f.quantity) > 0 && f.expiry_date
  const submit = async () => {
    setBusy(true)
    try {
      await Inventory.receive({ ...f, quantity: Number(f.quantity), expiry_date: new Date(f.expiry_date).toISOString(),
        manufacturing_date: f.manufacturing_date ? new Date(f.manufacturing_date).toISOString() : undefined,
        supplier: f.supplier || undefined, reference: f.reference || undefined })
      toast.success(`Batch ${f.batch_number} received`)
      onDone(); onClose()
    } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Record vaccine receipt" size="lg" description="Creates the batch and an immutable RECEIPT movement."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={!valid || busy} onClick={submit}>Receive stock</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Batch / lot number" required><input className="input" value={f.batch_number} onChange={(e) => set('batch_number', e.target.value)} /></Field>
        <Field label="Product" required><select className="input" value={f.product_id} onChange={(e) => set('product_id', e.target.value)}>
          <option value="">Select…</option>{(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.min_temperature}–{p.max_temperature}°C)</option>)}</select></Field>
        <Field label="Storage unit" required><select className="input" value={f.storage_unit_id} onChange={(e) => set('storage_unit_id', e.target.value)}>
          <option value="">Select…</option>{(units.data || []).map((u) => <option key={u.id} value={u.id}>{u.unit_code} — {u.name} ({u.effective_min}–{u.effective_max}°C)</option>)}</select></Field>
        <Field label="Quantity (doses)" required><input type="number" min={1} className="input" value={f.quantity} onChange={(e) => set('quantity', e.target.value)} /></Field>
        <Field label="Expiry date" required><input type="date" className="input" value={f.expiry_date} onChange={(e) => set('expiry_date', e.target.value)} /></Field>
        <Field label="Manufacturing date"><input type="date" className="input" value={f.manufacturing_date} onChange={(e) => set('manufacturing_date', e.target.value)} /></Field>
        <Field label="Supplier"><input className="input" value={f.supplier} onChange={(e) => set('supplier', e.target.value)} /></Field>
        <Field label="Delivery reference (GRN)"><input className="input" value={f.reference} onChange={(e) => set('reference', e.target.value)} /></Field>
      </div>
    </Modal>
  )
}

function FefoIssueModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const me = useAuthStore((s) => s.me)!
  const products = useApi(() => Inventory.products(), [], { enabled: open })
  const facilities = useApi(() => Org.facilities(), [], { enabled: open })
  const [product, setProduct] = useState('')
  const [facility, setFacility] = useState(me.facility_ids[0] || '')
  const [qty, setQty] = useState('')
  const [reason, setReason] = useState('Immunisation session')
  const queue = useApi(() => product && facility ? Inventory.fefo(product, facility) : Promise.resolve([]), [product, facility, open], { enabled: open })
  const [busy, setBusy] = useState(false)
  const avail = (queue.data || []).reduce((s, b) => s + b.current_quantity, 0)
  return (
    <Modal open={open} onClose={onClose} title="Issue stock (FEFO)" size="lg" description="Allocates earliest-expiring usable batches first, in one transaction."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || !product || !facility || !(Number(qty) > 0) || Number(qty) > avail} onClick={async () => {
          setBusy(true)
          try { const m = await Inventory.issueFefo({ product_id: product, facility_id: facility, quantity: Number(qty), reason })
            toast.success(`Issued from ${m.length} batch${m.length > 1 ? 'es' : ''}: ${m.map((x) => x.batch_number).join(', ')}`); onDone(); onClose() }
          catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) } }}>Issue</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Facility"><select className="input" value={facility} onChange={(e) => setFacility(e.target.value)}>
          <option value="">Select…</option>{(facilities.data || []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></Field>
        <Field label="Product"><select className="input" value={product} onChange={(e) => setProduct(e.target.value)}>
          <option value="">Select…</option>{(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
        <Field label="Quantity" hint={product ? `${avail.toLocaleString()} usable doses available` : undefined}><input type="number" className="input" value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
      {!!queue.data?.length && (
        <div className="mt-4">
          <p className="label">FEFO queue (issue order)</p>
          <ol className="divide-y divide-line rounded-lg border border-line">
            {queue.data.map((b, i) => <li key={b.id} className="flex justify-between px-3 py-2 text-xs"><span><b className="mr-2 text-ink-3">{i + 1}</b>{b.batch_number} · {b.storage_unit_code}</span><span>{b.current_quantity.toLocaleString()} · exp {fmtDate(b.expiry_date)}</span></li>)}
          </ol>
        </div>
      )}
    </Modal>
  )
}

export default function InventoryPage() {
  const can = useAuthStore((s) => s.can)
  const [tab, setTab] = useState<'batches' | 'quarantine' | 'expiring' | 'movements'>('batches')
  const [search, setSearch] = useState('')
  const [facility, setFacility] = useState('')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState<null | 'receive' | 'issue'>(null)
  const navigate = useNavigate()
  const facilities = useApi(() => Org.facilities(), [])
  const summary = useApi(() => Inventory.summary(facility || undefined), [facility])
  const batches = useApi(() => Inventory.batches({
    page, page_size: 20, search: search || undefined, facility_id: facility || undefined,
    ...(tab === 'quarantine' ? { status: ['QUARANTINED'] } : tab === 'expiring' ? { status: ['ACTIVE', 'EXPIRED'], expiring_within_days: 90 } : { status: ['ACTIVE', 'QUARANTINED', 'EXPIRED'] }),
  }), [page, search, facility, tab], { enabled: tab !== 'movements' })
  const moves = useApi(() => Inventory.movements({ page, page_size: 30, facility_id: facility || undefined }), [page, facility, tab], { enabled: tab === 'movements' })
  const reload = () => { batches.reload(); summary.reload() }
  const s = summary.data

  return (
    <>
      <PageHeader title="Vaccine inventory" subtitle="Batch-level stock, expiry, quarantine and full movement traceability."
        crumbs={[{ label: 'Home', to: '/' }, { label: 'Inventory' }]}
        actions={can('inventory.manage') && <>
          <button className="btn-secondary" onClick={() => setModal('issue')}><PackageMinus size={15} /> Issue (FEFO)</button>
          <button className="btn-primary" onClick={() => setModal('receive')}><PackagePlus size={15} /> Receive stock</button></>} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Usable doses" value={s ? s.doses_available.toLocaleString() : '—'} icon={Boxes} tone="brand" sub={s ? `${s.batches_active} active batches` : ''} />
        <KpiCard label="Expiring ≤ 30 days" value={s?.expiring_30d ?? '—'} icon={AlertTriangle} tone={s?.expiring_30d ? 'warn' : 'ok'} onClick={() => { setTab('expiring'); setPage(1) }} />
        <KpiCard label="Quarantined batches" value={s?.batches_quarantined ?? '—'} icon={ShieldAlert} tone={s?.batches_quarantined ? 'crit' : 'ok'} onClick={() => { setTab('quarantine'); setPage(1) }} />
        <KpiCard label="Expired (awaiting disposal)" value={s?.batches_expired ?? '—'} tone={s?.batches_expired ? 'crit' : 'neutral'} />
      </div>
      <Tabs value={tab} onChange={(t) => { setTab(t); setPage(1) }} tabs={[
        { value: 'batches', label: 'Batches' }, { value: 'expiring', label: 'Expiring (90 d)' },
        { value: 'quarantine', label: 'Quarantine queue', count: s?.batches_quarantined }, { value: 'movements', label: 'Movement ledger' }]} />
      <FilterBar>
        <Select ariaLabel="Facility" value={facility} onChange={(v) => { setFacility(v); setPage(1) }} placeholder="All facilities" className="w-60"
          options={(facilities.data || []).map((f) => ({ value: f.id, label: f.name }))} />
        {tab !== 'movements' && <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Batch or product" className="w-60" />}
      </FilterBar>
      <div className="card p-0">
        {tab === 'movements' ? (<>
          <DataTable<Movement> rows={moves.data?.items} loading={moves.loading} error={moves.error} columns={[
            { key: 't', header: 'When', render: (m) => <span className="text-xs">{fmtDateTime(m.created_at)}</span> },
            { key: 'b', header: 'Batch', render: (m) => <Link to={`/inventory/batches/${m.batch_id}`} className="text-brand-700 font-medium">{m.batch_number}</Link> },
            { key: 'ty', header: 'Movement', render: (m) => <StatusPill status={m.movement_type} label={humanize(m.movement_type)} /> },
            { key: 'c', header: 'Change', align: 'right', render: (m) => <span className={m.quantity_change < 0 ? 'text-crit' : m.quantity_change > 0 ? 'text-ok' : ''}>{m.quantity_change > 0 ? '+' : ''}{m.quantity_change}</span> },
            { key: 'a', header: 'Balance', align: 'right', render: (m) => m.quantity_after.toLocaleString() },
            { key: 'r', header: 'Reason / reference', render: (m) => <span className="text-xs">{m.reason}{m.reference && <span className="text-ink-3"> · {m.reference}</span>}</span> },
            { key: 'u', header: 'By', render: (m) => <span className="text-xs">{m.performed_by_name}</span> },
          ]} />
          <div className="px-4 pb-3"><Pagination page={page} pageSize={30} total={moves.data?.total || 0} onPage={setPage} /></div>
        </>) : (<>
          <DataTable<Batch> rows={batches.data?.items} loading={batches.loading} error={batches.error} onRowClick={(b) => navigate(`/inventory/batches/${b.id}`)} columns={[
            { key: 'n', header: 'Batch', render: (b) => <Link to={`/inventory/batches/${b.id}`} className="font-medium text-brand-700">{b.batch_number}</Link> },
            { key: 'p', header: 'Product', render: (b) => b.product_name },
            { key: 'f', header: 'Facility / unit', render: (b) => <div className="text-xs"><div>{b.facility_name}</div><div className="text-ink-3">{b.storage_unit_code}</div></div> },
            { key: 's', header: 'Status', render: (b) => <StatusPill status={b.status} /> },
            { key: 'q', header: 'Quantity', align: 'right', render: (b) => <span>{b.current_quantity.toLocaleString()}<span className="text-ink-3 text-xs"> / {b.quantity_received.toLocaleString()}</span></span> },
            { key: 'e', header: 'Expiry', render: (b) => <ExpiryCell b={b} /> },
            { key: 'x', header: 'Excursions', align: 'center', render: (b) => b.excursion_count ? <Pill tone="serious">{b.excursion_count}</Pill> : '—' },
          ]} />
          <div className="px-4 pb-3"><Pagination page={page} pageSize={20} total={batches.data?.total || 0} onPage={setPage} /></div>
        </>)}
      </div>
      <ReceiveModal open={modal === 'receive'} onClose={() => setModal(null)} onDone={reload} />
      <FefoIssueModal open={modal === 'issue'} onClose={() => setModal(null)} onDone={reload} />
    </>
  )
}
