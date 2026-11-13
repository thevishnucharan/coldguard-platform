import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { LoadingBlock } from '../../components/common/Feedback'
import { Field, Tabs } from '../../components/common/Form'
import { Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Monitoring, Org, System } from '../../services/api/endpoints'
import { humanize } from '../../utils/format'

/* eslint-disable @typescript-eslint/no-explicit-any */
const POLICY_FIELDS: [string, string, string][] = [
  ['min_temperature', 'Minimum °C', 'number'], ['max_temperature', 'Maximum °C', 'number'], ['warning_margin', 'Warning margin °C', 'number'],
  ['critical_deviation', 'Critical deviation °C', 'number'], ['critical_after_minutes', 'Critical after (min)', 'number'],
  ['expected_interval_seconds', 'Expected interval (s)', 'number'], ['missing_telemetry_minutes', 'Missing telemetry after (min)', 'number'],
  ['offline_minutes', 'Offline after (min)', 'number'], ['approved_by', 'Approved by', 'text'], ['reference', 'Approval reference', 'text'],
]

function PolicyModal({ initial, onClose, onDone }: { initial: any | null; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState<any>(initial || { name: '', description: '', min_temperature: 2, max_temperature: 8, warning_margin: 0.5, critical_deviation: 3,
    critical_after_minutes: 30, expected_interval_seconds: 60, missing_telemetry_minutes: 5, offline_minutes: 15, approved_by: '', reference: '', is_active: true })
  const save = async () => {
    const body = { ...f }
    POLICY_FIELDS.forEach(([k, , t]) => { if (t === 'number') body[k] = Number(body[k]) })
    delete body.id; delete body.updated_at
    try { if (initial) await Org.updatePolicy(initial.id, body); else await Org.createPolicy(body); toast.success('Policy saved'); onDone(); onClose() }
    catch (e) { toast.error(errorMessage(e)) }
  }
  return (
    <Modal open onClose={onClose} title={initial ? `Edit policy · ${initial.name}` : 'New monitoring policy'} size="lg"
      description="Approved storage limits used for excursion detection. Changes are audited and apply to all units linked to this policy."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={!f.name} onClick={save}>Save policy</button></>}>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Name" required className="sm:col-span-2"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        {POLICY_FIELDS.map(([k, l, t]) => (
          <Field key={k} label={l}><input type={t} step="0.1" className="input" value={f[k] ?? ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
        ))}
      </div>
    </Modal>
  )
}

function EscalationTab() {
  const q = useApi(() => System.escalation(), [])
  const [rules, setRules] = useState<Record<string, number> | null>(null)
  useEffect(() => { if (q.data) setRules(q.data.rules) }, [q.data])
  if (!rules) return <LoadingBlock />
  const LABELS: Record<string, string> = {
    unack_critical_minutes: 'Escalate CRITICAL incidents unacknowledged after (minutes)',
    long_running_hours: 'Escalate any incident still active after (hours)',
    overdue_review_hours: 'Escalate corrective-action proposals waiting for review after (hours)',
    repeated_excursion_signals: 'Escalate after N repeated excursion signals',
    max_level: 'Maximum escalation level',
  }
  return (
    <Card>
      <CardHeader title="Escalation rules" subtitle="Evaluated by the background worker; escalations notify regional supervisors." />
      <div className="grid sm:grid-cols-2 gap-3 max-w-3xl">
        {Object.keys(LABELS).map((k) => (
          <Field key={k} label={LABELS[k]}><input type="number" min={1} className="input" value={rules[k]} onChange={(e) => setRules({ ...rules, [k]: Number(e.target.value) })} /></Field>
        ))}
      </div>
      <button className="btn-primary mt-4" onClick={async () => { try { await System.setEscalation(rules); toast.success('Escalation rules saved') } catch (e) { toast.error(errorMessage(e)) } }}>Save rules</button>
    </Card>
  )
}

function NotificationsTab() {
  const q = useApi(() => System.configs(), [])
  const notif = q.data?.find((c) => c.key === 'notification_rules')
  const [text, setText] = useState('')
  useEffect(() => { if (notif) setText(JSON.stringify(notif.value, null, 2)) }, [notif])
  if (!q.data) return <LoadingBlock />
  return (
    <div className="grid xl:grid-cols-2 gap-4">
      <Card>
        <CardHeader title="External alert channels" subtitle="Which channels fire per incident severity (DASHBOARD = console, EMAIL = SMTP if configured). In-app notifications always go to responsible users." />
        <textarea className="input h-64 py-2 mono" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        <button className="btn-primary mt-3" onClick={async () => {
          let v: unknown
          try { v = JSON.parse(text) } catch { toast.error('Invalid JSON'); return }
          try { await System.setConfig('notification_rules', v); toast.success('Saved'); q.reload() } catch (e) { toast.error(errorMessage(e)) } }}>Save</button>
      </Card>
      <Card>
        <CardHeader title="Other system parameters" />
        <ul className="space-y-3">{q.data.filter((c) => c.key !== 'notification_rules').map((c) => (
          <li key={c.key}><p className="mono text-xs font-medium">{c.key}</p><p className="text-[11px] text-ink-3">{c.description}</p>
            <pre className="mono text-[11px] bg-canvas rounded p-2 mt-1 overflow-x-auto">{JSON.stringify(c.value)}</pre></li>))}</ul>
      </Card>
    </div>
  )
}

function UnitsTab({ policies }: { policies: any[] }) {
  const units = useApi(() => Monitoring.units(), [])
  const facilities = useApi(() => Org.facilities({ include_inactive: true }), [])
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ unit_code: '', name: '', location: '', unit_type: 'ILR', facility_id: '', policy_id: '' })
  const fac = Object.fromEntries((facilities.data || []).map((x) => [x.id, x.name]))
  const pol = Object.fromEntries(policies.map((p) => [p.id, p.name]))
  return (
    <>
      <div className="flex justify-end mb-3"><button className="btn-primary" onClick={() => setOpen(true)}><Plus size={15} /> Register storage unit</button></div>
      <div className="card p-0">
        <DataTable rows={units.data} loading={units.loading} columns={[
          { key: 'c', header: 'Unit', render: (u) => <span className="font-medium">{u.unit_code}</span> },
          { key: 'f', header: 'Facility', render: (u) => fac[u.facility_id] || '—' },
          { key: 't', header: 'Type', render: (u) => u.unit_type },
          { key: 'p', header: 'Policy', render: (u) => u.policy_id ? <Pill tone="brand">{pol[u.policy_id]}</Pill> : <Pill tone="warn">Unit-level limits</Pill> },
          { key: 'r', header: 'Effective range', render: (u) => `${u.effective_min} – ${u.effective_max}°C` },
          { key: 's', header: 'Status', render: (u) => <StatusPill status={u.status} /> },
          { key: 'x', header: 'Assign policy', render: (u) => (
            <select className="input h-8 text-xs w-48" value={u.policy_id || ''} onChange={async (e) => { try { await Monitoring.updateUnit(u.id, { policy_id: e.target.value || null }); toast.success('Policy assigned'); units.reload() } catch (er) { toast.error(errorMessage(er)) } }}>
              <option value="">—</option>{policies.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>) },
        ]} />
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Register storage unit"
        footer={<><button className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="btn-primary" disabled={!f.unit_code || !f.facility_id || !f.policy_id || !f.name}
          onClick={async () => { try { await Monitoring.createUnit(f); toast.success('Unit registered'); setOpen(false); units.reload() } catch (e) { toast.error(errorMessage(e)) } }}>Register</button></>}>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Unit code" required><input className="input" value={f.unit_code} onChange={(e) => setF({ ...f, unit_code: e.target.value })} /></Field>
          <Field label="Name" required><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Facility" required><select className="input" value={f.facility_id} onChange={(e) => setF({ ...f, facility_id: e.target.value })}>
            <option value="">Select…</option>{(facilities.data || []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <Field label="Monitoring policy" required><select className="input" value={f.policy_id} onChange={(e) => setF({ ...f, policy_id: e.target.value })}>
            <option value="">Select…</option>{policies.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Type"><input className="input" value={f.unit_type} onChange={(e) => setF({ ...f, unit_type: e.target.value })} /></Field>
          <Field label="Location"><input className="input" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></Field>
        </div>
      </Modal>
    </>
  )
}

export default function SystemConfigPage() {
  const [tab, setTab] = useState<'policies' | 'units' | 'escalation' | 'notifications'>('policies')
  const policies = useApi(() => Org.policies(), [])
  const [edit, setEdit] = useState<any | null | undefined>(undefined)
  return (
    <>
      <PageHeader title="System configuration" subtitle="Approved monitoring policies, equipment, escalation and notification settings. Every change is audited."
        crumbs={[{ label: 'Platform', to: '/admin' }, { label: 'Configuration' }]} />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'policies', label: 'Monitoring policies' }, { value: 'units', label: 'Storage units' },
        { value: 'escalation', label: 'Escalation' }, { value: 'notifications', label: 'Notifications & parameters' }]} />
      {tab === 'policies' && (<>
        <div className="flex justify-end mb-3"><button className="btn-primary" onClick={() => setEdit(null)}><Plus size={15} /> New policy</button></div>
        <div className="card p-0">
          <DataTable rows={policies.data} loading={policies.loading} error={policies.error} onRowClick={(p) => setEdit(p)} columns={[
            { key: 'n', header: 'Policy', render: (p) => <div><div className="font-medium">{p.name}</div><div className="text-xs text-ink-3">{p.description}</div></div> },
            { key: 'r', header: 'Approved range', render: (p) => `${p.min_temperature} – ${p.max_temperature}°C` },
            { key: 'w', header: 'Warning margin', render: (p) => `±${p.warning_margin}°C` },
            { key: 'c', header: 'Critical when', render: (p) => <span className="text-xs">&gt; {p.critical_deviation}°C off or &gt; {p.critical_after_minutes} min</span> },
            { key: 'm', header: 'Missing / offline', render: (p) => <span className="text-xs">{p.missing_telemetry_minutes} / {p.offline_minutes} min</span> },
            { key: 'a', header: 'Approval', render: (p) => <span className="text-xs">{p.approved_by || '—'}{p.reference && <div className="text-ink-3">{p.reference}</div>}</span> },
            { key: 's', header: 'Status', render: (p) => <Pill tone={p.is_active ? 'ok' : 'neutral'}>{p.is_active ? 'Active' : 'Inactive'}</Pill> },
          ]} />
        </div>
        <p className="text-[11px] text-ink-3 mt-2">ColdGuard does not hard-code a universal vaccine range: each unit follows the approved policy assigned to it.</p>
      </>)}
      {tab === 'units' && <UnitsTab policies={policies.data || []} />}
      {tab === 'escalation' && <EscalationTab />}
      {tab === 'notifications' && <NotificationsTab />}
      {edit !== undefined && <PolicyModal initial={edit} onClose={() => setEdit(undefined)} onDone={policies.reload} />}
      <span className="hidden">{humanize('')}</span>
    </>
  )
}
