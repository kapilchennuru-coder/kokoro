import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { ErrorState, LoadingState } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { friendlyError } from '../lib/labels'
import type { Voice } from '../types'

export function SettingsPage() {
  const { push } = useToast()
  const [voices, setVoices] = useState<Voice[]>([])
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const [v, s] = await Promise.all([api.voices(), api.settings()])
        setVoices(v.voices)
        setSettings(s.settings)
      } catch (e) {
        setError(friendlyError(e instanceof Error ? e.message : 'Unable to load settings'))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const res = await api.saveSettings({
        voice_id: settings.voice_id,
        opening_message: settings.opening_message,
        delay_ms: settings.delay_ms,
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
            value={settings.opening_message || ''}
            onChange={(e) => setSettings({ ...settings, opening_message: e.target.value })}
          />
          <span className="muted" style={{ fontSize: '0.75rem', marginTop: 4 }}>
            You can use {'{name}'}, {'{balance_display}'}, and {'{hospital}'}.
          </span>
        </label>

        <label className="field">
          <span className="label">Voice</span>
          <select
            className="select"
            value={settings.voice_id || 'af_jessica'}
            onChange={(e) => setSettings({ ...settings, voice_id: e.target.value })}
          >
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="label">Delay between calls (ms)</span>
          <input
            className="input"
            type="number"
            min={0}
            value={settings.delay_ms || '2000'}
            onChange={(e) => setSettings({ ...settings, delay_ms: e.target.value })}
          />
        </label>

        <button type="submit" className="btn btn-primary" disabled={busy} style={{ width: 160 }}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}
