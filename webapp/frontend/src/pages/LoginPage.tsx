import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { friendlyError } from '../lib/labels'
import { BrandMark } from '../components/BrandMark'
import { Wordmark } from '../components/Wordmark'

function WatermarkRing() {
  return (
    <svg className="watermark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="16" cy="16" r="9" stroke="currentColor" strokeWidth="1.1" />
      <circle cx="16" cy="16" r="2.6" fill="currentColor" />
      <path d="M24.2 9.3a13.2 13.2 0 0 1 3 8.4" stroke="currentColor" strokeWidth="0.9" strokeLinecap="round" opacity="0.6" />
      <path d="M26.8 5a19 19 0 0 1 4.5 12" stroke="currentColor" strokeWidth="0.9" strokeLinecap="round" opacity="0.35" />
    </svg>
  )
}

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const { push } = useToast()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!loading && user) return <Navigate to="/" replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username, password)
      push('Signed in', 'success')
    } catch (err) {
      setError(friendlyError(err instanceof Error ? err.message : 'Unable to sign in'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-brand">
        <WatermarkRing />
        <div className="login-brand-content">
          <BrandMark variant="mark" size={72} />
          <div className="wordmark"><Wordmark /></div>
          <p className="tagline">Making Every Call Count.</p>
          <p className="motto">Connect. Communicate. Collect.</p>
        </div>
      </div>

      <div className="login-form-panel">
        <div className="login-card">
          <div className="brand" style={{ marginBottom: 18, padding: 0 }}>
            <div className="brand-mark">
              <BrandMark />
            </div>
            <div className="brand-text">
              <strong className="brand-badge"><Wordmark text="Outreach" /></strong>
              <span>Sign in to continue</span>
            </div>
          </div>
          <h1>Sign in</h1>
          <p className="lede">Manage pending balance notifications.</p>
          <form onSubmit={onSubmit}>
            <label className="field">
              <span className="label">Username</span>
              <input
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label className="field">
              <span className="label">Password</span>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            {error ? <div style={{ color: 'var(--danger)', fontSize: '0.875rem' }}>{error}</div> : null}
            <button type="submit" className="btn btn-primary" disabled={busy} style={{ width: '100%', height: 42 }}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
