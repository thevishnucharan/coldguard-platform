import { Menu, MenuButton, MenuItem, MenuItems, Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import {
  ArrowRight, Bell, ChevronDown, ChevronsLeft, ChevronsRight, CircleUserRound, FlaskConical, LogOut, Menu as MenuIcon, Moon, Search,
  Snowflake, Sun, Wifi, WifiOff, X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useApi, useNow, useRealtimeEvent, useRealtimeStatus } from '../hooks/useApi'
import { Auth, Incidents, Logistics, Maintenance, Notifications } from '../services/api/endpoints'
import { realtime } from '../services/websocket/realtime'
import { useAuthStore } from '../store/authStore'
import { useThemeStore } from '../store/themeStore'
import type { Notification } from '../types'
import { ago, cx } from '../utils/format'
import { CommandPalette } from './CommandPalette'
import { HOME, navFor, ROLE_META } from './navigation'

function ConnectionIndicator() {
  const status = useRealtimeStatus()
  const now = useNow(5000)
  const quiet = realtime.lastMessageAt ? (now - realtime.lastMessageAt) / 1000 : null
  const healthy = status === 'open' && (quiet === null || quiet < 60)
  return (
    <span title={healthy ? 'Live updates connected' : 'Live updates unavailable — data refreshes on reconnect'}
      className={cx('hidden md:inline-flex items-center gap-1.5 rounded-xl px-2.5 h-9 text-xs font-medium border',
        healthy ? 'bg-ok-bg text-ok-ink border-ok/20' : 'bg-warn-bg text-warn-ink border-warn/30')}>
      {healthy ? <><span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-ok opacity-60" /><span className="relative inline-flex size-2 rounded-full bg-ok" /></span><Wifi size={13} /></> : <WifiOff size={13} />}
      {healthy ? 'Live' : status === 'connecting' ? 'Connecting…' : 'Offline'}
    </span>
  )
}

function NotificationCenter() {
  const navigate = useNavigate()
  const { data, reload } = useApi(() => Notifications.list({ limit: 20 }), [], { refreshOn: ['notification'], interval: 60000 })
  useRealtimeEvent('notification', (e) => {
    const d = e.data as { title?: string; level?: string }
    if (d.level === 'CRITICAL') toast.error(d.title || 'Critical alert', { duration: 6000 })
    else if (d.title) toast(d.title)
  })
  const open = async (n: Notification) => {
    if (!n.read_at) await Notifications.read(n.id).catch(() => undefined)
    reload()
    if (n.link) navigate(n.link)
  }
  const unread = data?.unread ?? 0
  return (
    <Popover className="relative">
      <PopoverButton className="btn-secondary relative h-9 w-9 p-0" aria-label={`Notifications, ${unread} unread`}>
        <Bell size={16} />
        {unread > 0 && <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-crit text-white text-[10px] font-semibold grid place-items-center">{unread > 99 ? '99+' : unread}</span>}
      </PopoverButton>
      <PopoverPanel anchor="bottom end" className="z-40 mt-2 w-[min(380px,calc(100vw-24px))] card shadow-xl">
        {({ close }) => (
          <>
            <div className="flex items-center justify-between px-4 py-3 border-b border-line">
              <span className="card-title text-[15px]">Notifications</span>
              {unread > 0 && <button className="text-xs text-brand-700 hover:underline" onClick={async () => { await Notifications.readAll(); reload() }}>Mark all read</button>}
            </div>
            <ul className="max-h-96 overflow-y-auto divide-y divide-line">
              {!data?.items.length && <li className="p-6 text-center text-xs text-ink-3">You're all caught up.</li>}
              {data?.items.map((n) => (
                <li key={n.id}>
                  <button className={cx('w-full text-left px-4 py-3 hover:bg-surface-2 flex gap-3', !n.read_at && 'bg-brand-50/50')}
                    onClick={() => { close(); open(n) }}>
                    <span className={cx('mt-1.5 size-2 rounded-full shrink-0', n.level === 'CRITICAL' ? 'bg-crit' : n.level === 'WARNING' ? 'bg-warn' : 'bg-series-1')} />
                    <span className="min-w-0">
                      <span className="block text-[13px] font-medium text-ink truncate">{n.title}</span>
                      <span className="block text-xs text-ink-3 line-clamp-2">{n.message}</span>
                      <span className="block text-[11px] text-ink-3 mt-1">{n.level.toLowerCase()} · {n.category.toLowerCase()} · {ago(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </PopoverPanel>
    </Popover>
  )
}

function useBadges(perms: string[]) {
  const inc = useApi(() => Incidents.list({ active: true, page_size: 1 }), [], { refreshOn: ['incident.created', 'incident.updated'], enabled: perms.includes('incidents.view') })
  const rev = useApi(() => Incidents.list({ status: ['CORRECTIVE_ACTION_PENDING', 'UNDER_REVIEW'], page_size: 1 }), [], { refreshOn: ['incident.updated'], enabled: perms.includes('incidents.review') })
  const wo = useApi(() => Maintenance.list({ status: ['OPEN', 'ASSIGNED', 'IN_PROGRESS'], page_size: 1 }), [], { refreshOn: ['maintenance.updated'], enabled: perms.includes('maintenance.update') })
  const tr = useApi(() => Logistics.transitAlerts(true), [], { refreshOn: ['transit.alert'], interval: 60000, enabled: perms.includes('logistics.view') })
  return { incidents: inc.data?.total, approvals: rev.data?.total, workorders: wo.data?.total, transit: tr.data?.length }
}

const initials = (name: string) => name.replace(/^Dr\.\s*/, '').split(' ').map((p) => p[0]).slice(0, 2).join('')

const COLLAPSE_KEY = 'cg.sidebar.collapsed'
const readCollapsed = () => { try { return localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false } }
const greeting = (h = new Date().getHours()) => (h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening')

/** Greeting + live status on each role's home page (one place for all five roles). */
function HomeBanner({ badges }: { badges: Record<string, number | undefined> }) {
  const me = useAuthStore((st) => st.me)!
  const meta = ROLE_META[me.role]
  const quick = navFor(me.role, me.permissions).flatMap((sec) => sec.items).filter((i) => i.to !== HOME[me.role]).slice(0, 3)
  const chips: [string, number | undefined, string][] = [
    ['active incidents', badges.incidents, 'bg-crit'], ['awaiting approval', badges.approvals, 'bg-[#2a78d6]'],
    ['open work orders', badges.workorders, 'bg-[#2a78d6]'], ['transit alerts', badges.transit, 'bg-crit'],
  ]
  return (
    <section className="relative mb-6 overflow-hidden rounded-2xl border border-line bg-surface px-5 py-4 sm:px-6"
      style={{ backgroundImage: `linear-gradient(110deg, ${meta.soft}, transparent 55%)` }} aria-label="Welcome">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="grid place-items-center size-11 rounded-2xl text-white shadow-sm" style={{ background: meta.accent }}><meta.icon size={20} /></span>
          <div className="min-w-0">
            <p className="display text-[19px] font-semibold text-ink leading-tight">{greeting()}, {me.name.replace(/^Dr\.\s*/, '').split(' ')[0]}</p>
            <p className="text-[12.5px] text-ink-3 truncate">{me.role_label} · {me.global_scope ? 'all facilities' : `${me.facility_ids.length} facilit${me.facility_ids.length === 1 ? 'y' : 'ies'}`} · {meta.tagline}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {chips.filter(([, n]) => n !== undefined).map(([label, n, dot]) => (
            <span key={label} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 h-8 text-xs text-ink-2">
              <span className={cx('size-2 rounded-full', n ? dot : 'bg-ok')} /><b className="tabular-nums text-ink">{n}</b> {label}
            </span>))}
          {quick.map((i) => (
            <Link key={i.to} to={i.to} className="hidden md:inline-flex items-center gap-1.5 rounded-lg px-2.5 h-8 text-xs font-medium text-ink-2 hover:bg-surface-2">
              <i.icon size={14} />{i.label}<ArrowRight size={12} className="text-ink-3" /></Link>))}
        </div>
      </div>
    </section>
  )
}

export function AppShell() {
  const { me, refreshToken, clear } = useAuthStore()
  const { theme, toggle } = useThemeStore()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const toggleCollapsed = () => setCollapsed((c) => { try { localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1') } catch { /* storage blocked */ } return !c })
  const [palette, setPalette] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => setMobileOpen(false), [location.pathname])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const badges = useBadges(me?.permissions || [])
  if (!me) return null
  const sections = navFor(me.role, me.permissions)

  const logout = async () => {
    try { if (refreshToken) await Auth.logout(refreshToken) } catch { /* session already invalid */ }
    realtime.disconnect()
    clear()
    navigate('/login')
  }

  const meta = ROLE_META[me.role]
  const scopeLabel = me.global_scope ? 'All facilities' : `${me.facility_ids.length} facilit${me.facility_ids.length === 1 ? 'y' : 'ies'} in scope`
  const sidebar = (mini: boolean) => (
    <aside className={cx('flex h-full flex-col bg-navy-900 text-[#c6d2e3] border-r border-white/5 transition-[width] duration-200', mini ? 'w-[76px]' : 'w-[264px]')}
      style={{ backgroundImage: `radial-gradient(420px 260px at 0% 0%, ${meta.soft}, transparent 70%)` }} aria-label="Sidebar">
      <div className={cx('flex items-center h-16 shrink-0', mini ? 'justify-center px-2' : 'gap-2.5 px-5')}>
        <Link to={HOME[me.role]} className="flex items-center gap-2.5" aria-label="ColdGuard home">
          <span className="grid place-items-center size-9 rounded-xl bg-gradient-to-br from-brand-500 to-[#2a78d6] text-white shadow-lg shadow-brand-600/20"><Snowflake size={18} /></span>
          {!mini && <span className="text-[17px] font-semibold text-white tracking-tight">ColdGuard</span>}
        </Link>
        {!mini && <span className="ml-auto rounded-md px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-white" style={{ background: meta.accent }}>{me.role.toLowerCase()}</span>}
      </div>

      <Link to="/profile" title={mini ? `${me.name} — ${me.role_label}` : undefined}
        className={cx('mb-3 flex items-center rounded-2xl border border-white/[0.06] bg-white/[0.04] hover:bg-white/[0.07] transition-colors', mini ? 'mx-3 justify-center p-2' : 'mx-4 gap-3 p-3')}>
        <span className="relative grid place-items-center size-10 shrink-0 rounded-xl text-white text-[13px] font-semibold"
          style={{ background: `linear-gradient(135deg, ${meta.accent}, #22324b)` }}>
          {initials(me.name)}
          <span className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-navy-900 bg-ok" aria-hidden />
        </span>
        {!mini && (
          <span className="min-w-0">
            <span className="block text-[13.5px] font-medium text-white truncate">{me.name}</span>
            <span className="block text-[11.5px] truncate" style={{ color: meta.accent }}>{me.role_label}</span>
            <span className="block text-[10.5px] text-[#8aa0bd] truncate">{scopeLabel}</span>
          </span>)}
      </Link>

      <nav className={cx('flex-1 overflow-y-auto py-1 space-y-5', mini ? 'px-2' : 'px-3')} aria-label="Main">
        {sections.map((sec) => (
          <div key={sec.title}>
            {mini ? <div className="mx-3 mb-2 h-px bg-white/[0.06]" aria-hidden />
              : <p className="px-3 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#6f86a6]">{sec.title}</p>}
            <ul className="space-y-0.5">
              {sec.items.map((i) => {
                const count = i.badge ? badges[i.badge] : undefined
                const alarm = i.badge === 'incidents' || i.badge === 'transit'
                return (
                  <li key={i.to}>
                    <NavLink to={i.to} end={i.to.split('/').length <= 2} title={mini ? i.label : undefined}
                      className={({ isActive }) => cx('group relative flex items-center rounded-xl h-10 text-[13.5px] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-brand-500',
                        mini ? 'justify-center' : 'gap-3 px-3',
                        isActive ? 'bg-white/[0.09] text-white font-medium shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]' : 'hover:bg-white/[0.05] hover:text-white')}>
                      {({ isActive }) => (<>
                        {isActive && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r" style={{ background: meta.accent }} />}
                        <span className={cx('grid place-items-center size-7 rounded-lg transition-colors', isActive ? 'text-white' : 'text-[#7f95b3] group-hover:text-[#c6d2e3]')}
                          style={isActive ? { background: meta.soft, color: meta.accent } : undefined}><i.icon size={16} /></span>
                        {!mini && <span className="flex-1 truncate">{i.label}</span>}
                        {!!count && (mini
                          ? <span className={cx('absolute top-1.5 right-2 size-2 rounded-full', alarm ? 'bg-crit' : 'bg-[#2a78d6]')} aria-label={`${count} pending`} />
                          : <span className={cx('rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold text-white tabular-nums', alarm ? 'bg-crit' : 'bg-[#2a78d6]')}>{count}</span>)}
                      </>)}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      {!mini && (
        <div className="mx-4 mb-2 rounded-xl border border-white/5 px-3 py-2.5 text-[11px] text-[#8aa0bd] flex items-start gap-2">
          <FlaskConical size={14} className="mt-0.5 shrink-0 text-[#86b6ef]" />
          <span>Readings tagged <b className="text-[#cde2fb]">Simulated</b> come from the demo simulator, not hardware.</span>
        </div>)}
      <div className={cx('mb-4 flex gap-1', mini ? 'mx-2 flex-col items-center' : 'mx-3')}>
        <button onClick={logout} title="Sign out" className={cx('flex items-center rounded-xl h-10 text-[13.5px] hover:bg-white/[0.05] hover:text-white', mini ? 'w-10 justify-center' : 'flex-1 gap-3 px-3')}>
          <LogOut size={17} className="text-[#7f95b3]" />{!mini && 'Sign out'}
        </button>
        <button onClick={toggleCollapsed} className="hidden lg:grid place-items-center size-10 rounded-xl hover:bg-white/[0.05] text-[#7f95b3] hover:text-white"
          aria-label={mini ? 'Expand sidebar' : 'Collapse sidebar'} title={mini ? 'Expand sidebar' : 'Collapse sidebar'}>
          {mini ? <ChevronsRight size={17} /> : <ChevronsLeft size={17} />}
        </button>
      </div>
    </aside>
  )

  return (
    <div className="flex h-full">
      <div className="hidden lg:block shrink-0">{sidebar(collapsed)}</div>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setMobileOpen(false)} />
          <div className="relative h-full w-[264px]">{sidebar(false)}
            <button className="absolute top-4 -right-11 btn-secondary h-9 w-9 p-0" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={16} /></button>
          </div>
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 h-16 shrink-0 flex items-center gap-2.5 border-b border-line bg-surface/80 backdrop-blur-md px-4 sm:px-6">
          <button className="lg:hidden btn-ghost h-9 w-9 p-0" onClick={() => setMobileOpen(true)} aria-label="Open menu"><MenuIcon size={18} /></button>
          <button onClick={() => setPalette(true)} className="flex items-center gap-2 h-9 w-full max-w-sm rounded-xl border border-line bg-surface px-3 text-[13px] text-ink-3 hover:border-brand-200">
            <Search size={15} /><span className="flex-1 text-left">Search pages, incidents, batches…</span>
            <kbd className="hidden sm:inline rounded-md border border-line bg-surface-2 px-1.5 text-[10.5px]">Ctrl K</kbd>
          </button>
          <div className="flex-1" />
          <ConnectionIndicator />
          <button onClick={toggle} className="btn-secondary h-9 w-9 p-0" aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} title="Toggle theme">
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <NotificationCenter />
          <Menu as="div" className="relative">
            <MenuButton className="flex items-center gap-2.5 rounded-xl border border-line bg-surface pl-1.5 pr-2.5 h-10 hover:bg-surface-2">
              <span className="grid place-items-center size-7 rounded-lg bg-gradient-to-br from-navy-700 to-navy-900 text-white text-[11px] font-semibold">{initials(me.name)}</span>
              <span className="hidden sm:block text-left">
                <span className="block text-[13px] font-medium leading-tight text-ink">{me.name}</span>
                <span className="block text-[11px] text-ink-3 leading-tight">{me.email}</span>
              </span>
              <ChevronDown size={14} className="text-ink-3" />
            </MenuButton>
            <MenuItems anchor="bottom end" className="z-40 mt-2 w-60 card shadow-xl p-1 focus:outline-none">
              <div className="px-3 py-2 border-b border-line mb-1">
                <p className="text-[13px] font-medium text-ink">{me.title || me.role_label}</p>
                <p className="text-[11px] text-ink-3">{me.role_label}</p>
              </div>
              <MenuItem><Link to="/profile" className="flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-ink data-focus:bg-surface-2"><CircleUserRound size={15} /> Profile & security</Link></MenuItem>
              <MenuItem><button onClick={toggle} className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-ink data-focus:bg-surface-2">{theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />} {theme === 'dark' ? 'Light theme' : 'Dark theme'}</button></MenuItem>
              <MenuItem><button onClick={logout} className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-crit-ink data-focus:bg-crit-bg"><LogOut size={15} /> Sign out</button></MenuItem>
            </MenuItems>
          </Menu>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 py-7">
            {location.pathname === HOME[me.role] && <HomeBanner badges={badges} />}
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  )
}
