import { Dialog, DialogPanel } from '@headlessui/react'
import { Boxes, CornerDownLeft, FileSearch, Search, ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Inventory, Incidents } from '../services/api/endpoints'
import { useAuthStore } from '../store/authStore'
import { cx } from '../utils/format'
import { navFor } from './navigation'

interface Item { id: string; label: string; hint: string; to: string; icon: React.ComponentType<{ size?: number; className?: string }> }

/** ⌘K / Ctrl+K: jump to any page you can access, or find incidents and batches by number/name.
 *  Results come from the API, so they are already permission- and scope-filtered. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const me = useAuthStore((s) => s.me)
  const can = useAuthStore((s) => s.can)
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [remote, setRemote] = useState<Item[]>([])
  const [active, setActive] = useState(0)

  const pages = useMemo<Item[]>(() => !me ? [] : navFor(me.role, me.permissions).flatMap((s) =>
    s.items.map((i) => ({ id: i.to, label: i.label, hint: s.title, to: i.to, icon: i.icon }))), [me])

  useEffect(() => {
    if (!open) { setQ(''); setRemote([]); setActive(0) }
  }, [open])

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setRemote([]); return }
    const t = window.setTimeout(async () => {
      const out: Item[] = []
      try {
        if (can('incidents.view')) {
          const r = await Incidents.list({ search: term, page_size: 5 })
          out.push(...r.items.map((i) => ({ id: i.id, label: `${i.incident_number} — ${i.title ?? ''}`, hint: `Incident · ${i.status.toLowerCase()}`, to: `/incidents/${i.id}`, icon: ShieldAlert })))
        }
        if (can('inventory.view')) {
          const r = await Inventory.batches({ search: term, page_size: 5 })
          out.push(...r.items.map((b) => ({ id: b.id, label: `${b.batch_number} — ${b.product_name ?? ''}`, hint: `Batch · ${b.facility_name ?? ''}`, to: `/inventory/batches/${b.id}`, icon: Boxes })))
        }
      } catch { /* show page matches only */ }
      setRemote(out)
    }, 250)
    return () => window.clearTimeout(t)
  }, [q, can])

  const items = useMemo(() => {
    const term = q.trim().toLowerCase()
    const pageHits = pages.filter((p) => !term || p.label.toLowerCase().includes(term) || p.hint.toLowerCase().includes(term))
    return [...pageHits.slice(0, 8), ...remote]
  }, [pages, remote, q])

  const go = (i: Item | undefined) => { if (i) { navigate(i.to); onClose() } }

  return (
    <Dialog open={open} onClose={onClose} className="relative z-[1000]">
      <div className="fixed inset-0 bg-navy-950/40 backdrop-blur-[2px]" aria-hidden />
      <div className="fixed inset-0 flex items-start justify-center p-4 pt-[12vh]">
        <DialogPanel className="card w-full max-w-xl shadow-2xl">
          <div className="flex items-center gap-2 border-b border-line px-4">
            <Search size={16} className="text-ink-3" />
            <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)) }
                if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)) }
                if (e.key === 'Enter') go(items[active])
              }}
              placeholder="Search pages, incident numbers, batches…" aria-label="Search"
              className="h-12 flex-1 bg-transparent text-[14px] text-ink placeholder:text-ink-3 outline-none" />
            <kbd className="rounded-md border border-line px-1.5 text-[10.5px] text-ink-3">Esc</kbd>
          </div>
          <ul className="max-h-80 overflow-y-auto p-2" role="listbox">
            {!items.length && <li className="flex items-center gap-2 px-3 py-6 justify-center text-xs text-ink-3"><FileSearch size={14} />No matches</li>}
            {items.map((i, idx) => (
              <li key={i.id} role="option" aria-selected={idx === active}>
                <button onMouseEnter={() => setActive(idx)} onClick={() => go(i)}
                  className={cx('w-full flex items-center gap-3 rounded-xl px-3 py-2 text-left', idx === active ? 'bg-brand-50' : 'hover:bg-surface-2')}>
                  <span className="grid place-items-center size-7 rounded-lg bg-surface-2 text-ink-2"><i.icon size={14} /></span>
                  <span className="min-w-0 flex-1"><span className="block truncate text-[13px] text-ink">{i.label}</span><span className="block text-[11px] text-ink-3">{i.hint}</span></span>
                  {idx === active && <CornerDownLeft size={13} className="text-ink-3" />}
                </button>
              </li>
            ))}
          </ul>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
