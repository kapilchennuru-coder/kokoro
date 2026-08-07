import type { CSSProperties, ReactNode } from 'react'
import { statusLabel } from '../lib/labels'

export function MetricCard({
  label,
  value,
  hint,
  loading,
}: {
  label: string
  value: string | number
  hint?: string
  loading?: boolean
}) {
  return (
    <div className="card metric-card">
      <div className="metric-label">{label}</div>
      {loading ? (
        <div className="skeleton" style={{ height: 32, width: 80, marginTop: 8 }} />
      ) : (
        <div className="metric-value">{value}</div>
      )}
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state card">
      <div className="empty-icon" aria-hidden>
        ∅
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state card">
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" className="btn btn-primary" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  )
}

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return (
    <div className="card" style={{ padding: 16, display: 'grid', gap: 10 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 18, width: `${90 - i * 8}%` }} />
      ))}
    </div>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: 'badge',
    ready: 'badge badge-info',
    running: 'badge badge-accent',
    paused: 'badge badge-warning',
    completed: 'badge badge-success',
    failed: 'badge badge-danger',
    answered: 'badge badge-success',
    successful: 'badge badge-success',
    no_answer: 'badge badge-warning',
    busy: 'badge badge-warning',
    in_progress: 'badge badge-info',
    not_called: 'badge badge-info',
    calling: 'badge badge-accent',
    valid: 'badge badge-success',
    invalid: 'badge badge-danger',
    duplicate: 'badge badge-warning',
    connecting: 'badge badge-info',
    speaking: 'badge badge-accent',
    thinking: 'badge badge-info',
    listening: 'badge badge-info',
    idle: 'badge',
    processing: 'badge badge-info',
  }
  return <span className={map[status] || 'badge'}>{statusLabel(status)}</span>
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="pagination">
      <span className="secondary">
        {total} total · page {page} of {pages}
      </span>
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  )
}

export function Drawer({
  open,
  title,
  onClose,
  children,
  width = 440,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  width?: number
}) {
  if (!open) return null
  return (
    <div className="drawer-overlay" onClick={onClose} role="presentation">
      <aside
        className="drawer"
        style={{ '--drawer-w': `${width}px` } as CSSProperties}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="drawer-header">
          <h2>{title}</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            Close
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  )
}
