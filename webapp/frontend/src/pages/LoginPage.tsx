import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { friendlyError } from '../lib/labels'

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
      <div className="login-card">
        <div className="brand" style={{ marginBottom: 18, padding: 0 }}>
          <div className="brand-mark">O</div>
          <div className="brand-text">
            <strong style={{ color: 'var(--text)' }}>Outreach</strong>
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
  )
}
