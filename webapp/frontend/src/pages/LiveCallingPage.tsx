import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ErrorState, LoadingState, StatusBadge } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { friendlyError, statusLabel } from '../lib/labels'
import type { Campaign } from '../types'

function activityLabel(state: string | undefined): string {
  switch (state) {
    case 'connecting':
      return 'Connecting'
    case 'speaking':
    case 'listening':
    case 'thinking':
      return 'In progress'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Unable to complete'
    case 'paused':
      return 'Paused'
    case 'waiting_for_hours':
      return 'Waiting for calling hours'
    case 'waiting_retry':
      return 'Waiting to retry'
    default:
      return statusLabel(state || 'Processing')
  }
}

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = Math.floor(totalSeconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const IN_PROGRESS_STATES = new Set(['connecting', 'speaking', 'listening', 'thinking'])

export function LiveCallingPage() {
  const { id } = useParams()
  const campaignId = Number(id)
  const { push } = useToast()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [mode, setMode] = useState<string | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [confirmStop, setConfirmStop] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!campaignId) return
    let alive = true
    const poll = async () => {
      try {
        const res = await api.liveCampaign(campaignId)
        if (!alive) return
        setCampaign(res.campaign)
        setMode(res.telephony?.mode)
        setError(null)
      } catch (e) {
        if (alive) setError(friendlyError(e instanceof Error ? e.message : 'Unable to load progress'))
      } finally {
        if (alive) setLoading(false)
      }
    }
    void poll()
    const iv = window.setInterval(poll, 1500)
    return () => {
      alive = false
      window.clearInterval(iv)
    }
  }, [campaignId])

  // Live elapsed timer for the call currently in progress - ticks locally
  // between polls, always replaced by the real backend/Twilio duration the
  // moment the call actually ends (never a substitute for it).
  useEffect(() => {
    const startedAt = campaign?.current_call?.started_at
    const inProgress = IN_PROGRESS_STATES.has(campaign?.agent_state || '')
    if (!startedAt || !inProgress) {
      setElapsed(0)
      return
    }
    const startMs = new Date(startedAt).getTime()
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
    tick()
    const iv = window.setInterval(tick, 1000)
    return () => window.clearInterval(iv)
  }, [campaign?.current_call?.started_at, campaign?.agent_state])

  const act = async (action: 'pause' | 'resume' | 'stop') => {
    if (!campaign) return
    setBusy(true)
    try {
      const fn = { pause: api.pauseCampaign, resume: api.resumeCampaign, stop: api.stopCampaign }[action]
      const res = await fn(campaign.id)
      setCampaign(res.campaign)
      push(action === 'pause' ? 'Paused' : action === 'resume' ? 'Resumed' : 'Stopped', 'info')
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to update'), 'error')
    } finally {
      setBusy(false)
      setConfirmStop(false)
    }
  }

  if (loading) return <LoadingState rows={8} />
  if (error || !campaign) return <ErrorState message={error || 'Not found'} />

  const contact = campaign.current_contact
  const call = campaign.current_call
  const total = campaign.total_contacts || 0
  const queued = Math.max(total - (campaign.completed_calls || 0) - (campaign.in_progress_calls || 0), 0)
  const calling = campaign.in_progress_calls || 0
  const answered = campaign.successful_calls || 0
  const noAnswer = campaign.no_answer_calls || 0
  const busyCount = campaign.busy_calls || 0
  const failed = campaign.failed_calls || 0
  const simulated = campaign.simulated_calls || 0
  const completed = campaign.completed_calls || 0
  const publicError = campaign.error_message ? friendlyError(campaign.error_message) : null

  const liveState = call?.status && !call.ended_at ? call.status : campaign.agent_state
  const callStatusLabel = calling > 0 || IN_PROGRESS_STATES.has(campaign.agent_state) ? activityLabel(liveState) : null

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Calling progress</h1>
          <p>Notifying patients about pending balances</p>
        </div>
        <div className="spacer" />
        {mode ? (
          <span className={`badge ${mode === 'live' ? 'badge-danger' : 'badge-info'}`} style={{ textTransform: 'uppercase' }}>
            {mode === 'live' ? 'Live mode — real calls' : 'Test mode — simulated'}
          </span>
        ) : null}
        <Link to="/calls" className="btn btn-ghost btn-sm">
          Call history
        </Link>
      </div>

      {publicError ? (
        <div className="card" style={{ padding: 16, borderColor: '#fecaca', background: '#fef2f2' }}>
          <strong>Unable to complete</strong>
          <div className="secondary" style={{ fontSize: '0.85rem', marginTop: 4 }}>
            {publicError}
          </div>
        </div>
      ) : null}

      <section className="card live-hero" style={{ maxWidth: 820 }}>
        <div className="live-header">
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', letterSpacing: '0.06em', fontWeight: 700 }}>
              CAMPAIGN
            </div>
            <h2 style={{ margin: '4px 0 0', fontFamily: 'var(--font-display)', fontSize: '1.35rem' }}>{campaign.name}</h2>
          </div>
          <StatusBadge status={campaign.status} />
        </div>

        <div>
          <div className="secondary" style={{ fontSize: '0.9rem', marginBottom: 8 }}>
            Progress · {completed} / {total} ({campaign.progress ?? 0}%)
          </div>
          <div className="progress-bar" style={{ height: 10 }}>
            <span style={{ width: `${campaign.progress || 0}%` }} />
          </div>
        </div>

        <div className="counters" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
          <div className="counter">
            <strong>{queued}</strong>
            <span>Queued</span>
          </div>
          <div className="counter">
            <strong>{calling}</strong>
            <span>Calling</span>
          </div>
          <div className="counter">
            <strong>{answered}</strong>
            <span>Answered</span>
          </div>
          <div className="counter">
            <strong>{noAnswer}</strong>
            <span>No Answer</span>
          </div>
          <div className="counter">
            <strong>{busyCount}</strong>
            <span>Busy</span>
          </div>
          <div className="counter">
            <strong>{failed}</strong>
            <span>Failed</span>
          </div>
          <div className="counter">
            <strong>{completed}</strong>
            <span>Completed</span>
          </div>
          {simulated > 0 ? (
            <div className="counter">
              <strong>{simulated}</strong>
              <span>Simulated</span>
            </div>
          ) : null}
        </div>

        <div className="contact-spotlight">
          <div className="muted" style={{ fontSize: '0.75rem', fontWeight: 650 }}>
            CURRENT CALL
          </div>
          {contact ? (
            <>
              <h3>{contact.name}</h3>
              <div className="meta-row">
                <span>{contact.phone}</span>
                <span>{contact.balance_display || '—'}</span>
                <span>{contact.hospital || '—'}</span>
                {call?.attempt_number ? <span>Attempt {call.attempt_number}</span> : null}
              </div>
              <div className="agent-state" style={{ marginTop: 8 }}>
                {callStatusLabel ? (
                  <>
                    <StatusBadge status={liveState || campaign.agent_state} /> {callStatusLabel}
                    {elapsed > 0 ? <span className="muted"> · {formatDuration(elapsed)} elapsed</span> : null}
                  </>
                ) : (
                  <span className="muted">{activityLabel(campaign.agent_state)}</span>
                )}
              </div>
            </>
          ) : (
            <>
              <h3 style={{ color: 'var(--text-muted)' }}>—</h3>
              {campaign.status === 'running' ? (
                <div className="agent-state" style={{ marginTop: 8 }}>
                  <span className="muted">{activityLabel(campaign.agent_state)}</span>
                </div>
              ) : null}
            </>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {campaign.status === 'running' ? (
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void act('pause')}>
              Pause Campaign
            </button>
          ) : null}
          {campaign.status === 'paused' ? (
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void act('resume')}>
              Resume Campaign
            </button>
          ) : null}
          {(campaign.status === 'running' || campaign.status === 'paused') && (
            <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirmStop(true)}>
              Stop Campaign
            </button>
          )}
        </div>
      </section>

      <ConfirmDialog
        open={confirmStop}
        title="Stop this campaign?"
        message="Remaining patients will not be called. This can't be resumed once stopped."
        confirmLabel="Stop Campaign"
        busyLabel="Stopping…"
        busy={busy}
        onCancel={() => setConfirmStop(false)}
        onConfirm={() => void act('stop')}
      />
    </div>
  )
}
