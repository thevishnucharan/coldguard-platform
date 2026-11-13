/** Lightweight SVG charts (no library): sparkline, gauge, horizontal bar list. */

export function Sparkline({ points, min, max, width = 120, height = 32, stale }: {
  points: { v: number }[]; min: number; max: number; width?: number; height?: number; stale?: boolean
}) {
  if (points.length < 2) return <div style={{ width, height }} className="grid place-items-center text-[10px] text-ink-3">no data</div>
  const vals = points.map((p) => p.v)
  const lo = Math.min(min - 0.5, ...vals)
  const hi = Math.max(max + 0.5, ...vals)
  const y = (v: number) => height - 2 - ((v - lo) / (hi - lo || 1)) * (height - 4)
  const x = (i: number) => (i / (points.length - 1)) * (width - 2) + 1
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join('')
  const last = points[points.length - 1].v
  const out = last > max || last < min
  return (
    <svg width={width} height={height} role="img" aria-label={`Trend, latest ${last.toFixed(1)}°C`} className="overflow-visible">
      <rect x={0} y={y(max)} width={width} height={Math.max(0, y(min) - y(max))} fill="var(--color-ok)" opacity={0.08} />
      <path d={d} fill="none" stroke={stale ? 'var(--color-ink-3)' : 'var(--color-series-1)'} strokeWidth={1.5}
        strokeDasharray={stale ? '3 2' : undefined} />
      <circle cx={x(points.length - 1)} cy={y(last)} r={2.5} fill={out ? 'var(--color-crit)' : 'var(--color-series-1)'} />
    </svg>
  )
}

/** Half-circle gauge (value of total). Status colour by ratio; label + number always shown. */
export function Gauge({ value, total, label, size = 180 }: { value: number; total: number; label: string; size?: number }) {
  const r = size / 2 - 14
  const cx = size / 2
  const cy = size / 2 + 4
  const ratio = total > 0 ? Math.min(1, value / total) : 0
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from), a1 = Math.PI * (1 - to)
    return `M${cx + r * Math.cos(a0)},${cy - r * Math.sin(a0)} A${r},${r} 0 0 1 ${cx + r * Math.cos(a1)},${cy - r * Math.sin(a1)}`
  }
  const color = ratio >= 0.5 ? 'var(--color-crit)' : ratio >= 0.2 ? 'var(--color-serious)' : ratio > 0 ? 'var(--color-warn)' : 'var(--color-ok)'
  const ang = Math.PI * (1 - ratio)
  return (
    <figure className="flex flex-col items-center">
      <svg width={size} height={size / 2 + 22} role="img" aria-label={`${label}: ${value} of ${total}`}>
        <path d={arc(0, 1)} stroke="var(--color-line)" strokeWidth={14} fill="none" strokeLinecap="round" />
        {ratio > 0 && <path d={arc(0, ratio)} stroke={color} strokeWidth={14} fill="none" strokeLinecap="round" />}
        <line x1={cx} y1={cy} x2={cx + (r - 18) * Math.cos(ang)} y2={cy - (r - 18) * Math.sin(ang)} stroke="var(--color-ink-2)" strokeWidth={2.5} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={4} fill="var(--color-ink-2)" />
        <text x={cx - r} y={cy + 16} fontSize={10} fill="var(--color-ink-3)" textAnchor="middle">0</text>
        <text x={cx + r} y={cy + 16} fontSize={10} fill="var(--color-ink-3)" textAnchor="middle">{total}</text>
      </svg>
      <figcaption className="text-center -mt-1">
        <div className="text-2xl font-semibold text-ink tabular-nums">{value}</div>
        <div className="text-xs text-ink-3">{label}</div>
      </figcaption>
    </figure>
  )
}

/** Horizontal bar list (compact ranking). Text in ink tokens; bar carries magnitude only. */
export function BarList({ items, max, unit = '', color = 'var(--color-series-1)', format }: {
  items: { label: string; value: number | null; hint?: string }[]; max?: number; unit?: string; color?: string
  format?: (v: number) => string
}) {
  const m = max ?? Math.max(1, ...items.map((i) => i.value ?? 0))
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.label}>
          <div className="flex items-baseline justify-between text-xs mb-1">
            <span className="text-ink-2 truncate pr-2">{i.label}</span>
            <span className="text-ink font-medium tabular-nums">{i.value === null ? '—' : format ? format(i.value) : `${i.value}${unit}`}</span>
          </div>
          <div className="h-2 rounded-full bg-canvas overflow-hidden" title={i.hint}>
            <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, ((i.value ?? 0) / m) * 100))}%`, background: color }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
