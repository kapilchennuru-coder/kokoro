import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/patients', label: 'Patients' },
  { to: '/calls', label: 'Calls' },
  { to: '/settings', label: 'Settings' },
]

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">O</div>
        <div className="brand-text">
          <strong>Outreach</strong>
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
    </aside>
  )
}
