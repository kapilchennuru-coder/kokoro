import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { EmptyState, ErrorState, LoadingState, Pagination, StatusBadge } from '../../components/ui'
import { friendlyError } from '../../lib/labels'
import type { LoginHistoryEntry } from '../../types'

export function LoginHistoryPage() {
  const [items, setItems] = useState<LoginHistoryEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.admin.loginHistory({ page, page_size: 25 })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load login history'))
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Login History</h1>
        <p>Every sign-in attempt, successful or not</p>
      </div>

      {loading ? (
        <LoadingState rows={8} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState title="No login activity yet" description="Sign-in attempts will show up here." />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Result</th>
                  <th>Reason</th>
                  <th>IP address</th>
                  <th>Device</th>
                  <th>Login at</th>
                  <th>Logout at</th>
                </tr>
              </thead>
              <tbody>
                {items.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.username}</td>
                    <td>
                      <StatusBadge status={entry.success ? 'successful' : 'failed'} />
                    </td>
                    <td>{entry.failure_reason || '—'}</td>
                    <td>{entry.ip_address || '—'}</td>
                    <td className="secondary" style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {entry.user_agent || '—'}
                    </td>
                    <td>{new Date(entry.login_at).toLocaleString()}</td>
                    <td>{entry.logout_at ? new Date(entry.logout_at).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={25} total={total} onChange={setPage} />
        </>
      )}
    </div>
  )
}
