import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Drawer, EmptyState, ErrorState, LoadingState, Pagination, StatusBadge } from '../components/ui'
import { friendlyError } from '../lib/labels'
import type { Call, Campaign } from '../types'

export function CallsPage() {
  const [items, setItems] = useState<Call[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Call | null>(null)
  const [active, setActive] = useState<Campaign | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [calls, dash] = await Promise.all([
        api.calls({ page, page_size: 20 }),
        api.dashboard() as Promise<{ active_campaign?: Campaign | null }>,
      ])
      setItems(calls.items)
      setTotal(calls.total)
      setActive(dash.active_campaign || null)
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load calls'))
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Calls</h1>
          <p>Balance notification call history</p>
        </div>
        <div className="spacer" />
        {active ? (
          <Link to={`/calls/live/${active.id}`} className="btn btn-primary">
            View progress
          </Link>
        ) : null}
      </div>

      {loading ? (
        <LoadingState rows={8} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState title="No calls yet" description="Call results will appear here after you start calling." />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Phone</th>
                  <th>Balance</th>
                  <th>Hospital</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => setSelected(c)}>
                    <td>{c.contact_name || '—'}</td>
                    <td>{c.contact_phone || '—'}</td>
                    <td>{(c as Call & { balance_display?: string }).balance_display || '—'}</td>
                    <td>{c.hospital || c.contact_company || '—'}</td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="secondary">{new Date(c.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={20} total={total} onChange={setPage} />
        </>
      )}

      <Drawer open={!!selected} title="Call details" onClose={() => setSelected(null)}>
        {selected ? (
          <div className="detail-block">
            <h4>Patient</h4>
            <p>{selected.contact_name}</p>
            <h4>Phone</h4>
            <p>{selected.contact_phone || '—'}</p>
            <h4>Balance</h4>
            <p>{(selected as Call & { balance_display?: string }).balance_display || '—'}</p>
            <h4>Hospital</h4>
            <p>{selected.hospital || selected.contact_company || '—'}</p>
            <h4>Status</h4>
            <p>
              <StatusBadge status={selected.status} />
            </p>
            <h4>Date</h4>
            <p>{selected.started_at ? new Date(selected.started_at).toLocaleString() : '—'}</p>
            <h4>Message</h4>
            <p>{selected.script_text || '—'}</p>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}
