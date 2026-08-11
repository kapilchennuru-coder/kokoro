import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { EmptyState, ErrorState, LoadingState, Pagination } from '../../components/ui'
import { friendlyError } from '../../lib/labels'
import type { AuditLogEntry } from '../../types'

export function AuditLogsPage() {
  const [items, setItems] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.admin.auditLogs({ page, page_size: 25, action })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load audit logs'))
    } finally {
      setLoading(false)
    }
  }, [page, action])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Audit Logs</h1>
          <p>Administrative and account activity</p>
        </div>
        <div className="spacer" />
        <input
          className="input"
          style={{ maxWidth: 220 }}
          placeholder="Filter by action…"
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(1)
          }}
        />
      </div>

      {loading ? (
        <LoadingState rows={8} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState title="No activity yet" description="Administrative actions will show up here." />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>IP address</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {items.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.actor_username || 'system'}</td>
                    <td>
                      <span className="badge">{entry.action}</span>
                    </td>
                    <td>
                      {entry.entity ? `${entry.entity}${entry.entity_id ? ` #${entry.entity_id}` : ''}` : '—'}
                    </td>
                    <td>{entry.ip_address || '—'}</td>
                    <td>{new Date(entry.created_at).toLocaleString()}</td>
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
