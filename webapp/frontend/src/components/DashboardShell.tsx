import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import './shell.css'

export function DashboardShell() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-col">
        <TopBar />
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
