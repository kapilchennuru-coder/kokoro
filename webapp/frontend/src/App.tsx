import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { DashboardShell } from './components/DashboardShell'
import { useAuth } from './context/AuthContext'
import { CallsPage } from './pages/CallsPage'
import { DashboardPage } from './pages/DashboardPage'
import { LiveCallingPage } from './pages/LiveCallingPage'
import { LoginPage } from './pages/LoginPage'
import { PatientsPage } from './pages/PatientsPage'
import { SettingsPage } from './pages/SettingsPage'
import { AuditLogsPage } from './pages/admin/AuditLogsPage'
import { DemoRequestsPage } from './pages/admin/DemoRequestsPage'
import { LoginHistoryPage } from './pages/admin/LoginHistoryPage'
import { UsersPage } from './pages/admin/UsersPage'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="login-page">
        <div className="skeleton" style={{ width: 280, height: 18 }} />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth()
  if (!isAdmin) return <Navigate to="/" replace />
  return children
}

function LegacyLiveRedirect() {
  const { id } = useParams()
  return <Navigate to={`/calls/live/${id}`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <Protected>
            <DashboardShell />
          </Protected>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="patients" element={<PatientsPage />} />
        <Route path="records" element={<Navigate to="/patients" replace />} />
        <Route path="contacts" element={<Navigate to="/patients" replace />} />
        <Route path="calls" element={<CallsPage />} />
        <Route path="calls/live/:id" element={<LiveCallingPage />} />
        <Route path="history" element={<Navigate to="/calls" replace />} />
        <Route path="campaigns" element={<Navigate to="/calls" replace />} />
        <Route path="campaigns/new" element={<Navigate to="/" replace />} />
        <Route path="campaigns/:id/live" element={<LegacyLiveRedirect />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="admin/users"
          element={
            <AdminOnly>
              <UsersPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/login-history"
          element={
            <AdminOnly>
              <LoginHistoryPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/audit-logs"
          element={
            <AdminOnly>
              <AuditLogsPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/demo-requests"
          element={
            <AdminOnly>
              <DemoRequestsPage />
            </AdminOnly>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
