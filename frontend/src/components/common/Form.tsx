import { Search } from 'lucide-react'
import type { ReactNode } from 'react'
import { cx } from '../../utils/format'

export function Field({ label, error, hint, children, required, className }: {
  label: string; error?: string | null; hint?: string; children: ReactNode; required?: boolean; className?: string
}) {
  // The <label> wraps its control so the association is programmatic (screen readers, getByLabelText).
  return (
    <div className={className}>
      <label className="block">
        <span className="label">{label}{required && <span className="text-crit"> *</span>}</span>
        {children}
      </label>
      {error ? <p className="text-[11px] text-crit mt-1" role="alert">{error}</p> : hint && <p className="text-[11px] text-ink-3 mt-1">{hint}</p>}
    </div>
  )
}

export function Select({ value, onChange, options, placeholder, className, ariaLabel }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]
  placeholder?: string; className?: string; ariaLabel?: string
}) {
  return (
    <select aria-label={ariaLabel || placeholder} className={cx('input pr-8', className)} value={value} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

export function SearchInput({ value, onChange, placeholder = 'Search…', className }: {
  value: string; onChange: (v: string) => void; placeholder?: string; className?: string
}) {
  return (
    <div className={cx('relative', className)}>
      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
      <input className="input pl-8" value={value} placeholder={placeholder} aria-label={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

export function Segmented<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-canvas p-0.5" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cx('px-2.5 h-7 rounded-md text-xs font-medium transition-colors',
            value === o.value ? 'bg-surface text-ink shadow-sm' : 'text-ink-3 hover:text-ink')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2 mb-3">{children}</div>
}

export function Tabs<T extends string>({ value, onChange, tabs }: {
  value: T; onChange: (v: T) => void; tabs: { value: T; label: string; count?: number }[]
}) {
  return (
    <div className="flex gap-1 border-b border-line mb-4 overflow-x-auto" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)}
          className={cx('px-3 py-2 text-[13px] font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
            value === t.value ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-3 hover:text-ink')}>
          {t.label}{t.count !== undefined && <span className="ml-1.5 rounded bg-canvas px-1.5 text-[11px] text-ink-2">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

export const DAY_RANGES = [
  { value: '1', label: '24 h' }, { value: '7', label: '7 d' }, { value: '30', label: '30 d' }, { value: '90', label: '90 d' },
]
