import { format, formatDistanceStrict } from 'date-fns'

export const fmtTemp = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(digits).replace('-', '−')}°C` // true minus sign

export const fmtDateTime = (s: string | null | undefined) => (s ? format(new Date(s), 'dd MMM yyyy, HH:mm') : '—')
export const fmtDate = (s: string | null | undefined) => (s ? format(new Date(s), 'dd MMM yyyy') : '—')
export const fmtTime = (s: string | null | undefined) => (s ? format(new Date(s), 'HH:mm:ss') : '—')

export function ago(s: string | null | undefined, now = Date.now()) {
  if (!s) return 'never'
  const d = new Date(s).getTime()
  if (now - d < 15000) return 'just now'
  return `${formatDistanceStrict(d, now)} ago`
}

export function fmtDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return '—'
  const m = Math.floor(seconds / 60)
  if (m < 1) return `${seconds}s`
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h} h ${m % 60} m`
  return `${Math.floor(h / 24)} d ${h % 24} h`
}

export const fmtNum = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: digits })

export const humanize = (s: string | null | undefined) =>
  s ? s.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()) : '—'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')
