import { ArrowRight, Eye, EyeOff, Lock, Mail, ShieldCheck, Snowflake, Thermometer, Truck, Wrench } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { HOME, ROLE_META } from '../../app/navigation'
import { errorMessage } from '../../services/api/client'
import { Auth } from '../../services/api/endpoints'
import { useAuthStore } from '../../store/authStore'
import type { Role } from '../../types'

// Local demonstration accounts (seeded by scripts/seed.py). Hidden when VITE_SHOW_DEMO_LOGINS=false.
const SHOW_DEMO = import.meta.env.VITE_SHOW_DEMO_LOGINS !== 'false'
const DEMO_PASSWORD = 'ColdGuard#2026'
const DEMO: { email: string; role: Role; label: string; hint: string }[] = [
  { email: 'admin@coldguard.local', role: 'ADMIN', label: 'System Administrator', hint: 'Platform, users, routing' },
  { email: 'operator.blr@coldguard.local', role: 'OPERATOR', label: 'Facility Operator', hint: 'Alarms, stock, vehicles' },
  { email: 'supervisor@coldguard.local', role: 'SUPERVISOR', label: 'Regional Supervisor', hint: 'Approvals & oversight' },
  { email: 'technician@coldguard.local', role: 'TECHNICIAN', label: 'Maintenance Technician', hint: 'Work orders, calibration' },
  { email: 'auditor@coldguard.local', role: 'AUDITOR', label: 'Auditor / Compliance', hint: 'Read-only evidence' },
]

const FEATURES = [
  { icon: Thermometer, title: 'Live temperature monitoring', text: 'Every reading checked against approved storage policies, with offline and missing-data detection.' },
  { icon: ShieldCheck, title: 'Incident response with review', text: 'Role-based workflows, supervisor approvals and an immutable audit trail.' },
  { icon: Truck, title: 'Supply-chain relocation', text: 'ML-optimised routes for at-risk stock; in-transit logger failures alert the nearest cold store.' },
  { icon: Wrench, title: 'Equipment & traceability', text: 'Maintenance, calibration and batch-level movement history.' },
]

/** Decorative temperature trace inside the 2–8 °C band (illustrative, not data). */
function TraceArt() {
  return (
    <svg viewBox="0 0 400 120" className="w-full h-28" role="img" aria-label="Illustration: temperature trace inside the 2 to 8 degree band">
      <defs>
        <linearGradient id="cg-trace" x1="0" x2="1"><stop offset="0" stopColor="#14a294" stopOpacity=".2" /><stop offset="1" stopColor="#3b8ff0" stopOpacity=".9" /></linearGradient>
      </defs>
      <rect x="0" y="30" width="400" height="60" rx="8" fill="#14a294" opacity=".08" />
      <line x1="0" x2="400" y1="30" y2="30" stroke="#9ee8d9" strokeOpacity=".35" strokeDasharray="4 6" />
      <line x1="0" x2="400" y1="90" y2="90" stroke="#9ee8d9" strokeOpacity=".35" strokeDasharray="4 6" />
      <text x="6" y="24" fill="#8aa0bd" fontSize="10">8 °C</text>
      <text x="6" y="104" fill="#8aa0bd" fontSize="10">2 °C</text>
      <path d="M0 62 C 30 50, 50 70, 80 60 S 130 48, 160 58 S 210 72, 240 56 S 290 44, 320 60 S 370 66, 400 54"
        fill="none" stroke="url(#cg-trace)" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="400" cy="54" r="4" fill="#3b8ff0" />
    </svg>
  )
}

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [caps, setCaps] = useState(false)
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
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.('CapsLock') ?? false)

  return (
    <div className="min-h-full grid lg:grid-cols-[1.1fr_1fr]">
      {/* ------------------------------------------------------------ brand panel */}
      <div className="relative hidden lg:flex flex-col justify-between overflow-hidden bg-navy-950 text-[#c6d2e3] p-12">
        <div className="pointer-events-none absolute inset-0" aria-hidden
          style={{ backgroundImage: 'radial-gradient(600px 380px at 15% 10%, rgba(20,162,148,.22), transparent 70%), radial-gradient(520px 360px at 95% 90%, rgba(59,143,240,.20), transparent 70%), linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px)', backgroundSize: 'auto, auto, 32px 32px, 32px 32px' }} />
        <div className="relative flex items-center gap-2.5">
          <span className="grid place-items-center size-10 rounded-xl bg-gradient-to-br from-brand-500 to-[#2a78d6] text-white shadow-lg shadow-brand-600/30"><Snowflake size={20} /></span>
          <span className="text-lg font-semibold text-white">ColdGuard</span>
          <span className="ml-2 rounded-full border border-white/10 px-2 py-0.5 text-[10.5px] uppercase tracking-wider text-[#9ee8d9]">Vaccine cold chain</span>
        </div>

        <div className="relative max-w-lg">
          <h1 className="display text-[38px] font-semibold text-white tracking-tight leading-[1.1]">Every dose, kept in range — from the store room to the road.</h1>
          <p className="mt-4 text-[14.5px] text-[#9fb2cc] leading-relaxed">Monitoring, incident response, maintenance and ML-assisted relocation for immunisation supply chains.</p>
          <div className="mt-6 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4">
            <TraceArt />
            <div className="mt-2 flex items-center justify-between text-[11.5px] text-[#8aa0bd]">
              <span className="flex items-center gap-1.5"><span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-ok opacity-60" /><span className="relative inline-flex size-2 rounded-full bg-ok" /></span>Within approved 2–8 °C policy</span>
              <span>Illustration</span>
            </div>
          </div>
          <ul className="mt-6 grid grid-cols-2 gap-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="rounded-xl border border-white/[0.06] bg-white/[0.025] p-3.5">
                <Icon size={17} className="text-[#9ee8d9]" />
                <p className="mt-2 text-[13px] font-medium text-white">{title}</p>
                <p className="mt-1 text-[11.5px] leading-snug text-[#8aa0bd]">{text}</p>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-[#6f86a6]">ColdGuard supports — and does not replace — clinical and regulatory decision-making.</p>
      </div>

      {/* ------------------------------------------------------------ sign-in */}
      <div className="flex items-center justify-center p-6 sm:p-12 bg-canvas">
        <div className="w-full max-w-[400px]">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <span className="grid place-items-center size-9 rounded-xl bg-gradient-to-br from-brand-500 to-[#2a78d6] text-white"><Snowflake size={18} /></span>
            <span className="font-semibold text-lg">ColdGuard</span>
          </div>
          <div className="card card-pad shadow-xl shadow-navy-900/5">
            <h2 className="display text-[24px] font-semibold tracking-tight text-ink">Welcome back</h2>
            <p className="text-[13px] text-ink-3 mt-1">Sign in with the account issued by your administrator.</p>
            {params.get('expired') && <p className="mt-4 rounded-lg bg-warn-bg px-3 py-2 text-xs text-warn-ink">Your session expired. Please sign in again.</p>}
            <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
              <div>
                <label className="label" htmlFor="email">Email</label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                  <input id="email" name="email" type="email" autoComplete="username" placeholder="you@facility.org" className="input h-11 pl-9"
                    value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
              </div>
              <div>
                <label className="label" htmlFor="password">Password</label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                  <input id="password" name="password" type={show ? 'text' : 'password'} autoComplete="current-password" className="input h-11 pl-9 pr-10"
                    value={password} onChange={(e) => setPassword(e.target.value)} onKeyUp={onKey} onKeyDown={onKey} />
                  <button type="button" onClick={() => setShow((v) => !v)} className="absolute right-1.5 top-1/2 -translate-y-1/2 grid place-items-center size-8 rounded-lg text-ink-3 hover:bg-surface-2"
                    aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
                    {show ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {caps && <p className="mt-1 text-[11px] text-warn-ink">Caps Lock is on</p>}
              </div>
              {error && <p role="alert" className="rounded-lg bg-crit-bg px-3 py-2 text-xs text-crit-ink">{error}</p>}
              <button type="submit" className="btn-primary w-full h-11 text-[14px]" disabled={busy}>
                {busy ? 'Signing in…' : <>Sign in <ArrowRight size={15} /></>}
              </button>
            </form>
            <p className="mt-4 text-[11.5px] text-ink-3 flex items-center gap-1.5"><ShieldCheck size={13} /> 5 failed attempts lock the account for 15 minutes.</p>
          </div>

          {SHOW_DEMO && (
            <div className="mt-6">
              <div className="flex items-center gap-3 mb-2.5">
                <span className="h-px flex-1 bg-line" /><p className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Local demo accounts</p><span className="h-px flex-1 bg-line" />
              </div>
              <div className="grid sm:grid-cols-2 gap-2">
                {DEMO.map((d) => {
                  const meta = ROLE_META[d.role]
                  return (
                    <button key={d.email} type="button" disabled={busy}
                      onClick={() => { setEmail(d.email); setPassword(DEMO_PASSWORD); signIn(d.email, DEMO_PASSWORD) }}
                      className="group flex items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2.5 text-left transition-all hover:-translate-y-px hover:shadow-md disabled:opacity-60"
                      style={{ borderLeft: `3px solid ${meta.accent}` }}>
                      <span className="grid place-items-center size-8 shrink-0 rounded-lg" style={{ background: meta.soft, color: meta.accent }}><meta.icon size={15} /></span>
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium text-ink truncate">{d.label}</span>
                        <span className="block text-[11px] text-ink-3 truncate">{d.hint}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
              <p className="text-[11px] text-ink-3 mt-2.5">Click a role to sign in. Demonstration data only — never use these credentials outside local development.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
