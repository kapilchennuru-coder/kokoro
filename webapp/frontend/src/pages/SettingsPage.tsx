import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { ErrorState, LoadingState } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { friendlyError } from '../lib/labels'
import type { Voice } from '../types'

const DAY_LABELS: Array<[string, string]> = [
  ['1', 'Mon'],
  ['2', 'Tue'],
  ['3', 'Wed'],
  ['4', 'Thu'],
  ['5', 'Fri'],
  ['6', 'Sat'],
  ['7', 'Sun'],
]

const COMMON_TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Phoenix',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Europe/London',
  'Europe/Berlin',
  'Australia/Sydney',
  'UTC',
]

function msToMinutes(ms: string | undefined): string {
  const n = Number(ms || 0)
  return n > 0 ? String(Math.round(n / 60000)) : ''
}

function minutesToMs(minutes: string): string {
  const n = Number(minutes || 0)
  return String(Math.max(n, 0) * 60000)
}

export function SettingsPage() {
  const { user } = useAuth()
  const canManageSettings = user?.role ? ['SUPER_ADMIN', 'ADMIN', 'MANAGER'].includes(user.role) : false
  const canManageVoices = canManageSettings

  const { push } = useToast()
  const [voices, setVoices] = useState<Voice[]>([])
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [days, setDays] = useState<Set<string>>(new Set(['1', '2', '3', '4', '5']))

  useEffect(() => {
    ;(async () => {
      try {
        const [v, s] = await Promise.all([api.voices(), api.settings()])
        setVoices(v.voices)
        setSettings(s.settings)
        setDays(new Set((s.settings.calling_days || '1,2,3,4,5').split(',').filter(Boolean)))
      } catch (e) {
        setError(friendlyError(e instanceof Error ? e.message : 'Unable to load settings'))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const previewVoice = async () => {
    setPreviewBusy(true)
    try {
      const blob = await api.previewVoice(settings.voice_id || 'af_jessica', Number(settings.voice_speed || 1))
      const url = URL.createObjectURL(blob)
      if (audioRef.current) {
        audioRef.current.src = url
        await audioRef.current.play()
      }
    } catch (e) {
      push(friendlyError(e instanceof Error ? e.message : 'Unable to generate a voice preview'), 'error')
    } finally {
      setPreviewBusy(false)
    }
  }

  const toggleDay = (day: string) => {
    setDays((prev) => {
      const next = new Set(prev)
      if (next.has(day)) next.delete(day)
      else next.add(day)
      return next
    })
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const res = await api.saveSettings({
        voice_id: settings.voice_id,
        opening_message: settings.opening_message,
        delay_ms: settings.delay_ms,
        retry_max_attempts: settings.retry_max_attempts ?? '2',
        retry_delay_no_answer_ms: settings.retry_delay_no_answer_ms ?? String(30 * 60 * 1000),
        retry_delay_busy_ms: settings.retry_delay_busy_ms ?? String(15 * 60 * 1000),
        calling_hours_enabled: settings.calling_hours_enabled ?? 'false',
        calling_hours_start: settings.calling_hours_start ?? '09:00',
        calling_hours_end: settings.calling_hours_end ?? '18:00',
        calling_days: Array.from(days).sort().join(','),
        timezone: settings.timezone ?? 'America/New_York',
      })
      setSettings(res.settings)
      push('Settings saved', 'success')
    } catch (err) {
      push(friendlyError(err instanceof Error ? err.message : 'Unable to save'), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} />

  return (
    <div className="page">
      <div className="page-header">
        <h1>Settings</h1>
        <p>Message, voice, and calling preferences</p>
      </div>

      <form className="card setup-form" style={{ maxWidth: 560 }} onSubmit={onSubmit}>
        <label className="field">
          <span className="label">Greeting / message</span>
          <textarea
            className="textarea"
            disabled={!canManageSettings}
            value={settings.opening_message || ''}
            onChange={(e) => setSettings({ ...settings, opening_message: e.target.value })}
          />
          <span className="muted" style={{ fontSize: '0.75rem', marginTop: 4 }}>
            You can use {'{name}'}, {'{balance_display}'}, and {'{hospital}'}.
          </span>
        </label>

        <label className="field">
          <span className="label">Voice</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <select
              className="select"
              disabled={!canManageSettings}
              value={settings.voice_id || 'af_jessica'}
              onChange={(e) => setSettings({ ...settings, voice_id: e.target.value })}
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
            {canManageVoices ? (
              <button type="button" className="btn btn-ghost" disabled={previewBusy} onClick={() => void previewVoice()}>
                {previewBusy ? 'Generating…' : 'Test voice'}
              </button>
            ) : null}
          </div>
          <audio ref={audioRef} style={{ marginTop: 8, width: '100%' }} controls />
        </label>

        <label className="field">
          <span className="label">Delay between calls (ms)</span>
          <input
            className="input"
            type="number"
            min={0}
            disabled={!canManageSettings}
            value={settings.delay_ms || '2000'}
            onChange={(e) => setSettings({ ...settings, delay_ms: e.target.value })}
          />
        </label>

        <button type="submit" className="btn btn-primary" disabled={busy || !canManageSettings} style={{ width: 160 }}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>

      <div className="page-header" style={{ marginTop: 32 }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem' }}>Calling rules</h2>
        <p>Retry behavior and allowed calling hours</p>
      </div>

      <form className="card setup-form" style={{ maxWidth: 560 }} onSubmit={onSubmit}>
        <label className="field">
          <span className="label">Max retry attempts</span>
          <input
            className="input"
            type="number"
            min={0}
            max={5}
            disabled={!canManageSettings}
            value={settings.retry_max_attempts ?? '2'}
            onChange={(e) => setSettings({ ...settings, retry_max_attempts: e.target.value })}
          />
          <span className="muted" style={{ fontSize: '0.75rem', marginTop: 4 }}>
            No-answer and busy outcomes get retried up to this many times. Invalid numbers are never retried.
          </span>
        </label>

        <label className="field">
          <span className="label">Retry delay — no answer (minutes)</span>
          <input
            className="input"
            type="number"
            min={1}
            disabled={!canManageSettings}
            value={msToMinutes(settings.retry_delay_no_answer_ms) || '30'}
            onChange={(e) => setSettings({ ...settings, retry_delay_no_answer_ms: minutesToMs(e.target.value) })}
          />
        </label>

        <label className="field">
          <span className="label">Retry delay — busy (minutes)</span>
          <input
            className="input"
            type="number"
            min={1}
            disabled={!canManageSettings}
            value={msToMinutes(settings.retry_delay_busy_ms) || '15'}
            onChange={(e) => setSettings({ ...settings, retry_delay_busy_ms: minutesToMs(e.target.value) })}
          />
        </label>

        <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            disabled={!canManageSettings}
            checked={settings.calling_hours_enabled === 'true'}
            onChange={(e) => setSettings({ ...settings, calling_hours_enabled: e.target.checked ? 'true' : 'false' })}
          />
          <span className="label" style={{ margin: 0 }}>Restrict calling to specific hours</span>
        </label>

        <div style={{ display: 'flex', gap: 12 }}>
          <label className="field" style={{ flex: 1 }}>
            <span className="label">Start time</span>
            <input
              className="input"
              type="time"
              disabled={!canManageSettings}
              value={settings.calling_hours_start || '09:00'}
              onChange={(e) => setSettings({ ...settings, calling_hours_start: e.target.value })}
            />
          </label>
          <label className="field" style={{ flex: 1 }}>
            <span className="label">End time</span>
            <input
              className="input"
              type="time"
              disabled={!canManageSettings}
              value={settings.calling_hours_end || '18:00'}
              onChange={(e) => setSettings({ ...settings, calling_hours_end: e.target.value })}
            />
          </label>
        </div>

        <label className="field">
          <span className="label">Days</span>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {DAY_LABELS.map(([value, label]) => (
              <button
                key={value}
                type="button"
                disabled={!canManageSettings}
                className={`btn btn-sm ${days.has(value) ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => toggleDay(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </label>

        <label className="field">
          <span className="label">Timezone</span>
          <select
            className="select"
            disabled={!canManageSettings}
            value={settings.timezone || 'America/New_York'}
            onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
          >
            {COMMON_TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" className="btn btn-primary" disabled={busy || !canManageSettings} style={{ width: 160 }}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}
