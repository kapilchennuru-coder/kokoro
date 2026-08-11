import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { EmptyState, ErrorState, LoadingState, Pagination } from '../../components/ui'
import { useToast } from '../../context/ToastContext'
import { friendlyError } from '../../lib/labels'
import type { DemoRequest } from '../../types'

const STATUSES: DemoRequest['status'][] = ['NEW', 'CONTACTED', 'QUALIFIED', 'DEMO_SCHEDULED', 'CLOSED']

export function DemoRequestsPage() {
  const { push } = useToast()
  const [items, setItems] = useState<DemoRequest[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.admin.demoRequests({ page, page_size: 25, status })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load demo requests'))
    } finally {
      setLoading(false)
    }
  }, [page, status])

  useEffect(() => {
    void load()
  }, [load])

  const changeStatus = async (id: number, next: string) => {
    setSavingId(id)
    try {
      await api.admin.updateDemoRequest(id, { status: next })
      setItems((prev) => prev.map((r) => (r.id === id ? { ...r, status: next as DemoRequest['status'] } : r)))
      push('Status updated', 'success')
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to update status'), 'error')
    } finally {
      setSavingId(null)
    }
  }

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Demo Requests</h1>
          <p>Leads submitted from the public marketing site</p>
        </div>
        <div className="spacer" />
        <select
          className="select"
          style={{ maxWidth: 200 }}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setPage(1)
          }}
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <LoadingState rows={8} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState title="No demo requests yet" description="Leads from the public website will show up here." />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th>Country</th>
                  <th>Industry</th>
                  <th>Call volume</th>
                  <th>Status</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td>{r.first_name} {r.last_name}</td>
                    <td>{r.company_name}</td>
                    <td>{r.email}</td>
                    <td>{r.phone}</td>
                    <td>{r.country}</td>
                    <td>{r.industry}</td>
                    <td>{r.monthly_call_volume || '—'}</td>
                    <td>
                      <select
                        className="select"
                        style={{ height: 32, fontSize: '0.8rem' }}
                        value={r.status}
                        disabled={savingId === r.id}
                        onChange={(e) => void changeStatus(r.id, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{s.replace('_', ' ')}</option>
                        ))}
                      </select>
                    </td>
                    <td className="secondary">{new Date(r.created_at).toLocaleString()}</td>
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
