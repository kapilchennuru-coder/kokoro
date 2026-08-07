import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
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
    default:
      return statusLabel(state || 'Processing')
  }
}

export function LiveCallingPage() {
  const { id } = useParams()
  const campaignId = Number(id)
  const { push } = useToast()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!campaignId) return
    let alive = true
    const poll = async () => {
      try {
        const res = await api.liveCampaign(campaignId)
        if (!alive) return
        setCampaign(res.campaign)
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
    }
  }

  if (loading) return <LoadingState rows={8} />
  if (error || !campaign) return <ErrorState message={error || 'Not found'} />

  const contact = campaign.current_contact
  const remaining = Math.max((campaign.total_contacts || 0) - (campaign.completed_calls || 0), 0)
  const publicError = campaign.error_message ? friendlyError(campaign.error_message) : null

  return (
    <div className="page">
      <div className="toolbar">
        <div className="page-header" style={{ margin: 0 }}>
          <h1>Calling progress</h1>
          <p>Notifying patients about pending balances</p>
        </div>
        <div className="spacer" />
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

      <section className="card live-hero" style={{ maxWidth: 720 }}>
        <div className="live-header">
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', letterSpacing: '0.06em', fontWeight: 700 }}>
              CALLING
            </div>
            <h2 style={{ margin: '4px 0 0', fontFamily: 'var(--font-display)', fontSize: '1.35rem' }}>
              Balance notifications
            </h2>
          </div>
          <StatusBadge status={campaign.status} />
        </div>

        <div>
          <div className="secondary" style={{ fontSize: '0.9rem', marginBottom: 8 }}>
            Progress · {campaign.completed_calls} / {campaign.total_contacts}
          </div>
          <div className="progress-bar" style={{ height: 10 }}>
            <span style={{ width: `${campaign.progress || 0}%` }} />
          </div>
        </div>

        <div className="contact-spotlight">
          <div className="muted" style={{ fontSize: '0.75rem', fontWeight: 650 }}>
            CURRENT PATIENT
          </div>
          {contact ? (
            <>
              <h3>{contact.name}</h3>
              <div className="meta-row">
                <span>{contact.phone}</span>
                <span>{contact.balance_display || '—'}</span>
                <span>{contact.hospital || '—'}</span>
              </div>
            </>
          ) : (
            <h3 style={{ color: 'var(--text-muted)' }}>—</h3>
          )}
        </div>

        <div className="agent-state">Status · {activityLabel(campaign.agent_state)}</div>

        <div className="counters" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <div className="counter">
            <strong>{campaign.completed_calls}</strong>
            <span>Completed</span>
          </div>
          <div className="counter">
            <strong>{remaining}</strong>
            <span>Remaining</span>
          </div>
          <div className="counter">
            <strong>{campaign.failed_calls}</strong>
            <span>Failed</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {campaign.status === 'running' ? (
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void act('pause')}>
              Pause
            </button>
          ) : null}
          {campaign.status === 'paused' ? (
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void act('resume')}>
              Resume
            </button>
          ) : null}
          {(campaign.status === 'running' || campaign.status === 'paused') && (
            <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void act('stop')}>
              Stop
            </button>
          )}
        </div>
      </section>
    </div>
  )
}
