export type User = {
  id: number
  username: string
  client_name: string
}

export type Patient = {
  id?: number
  row_index?: number
  name: string
  phone?: string
  balance?: number | null
  balance_display?: string
  hospital?: string
  validation_status?: 'valid' | 'invalid' | 'duplicate'
  validation_errors?: string[]
  calling_status?: string
  last_called_at?: string
}

/** @deprecated use Patient */
export type Contact = Patient & {
  email?: string
  company?: string
  list_id?: number
}

export type ContactList = {
  id: number
  name: string
  filename?: string
  row_count: number
  valid_count: number
  invalid_count: number
  created_at: string
}

export type Voice = {
  id: string
  name: string
  language: string
  gender: string
  grade: string
  label: string
}

export type Agent = {
  id: string
  name: string
  description: string
}

export type Campaign = {
  id: number
  name: string
  status: 'draft' | 'ready' | 'running' | 'paused' | 'completed' | 'failed'
  list_id?: number
  voice_id: string
  voice_speed: number
  agent_name: string
  opening_message?: string
  calling_mode: string
  max_calls?: number
  delay_ms: number
  concurrency: number
  total_contacts: number
  completed_calls: number
  successful_calls: number
  no_answer_calls: number
  failed_calls: number
  in_progress_calls: number
  current_contact_id?: number
  current_call_id?: number
  agent_state: string
  error_message?: string
  created_at: string
  started_at?: string
  completed_at?: string
  progress?: number
  success_rate?: number
  voice?: Voice
  current_contact?: Patient
  current_call?: Call
  ready_contacts?: number
}

export type Call = {
  id: number
  campaign_id?: number
  contact_id?: number
  status: string
  outcome?: string
  duration_sec?: number
  script_text?: string
  transcript?: TranscriptEntry[]
  events?: CallEvent[]
  detail?: string
  started_at?: string
  ended_at?: string
  created_at: string
  contact_name?: string
  contact_phone?: string
  contact_company?: string
  contact_email?: string
  campaign_name?: string
  balance?: number
  balance_display?: string
  hospital?: string
}

export type TranscriptEntry = {
  speaker: 'agent' | 'contact' | 'system'
  text: string
  ts: string
}

export type CallEvent = {
  ts: string
  type: string
  message: string
  detail?: string
}

export type Mapping = Record<string, string | null>

export type Health = {
  available: boolean
  configured?: boolean
  reachable?: boolean
  detail: string
}
