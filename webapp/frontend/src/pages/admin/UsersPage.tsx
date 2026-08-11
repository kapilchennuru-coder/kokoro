import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Drawer, EmptyState, ErrorState, LoadingState, StatusBadge } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { friendlyError } from '../../lib/labels'
import type { AdminUser, Role } from '../../types'

const ROLES: Role[] = ['SUPER_ADMIN', 'ADMIN', 'MANAGER', 'AGENT', 'VIEWER']

export function UsersPage() {
  const { user: me } = useAuth()
  const { push } = useToast()
  const [items, setItems] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [form, setForm] = useState({ username: '', email: '', password: '', role: 'AGENT' as Role })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.admin.users()
      setItems(res.users)
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load users'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const createUser = async () => {
    if (!form.username || !form.password) {
      push('Username and password are required', 'error')
      return
    }
    setBusy(true)
    try {
      await api.admin.createUser(form)
      push('User created', 'success')
      setCreating(false)
      setForm({ username: '', email: '', password: '', role: 'AGENT' })
      await load()
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to create user'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const changeRole = async (u: AdminUser, role: Role) => {
    try {
      await api.admin.updateUser(u.id, { role })
      push('Role updated', 'success')
      await load()
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to update role'), 'error')
    }
  }

  const toggleStatus = async (u: AdminUser) => {
    try {
      await api.admin.updateUser(u.id, { status: u.status === 'active' ? 'inactive' : 'active' })
      push(u.status === 'active' ? 'User deactivated' : 'User reactivated', 'success')
      await load()
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to update status'), 'error')
    }
  }

  const submitReset = async () => {
    if (!resetTarget || resetPassword.length < 8) {
      push('Password must be at least 8 characters', 'error')
      return
    }
    setBusy(true)
    try {
      await api.admin.resetPassword(resetTarget.id, resetPassword)
      push('Password reset', 'success')
      setResetTarget(null)
      setResetPassword('')
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to reset password'), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Users</h1>
          <p>Manage accounts, roles, and access</p>
        </div>
        <div className="spacer" />
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          Add User
        </button>
      </div>

      {loading ? (
        <LoadingState rows={6} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState title="No users yet" description="Add a user to get started." />
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.email || '—'}</td>
                  <td>
                    <select
                      className="select"
                      style={{ maxWidth: 160 }}
                      value={u.role}
                      disabled={u.id === me?.id}
                      onChange={(e) => void changeRole(u, e.target.value as Role)}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <StatusBadge status={u.status} />
                  </td>
                  <td>{u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setResetTarget(u)}>
                        Reset password
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={u.id === me?.id}
                        onClick={() => void toggleStatus(u)}
                      >
                        {u.status === 'active' ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Drawer open={creating} title="Add user" onClose={() => setCreating(false)}>
        <div style={{ display: 'grid', gap: 12 }}>
          <label className="field">
            <span className="label">Username</span>
            <input className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </label>
          <label className="field">
            <span className="label">Email</span>
            <input className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label className="field">
            <span className="label">Temporary password</span>
            <input
              className="input"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="label">Role</span>
            <select className="select" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void createUser()}>
            {busy ? 'Creating…' : 'Create user'}
          </button>
        </div>
      </Drawer>

      <Drawer open={!!resetTarget} title={`Reset password — ${resetTarget?.username ?? ''}`} onClose={() => setResetTarget(null)}>
        <div style={{ display: 'grid', gap: 12 }}>
          <label className="field">
            <span className="label">New password</span>
            <input className="input" type="password" value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} />
          </label>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void submitReset()}>
            {busy ? 'Saving…' : 'Reset password'}
          </button>
        </div>
      </Drawer>
    </div>
  )
}
