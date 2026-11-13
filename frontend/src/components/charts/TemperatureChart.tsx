import { format } from 'date-fns'
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export interface TempPoint { t: string; v: number; sim?: boolean; anomaly?: string | null }

/** Temperature history against the approved range. One series => no legend box; the band and
 *  limit lines are labelled directly. Out-of-range readings get a critical marker. */
export function TemperatureChart({ points, min, max, margin = 0.5, height = 260, window }: {
  points: TempPoint[]; min: number; max: number; margin?: number; height?: number
  window?: { start?: string | null; end?: string | null }
}) {
  const data = points.map((p) => ({ ...p, ts: new Date(p.t).getTime() }))
  const vals = data.map((d) => d.v)
  const lo = Math.min(min - 1.5, ...vals)
  const hi = Math.max(max + 1.5, ...vals)
  const spanHours = data.length > 1 ? (data[data.length - 1].ts - data[0].ts) / 3.6e6 : 1
  const tickFmt = (ts: number) => format(ts, spanHours > 36 ? 'dd MMM' : 'HH:mm')
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 56, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="var(--color-line)" strokeDasharray="0" vertical={false} />
          <ReferenceArea y1={min} y2={max} fill="var(--color-ok)" fillOpacity={0.06} ifOverflow="extendDomain" />
          <ReferenceArea y1={max - margin} y2={max} fill="var(--color-warn)" fillOpacity={0.12} />
          <ReferenceArea y1={min} y2={min + margin} fill="var(--color-warn)" fillOpacity={0.12} />
          {window?.start && (
            <ReferenceArea x1={new Date(window.start).getTime()} x2={window.end ? new Date(window.end).getTime() : data.at(-1)?.ts}
              fill="var(--color-crit)" fillOpacity={0.06} />
          )}
          <ReferenceLine y={max} stroke="var(--color-crit)" strokeDasharray="4 3" strokeWidth={1}
            label={{ value: `max ${max}°`, position: 'right', fontSize: 11, fill: 'var(--color-ink-2)' }} />
          <ReferenceLine y={min} stroke="var(--color-series-1)" strokeDasharray="4 3" strokeWidth={1}
            label={{ value: `min ${min}°`, position: 'right', fontSize: 11, fill: 'var(--color-ink-2)' }} />
          <XAxis dataKey="ts" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={tickFmt}
            tick={{ fontSize: 11, fill: 'var(--color-ink-3)' }} axisLine={{ stroke: 'var(--color-line)' }} tickLine={false} minTickGap={40} />
          <YAxis domain={[Math.floor(lo), Math.ceil(hi)]} tick={{ fontSize: 11, fill: 'var(--color-ink-3)' }} axisLine={false}
            tickLine={false} width={44} unit="°" />
          <Tooltip
            cursor={{ stroke: 'var(--color-ink-3)', strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as TempPoint & { ts: number }
              const out = p.v > max || p.v < min
              return (
                <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-md text-xs">
                  <div className="text-ink-3">{format(p.ts, 'dd MMM, HH:mm:ss')}</div>
                  <div className="font-semibold text-ink text-[13px] mt-0.5">{p.v.toFixed(2)}°C</div>
                  <div className={out ? 'text-crit font-medium' : 'text-ink-2'}>{out ? 'Outside approved range' : 'Within range'}</div>
                  {p.anomaly && <div className="text-brand-700">Anomaly signal: {p.anomaly}</div>}
                  {p.sim && <div className="text-info-ink">Simulated reading</div>}
                </div>
              )
            }}
          />
          <Line type="monotone" dataKey="v" stroke="var(--color-series-1)" strokeWidth={2} isAnimationActive={false}
            dot={(props: { cx?: number; cy?: number; payload?: TempPoint; index?: number }) => {
              const { cx, cy, payload, index } = props
              if (!payload || cx === undefined || cy === undefined) return <g key={index} />
              const out = payload.v > max || payload.v < min
              if (!out && !payload.anomaly) return <g key={index} />
              return <circle key={index} cx={cx} cy={cy} r={4} fill={out ? 'var(--color-crit)' : 'var(--color-brand-600)'}
                stroke="var(--color-surface)" strokeWidth={2} />
            }}
            activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--color-surface)' }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
