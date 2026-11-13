import { Lock, Mail, ShieldCheck, Snowflake, Thermometer, Wrench } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { HOME } from '../../app/navigation'
import { errorMessage } from '../../services/api/client'
import { Auth } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'

// Local demonstration accounts (seeded by scripts/seed.py). Hidden when VITE_SHOW_DEMO_LOGINS=false.
const SHOW_DEMO = import.meta.env.VITE_SHOW_DEMO_LOGINS !== 'false'
const DEMO_PASSWORD = 'ColdGuard#2026'
const DEMO = [
  { email: 'admin@coldguard.local', role: 'System Administrator' },
  { email: 'operator.blr@coldguard.local', role: 'Facility Operator' },
  { email: 'supervisor@coldguard.local', role: 'Regional Supervisor' },
  { email: 'technician@coldguard.local', role: 'Maintenance Technician' },
  { email: 'auditor@coldguard.local', role: 'Auditor / Compliance' },
]

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { me, accessToken, setSession, setMe } = useAuthStore()
  const navigate = useNavigate()
  const loc = useLocation()
  const [params] = useSearchParams()
  if (me && accessToken) return <Navigate to={HOME[me.role]} replace />

  const signIn = async (rawEmail: string, pw: string) => {
    setError(null)
    const em = rawEmail.trim().toLowerCase()
    if (!em || !pw) { setError('Enter your email and password'); return }
    setBusy(true)
    try {
      const t = await Auth.login(em, pw)
      setSession(t.access_token, t.refresh_token)
      const profile = await Auth.me()
      setMe(profile)
      const from = (loc.state as { from?: string } | null)?.from
      navigate(from && from !== '/login' ? from : HOME[profile.role], { replace: true })
    } catch (err) {
      const msg = errorMessage(err, 'Sign-in failed')
      setError(em.endsWith('@coldguard.com')
        ? `${msg}. ColdGuard v1 accounts (@coldguard.com) were not carried over — use a demo account below (@coldguard.local).`
        : msg)
    } finally {
      setBusy(false)
    }
  }

  // Read the real field values: browser password managers can autofill without firing React onChange.
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    signIn(String(fd.get('email') || email), String(fd.get('password') || password))
  }

  return (
    <div className="min-h-full grid lg:grid-cols-[1.05fr_1fr]">
      <div className="hidden lg:flex flex-col justify-between bg-navy-900 text-[#c6d2e3] p-12">
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center size-9 rounded-lg bg-brand-600 text-white"><Snowflake size={19} /></span>
          <span className="text-lg font-semibold text-white">ColdGuard</span>
        </div>
        <div className="max-w-md">
          <h1 className="text-3xl font-semibold text-white tracking-tight leading-tight">Vaccine cold-chain monitoring, incident response and traceability.</h1>
          <ul className="mt-8 space-y-4 text-[13.5px]">
            {[[Thermometer, 'Live temperature monitoring against approved storage policies'],
              [ShieldCheck, 'Role-based incident workflows with supervisor review and full audit trail'],
              [Wrench, 'Equipment maintenance, calibration and batch-level traceability']].map(([I, t], i) => {
              const Icon = I as typeof Thermometer
              return <li key={i} className="flex gap-3"><Icon size={18} className="text-brand-200 shrink-0 mt-0.5" />{t as string}</li>
            })}
          </ul>
        </div>
        <p className="text-xs text-[#6f86a6]">ColdGuard supports — and does not replace — clinical and regulatory decision-making.</p>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12 bg-canvas">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <span className="grid place-items-center size-8 rounded-lg bg-brand-600 text-white"><Snowflake size={17} /></span>
            <span className="font-semibold">ColdGuard</span>
          </div>
          <h2 className="text-xl font-semibold tracking-tight">Sign in</h2>
          <p className="text-[13px] text-ink-3 mt-1">Use the account issued by your administrator.</p>
          {params.get('expired') && <p className="mt-4 rounded-lg bg-warn-bg px-3 py-2 text-xs text-warn-ink">Your session expired. Please sign in again.</p>}
          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <div>
              <label className="label" htmlFor="email">Email</label>
              <div className="relative">
                <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                <input id="email" name="email" type="email" autoComplete="username" className="input pl-9" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
            </div>
            <div>
              <label className="label" htmlFor="password">Password</label>
              <div className="relative">
                <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                <input id="password" name="password" type="password" autoComplete="current-password" className="input pl-9" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
            </div>
            {error && <p role="alert" className="rounded-lg bg-crit-bg px-3 py-2 text-xs text-crit-ink">{error}</p>}
            <button type="submit" className="btn-primary w-full h-10" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          </form>

          {SHOW_DEMO && (
            <div className="mt-8">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-3 mb-2">Local demo accounts — click to sign in</p>
              <div className="grid gap-1.5">
                {DEMO.map((d) => (
                  <button key={d.email} type="button" disabled={busy} onClick={() => { setEmail(d.email); setPassword(DEMO_PASSWORD); signIn(d.email, DEMO_PASSWORD) }}
                    className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2 text-left hover:border-brand-200">
                    <span className="text-[13px] font-medium">{d.role}</span>
                    <span className="text-[11px] text-ink-3 mono">{d.email.split('@')[0]}</span>
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-ink-3 mt-2">Demonstration data only. Never use these credentials outside local development.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
