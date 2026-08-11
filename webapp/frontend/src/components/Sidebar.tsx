import { NavLink } from 'react-router-dom'
import { BrandMark } from './BrandMark'
import { Wordmark } from './Wordmark'
import { useAuth } from '../context/AuthContext'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/patients', label: 'Patients' },
  { to: '/calls', label: 'Calls' },
  { to: '/settings', label: 'Settings' },
]

const adminLinks = [
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/login-history', label: 'Login History' },
  { to: '/admin/audit-logs', label: 'Audit Logs' },
  { to: '/admin/demo-requests', label: 'Demo Requests' },
]

export function Sidebar() {
  const { isAdmin } = useAuth()

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <BrandMark />
        </div>
        <div className="brand-text">
          <strong><Wordmark text="Outreach" /></strong>
          <span>Workspace</span>
        </div>
      </div>
      <nav className="nav" aria-label="Main">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.to === '/'} className={({ isActive }) => (isActive ? 'active' : undefined)}>
            <span className="label">{l.label}</span>
          </NavLink>
        ))}
      </nav>
      {isAdmin ? (
        <>
          <div className="nav-section-label">Administration</div>
          <nav className="nav" aria-label="Administration">
            {adminLinks.map((l) => (
              <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                <span className="label">{l.label}</span>
              </NavLink>
            ))}
          </nav>
        </>
      ) : null}
    </aside>
  )
}
