async function request<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(path, {
    credentials: 'include',
    ...options,
    headers,
  })

  const data = await res.json().catch(() => ({ ok: false, error: 'Invalid server response' }))
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`)
  }
  return data as T
}

export const api = {
  login: (username: string, password: string) =>
    request<{ user: import('../types').User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request('/api/auth/logout', { method: 'POST' }),

  me: () => request<{ user: import('../types').User }>('/api/auth/me'),

  dashboard: () => request<Record<string, unknown>>('/api/dashboard'),

  contacts: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    })
    return request<{ items: import('../types').Patient[]; total: number; page: number; page_size: number }>(
      `/api/contacts?${qs}`,
    )
  },

  contact: (id: number) => request<{ contact: import('../types').Patient }>(`/api/contacts/${id}`),

  createContact: (data: { name: string; phone: string; balance: string | number; hospital: string }) =>
    request<{ contact: import('../types').Patient }>('/api/contacts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateContact: (id: number, data: Record<string, unknown>) =>
    request<{ contact: import('../types').Patient }>(`/api/contacts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteContact: (id: number) =>
    request<{ deleted: boolean }>(`/api/contacts/${id}`, { method: 'DELETE' }),

  deleteContacts: (ids: number[]) =>
    request<{ deleted_count: number }>('/api/contacts', {
      method: 'DELETE',
      body: JSON.stringify({ ids }),
    }),

  uploadExcel: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{
      filename: string
      columns: string[]
      detected_mapping: import('../types').Mapping
      row_count: number
      requires_mapping: boolean
      persisted: boolean
      patients?: import('../types').Patient[]
      contacts?: import('../types').Patient[]
      valid_count?: number
      invalid_count?: number
      duplicate_count?: number
      attention_count?: number
    }>('/api/contacts/upload', { method: 'POST', body: fd })
  },

  previewMapping: (mapping: import('../types').Mapping) =>
    request<{
      contacts: import('../types').Patient[]
      patients: import('../types').Patient[]
      row_count: number
      valid_count: number
      invalid_count: number
      duplicate_count: number
      attention_count: number
      filename: string
      mapping: import('../types').Mapping
      persisted: boolean
    }>('/api/contacts/upload/preview', {
      method: 'POST',
      body: JSON.stringify({ mapping }),
    }),

  confirmImport: (mapping: import('../types').Mapping, list_name?: string) =>
    request<{
      list_id: number
      name: string
      row_count: number
      valid_count: number
      invalid_count: number
      duplicate_count: number
      imported_count: number
      persisted: boolean
    }>('/api/contacts/upload/confirm', {
      method: 'POST',
      body: JSON.stringify({ mapping, list_name }),
    }),

  cancelImport: () =>
    request<{ cancelled: boolean; persisted: boolean }>('/api/contacts/upload/pending', {
      method: 'DELETE',
    }),

  startCalling: () =>
    request<{ campaign: import('../types').Campaign }>('/api/calling/start', { method: 'POST' }),

  campaigns: () => request<{ campaigns: import('../types').Campaign[] }>('/api/campaigns'),

  campaign: (id: number) => request<{ campaign: import('../types').Campaign }>(`/api/campaigns/${id}`),

  liveCampaign: (id: number) =>
    request<{ campaign: import('../types').Campaign; telephony: import('../types').Health & { mode?: string } }>(
      `/api/campaigns/${id}/live`,
    ),

  startCampaign: (id: number) =>
    request<{ campaign: import('../types').Campaign }>(`/api/campaigns/${id}/start`, { method: 'POST' }),

  pauseCampaign: (id: number) =>
    request<{ campaign: import('../types').Campaign }>(`/api/campaigns/${id}/pause`, { method: 'POST' }),

  resumeCampaign: (id: number) =>
    request<{ campaign: import('../types').Campaign }>(`/api/campaigns/${id}/resume`, { method: 'POST' }),

  stopCampaign: (id: number) =>
    request<{ campaign: import('../types').Campaign }>(`/api/campaigns/${id}/stop`, { method: 'POST' }),

  calls: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    })
    return request<{ items: import('../types').Call[]; total: number; page: number; page_size: number }>(
      `/api/calls?${qs}`,
    )
  },

  call: (id: number) => request<{ call: import('../types').Call }>(`/api/calls/${id}`),

  voices: () =>
    request<{ voices: import('../types').Voice[]; agents: import('../types').Agent[] }>('/api/voices'),

  settings: () => request<{ settings: Record<string, string> }>('/api/settings'),

  saveSettings: (payload: Record<string, string | number>) =>
    request<{ settings: Record<string, string> }>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  notifications: () =>
    request<{ notifications: Array<{ id: number; message: string; level: string; read: number; created_at: string }> }>(
      '/api/notifications',
    ),

  markNotificationsRead: () => request('/api/notifications/read', { method: 'POST' }),

  health: () => request<import('../types').HealthStatus>('/api/health'),

  previewVoice: (voice_id: string, speed: number, text?: string) =>
    fetch('/api/voices/preview', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice_id, speed, text }),
    }).then(async (res) => {
      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: 'Unable to generate a voice preview' }))
        throw new Error(data.error || 'Unable to generate a voice preview')
      }
      return res.blob()
    }),

  admin: {
    users: () => request<{ users: import('../types').AdminUser[] }>('/api/admin/users'),

    createUser: (payload: { username: string; password: string; role: string; email?: string }) =>
      request<{ user: import('../types').AdminUser }>('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    updateUser: (id: number, payload: Record<string, string>) =>
      request<{ user: import('../types').AdminUser }>(`/api/admin/users/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),

    resetPassword: (id: number, password: string) =>
      request<{ reset: boolean }>(`/api/admin/users/${id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password }),
      }),

    loginHistory: (params: { page?: number; page_size?: number } = {}) => {
      const qs = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)))
      return request<{ items: import('../types').LoginHistoryEntry[]; total: number; page: number; page_size: number }>(
        `/api/admin/login-history?${qs}`,
      )
    },

    auditLogs: (params: { page?: number; page_size?: number; action?: string; entity?: string } = {}) => {
      const qs = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
      return request<{ items: import('../types').AuditLogEntry[]; total: number; page: number; page_size: number }>(
        `/api/admin/audit-logs?${qs}`,
      )
    },

    demoRequests: (params: { page?: number; page_size?: number; status?: string } = {}) => {
      const qs = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
      return request<{ items: import('../types').DemoRequest[]; total: number; page: number; page_size: number }>(
        `/api/demo-requests?${qs}`,
      )
    },

    updateDemoRequest: (id: number, payload: { status?: string; notes?: string }) =>
      request<{ demo_request: import('../types').DemoRequest }>(`/api/demo-requests/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
  },
}
