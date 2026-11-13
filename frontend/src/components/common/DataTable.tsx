import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { cx } from '../../utils/format'
import { EmptyState, ErrorState, Skeleton } from './Feedback'

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  className?: string
  align?: 'left' | 'right' | 'center'
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function DataTable<T = any>({
  columns, rows, loading, error, onRetry, onRowClick, empty, rowKey, selectedKey, dense,
}: {
  columns: Column<T>[]; rows: T[] | null | undefined; loading?: boolean; error?: string | null; onRetry?: () => void
  onRowClick?: (row: T) => void; empty?: ReactNode; rowKey?: (row: T) => string; selectedKey?: string | null; dense?: boolean
}) {
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  return (
    <div className="overflow-x-auto -mx-px">
      <table className="w-full border-collapse">
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={cx('th', c.align === 'right' && 'text-right', c.className)}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {loading && !rows?.length
            ? Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>{columns.map((c) => <td key={c.key} className="td"><Skeleton className="h-4 w-full max-w-40" /></td>)}</tr>
              ))
            : rows?.map((r, i) => {
                const k = rowKey ? rowKey(r) : ((r as { id?: string }).id ?? String(i))
                return (
                  <tr key={k} onClick={onRowClick ? () => onRowClick(r) : undefined}
                      className={cx(onRowClick && 'cursor-pointer hover:bg-canvas/70', selectedKey === k && 'bg-brand-50/60')}>
                    {columns.map((c) => (
                      <td key={c.key} className={cx('td', dense && 'py-2', c.align === 'right' && 'text-right tabular-nums', c.align === 'center' && 'text-center', c.className)}>
                        {c.render(r)}
                      </td>
                    ))}
                  </tr>
                )
              })}
        </tbody>
      </table>
      {!loading && !rows?.length && (empty ?? <EmptyState title="No records found" description="Try adjusting the filters." />)}
    </div>
  )
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  return (
    <div className="flex items-center justify-between gap-2 pt-3 text-xs text-ink-3">
      <span>{from}–{Math.min(total, page * pageSize)} of {total.toLocaleString()}</span>
      <div className="flex items-center gap-1">
        <button className="btn-ghost btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft size={14} /></button>
        <span className="px-1 text-ink-2">Page {page} / {pages}</span>
        <button className="btn-ghost btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight size={14} /></button>
      </div>
    </div>
  )
}
