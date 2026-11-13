import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import type { ReactNode } from 'react'
import { cx } from '../../utils/format'

export function Card({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <section className={cx('card overflow-hidden', pad && 'card-pad', className)}>{children}</section>
}

export function CardHeader({ title, subtitle, actions, className }: {
  title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; className?: string
}) {
  return (
    <div className={cx('flex flex-wrap items-start justify-between gap-2 mb-4', className)}>
      <div className="min-w-0">
        <h3 className="card-title">{title}</h3>
        {subtitle && <p className="card-sub mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/**
 * Period-over-period change chip. `goodWhen` says which direction is good for this metric
 * (e.g. incidents going DOWN is good) so colour + arrow are never misleading.
 */
export function Delta({ value, suffix = '%', goodWhen = 'up', label }: {
  value: number | null | undefined; suffix?: string; goodWhen?: 'up' | 'down'; label?: string
}) {
  if (value === null || value === undefined || Number.isNaN(value)) return label ? <span className="text-xs text-ink-3">{label}</span> : null
  const flat = Math.abs(value) < 0.05
  const good = flat ? null : (value > 0) === (goodWhen === 'up')
  const Icon = flat ? Minus : value > 0 ? ArrowUpRight : ArrowDownRight
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={cx('inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-semibold tabular-nums',
        good === null ? 'bg-surface-2 text-ink-2' : good ? 'bg-ok-bg text-ok-ink' : 'bg-crit-bg text-crit-ink')}>
        <Icon size={12} />{value > 0 ? '+' : ''}{Number.isInteger(value) ? value : value.toFixed(1)}{suffix}
      </span>
      {label && <span className="text-ink-3">{label}</span>}
    </span>
  )
}

type Tone = 'neutral' | 'ok' | 'warn' | 'serious' | 'crit' | 'brand' | 'info'
const ICON_TONE: Record<Tone, string> = {
  neutral: 'bg-surface-2 text-ink-2', ok: 'bg-ok-bg text-ok-ink', serious: 'bg-serious-bg text-serious-ink',
  warn: 'bg-warn-bg text-warn-ink', crit: 'bg-crit-bg text-crit-ink', brand: 'bg-brand-50 text-brand-700', info: 'bg-info-bg text-info-ink',
}
const STRIP_TONE: Record<Tone, string> = {
  neutral: 'bg-ink-3', serious: 'bg-serious', ok: 'bg-ok', warn: 'bg-warn', crit: 'bg-crit', brand: 'bg-brand-500', info: 'bg-series-1',
}

/** KPI tile: icon chip, label, optional corner badge, hero value, delta/sub line and a
 *  proportion strip (e.g. 18 of 22 sensors online). */
export function KpiCard({ label, value, sub, icon: Icon, tone = 'neutral', ratio, onClick, badge, delta, className }: {
  label: string; value: ReactNode; sub?: ReactNode; icon?: React.ComponentType<{ size?: number; className?: string }>
  tone?: Tone; ratio?: number; onClick?: () => void; badge?: ReactNode; delta?: ReactNode; className?: string
}) {
  const Comp = onClick ? 'button' : 'div'
  return (
    <Comp onClick={onClick} className={cx('card card-pad text-left w-full flex flex-col', onClick && 'hover:border-brand-200 hover:-translate-y-px transition-all cursor-pointer', className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && <span className={cx('grid place-items-center size-7 rounded-lg shrink-0', ICON_TONE[tone])}><Icon size={15} /></span>}
          <span className="text-[13px] font-medium text-ink-2 truncate">{label}</span>
        </div>
        {badge && <span className="rounded-md bg-series-1 px-1.5 py-0.5 text-[10.5px] font-semibold text-white">{badge}</span>}
      </div>
      <div className="mt-3 display text-[32px] leading-none font-semibold text-ink tabular-nums">{value}</div>
      {(delta || sub) && <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">{delta}{sub && <span>{sub}</span>}</div>}
      {ratio !== undefined && (
        <div className="mt-auto pt-3 flex gap-[2px]" aria-hidden>
          {Array.from({ length: 28 }).map((_, i) => (
            <span key={i} className={cx('h-2 flex-1 rounded-[2px]', i < Math.round(Math.max(0, Math.min(1, ratio)) * 28) ? STRIP_TONE[tone] : 'bg-line')} />
          ))}
        </div>
      )}
    </Comp>
  )
}

/** Compact insight card (trend + three facts), e.g. "Excursion trend · Affected facility / Change / Confidence". */
export function InsightCard({ title, subtitle, chart, facts }: {
  title: string; subtitle: string; chart: ReactNode; facts: [string, ReactNode][]
}) {
  return (
    <Card className="flex flex-col">
      <h3 className="card-title">{title}</h3>
      <p className="card-sub mb-2">{subtitle}</p>
      <div className="flex-1 min-h-[120px]">{chart}</div>
      <dl className="mt-3 divide-y divide-line border-t border-line text-xs">
        {facts.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 py-1.5"><dt className="text-ink-3">{k}</dt><dd className="font-medium text-ink text-right">{v}</dd></div>
        ))}
      </dl>
    </Card>
  )
}
