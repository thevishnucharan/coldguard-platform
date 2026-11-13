import { Plus, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { DataTable, Pagination } from '../../components/common/DataTable'
import { LoadingBlock } from '../../components/common/Feedback'
import { Field, FilterBar, SearchInput, Select, Tabs } from '../../components/common/Form'
import { ConfirmDialog, Modal } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { Org, Users } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { ago, fmtDateTime, humanize } from '../../utils/format'

const ROLES = ['ADMIN', 'OPERATOR', 'SUPERVISOR', 'TECHNICIAN', 'AUDITOR']
const GLOBAL = ['ADMIN', 'AUDITOR']

function ScopePicker({ role, facilityIds, regionIds, onChange }: { role: string; facilityIds: string[]; regionIds: string[]; onChange: (f: string[], r: string[]) => void }) {
  const facilities = useApi(() => Org.facilities({ include_inactive: true }), [])
  const regions = useApi(() => Org.regions(), [])
  if (GLOBAL.includes(role)) return <p className="text-xs text-ink-3 rounded-lg bg-canvas p-3">{humanize(role)} accounts have platform-wide read scope; no facility assignment is needed.</p>
  const toggle = (arr: string[], id: string) => arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]
  return (
    <div className="space-y-3">
      {role === 'SUPERVISOR' && (
        <div><p className="label">Regions (all facilities in a region)</p>
          <div className="flex flex-wrap gap-2">{(regions.data || []).map((r) => (
            <label key={r.id} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs cursor-pointer">
              <input type="checkbox" checked={regionIds.includes(r.id)} onChange={() => onChange(facilityIds, toggle(regionIds, r.id))} />{r.name}</label>))}</div></div>
      )}
      <div><p className="label">Facilities</p>
        <div className="grid sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto">{(facilities.data || []).map((f) => (
          <label key={f.id} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs cursor-pointer">
            <input type="checkbox" checked={facilityIds.includes(f.id)} onChange={() => onChange(toggle(facilityIds, f.id), regionIds)} />{f.name}</label>))}</div></div>
    </div>
  )
}

function CreateUser({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: '', email: '', password: '', role: 'OPERATOR', title: '' })
  const [fac, setFac] = useState<string[]>([])
  const [reg, setReg] = useState<string[]>([])
  const weak = f.password.length > 0 && (f.password.length < 10 || !/\d/.test(f.password) || !/[a-z]/i.test(f.password))
  return (
    <Modal open={open} onClose={onClose} title="Create user" size="lg" description="Users can only act within the facilities you assign. Permissions come from the role."
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={!f.name || !f.email || weak || !f.password}
        onClick={async () => { try { await Users.create({ ...f, title: f.title || undefined, facility_ids: fac, region_ids: reg }); toast.success('User created'); onDone(); onClose() } catch (e) { toast.error(errorMessage(e)) } }}>Create user</button></>}>
      <div className="grid sm:grid-cols-2 gap-3 mb-4">
        <Field label="Full name" required><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email" required><input type="email" className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Role" required><select className="input" value={f.role} onChange={(e) => { setF({ ...f, role: e.target.value }); setFac([]); setReg([]) }}>
          {ROLES.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}</select></Field>
        <Field label="Job title"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Initial password" required error={weak ? '10+ characters with letters and digits' : null} className="sm:col-span-2">
          <input type="password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" /></Field>
      </div>
      <ScopePicker role={f.role} facilityIds={fac} regionIds={reg} onChange={(a, b) => { setFac(a); setReg(b) }} />
    </Modal>
  )
}

function UserDetail({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
  const me = useAuthStore((s) => s.me)
  const u = useApi(() => Users.get(id), [id])
  const activity = useApi(() => Users.activity(id), [id])
  const [tab, setTab] = useState<'access' | 'activity'>('access')
  const [fac, setFac] = useState<string[] | null>(null)
  const [reg, setReg] = useState<string[] | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<null | 'toggle'>(null)
  if (!u.data) return <Modal open onClose={onClose} title="User"><LoadingBlock /></Modal>
  const d = u.data
  const fIds = fac ?? d.assignments.filter((a: { facility_id: string | null }) => a.facility_id).map((a: { facility_id: string }) => a.facility_id)
  const rIds = reg ?? d.assignments.filter((a: { region_id: string | null }) => a.region_id).map((a: { region_id: string }) => a.region_id)
  const curRole = role ?? d.role
  const self = me?.id === d.id
  const save = async () => {
    try {
      if (curRole !== d.role) await Users.update(id, { role: curRole })
      if (!GLOBAL.includes(curRole)) await Users.setAssignments(id, { facility_ids: fIds, region_ids: curRole === 'SUPERVISOR' ? rIds : [] })
      toast.success('Access updated'); onDone(); u.reload()
    } catch (e) { toast.error(errorMessage(e)) }
  }
  return (
    <Modal open onClose={onClose} title={d.name} description={`${d.email} · last sign-in ${ago(d.last_login_at)}`} size="lg"
      footer={<>{!self && <button className={d.is_active ? 'btn-danger mr-auto' : 'btn-secondary mr-auto'} onClick={() => setConfirm('toggle')}>{d.is_active ? 'Deactivate account' : 'Reactivate account'}</button>}
        <button className="btn-secondary" onClick={onClose}>Close</button>{tab === 'access' && <button className="btn-primary" onClick={save}>Save access</button>}</>}>
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'access', label: 'Role & access' }, { value: 'activity', label: 'Activity' }]} />
      {tab === 'access' ? (
        <div className="space-y-4">
          <Field label="Role" hint={self ? 'You cannot change your own role.' : 'Changing the role clears facility assignments.'}>
            <select className="input" disabled={self} value={curRole} onChange={(e) => { setRole(e.target.value); setFac([]); setReg([]) }}>
              {ROLES.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}</select></Field>
          <ScopePicker role={curRole} facilityIds={fIds} regionIds={rIds} onChange={(a, b) => { setFac(a); setReg(b) }} />
        </div>
      ) : (
        <DataTable dense rows={activity.data} loading={activity.loading} columns={[
          { key: 't', header: 'When', render: (a) => <span className="text-xs">{fmtDateTime(a.timestamp)}</span> },
          { key: 'a', header: 'Action', render: (a) => <span className="mono">{a.action}</span> },
          { key: 'o', header: 'Outcome', render: (a) => <StatusPill status={a.outcome} /> },
          { key: 'ip', header: 'IP', render: (a) => <span className="text-xs mono">{a.ip_address || '—'}</span> },
        ]} />
      )}
      <ConfirmDialog open={confirm === 'toggle'} onClose={() => setConfirm(null)} danger={d.is_active} title={d.is_active ? 'Deactivate account' : 'Reactivate account'}
        description={d.is_active ? 'The user is signed out of all API access immediately.' : undefined} confirmLabel={d.is_active ? 'Deactivate' : 'Reactivate'}
        onConfirm={async () => { try { await Users.update(id, { is_active: !d.is_active }); toast.success('Account updated'); u.reload(); onDone() } catch (e) { toast.error(errorMessage(e)) } }} />
    </Modal>
  )
}

export default function UsersPage() {
  const can = useAuthStore((s) => s.can)
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [create, setCreate] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  const [tab, setTab] = useState<'users' | 'matrix'>('users')
  const q = useApi(() => Users.list({ page, page_size: 25, role: role || undefined, search: search || undefined }), [page, role, search])
  const matrix = useApi(() => Users.roles(), [], { enabled: tab === 'matrix' })
  return (
    <>
      <PageHeader title="Users & access" subtitle="Accounts, roles and facility / region scope." crumbs={[{ label: 'Platform', to: '/admin' }, { label: 'Users' }]}
        actions={can('users.create') && <button className="btn-primary" onClick={() => setCreate(true)}><Plus size={15} /> Create user</button>} />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'users', label: 'Users' }, { value: 'matrix', label: 'Permission matrix' }]} />
      {tab === 'users' ? (<>
        <FilterBar>
          <Select ariaLabel="Role" value={role} onChange={(v) => { setRole(v); setPage(1) }} placeholder="All roles" className="w-48" options={ROLES.map((r) => ({ value: r, label: humanize(r) }))} />
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Name or email" className="w-64" />
        </FilterBar>
        <div className="card p-0">
          <DataTable rows={q.data?.items} loading={q.loading} error={q.error} onRowClick={(u) => setSel(u.id)} columns={[
            { key: 'n', header: 'User', render: (u) => <div><div className="font-medium">{u.name}</div><div className="text-xs text-ink-3">{u.email}</div></div> },
            { key: 'r', header: 'Role', render: (u) => <Pill tone={u.role === 'ADMIN' ? 'brand' : 'neutral'}>{humanize(u.role)}</Pill> },
            { key: 't', header: 'Title', render: (u) => <span className="text-xs">{u.title || '—'}</span> },
            { key: 's', header: 'Status', render: (u) => u.locked_until && new Date(u.locked_until) > new Date() ? <Pill tone="serious">Locked</Pill> : <Pill tone={u.is_active ? 'ok' : 'neutral'}>{u.is_active ? 'Active' : 'Deactivated'}</Pill> },
            { key: 'l', header: 'Last sign-in', render: (u) => <span className="text-xs">{ago(u.last_login_at)}</span> },
          ]} />
          <div className="px-4 pb-3"><Pagination page={page} pageSize={25} total={q.data?.total || 0} onPage={setPage} /></div>
        </div>
      </>) : (
        <div className="card p-0 overflow-x-auto">
          {!matrix.data ? <LoadingBlock className="p-4" /> : (
            <table className="w-full border-collapse">
              <thead><tr><th className="th">Permission</th>{matrix.data.roles.map((r: { code: string; label: string }) => <th key={r.code} className="th text-center">{r.label}</th>)}</tr></thead>
              <tbody>{matrix.data.permissions.map((p: { code: string; description: string }) => (
                <tr key={p.code}><td className="td"><div className="mono">{p.code}</div><div className="text-[11px] text-ink-3">{p.description}</div></td>
                  {matrix.data!.roles.map((r: { code: string; permissions: string[] }) => <td key={r.code} className="td text-center">
                    {r.permissions.includes(p.code) ? <ShieldCheck size={15} className="inline text-ok" aria-label="granted" /> : <span className="text-ink-3" aria-label="not granted">—</span>}</td>)}
                </tr>))}</tbody>
            </table>
          )}
        </div>
      )}
      <CreateUser open={create} onClose={() => setCreate(false)} onDone={q.reload} />
      {sel && <UserDetail id={sel} onClose={() => setSel(null)} onDone={q.reload} />}
    </>
  )
}
