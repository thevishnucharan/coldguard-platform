import {
  AlertOctagon, ArrowUpCircle, CheckCircle2, CircleDot, ClipboardCheck, FileCheck2, MessageSquare, RefreshCcw,
  ShieldCheck, ThermometerSun, UserCheck, XCircle,
} from 'lucide-react'
import type { IncidentEvent } from '../../types'
import { cx, fmtDateTime, humanize } from '../../utils/format'

const ICONS: Record<string, [React.ComponentType<{ size?: number }>, string]> = {
  DETECTED: [AlertOctagon, 'text-crit bg-crit-bg'], OPENED: [CircleDot, 'text-crit bg-crit-bg'],
  ACKNOWLEDGED: [UserCheck, 'text-warn-ink bg-warn-bg'], INVESTIGATION_STARTED: [CircleDot, 'text-warn-ink bg-warn-bg'],
  NOTE_ADDED: [MessageSquare, 'text-ink-2 bg-canvas'], ESCALATED: [ArrowUpCircle, 'text-crit bg-crit-bg'],
  SEVERITY_RAISED: [ArrowUpCircle, 'text-crit bg-crit-bg'], CORRECTIVE_ACTION_PROPOSED: [ClipboardCheck, 'text-info-ink bg-info-bg'],
  CORRECTIVE_ACTION_APPROVED: [CheckCircle2, 'text-ok bg-ok-bg'], CORRECTIVE_ACTION_REJECTED: [XCircle, 'text-crit bg-crit-bg'],
  FURTHER_INVESTIGATION_REQUESTED: [RefreshCcw, 'text-warn-ink bg-warn-bg'], CORRECTIVE_ACTION_IMPLEMENTED: [FileCheck2, 'text-brand-700 bg-brand-50'],
  RECOVERY_VERIFIED: [ShieldCheck, 'text-ok bg-ok-bg'], RESOLVED: [CheckCircle2, 'text-ok bg-ok-bg'], CLOSED: [CheckCircle2, 'text-ink-2 bg-canvas'],
  CLOSED_FALSE_ALARM: [XCircle, 'text-ink-2 bg-canvas'], TEMPERATURE_RECOVERED: [ThermometerSun, 'text-ok bg-ok-bg'],
  TELEMETRY_RESTORED: [CheckCircle2, 'text-ok bg-ok-bg'],
}

/** Immutable incident event history (append-only on the server). */
export function IncidentTimeline({ events }: { events: IncidentEvent[] }) {
  return (
    <ol className="relative">
      {events.map((e, i) => {
        const [Icon, tone] = ICONS[e.event_type] || [CircleDot, 'text-ink-2 bg-canvas']
        return (
          <li key={e.id} className="relative flex gap-3 pb-4">
            {i < events.length - 1 && <span className="absolute left-[13px] top-7 bottom-0 w-px bg-line" aria-hidden />}
            <span className={cx('grid place-items-center size-7 rounded-full shrink-0 ring-4 ring-surface', tone)}><Icon size={14} /></span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[13px] font-medium text-ink">{humanize(e.event_type)}</span>
                <span className="text-xs text-ink-3">by {e.actor_name} · {fmtDateTime(e.created_at)}</span>
              </div>
              {e.to_status && e.from_status && <div className="text-[11px] text-ink-3">{humanize(e.from_status)} → {humanize(e.to_status)}</div>}
              {e.note && <p className="text-xs text-ink-2 mt-1 whitespace-pre-wrap">{e.note}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
