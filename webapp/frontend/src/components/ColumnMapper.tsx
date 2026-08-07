import type { Mapping } from '../types'

const FIELDS: Array<{ key: string; label: string; required?: boolean }> = [
  { key: 'name', label: 'Name', required: true },
  { key: 'phone', label: 'Phone Number', required: true },
  { key: 'balance', label: 'Balance', required: true },
  { key: 'hospital', label: 'Hospital', required: true },
]

type Props = {
  columns: string[]
  mapping: Mapping
  onChange: (mapping: Mapping) => void
}

export function ColumnMapper({ columns, mapping, onChange }: Props) {
  return (
    <div className="card" style={{ padding: 20 }}>
      <h3 style={{ margin: '0 0 6px', fontFamily: 'var(--font-display)' }}>Match your file fields</h3>
      <p className="secondary" style={{ margin: '0 0 16px', fontSize: '0.875rem' }}>
        Select which Excel columns match Name, Phone, Balance, and Hospital.
      </p>
      <div className="mapper-grid">
        {FIELDS.map((f) => (
          <label key={f.key} className="field">
            <span className="label">
              {f.label}
              {f.required ? ' *' : ''}
            </span>
            <select
              className="select"
              value={mapping[f.key] || ''}
              onChange={(e) => onChange({ ...mapping, [f.key]: e.target.value || null })}
            >
              <option value="">— Not mapped —</option>
              {columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
    </div>
  )
}
