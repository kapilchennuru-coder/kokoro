import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Drawer, EmptyState, ErrorState, LoadingState, Pagination, StatusBadge } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { friendlyError } from '../lib/labels'
import type { Patient } from '../types'

function statusDisplay(status?: string) {
  if (!status || status === 'not_called') return 'ready'
  if (status === 'in_progress') return 'calling'
  return status
}

export function PatientsPage() {
  const { push } = useToast()
  const [items, setItems] = useState<Patient[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Patient | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Patient | null>(null)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '', balance: '', hospital: '' })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.contacts({ page, page_size: 20, search })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load patients'))
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => {
    void load()
  }, [load])

  const openEdit = (p: Patient) => {
    setEditing(p)
    setForm({
      name: p.name || '',
      phone: p.phone || '',
      balance: p.balance != null ? String(p.balance) : '',
      hospital: p.hospital || '',
    })
  }

  const saveEdit = async () => {
    if (!editing?.id) return
    setBusy(true)
    try {
      await api.updateContact(editing.id, {
        name: form.name,
        phone: form.phone,
        balance: form.balance,
        hospital: form.hospital,
      })
      push('Patient updated', 'success')
      setEditing(null)
      await load()
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to update'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget?.id) return
    setBusy(true)
    try {
      await api.deleteContact(deleteTarget.id)
      push('Patient removed', 'success')
      setDeleteTarget(null)
      await load()
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to delete'), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Patients</h1>
          <p>People with pending balances</p>
        </div>
        <div className="spacer" />
        <Link to="/" className="btn btn-primary">
          Import Patients
        </Link>
      </div>

      <div className="toolbar">
        <input
          className="input"
          style={{ maxWidth: 280 }}
          placeholder="Search patients…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
      </div>

      {loading ? (
        <LoadingState rows={8} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No patients yet"
          description="Import an Excel file from the dashboard to add patients."
          action={
            <Link to="/" className="btn btn-primary">
              Import Patients
            </Link>
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Balance</th>
                  <th>Hospital</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td>{p.phone || '—'}</td>
                    <td>{p.balance_display || '—'}</td>
                    <td>{p.hospital || '—'}</td>
                    <td>
                      <StatusBadge status={statusDisplay(p.calling_status)} />
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => openEdit(p)}>
                          Edit
                        </button>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDeleteTarget(p)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={20} total={total} onChange={setPage} />
        </>
      )}

      <Drawer open={!!editing} title="Edit patient" onClose={() => setEditing(null)}>
        {editing ? (
          <div style={{ display: 'grid', gap: 12 }}>
            <label className="field">
              <span className="label">Name</span>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="field">
              <span className="label">Phone</span>
              <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </label>
            <label className="field">
              <span className="label">Balance</span>
              <input
                className="input"
                type="number"
                step="0.01"
                value={form.balance}
                onChange={(e) => setForm({ ...form, balance: e.target.value })}
              />
            </label>
            <label className="field">
              <span className="label">Hospital</span>
              <input
                className="input"
                value={form.hospital}
                onChange={(e) => setForm({ ...form, hospital: e.target.value })}
              />
            </label>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void saveEdit()}>
              Save
            </button>
          </div>
        ) : null}
      </Drawer>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete patient?"
        message="This patient will be removed from the list."
        confirmLabel="Delete"
        busy={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  )
}
