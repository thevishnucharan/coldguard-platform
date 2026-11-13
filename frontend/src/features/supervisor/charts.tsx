import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const axis = { tick: { fontSize: 11, fill: 'var(--color-ink-3)' }, tickLine: false }

/** Single-series compliance trend (no legend box needed; title names the series). */
export function ComplianceTrend({ data, height = 240 }: { data: { date: string; compliance: number | null; readings: number }[]; height?: number }) {
  const vals = data.map((d) => d.compliance).filter((v): v is number => v !== null)
  const lo = vals.length ? Math.max(0, Math.floor(Math.min(...vals) - 2)) : 80
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ left: -12, right: 8, top: 8 }}>
          <defs><linearGradient id="cg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--color-series-1)" stopOpacity={0.18} /><stop offset="1" stopColor="var(--color-series-1)" stopOpacity={0} /></linearGradient></defs>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} {...axis} axisLine={{ stroke: 'var(--color-line)' }} />
          <YAxis domain={[lo, 100]} unit="%" {...axis} axisLine={false} width={48} />
          <Tooltip formatter={(v, _n, p) => [v === null ? 'no data' : `${v}% of ${(p.payload as { readings: number }).readings.toLocaleString()} readings`, 'In range']} />
          <Area dataKey="compliance" type="monotone" stroke="var(--color-series-1)" strokeWidth={2} fill="url(#cg)" connectNulls dot={{ r: 2.5 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Incidents per day by severity. Severity is a state, so the reserved status colours are used,
 *  with a legend (identity never by colour alone). */
export function IncidentsPerDay({ data, height = 220 }: { data: { date: string; WARNING: number; HIGH: number; CRITICAL: number }[]; height?: number }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: -18, right: 8, top: 8 }} barCategoryGap="25%">
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} {...axis} axisLine={{ stroke: 'var(--color-line)' }} />
          <YAxis allowDecimals={false} {...axis} axisLine={false} />
          <Tooltip cursor={{ fill: 'var(--color-canvas)' }} />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="CRITICAL" name="Critical" stackId="a" fill="var(--color-crit)" stroke="var(--color-surface)" strokeWidth={1} />
          <Bar dataKey="HIGH" name="High" stackId="a" fill="var(--color-serious)" stroke="var(--color-surface)" strokeWidth={1} />
          <Bar dataKey="WARNING" name="Warning" stackId="a" fill="var(--color-warn)" stroke="var(--color-surface)" strokeWidth={1} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
