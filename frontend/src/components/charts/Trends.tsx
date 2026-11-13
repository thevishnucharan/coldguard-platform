import { useId } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

const axis = { tick: { fontSize: 11, fill: 'var(--color-ink-3)' }, tickLine: false } as const

function Tip({ active, payload, label, unit = '', names }: {
  active?: boolean; payload?: { value: number | null; dataKey: string; color?: string }[]; label?: string; unit?: string; names?: Record<string, string>
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="text-ink-3 mb-0.5">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-ink">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          <span className="text-ink-2">{names?.[p.dataKey] ?? p.dataKey}</span>
          <span className="ml-auto font-semibold tabular-nums">{p.value === null ? '—' : `${p.value}${unit}`}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * Surveillance-style area chart: gradient fill, markers every `markerEvery` points and a
 * callout on the peak. One or two series (legend rendered by the caller as text chips).
 */
export function SurveillanceChart({ data, x, series, height = 260, unit = '', domain, markerEvery = 2 }: {
  data: Record<string, string | number | null>[]; x: string
  series: { key: string; name: string; color: string }[]; height?: number; unit?: string
  domain?: [number | 'auto', number | 'auto']; markerEvery?: number
}) {
  const uid = useId().replace(/:/g, '')
  const first = series[0]
  const vals = data.map((d) => d[first.key]).filter((v): v is number => typeof v === 'number')
  const peak = vals.length ? Math.max(...vals) : null
  const peakRow = peak !== null ? data.find((d) => d[first.key] === peak) : undefined
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ left: -8, right: 12, top: 26, bottom: 0 }}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`g-${uid}-${s.key}`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor={s.color} stopOpacity={0.28} />
                <stop offset="1" stopColor={s.color} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey={x} {...axis} axisLine={{ stroke: 'var(--color-line)' }} minTickGap={24} />
          <YAxis {...axis} axisLine={false} width={44} domain={domain ?? ['auto', 'auto']} unit={unit} />
          <Tooltip content={<Tip unit={unit} names={Object.fromEntries(series.map((s) => [s.key, s.name]))} />} cursor={{ stroke: 'var(--color-ink-3)', strokeDasharray: '3 3' }} />
          {series.map((s) => (
            <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} fill={`url(#g-${uid}-${s.key})`}
              connectNulls isAnimationActive={false}
              dot={(p: { cx?: number; cy?: number; index?: number; value?: number | null }) =>
                p.cx === undefined || p.cy === undefined || p.value === null || (p.index ?? 0) % markerEvery !== 0
                  ? <g key={p.index} />
                  : <circle key={p.index} cx={p.cx} cy={p.cy} r={3.5} fill="var(--color-surface)" stroke={s.color} strokeWidth={2} />}
              activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--color-surface)' }} />
          ))}
          {peakRow && peak !== null && (
            <ReferenceDot x={peakRow[x] as string} y={peak} r={5} fill={first.color} stroke="var(--color-surface)" strokeWidth={2}
              label={{ value: `${peakRow[x]}: ${peak}${unit}`, position: data.indexOf(peakRow) > data.length * 0.7 ? 'left' : data.indexOf(peakRow) < data.length * 0.3 ? 'right' : 'top', fontSize: 11, fill: 'var(--color-ink)', offset: 10 }} />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Small line with point markers (insight card). */
export function MiniLine({ data, color, height = 120, step }: { data: { x: string; v: number | null }[]; color: string; height?: number; step?: boolean }) {
  const uid = useId().replace(/:/g, '')
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ left: 2, right: 2, top: 8, bottom: 0 }}>
          <defs><linearGradient id={`m-${uid}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity={0.25} /><stop offset="1" stopColor={color} stopOpacity={0} /></linearGradient></defs>
          <XAxis dataKey="x" hide />
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Tooltip content={<Tip names={{ v: 'Value' }} />} />
          <Area type={step ? 'stepAfter' : 'monotone'} dataKey="v" stroke={color} strokeWidth={2} fill={`url(#m-${uid})`} isAnimationActive={false}
            dot={{ r: 3, fill: 'var(--color-surface)', stroke: color, strokeWidth: 1.5 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Column matrix (stacked cells) — e.g. hourly telemetry volume. */
export function MiniMatrix({ data, color, rows = 8, height = 120 }: { data: { x: string; v: number }[]; color: string; rows?: number; height?: number }) {
  const max = Math.max(1, ...data.map((d) => d.v))
  return (
    <div className="flex items-end gap-[3px]" style={{ height }} role="img" aria-label="Volume by hour">
      {data.map((d) => {
        const filled = Math.round((d.v / max) * rows)
        return (
          <div key={d.x} className="flex-1 flex flex-col-reverse gap-[3px]" title={`${d.x}: ${d.v}`}>
            {Array.from({ length: rows }).map((_, i) => (
              <span key={i} className="block h-[10px] rounded-[2px]" style={{ background: i < filled ? color : 'var(--color-line)', opacity: i < filled ? 0.55 + (0.45 * i) / rows : 0.6 }} />
            ))}
          </div>
        )
      })}
    </div>
  )
}

/** Simple vertical bars (two series stacked) with rounded tops. */
export function StackedBars({ data, x, series, height = 240 }: {
  data: Record<string, string | number>[]; x: string; series: { key: string; name: string; color: string }[]; height?: number
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: -14, right: 8, top: 8 }} barCategoryGap="28%">
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey={x} {...axis} axisLine={{ stroke: 'var(--color-line)' }} minTickGap={12} />
          <YAxis {...axis} axisLine={false} allowDecimals={false} />
          <Tooltip cursor={{ fill: 'var(--color-surface-2)' }} content={<Tip names={Object.fromEntries(series.map((s) => [s.key, s.name]))} />} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} stackId="a" fill={s.color} stroke="var(--color-surface)" strokeWidth={1}
              radius={i === series.length - 1 ? [5, 5, 0, 0] : undefined} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Two-series line with markers and legend chips rendered by caller. */
export function TwoLines({ data, x, series, height = 240 }: {
  data: Record<string, string | number>[]; x: string; series: { key: string; name: string; color: string }[]; height?: number
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ left: -16, right: 12, top: 10 }}>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey={x} {...axis} axisLine={{ stroke: 'var(--color-line)' }} />
          <YAxis {...axis} axisLine={false} allowDecimals={false} />
          <Tooltip content={<Tip names={Object.fromEntries(series.map((s) => [s.key, s.name]))} />} />
          {series.map((s) => (
            <Line key={s.key} dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} isAnimationActive={false}
              dot={{ r: 3.5, fill: 'var(--color-surface)', stroke: s.color, strokeWidth: 2 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Legend chips (identity never by colour alone: label text always present). */
export function LegendChips({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-ink-2">
      {items.map((i) => <span key={i.name} className="flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: i.color }} />{i.name}</span>)}
    </div>
  )
}

/** Gradient coverage bars ("equity gap" style). */
export function CoverageBars({ items, max = 100, unit = '%' }: { items: { label: string; value: number | null; color: string }[]; max?: number; unit?: string }) {
  return (
    <ul className="space-y-3">
      {items.map((i) => (
        <li key={i.label}>
          <div className="flex items-baseline justify-between text-[12.5px] mb-1">
            <span className="text-ink-2 truncate pr-2">{i.label}</span>
            <span className="font-semibold text-ink tabular-nums">{i.value === null ? '—' : `${i.value}${unit}`}</span>
          </div>
          <div className="h-3 rounded-md bg-surface-2 overflow-hidden">
            <div className="h-full rounded-md" style={{ width: `${Math.max(0, Math.min(100, ((i.value ?? 0) / max) * 100))}%`, background: `linear-gradient(90deg, color-mix(in srgb, ${i.color} 70%, white), ${i.color})` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
