import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { statusLabel } from '../lib/labels'
import type { Campaign } from '../types'

export function TopBar() {
  const { user, logout } = useAuth()
  const [active, setActive] = useState<Campaign | null>(null)
  const [notifs, setNotifs] = useState<Array<{ id: number; message: string; read: number }>>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const dash = (await api.dashboard()) as {
          active_campaign?: Campaign | null
          notifications?: Array<{ id: number; message: string; read: number }>
        }
        if (!alive) return
        setActive(dash.active_campaign || null)
        setNotifs(dash.notifications || [])
      } catch {
        /* ignore */
      }
    }
    void tick()
    const id = window.setInterval(tick, 8000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  const unread = notifs.filter((n) => !n.read).length
  const initials = (user?.client_name || user?.username || 'U')
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <>
      <header className="topbar">
        <div className="topbar-left">
          {active ? (
            <Link to={`/calls/live/${active.id}`} className="status-chip">
              {active.status === 'running' ? <span className="live-dot" /> : null}
              <strong>Calling in progress</strong>
              <span className="muted">· {statusLabel(active.status)}</span>
            </Link>
          ) : (
            <span className="status-chip">
              <span className="muted">Ready for outreach</span>
            </span>
          )}
        </div>
        <div className="topbar-right">
          <button
            type="button"
            className="btn btn-ghost btn-sm notif-btn"
            onClick={async () => {
              setOpen((v) => !v)
              if (!open) {
                try {
                  await api.markNotificationsRead()
                } catch {
                  /* ignore */
                }
              }
            }}
            aria-label="Notifications"
          >
            Alerts
            {unread > 0 ? <span className="notif-dot" /> : null}
          </button>
          <div className="profile">
            <div className="avatar">{initials}</div>
            <div style={{ lineHeight: 1.2 }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{user?.client_name || 'Outreach'}</div>
              <div className="muted" style={{ fontSize: '0.72rem' }}>
                {user?.username}
              </div>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      {open ? (
        <div className="notif-panel">
          <header>Notifications</header>
          {notifs.length === 0 ? (
            <div className="notif-item muted">No notifications yet</div>
          ) : (
            notifs.map((n) => (
              <div key={n.id} className="notif-item">
                {n.message}
              </div>
            ))
          )}
        </div>
      ) : null}
    </>
  )
}
