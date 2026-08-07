"""Voice catalog for the dashboard (product-facing labels only)."""

VOICES = [
    {"id": "af_heart", "name": "Heart", "language": "en-us", "gender": "Female", "grade": "A", "label": "Heart — Female"},
    {"id": "af_bella", "name": "Bella", "language": "en-us", "gender": "Female", "grade": "A-", "label": "Bella — Female"},
    {"id": "af_nicole", "name": "Nicole", "language": "en-us", "gender": "Female", "grade": "B-", "label": "Nicole — Female"},
    {"id": "af_sarah", "name": "Sarah", "language": "en-us", "gender": "Female", "grade": "C+", "label": "Sarah — Female"},
    {"id": "af_jessica", "name": "Jessica", "language": "en-us", "gender": "Female", "grade": "D", "label": "Jessica — Female"},
    {"id": "af_aoede", "name": "Aoede", "language": "en-us", "gender": "Female", "grade": "C+", "label": "Aoede — Female"},
    {"id": "af_kore", "name": "Kore", "language": "en-us", "gender": "Female", "grade": "C+", "label": "Kore — Female"},
    {"id": "af_nova", "name": "Nova", "language": "en-us", "gender": "Female", "grade": "C", "label": "Nova — Female"},
    {"id": "af_river", "name": "River", "language": "en-us", "gender": "Female", "grade": "D", "label": "River — Female"},
    {"id": "af_sky", "name": "Sky", "language": "en-us", "gender": "Female", "grade": "C-", "label": "Sky — Female"},
    {"id": "af_alloy", "name": "Alloy", "language": "en-us", "gender": "Female", "grade": "C", "label": "Alloy — Female"},
    {"id": "am_michael", "name": "Michael", "language": "en-us", "gender": "Male", "grade": "C+", "label": "Michael — Male"},
    {"id": "am_fenrir", "name": "Fenrir", "language": "en-us", "gender": "Male", "grade": "C+", "label": "Fenrir — Male"},
    {"id": "am_puck", "name": "Puck", "language": "en-us", "gender": "Male", "grade": "C+", "label": "Puck — Male"},
    {"id": "am_echo", "name": "Echo", "language": "en-us", "gender": "Male", "grade": "D", "label": "Echo — Male"},
    {"id": "am_eric", "name": "Eric", "language": "en-us", "gender": "Male", "grade": "D", "label": "Eric — Male"},
    {"id": "am_liam", "name": "Liam", "language": "en-us", "gender": "Male", "grade": "D", "label": "Liam — Male"},
    {"id": "am_onyx", "name": "Onyx", "language": "en-us", "gender": "Male", "grade": "D", "label": "Onyx — Male"},
    {"id": "am_adam", "name": "Adam", "language": "en-us", "gender": "Male", "grade": "F+", "label": "Adam — Male"},
    {"id": "bf_emma", "name": "Emma", "language": "en-gb", "gender": "Female", "grade": "B-", "label": "Emma — Female (UK)"},
    {"id": "bf_isabella", "name": "Isabella", "language": "en-gb", "gender": "Female", "grade": "C", "label": "Isabella — Female (UK)"},
    {"id": "bf_alice", "name": "Alice", "language": "en-gb", "gender": "Female", "grade": "D", "label": "Alice — Female (UK)"},
    {"id": "bf_lily", "name": "Lily", "language": "en-gb", "gender": "Female", "grade": "D", "label": "Lily — Female (UK)"},
    {"id": "bm_george", "name": "George", "language": "en-gb", "gender": "Male", "grade": "C", "label": "George — Male (UK)"},
    {"id": "bm_lewis", "name": "Lewis", "language": "en-gb", "gender": "Male", "grade": "D+", "label": "Lewis — Male (UK)"},
    {"id": "bm_daniel", "name": "Daniel", "language": "en-gb", "gender": "Male", "grade": "D", "label": "Daniel — Male (UK)"},
    {"id": "bm_fable", "name": "Fable", "language": "en-gb", "gender": "Male", "grade": "C", "label": "Fable — Male (UK)"},
]

AGENTS = [
    {"id": "sales_outreach", "name": "Outreach", "description": "General outreach conversations."},
    {"id": "appointment", "name": "Appointments", "description": "Appointment reminders."},
    {"id": "collections", "name": "Accounts", "description": "Account follow-up."},
    {"id": "support", "name": "Support", "description": "Customer follow-up."},
]


def list_voices():
    return VOICES


def get_voice(voice_id: str):
    for v in VOICES:
        if v["id"] == voice_id:
            return v
    return VOICES[4]


def list_agents():
    return AGENTS
