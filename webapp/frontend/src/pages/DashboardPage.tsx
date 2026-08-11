import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { ColumnMapper } from '../components/ColumnMapper'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FileUpload } from '../components/FileUpload'
import { EmptyState, ErrorState, LoadingState, MetricCard, StatusBadge } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { friendlyError } from '../lib/labels'
import type { Call, Mapping, Patient, Voice } from '../types'

type Step = 'idle' | 'mapping' | 'preview' | 'success'

type PreviewState = {
  patients: Patient[]
  row_count: number
  valid_count: number
  invalid_count: number
  duplicate_count: number
  attention_count: number
  filename: string
}

export function DashboardPage() {
  const { push } = useToast()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [kpis, setKpis] = useState({
    total_contacts: 0,
    contacts_ready: 0,
    calls_completed: 0,
    remaining: 0,
  })
  const [recentCalls, setRecentCalls] = useState<Call[]>([])

  const [step, setStep] = useState<Step>('idle')
  const [columns, setColumns] = useState<string[]>([])
  const [mapping, setMapping] = useState<Mapping>({})
  const [filename, setFilename] = useState('')
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [imported, setImported] = useState<{ imported_count: number } | null>(null)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [addForm, setAddForm] = useState({ name: '', phone: '', balance: '', hospital: '' })
  const [startConfirmOpen, setStartConfirmOpen] = useState(false)
  const [startSummary, setStartSummary] = useState<{
    voiceLabel: string
    callingWindow: string
    retries: string
    mode: string
    outsideWindowWarning: string | null
  } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const dash = (await api.dashboard()) as {
        kpis: typeof kpis
        recent_calls?: Call[]
      }
      setKpis(dash.kpis)
      setRecentCalls(dash.recent_calls || [])
    } catch (e) {
      setError(friendlyError(e instanceof Error ? e.message : 'Unable to load dashboard'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const addField = (key: keyof typeof addForm, value: string) => {
    setAddForm((f) => ({ ...f, [key]: value }))
  }

  const submitAddPatient = async (e: FormEvent) => {
    e.preventDefault()
    setAddBusy(true)
    try {
      await api.createContact(addForm)
      push('Patient added', 'success')
      setAddForm({ name: '', phone: '', balance: '', hospital: '' })
      setAddOpen(false)
      await load()
    } catch (err) {
      push(friendlyError(err instanceof Error ? err.message : 'Unable to add patient'), 'error')
    } finally {
      setAddBusy(false)
    }
  }

  const resetWizard = () => {
    setStep('idle')
    setColumns([])
    setMapping({})
    setFilename('')
    setPreview(null)
    setPage(1)
    setSearch('')
    setConfirmOpen(false)
    setUploadStatus(null)
  }

  const applyPreview = (filenameValue: string, patients: Patient[], summary: Partial<PreviewState>) => {
    setPreview({
      patients,
      filename: filenameValue,
      row_count: summary.row_count ?? patients.length,
      valid_count: summary.valid_count ?? patients.filter((p) => p.validation_status === 'valid').length,
      invalid_count: summary.invalid_count ?? 0,
      duplicate_count: summary.duplicate_count ?? 0,
      attention_count:
        summary.attention_count ??
        patients.filter((p) => p.validation_status !== 'valid').length,
    })
    setStep('preview')
    setPage(1)
  }

  const onFile = async (file: File) => {
    setImported(null)
    setUploadStatus('Preparing your patient list...')
    try {
      const res = await api.uploadExcel(file)
      if (res.persisted) {
        throw new Error('Unexpected import state. Please try again.')
      }
      setColumns(res.columns)
      setMapping(res.detected_mapping)
      setFilename(res.filename)

      const patients = res.patients || res.contacts || []
      if (!res.requires_mapping && patients.length > 0) {
        applyPreview(res.filename, patients, res)
        return
      }

      if (res.requires_mapping) {
        setStep('mapping')
        return
      }

      // Fallback: request preview explicitly when mapping is confident but rows omitted
      const previewRes = await api.previewMapping(res.detected_mapping)
      const rows = previewRes.patients || previewRes.contacts || []
      if (rows.length === 0) {
        throw new Error('No patients were found in this file.')
      }
      applyPreview(previewRes.filename, rows, previewRes)
    } finally {
      setUploadStatus(null)
    }
  }

  const goToPreview = async () => {
    if (!mapping.name || !mapping.phone || !mapping.balance || !mapping.hospital) {
      push('Please match Name, Phone, Balance, and Hospital', 'error')
      return
    }
    setBusy(true)
    try {
      const previewRes = await api.previewMapping(mapping)
      const rows = previewRes.patients || previewRes.contacts || []
      applyPreview(previewRes.filename, rows, previewRes)
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to prepare preview'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const onCancel = async () => {
    setBusy(true)
    try {
      await api.cancelImport()
    } catch {
      /* ignore */
    } finally {
      resetWizard()
      setBusy(false)
    }
  }

  const runImport = async () => {
    if (!preview || preview.valid_count < 1) return
    setBusy(true)
    try {
      const res = await api.confirmImport(mapping, filename.replace(/\.[^.]+$/, ''))
      setImported({ imported_count: res.imported_count ?? res.valid_count })
      setConfirmOpen(false)
      resetWizard()
      setStep('success')
      push('Patients imported successfully', 'success')
      await load()
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to import'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const openStartConfirm = async () => {
    setBusy(true)
    try {
      const [settingsRes, voicesRes] = await Promise.all([api.settings(), api.voices()])
      const s = settingsRes.settings
      const voice = (voicesRes.voices as Voice[]).find((v) => v.id === s.voice_id)
      const callingWindow =
        s.calling_hours_enabled === 'true'
          ? `${s.calling_hours_start || '09:00'} – ${s.calling_hours_end || '18:00'} (${s.timezone || 'local time'})`
          : 'No restriction'

      let outsideWindowWarning: string | null = null
      if (s.calling_hours_enabled === 'true' && s.timezone) {
        try {
          const fmt = new Intl.DateTimeFormat('en-US', {
            timeZone: s.timezone,
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            weekday: 'short',
          })
          const parts = Object.fromEntries(fmt.formatToParts(new Date()).map((p) => [p.type, p.value]))
          const nowMinutes = Number(parts.hour) * 60 + Number(parts.minute)
          const dayMap: Record<string, string> = { Mon: '1', Tue: '2', Wed: '3', Thu: '4', Fri: '5', Sat: '6', Sun: '7' }
          const todayCode = dayMap[parts.weekday || ''] || ''
          const days = (s.calling_days || '1,2,3,4,5').split(',')
          const [startH, startM] = (s.calling_hours_start || '09:00').split(':').map(Number)
          const [endH, endM] = (s.calling_hours_end || '18:00').split(':').map(Number)
          const withinWindow =
            days.includes(todayCode) && nowMinutes >= startH * 60 + startM && nowMinutes < endH * 60 + endM
          if (!withinWindow) {
            outsideWindowWarning = `It's currently outside the calling window (${parts.weekday} ${parts.hour}:${parts.minute} in ${s.timezone}) — the campaign will start but wait until the window opens before dialing anyone.`
          }
        } catch {
          /* unknown/invalid timezone string - skip the proactive check, backend still enforces it */
        }
      }

      setStartSummary({
        voiceLabel: voice?.label || s.voice_id || 'Default voice',
        callingWindow,
        retries: `${s.retry_max_attempts ?? '2'} max attempts`,
        mode: s.twilio_mode === 'live' ? 'LIVE — real calls will be placed' : 'TEST — simulated, no real calls',
        outsideWindowWarning,
      })
      setStartConfirmOpen(true)
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to load calling settings'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const startCalling = async () => {
    setBusy(true)
    try {
      const res = await api.startCalling()
      push('Calling started', 'success')
      setStartConfirmOpen(false)
      navigate(`/calls/live/${res.campaign.id}`)
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to start calling'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const filtered = useMemo(() => {
    const items = preview?.patients || []
    if (!search.trim()) return items
    const q = search.toLowerCase()
    return items.filter(
      (c) =>
        c.name?.toLowerCase().includes(q) ||
        c.phone?.includes(q) ||
        c.hospital?.toLowerCase().includes(q) ||
        String(c.balance_display || '').includes(q),
    )
  }, [preview, search])

  const pageSize = 25
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize)
  const rangeStart = filtered.length === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, filtered.length)

  if (error && step === 'idle') {
    return <ErrorState message={error} onRetry={() => void load()} />
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Patient Outreach</h1>
        <p>Manage pending balance notifications.</p>
      </div>

      <div className="grid-kpi">
        <MetricCard label="Patients" value={kpis.total_contacts} loading={loading} />
        <MetricCard label="Ready" value={kpis.contacts_ready} loading={loading} />
        <MetricCard label="Completed" value={kpis.calls_completed} loading={loading} />
        <MetricCard label="Remaining" value={kpis.remaining} loading={loading} />
      </div>

      {step === 'success' && imported ? (
        <section className="card" style={{ padding: 28, textAlign: 'center' }}>
          <h2 style={{ margin: '0 0 8px', fontFamily: 'var(--font-display)' }}>Patients imported successfully</h2>
          <p className="secondary" style={{ margin: '0 0 20px' }}>
            {imported.imported_count} patients are ready.
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link to="/patients" className="btn btn-ghost">
              View Patients
            </Link>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || kpis.contacts_ready < 1}
              onClick={() => void openStartConfirm()}
            >
              Start Calling
            </button>
          </div>
          <div style={{ marginTop: 16 }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setStep('idle')}>
              Import more patients
            </button>
          </div>
        </section>
      ) : null}

      {step === 'idle' ? (
        <section className="card" style={{ padding: 22 }}>
          <div className="toolbar" style={{ marginBottom: 16, alignItems: 'flex-start' }}>
            <div>
              <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '1.15rem' }}>Import Patients</h2>
              <p className="secondary" style={{ margin: '6px 0 0', fontSize: '0.875rem' }}>
                Upload an Excel file with Name, Phone Number, Balance, and Hospital.
              </p>
            </div>
            <div className="spacer" />
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy || kpis.contacts_ready < 1}
              onClick={() => void startCalling()}
              title={kpis.contacts_ready < 1 ? 'Import patients who are ready to call first' : undefined}
            >
              Start Calling
            </button>
          </div>
          <FileUpload onFile={onFile} disabled={busy} statusMessage={uploadStatus} />

          <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
            {!addOpen ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAddOpen(true)}>
                + Add one patient manually
              </button>
            ) : (
              <form onSubmit={(e) => void submitAddPatient(e)}>
                <div className="toolbar" style={{ marginBottom: 12 }}>
                  <strong style={{ fontSize: '0.9rem' }}>Add a single patient</strong>
                  <div className="spacer" />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setAddOpen(false)
                      setAddForm({ name: '', phone: '', balance: '', hospital: '' })
                    }}
                  >
                    Cancel
                  </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                  <label className="field">
                    <span className="label">Name</span>
                    <input
                      className="input"
                      value={addForm.name}
                      onChange={(e) => addField('name', e.target.value)}
                      placeholder="Patient name"
                      required
                    />
                  </label>
                  <label className="field">
                    <span className="label">Phone Number</span>
                    <input
                      className="input"
                      value={addForm.phone}
                      onChange={(e) => addField('phone', e.target.value)}
                      placeholder="+1 555 123 4567"
                      required
                    />
                  </label>
                  <label className="field">
                    <span className="label">Balance</span>
                    <input
                      className="input"
                      value={addForm.balance}
                      onChange={(e) => addField('balance', e.target.value)}
                      placeholder="250.00"
                      inputMode="decimal"
                      required
                    />
                  </label>
                  <label className="field">
                    <span className="label">Hospital</span>
                    <input
                      className="input"
                      value={addForm.hospital}
                      onChange={(e) => addField('hospital', e.target.value)}
                      placeholder="Hospital / facility name"
                      required
                    />
                  </label>
                </div>
                <button type="submit" className="btn btn-primary btn-sm" disabled={addBusy} style={{ marginTop: 14 }}>
                  {addBusy ? 'Adding…' : 'Add Patient'}
                </button>
              </form>
            )}
          </div>
        </section>
      ) : null}

      {step === 'mapping' ? (
        <div className="preview-panel">
          <div className="card" style={{ padding: '14px 20px' }}>
            <div className="toolbar">
              <div>
                <strong>{filename}</strong>
                <div className="secondary" style={{ fontSize: '0.85rem' }}>
                  Match the columns in your file, then continue to preview.
                </div>
              </div>
              <div className="spacer" />
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void onCancel()}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void goToPreview()}>
                Continue
              </button>
            </div>
          </div>
          <ColumnMapper columns={columns} mapping={mapping} onChange={setMapping} />
        </div>
      ) : null}

      {step === 'preview' && preview ? (
        <section className="card" style={{ padding: 20 }}>
          <div className="toolbar" style={{ marginBottom: 8, alignItems: 'flex-start' }}>
            <div>
              <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '1.2rem' }}>Review Patients</h2>
              <p className="secondary" style={{ margin: '6px 0 0', fontSize: '0.875rem' }}>
                Check the patient information before importing.
              </p>
              <p style={{ margin: '10px 0 0', fontSize: '0.9rem' }}>
                <strong>{preview.filename}</strong>
              </p>
              <div className="summary-pills" style={{ marginTop: 10 }}>
                <span className="badge">{preview.row_count} patients found</span>
                <span className="badge badge-success">{preview.valid_count} ready</span>
                <span className="badge badge-danger">{preview.attention_count} need attention</span>
              </div>
            </div>
            <div className="spacer" />
            <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => setStep('mapping')}>
              Match fields
            </button>
          </div>

          <div className="toolbar" style={{ margin: '16px 0 12px' }}>
            <input
              className="input"
              style={{ maxWidth: 280 }}
              placeholder="Search…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
          </div>

          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Balance</th>
                  <th>Hospital</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((c, i) => (
                  <tr key={`${c.row_index || i}-${c.phone}`} className={c.validation_status !== 'valid' ? 'selected' : undefined}>
                    <td>{c.name || '—'}</td>
                    <td>{c.phone || '—'}</td>
                    <td>{c.balance_display || '—'}</td>
                    <td>{c.hospital || '—'}</td>
                    <td>
                      <StatusBadge status={c.validation_status || 'invalid'} />
                      {c.validation_errors?.length ? (
                        <div className="muted" style={{ fontSize: '0.75rem', marginTop: 4 }}>
                          {c.validation_errors.join(' · ')}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {pageItems.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="secondary">
                      No patients to show.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span className="secondary">
              Showing {rangeStart}–{rangeEnd} of {filtered.length} patients
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={page * pageSize >= filtered.length}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </div>

          <div className="toolbar" style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void onCancel()}>
              Cancel
            </button>
            <div className="spacer" />
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || preview.valid_count < 1}
              onClick={() => setConfirmOpen(true)}
            >
              Import {preview.valid_count} Patients
            </button>
          </div>
        </section>
      ) : null}

      {step === 'idle' ? (
        <section>
          <h2 style={{ margin: '0 0 12px', fontFamily: 'var(--font-display)', fontSize: '1.1rem' }}>Recent Calls</h2>
          {loading ? (
            <LoadingState />
          ) : recentCalls.length === 0 ? (
            <EmptyState title="No calls yet" description="Imported patients will appear here after calling begins." />
          ) : (
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
                  {recentCalls.map((c) => (
                    <tr key={c.id}>
                      <td>{c.contact_name || '—'}</td>
                      <td>{c.contact_phone || '—'}</td>
                      <td>{c.balance_display || '—'}</td>
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
          )}
        </section>
      ) : null}

      <ConfirmDialog
        open={confirmOpen}
        title="Import patients?"
        message={`${preview?.valid_count || 0} patients will be added to your list.`}
        confirmLabel="Import Patients"
        busy={busy}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => void runImport()}
      />

      <ConfirmDialog
        open={startConfirmOpen}
        title="Start Campaign?"
        confirmLabel="Start Calling"
        busyLabel="Starting…"
        busy={busy}
        onCancel={() => setStartConfirmOpen(false)}
        onConfirm={() => void startCalling()}
        message={
          startSummary ? (
            <div style={{ display: 'grid', gap: 6 }}>
              <div>
                <strong>{kpis.contacts_ready}</strong> patient{kpis.contacts_ready === 1 ? '' : 's'} will be called
              </div>
              <div>Voice: {startSummary.voiceLabel}</div>
              <div>Calling window: {startSummary.callingWindow}</div>
              <div>Retries: {startSummary.retries}</div>
              <div
                style={{
                  marginTop: 8,
                  padding: '8px 10px',
                  borderRadius: 8,
                  fontWeight: 600,
                  background: startSummary.mode.startsWith('LIVE') ? '#fef2f2' : '#eff6ff',
                  color: startSummary.mode.startsWith('LIVE') ? 'var(--danger)' : 'var(--info, #2563eb)',
                }}
              >
                {startSummary.mode}
              </div>
              {startSummary.outsideWindowWarning ? (
                <div
                  style={{
                    marginTop: 4,
                    padding: '8px 10px',
                    borderRadius: 8,
                    fontSize: '0.85rem',
                    background: '#fffbeb',
                    color: '#92400e',
                  }}
                >
                  ⏳ {startSummary.outsideWindowWarning}
                </div>
              ) : null}
            </div>
          ) : (
            ''
          )
        }
      />
    </div>
  )
}
