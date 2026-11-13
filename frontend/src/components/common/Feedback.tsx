import { AlertCircle, Inbox, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { cx } from '../../utils/format'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('skeleton', className)} />
}

export function LoadingBlock({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx('space-y-2.5', className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
    </div>
  )
}

export function PageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      <div className="grid lg:grid-cols-3 gap-4"><Skeleton className="h-72 lg:col-span-2" /><Skeleton className="h-72" /></div>
    </div>
  )
}

export function EmptyState({ title, description, icon: Icon = Inbox, action }: {
  title: string; description?: string; icon?: React.ComponentType<{ size?: number; className?: string }>; action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-10 px-4">
      <span className="grid place-items-center size-10 rounded-full bg-canvas text-ink-3 mb-3"><Icon size={18} /></span>
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {description && <p className="text-xs text-ink-3 mt-1 max-w-sm">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-crit/30 bg-crit-bg p-4">
      <AlertCircle size={18} className="text-crit mt-0.5 shrink-0" />
      <div className="flex-1">
        <p className="text-[13px] font-medium text-crit-ink">Could not load data</p>
        <p className="text-xs text-crit-ink/80 mt-0.5">{message}</p>
      </div>
      {onRetry && <button className="btn-secondary btn-sm" onClick={onRetry}><RefreshCw size={13} /> Retry</button>}
    </div>
  )
}
