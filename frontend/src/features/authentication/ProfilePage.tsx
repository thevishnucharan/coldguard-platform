import { useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader } from '../../components/common/Card'
import { Field } from '../../components/common/Form'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill } from '../../components/common/Status'
import { errorMessage } from '../../services/api/client'
import { Auth } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import { fmtDateTime } from '../../utils/format'

export default function ProfilePage() {
  const me = useAuthStore((s) => s.me)!
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const weak = next.length > 0 && (next.length < 10 || !/\d/.test(next) || !/[a-z]/i.test(next))
  const mismatch = confirm.length > 0 && confirm !== next
  const submit = async () => {
    setBusy(true)
    try {
      await Auth.changePassword(cur, next)
      toast.success('Password changed. Other sessions have been signed out.')
      setCur(''); setNext(''); setConfirm('')
    } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <>
      <PageHeader title="Profile & security" crumbs={[{ label: 'Home', to: '/' }, { label: 'Profile' }]} />
      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Account" subtitle="Your role and permissions are assigned by an administrator." />
          <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-[13px]">
            <dt className="text-ink-3">Name</dt><dd>{me.name}</dd>
            <dt className="text-ink-3">Email</dt><dd>{me.email}</dd>
            <dt className="text-ink-3">Role</dt><dd>{me.role_label}</dd>
            <dt className="text-ink-3">Data scope</dt><dd>{me.global_scope ? 'All facilities' : `${me.facility_ids.length} facilities`}</dd>
            <dt className="text-ink-3">Last sign-in</dt><dd>{fmtDateTime(me.last_login_at)}</dd>
          </dl>
          <p className="text-xs font-medium text-ink-2 mt-4 mb-2">Permissions ({me.permissions.length})</p>
          <div className="flex flex-wrap gap-1">{me.permissions.map((p) => <Pill key={p}>{p}</Pill>)}</div>
        </Card>
        <Card>
          <CardHeader title="Change password" subtitle="At least 10 characters with letters and digits." />
          <div className="space-y-3">
            <Field label="Current password"><input type="password" className="input" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></Field>
            <Field label="New password" error={weak ? 'Too weak: 10+ characters, letters and digits' : null}>
              <input type="password" className="input" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field>
            <Field label="Confirm new password" error={mismatch ? 'Passwords do not match' : null}>
              <input type="password" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" /></Field>
            <button className="btn-primary" disabled={busy || !cur || !next || weak || mismatch || confirm !== next} onClick={submit}>Update password</button>
          </div>
        </Card>
      </div>
    </>
  )
}
