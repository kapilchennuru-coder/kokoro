import type { ReactNode } from 'react'

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Import Records',
  cancelLabel = 'Cancel',
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null
  return (
    <div className="drawer-overlay" onClick={onCancel} role="presentation">
      <div
        className="card"
        style={{
          width: 'min(420px, calc(100vw - 32px))',
          margin: '20vh auto 0',
          padding: 24,
          position: 'relative',
        }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <h2 id="confirm-title" style={{ margin: '0 0 8px', fontFamily: 'var(--font-display)', fontSize: '1.15rem' }}>
          {title}
        </h2>
        <p className="secondary" style={{ margin: '0 0 20px', fontSize: '0.9rem' }}>
          {message}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={onConfirm}>
            {busy ? 'Importing…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function StepHint({ children }: { children: ReactNode }) {
  return (
    <div className="muted" style={{ fontSize: '0.8rem', marginBottom: 12 }}>
      {children}
    </div>
  )
}
