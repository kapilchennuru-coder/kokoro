import { useCallback, useRef, useState } from 'react'

type Props = {
  onFile: (file: File) => Promise<void> | void
  disabled?: boolean
  statusMessage?: string | null
}

export function FileUpload({ onFile, disabled, statusMessage }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [localStatus, setLocalStatus] = useState<string | null>(null)

  const handle = useCallback(
    async (file: File | undefined) => {
      if (!file || disabled) return
      const lower = file.name.toLowerCase()
      if (!lower.endsWith('.xlsx') && !lower.endsWith('.xls') && !lower.endsWith('.csv')) {
        setError('Please upload an Excel file (.xlsx or .xls)')
        return
      }
      setError(null)
      setLocalStatus('Reading file...')
      setProgress(18)
      const timer = window.setInterval(() => {
        setProgress((p) => (p === null || p >= 88 ? p : p + 6))
      }, 140)
      try {
        await onFile(file)
        setProgress(100)
        setLocalStatus(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unable to upload file')
        setProgress(null)
        setLocalStatus(null)
      } finally {
        window.clearInterval(timer)
        window.setTimeout(() => setProgress(null), 400)
      }
    },
    [disabled, onFile],
  )

  const message = statusMessage || localStatus

  return (
    <div
      className={`upload-zone ${drag ? 'drag' : ''} ${error ? 'has-error' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDrag(true)
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDrag(false)
        void handle(e.dataTransfer.files?.[0])
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xls,.csv"
        hidden
        disabled={disabled}
        onChange={(e) => void handle(e.target.files?.[0])}
      />
      <div className="upload-icon" aria-hidden>
        ↑
      </div>
      <strong>{drag ? 'Drop your file here' : 'Drag & drop your Excel file'}</strong>
      <p>Supports .xlsx and .xls</p>
      <button
        type="button"
        className="btn btn-primary"
        style={{ marginTop: 16 }}
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation()
          inputRef.current?.click()
        }}
      >
        Choose Excel File
      </button>
      {progress !== null || message ? (
        <div style={{ marginTop: 16 }}>
          {message ? <div className="secondary" style={{ fontSize: '0.85rem', marginBottom: 8 }}>{message}</div> : null}
          {progress !== null ? (
            <div className="upload-progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
              <div style={{ width: `${progress}%` }} />
            </div>
          ) : null}
        </div>
      ) : null}
      {error ? <div className="upload-msg error">{error}</div> : null}
    </div>
  )
}
