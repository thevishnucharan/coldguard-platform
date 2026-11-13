import { ArrowUpCircle, Bot, CheckCircle2, ClipboardCheck, MessageSquare, ShieldCheck, UserCheck, Wrench, XCircle } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import toast from 'react-hot-toast'
import { Link, useParams } from 'react-router-dom'
import { TemperatureChart } from '../../components/charts/TemperatureChart'
import { Card, CardHeader } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { EmptyState, ErrorState, LoadingBlock, PageSkeleton } from '../../components/common/Feedback'
import { Field } from '../../components/common/Form'
import { ConfirmDialog, Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, SeverityBadge, SimulatedTag, SourceTag, StatusPill } from '../../components/common/Status'
import { IncidentTimeline } from '../../components/incidents/IncidentTimeline'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Incidents, Maintenance, Users } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { CorrectiveAction, IncidentDetail } from '../../types'
import { fmtDate, fmtDateTime, fmtDuration, fmtTemp, humanize } from '../../utils/format'

type Dialog = null | 'ack' | 'investigate' | 'note' | 'escalate' | 'propose' | 'verify' | 'resolve' | 'more' | 'close' | 'false_alarm' | 'assign' | 'workorder'

function Row({ k, v }: { k: string; v: ReactNode }) {
  return <div className="flex justify-between gap-3 py-1.5 border-b border-line last:border-0 text-[13px]"><span className="text-ink-3">{k}</span><span className="text-right">{v}</span></div>
}

export default function IncidentDetailPage() {
  const { id = '' } = useParams()
  const can = useAuthStore((s) => s.can)
  const q = useApi(() => Incidents.get(id), [id], { refreshOn: ['incident.updated'] })
  const evidence = useApi(() => Incidents.evidence(id), [id], { refreshOn: ['incident.updated'] })
  const batches = useApi(() => Incidents.affectedBatches(id), [id], { enabled: can('inventory.view') })
  const [dialog, setDialog] = useState<Dialog>(null)
  const [caReview, setCaReview] = useState<{ ca: CorrectiveAction; decision: 'approve' | 'reject' | 'request_revision' } | null>(null)
  const [caImpl, setCaImpl] = useState<CorrectiveAction | null>(null)
  const [ai, setAi] = useState<string | null>(null)

  const inc = q.data
  if (q.loading && !inc) return <PageSkeleton />
  if (q.error || !inc) return <ErrorState message={q.error || 'Incident not found'} onRetry={q.reload} />
  const acts = new Set(inc.available_actions)
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { const r = await fn(); toast.success(ok); if (r && (r as IncidentDetail).events) q.setData(r as IncidentDetail); else q.reload(); evidence.reload() }
    catch (e) { toast.error(errorMessage(e)); throw e }
  }

  return (
    <>
      <PageHeader title={<span className="flex items-center gap-2">{inc.incident_number}</span>} subtitle={inc.title}
        crumbs={[{ label: 'Incidents', to: '/incidents' }, { label: inc.incident_number }]}
        meta={<><SeverityBadge severity={inc.severity} /><StatusPill status={inc.status} /><Pill>{humanize(inc.incident_type)}</Pill>
          <SourceTag source={inc.source} /><SimulatedTag show={inc.is_simulated} />
          {inc.escalation_level > 0 && <Pill tone="crit" icon={ArrowUpCircle}>Escalation L{inc.escalation_level}</Pill>}</>}
        actions={<>
          {acts.has('acknowledge') && <button className="btn-primary" onClick={() => setDialog('ack')}><UserCheck size={15} /> Acknowledge</button>}
          {acts.has('investigate') && <button className="btn-primary" onClick={() => setDialog('investigate')}>Start investigation</button>}
          {acts.has('propose_corrective_action') && <button className="btn-primary" onClick={() => setDialog('propose')}><ClipboardCheck size={15} /> Propose corrective action</button>}
          {acts.has('verify_recovery') && <button className="btn-primary" onClick={() => setDialog('verify')}><ShieldCheck size={15} /> Verify recovery</button>}
          {acts.has('review') && <><button className="btn-primary" onClick={() => setDialog('resolve')}><CheckCircle2 size={15} /> Resolve</button>
            <button className="btn-secondary" onClick={() => setDialog('more')}>Request more investigation</button></>}
          {acts.has('close') && <button className="btn-primary" onClick={() => setDialog('close')}>Close with disposition</button>}
          {acts.has('add_note') && <button className="btn-secondary" onClick={() => setDialog('note')}><MessageSquare size={15} /> Note</button>}
          {acts.has('escalate') && <button className="btn-secondary" onClick={() => setDialog('escalate')}><ArrowUpCircle size={15} /> Escalate</button>}
        </>} />

      {inc.source === 'ML' && (
        <div className="mb-4 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-[13px] text-brand-700">
          This incident was raised by statistical/ML anomaly detection as <b>decision support</b>. It is not a confirmed temperature excursion
          and does not imply any action on stock. Approved threshold rules determine excursions.
        </div>
      )}

      <div className="grid xl:grid-cols-[1fr_360px] gap-4">
        <div className="space-y-4 min-w-0">
          <Card>
            <CardHeader title="Temperature evidence" subtitle={`Readings around the incident window (±60 min). Red band: excursion period${inc.peak_temperature !== null ? ` · peak ${fmtTemp(inc.peak_temperature)}` : ''}`} />
            {evidence.error ? <ErrorState message={evidence.error} /> : !evidence.data ? <LoadingBlock rows={5} /> :
              evidence.data.points.length ? <TemperatureChart height={280} points={evidence.data.points.map((p: { t: string; v: number; sim: boolean; anomaly: string | null }) => p)}
                min={evidence.data.min_limit} max={evidence.data.max_limit} window={{ start: evidence.data.window_start, end: evidence.data.window_end }} />
                : <EmptyState title="No readings in this window" description="For connectivity incidents the absence of data is itself the evidence." />}
          </Card>

          <Card>
            <CardHeader title="Corrective actions" subtitle="Operator proposes → supervisor approves → operator implements and verifies recovery." />
            {!inc.corrective_actions.length ? <EmptyState title="No corrective action proposed yet" /> : (
              <ul className="space-y-3">
                {inc.corrective_actions.map((ca) => (
                  <li key={ca.id} className="rounded-lg border border-line p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2"><StatusPill status={ca.status} /><span className="text-xs text-ink-3">{humanize(ca.action_type)} · proposed by {ca.proposer_name} · {fmtDateTime(ca.created_at)}</span></div>
                      <div className="flex gap-1.5">
                        {ca.status === 'PROPOSED' && acts.has('review_corrective_action') && <>
                          <button className="btn-primary btn-sm" onClick={() => setCaReview({ ca, decision: 'approve' })}>Approve</button>
                          <button className="btn-secondary btn-sm" onClick={() => setCaReview({ ca, decision: 'request_revision' })}>Request revision</button>
                          <button className="btn-secondary btn-sm text-crit" onClick={() => setCaReview({ ca, decision: 'reject' })}>Reject</button></>}
                        {ca.status === 'APPROVED' && acts.has('implement_corrective_action') &&
                          <button className="btn-primary btn-sm" onClick={() => setCaImpl(ca)}>Mark implemented</button>}
                      </div>
                    </div>
                    {ca.root_cause && <p className="text-xs mt-2"><span className="text-ink-3">Root cause: </span>{ca.root_cause}</p>}
                    <p className="text-[13px] mt-1">{ca.description}</p>
                    {ca.review_comment && <p className="text-xs mt-2 text-ink-2"><span className="text-ink-3">{ca.reviewer_name}: </span>{ca.review_comment}</p>}
                    {ca.implementation_notes && <p className="text-xs mt-1 text-ink-2"><span className="text-ink-3">Implementation: </span>{ca.implementation_notes}</p>}
                    {ca.due_date && ca.status === 'APPROVED' && <p className="text-[11px] text-ink-3 mt-1">Due {fmtDate(ca.due_date)}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {can('inventory.view') && (
            <Card pad={false}>
              <div className="card-pad pb-0"><CardHeader title={`Potentially affected batches (${batches.data?.length ?? inc.affected_batch_count})`}
                subtitle="Batches present in the unit during the excursion window. Disposition is a recorded human decision — never automatic." /></div>
              <DataTable rows={batches.data} loading={batches.loading} error={batches.error} rowKey={(b) => b.batch_id}
                empty={<EmptyState title="No batches were stored in this unit during the window" />} columns={[
                  { key: 'b', header: 'Batch', render: (b) => <Link className="font-medium text-brand-700" to={`/inventory/batches/${b.batch_id}`}>{b.batch_number}</Link> },
                  { key: 'p', header: 'Product', render: (b) => b.product_name },
                  { key: 's', header: 'Status', render: (b) => <StatusPill status={b.status} /> },
                  { key: 'q', header: 'Quantity', align: 'right', render: (b) => b.current_quantity.toLocaleString() },
                  { key: 'e', header: 'Expiry', render: (b) => fmtDate(b.expiry_date) },
                ]} />
            </Card>
          )}

          <Card>
            <CardHeader title="Timeline" subtitle="Immutable record of every transition, note and decision." />
            <IncidentTimeline events={inc.events} />
          </Card>
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Details" />
            <Row k="Facility" v={inc.facility_name || '—'} />
            <Row k="Storage unit" v={inc.storage_unit_id ? <Link className="text-brand-700" to={`/monitoring/units/${inc.storage_unit_id}`}>{inc.storage_unit_code}</Link> : '—'} />
            <Row k="Sensor" v={<span className="mono">{inc.sensor_code || '—'}</span>} />
            <Row k="Approved range" v={inc.limit_min !== null ? `${inc.limit_min} – ${inc.limit_max}°C` : '—'} />
            <Row k="Detected" v={fmtDateTime(inc.created_at)} />
            <Row k="Acknowledged" v={fmtDateTime(inc.acknowledged_at)} />
            <Row k="Duration" v={fmtDuration(inc.duration_seconds)} />
            <Row k="Assigned operator" v={<span className="flex items-center gap-2 justify-end">{inc.assignee_name || 'Unassigned'}
              {acts.has('assign') && <button className="text-xs text-brand-700 hover:underline" onClick={() => setDialog('assign')}>Change</button>}</span>} />
            {inc.escalation_reason && <Row k="Escalation" v={<span className="text-crit text-xs">{inc.escalation_reason}</span>} />}
            {inc.review_decision && <Row k="Review decision" v={humanize(inc.review_decision)} />}
          </Card>
          {inc.description && <Card><CardHeader title="Description" /><p className="text-[13px] text-ink-2 whitespace-pre-wrap">{inc.description}</p></Card>}
          {inc.investigation_notes && <Card><CardHeader title="Investigation notes" /><p className="text-xs text-ink-2 whitespace-pre-wrap leading-relaxed">{inc.investigation_notes}</p></Card>}
          {(inc.vaccine_disposition || inc.closure_evidence) && (
            <Card><CardHeader title="Closure" />
              {inc.closure_evidence && <p className="text-xs"><span className="text-ink-3">Evidence: </span>{inc.closure_evidence}</p>}
              {inc.vaccine_disposition && <p className="text-xs mt-2"><span className="text-ink-3">Vaccine disposition: </span>{inc.vaccine_disposition}</p>}
            </Card>)}
          <Card>
            <CardHeader title="Other actions" />
            <div className="flex flex-col gap-2">
              {acts.has('create_work_order') && inc.storage_unit_id && <button className="btn-secondary justify-start" onClick={() => setDialog('workorder')}><Wrench size={15} /> Raise work order</button>}
              {acts.has('close_false_alarm') && <button className="btn-secondary justify-start" onClick={() => setDialog('false_alarm')}><XCircle size={15} /> Close as false alarm</button>}
              {can('incidents.investigate') && inc.incident_type === 'TEMPERATURE_EXCURSION' && (
                <button className="btn-secondary justify-start" onClick={async () => { try { setAi((await Incidents.aiSummary(id)).ai_summary) } catch (e) { toast.error(errorMessage(e)) } }}>
                  <Bot size={15} /> Generate investigation checklist</button>)}
              {!inc.available_actions.length && <p className="text-xs text-ink-3">You have read-only access to this incident.</p>}
            </div>
            {(ai || inc.ai_summary) && <div className="mt-3 rounded-lg bg-canvas p-3 text-xs whitespace-pre-wrap text-ink-2">
              <p className="font-medium text-ink mb-1">Assistant output (template-based, not a safety decision)</p>{ai || inc.ai_summary}</div>}
          </Card>
        </aside>
      </div>

      {/* --- dialogs --- */}
      <ConfirmDialog open={dialog === 'ack'} onClose={() => setDialog(null)} title="Acknowledge incident" reasonLabel="Initial notes (optional)"
        confirmLabel="Acknowledge" onConfirm={(n) => run(() => Incidents.acknowledge(id, n || undefined), 'Incident acknowledged')} />
      <ConfirmDialog open={dialog === 'investigate'} onClose={() => setDialog(null)} title="Start investigation" reasonLabel="Investigation notes"
        confirmLabel="Start" onConfirm={(n) => run(() => Incidents.investigate(id, n || undefined), 'Investigation started')} />
      <ConfirmDialog open={dialog === 'note'} onClose={() => setDialog(null)} title="Add investigation note" reasonLabel="Note" reasonRequired
        confirmLabel="Add note" onConfirm={(n) => run(() => Incidents.note(id, n), 'Note added')} />
      <ConfirmDialog open={dialog === 'escalate'} onClose={() => setDialog(null)} title="Escalate to supervisor" reasonLabel="Reason" reasonRequired minReason={3}
        confirmLabel="Escalate" danger onConfirm={(n) => run(() => Incidents.escalate(id, n), 'Escalated')} />
      <ConfirmDialog open={dialog === 'verify'} onClose={() => setDialog(null)} title="Verify operational recovery"
        description="Confirm the unit is stable within its approved range and the corrective action is effective. The incident moves to supervisor review."
        reasonLabel="Verification notes" reasonRequired confirmLabel="Submit for review" onConfirm={(n) => run(() => Incidents.verifyRecovery(id, n), 'Submitted for supervisor review')} />
      <ConfirmDialog open={dialog === 'resolve'} onClose={() => setDialog(null)} title="Resolve incident" reasonLabel="Review notes"
        confirmLabel="Resolve" onConfirm={(n) => run(() => Incidents.review(id, 'resolve', n || undefined), 'Incident resolved')} />
      <ConfirmDialog open={dialog === 'more'} onClose={() => setDialog(null)} title="Request further investigation" reasonLabel="What is missing?" reasonRequired
        confirmLabel="Send back" onConfirm={(n) => run(() => Incidents.review(id, 'request_more_investigation', n), 'Sent back to operator')} />
      <ConfirmDialog open={dialog === 'false_alarm'} onClose={() => setDialog(null)} title="Close as false alarm" danger
        description="Use only when evidence shows no real excursion (e.g. probe removed for testing). This is recorded in the audit trail."
        reasonLabel="Justification" reasonRequired minReason={10} confirmLabel="Close incident"
        onConfirm={(n) => run(() => Incidents.close(id, { false_alarm: true, closure_evidence: n }), 'Closed as false alarm')} />
      <CloseDialog open={dialog === 'close'} onClose={() => setDialog(null)} needsDisposition={inc.affected_batch_count > 0}
        onSubmit={(b) => run(() => Incidents.close(id, b), 'Incident closed')} />
      <ProposeDialog open={dialog === 'propose'} onClose={() => setDialog(null)} onSubmit={(b) => run(() => Incidents.proposeCA(id, b), 'Corrective action sent for approval')} />
      <AssignDialog open={dialog === 'assign'} onClose={() => setDialog(null)} facilityId={inc.facility_id}
        onSubmit={(uid) => run(() => Incidents.assign(id, uid), 'Assigned')} />
      <ConfirmDialog open={dialog === 'workorder'} onClose={() => setDialog(null)} title="Raise maintenance work order" reasonLabel="Describe the equipment problem" reasonRequired minReason={5}
        confirmLabel="Create work order" onConfirm={(n) => run(() => Maintenance.create({ facility_id: inc.facility_id, storage_unit_id: inc.storage_unit_id,
          incident_id: inc.id, title: `Repair for ${inc.incident_number}`, description: n, priority: inc.severity === 'CRITICAL' ? 'URGENT' : 'HIGH' }), 'Work order created')} />
      {caReview && <ConfirmDialog open onClose={() => setCaReview(null)} danger={caReview.decision === 'reject'}
        title={caReview.decision === 'approve' ? 'Approve corrective action' : caReview.decision === 'reject' ? 'Reject corrective action' : 'Request revision'}
        description={caReview.ca.description} reasonLabel="Comment" reasonRequired={caReview.decision !== 'approve'}
        confirmLabel={humanize(caReview.decision)} onConfirm={(c) => run(() => Incidents.reviewCA(id, caReview.ca.id, caReview.decision, c || undefined), 'Decision recorded')} />}
      {caImpl && <ConfirmDialog open onClose={() => setCaImpl(null)} title="Mark corrective action implemented" description={caImpl.description}
        reasonLabel="Implementation notes" reasonRequired confirmLabel="Mark implemented" onConfirm={(n) => run(() => Incidents.implementCA(id, caImpl.id, n), 'Implementation recorded')} />}
    </>
  )
}

function ProposeDialog({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (b: Record<string, unknown>) => Promise<unknown> }) {
  const [rootCause, setRootCause] = useState('')
  const [description, setDescription] = useState('')
  const [actionType, setActionType] = useState('EQUIPMENT')
  const [busy, setBusy] = useState(false)
  return (
    <Modal open={open} onClose={onClose} title="Propose corrective action" description="Sent to your regional supervisor for approval."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || description.trim().length < 5} onClick={async () => {
          setBusy(true); try { await onSubmit({ root_cause: rootCause || undefined, description, action_type: actionType }); onClose() } catch { /* toast shown */ } finally { setBusy(false) } }}>Submit for approval</button></>}>
      <div className="space-y-3">
        <Field label="Root cause"><textarea className="input h-20 py-2" value={rootCause} onChange={(e) => setRootCause(e.target.value)} /></Field>
        <Field label="Corrective action" required><textarea className="input h-24 py-2" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Field label="Category"><select className="input" value={actionType} onChange={(e) => setActionType(e.target.value)}>
          {['EQUIPMENT', 'POWER', 'PROCEDURE', 'TRAINING', 'OPERATIONAL'].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</select></Field>
      </div>
    </Modal>
  )
}

function CloseDialog({ open, onClose, onSubmit, needsDisposition }: { open: boolean; onClose: () => void; needsDisposition: boolean; onSubmit: (b: Record<string, unknown>) => Promise<unknown> }) {
  const [evidence, setEvidence] = useState('')
  const [disposition, setDisposition] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Modal open={open} onClose={onClose} title="Close incident"
      description="Record closure evidence and the vaccine disposition decision according to applicable guidance."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || !evidence.trim() || (needsDisposition && !disposition.trim())} onClick={async () => {
          setBusy(true); try { await onSubmit({ closure_evidence: evidence, vaccine_disposition: disposition || undefined }); onClose() } catch { /* */ } finally { setBusy(false) } }}>Close incident</button></>}>
      <div className="space-y-3">
        <Field label="Closure evidence" required><textarea className="input h-20 py-2" value={evidence} onChange={(e) => setEvidence(e.target.value)} /></Field>
        <Field label="Vaccine disposition decision" required={needsDisposition}
          hint={needsDisposition ? 'Required: potentially affected batches exist. Quarantine/release/disposal of each batch is recorded on the batch.' : 'No batches were affected.'}>
          <textarea className="input h-20 py-2" value={disposition} onChange={(e) => setDisposition(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}

function AssignDialog({ open, onClose, onSubmit, facilityId }: { open: boolean; onClose: () => void; facilityId: string | null; onSubmit: (id: string) => Promise<unknown> }) {
  const users = useApi(() => facilityId ? Users.assignable('OPERATOR', facilityId) : Promise.resolve([]), [facilityId, open], { enabled: open })
  const [sel, setSel] = useState('')
  return (
    <Modal open={open} onClose={onClose} title="Assign operator" size="sm"
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!sel} onClick={async () => { try { await onSubmit(sel); onClose() } catch { /* */ } }}>Assign</button></>}>
      <select className="input" value={sel} onChange={(e) => setSel(e.target.value)}>
        <option value="">Select an operator…</option>
        {(users.data || []).map((u) => <option key={u.id} value={u.id}>{u.name}{u.title ? ` — ${u.title}` : ''}</option>)}
      </select>
    </Modal>
  )
}
