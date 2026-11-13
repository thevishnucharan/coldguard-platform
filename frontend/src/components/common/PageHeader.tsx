import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export interface Crumb { label: string; to?: string }

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-ink-3 mb-1.5">
      {items.map((c, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight size={12} />}
          {c.to ? <Link to={c.to} className="hover:text-ink">{c.label}</Link> : <span className="text-ink-2">{c.label}</span>}
        </span>
      ))}
    </nav>
  )
}

export function PageHeader({ title, subtitle, crumbs, actions, meta }: {
  title: ReactNode; subtitle?: ReactNode; crumbs?: Crumb[]; actions?: ReactNode; meta?: ReactNode
}) {
  return (
    <header className="mb-6">
      {crumbs && <Breadcrumbs items={crumbs} />}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="display text-[28px] leading-tight font-semibold text-ink">{title}</h1>
          {subtitle && <p className="text-[13.5px] text-ink-3 mt-1 max-w-3xl">{subtitle}</p>}
          {meta && <div className="flex flex-wrap items-center gap-2 mt-2.5">{meta}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}
