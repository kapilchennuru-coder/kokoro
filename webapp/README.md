# Kokoro AI Calling Dashboard

Production-style operations UI for AI outbound calling, built on Kokoro TTS + Twilio Voice.

## Architecture

- **Backend:** Flask JSON API (`app.py`) + SQLite (`db.py`)
- **Services:** Excel parse/validate, campaigns, call runner, RBAC (`services/rbac.py`)
- **Voice:** [`voice.py`](voice.py) — Kokoro `KPipeline` (unchanged adapter boundary)
- **Telephony:** [`services/twilio_client.py`](services/twilio_client.py) — real Twilio Voice calls (never faked); `test`/`live` credential modes let you exercise the full pipeline safely before a real call ever goes out
- **Frontend:** React + Vite + TypeScript in [`frontend/`](frontend/)

> Note: `kokoro/asterisk/` (the previous Asterisk/PJSIP/VoIP Office setup) is no longer used by this app — VoIP Office does not support third-party SIP registration on their platform. It's left in the repo as a fallback but nothing here calls into it.

## Quick start

```bash
# Backend deps
pip install -r requirements.txt
cp .env.example .env   # fill in SECRET_KEY at minimum

# Frontend
cd frontend
npm install
npm run build
cd ..

# Run API + SPA
python app.py
```

Open http://127.0.0.1:5000

**Demo login:** `demo` / `demo123` (auto-seeded as `SUPER_ADMIN` on first run — change this before any real deployment). To seed an additional admin instead, set `SUPERADMIN_USERNAME` / `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` in `.env` before first run.

## Roles & permissions

Five roles, enforced server-side only (`services/rbac.py` — never trust a role from the frontend): `SUPER_ADMIN`, `ADMIN`, `MANAGER`, `AGENT`, `VIEWER`. Manage users, roles, and status from **Administration → Users** in the sidebar (visible to `SUPER_ADMIN`/`ADMIN` only). Every sign-in attempt is logged to **Login History**; every mutating admin/data action is logged to **Audit Logs**.

## Retry engine & calling hours

Configurable from **Settings → Calling rules**: max retry attempts, separate retry delays for no-answer vs. busy outcomes, and an optional calling-hours window (start/end/days/timezone) that pauses a running campaign until the window reopens rather than dialing outside it. Invalid phone numbers are detected before dialing and are never retried. All of this lives in `services/call_runner.py` and runs in the existing background thread — no external queue/worker needed.

## Tests

```bash
python -m unittest discover -s tests
```

Runs against a disposable temp SQLite file — never touches `app.db`.

### Development (hot reload UI)

```bash
# Terminal 1
python app.py

# Terminal 2
cd frontend
npm run dev
```

Vite proxies `/api` to port 5000.

## Telephony (Twilio)

- Campaign Start places real calls via Twilio Voice. If `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` (or the `TWILIO_TEST_*` pair, depending on `twilio_mode`) aren't configured, the live UI shows **Telephony unavailable** and does not invent successful dials.
- **Test mode** (default) uses `TWILIO_TEST_ACCOUNT_SID`/`TWILIO_TEST_AUTH_TOKEN` — Twilio accepts the request and returns a real Call SID, but no phone actually rings and nothing is charged. Results are recorded as **Simulated**, kept out of real answered/no-answer/busy stats.
- **Live mode** places a real call. Switch via **Settings → Calling rules** (or `TWILIO_MODE=live` as the startup default) — this is a deliberate, visible toggle, never silent.
- The Kokoro-generated reminder actually plays on the call via TwiML `<Play>` **only if `PUBLIC_BASE_URL` is set** (Twilio's servers must fetch the audio over the public internet — they can't reach `localhost`). Without it, calls fall back to Twilio's own `<Say>` reading the script text aloud — still a real, correct call, just synthesized by Twilio instead of Kokoro.
- Call status (`answered`/`no-answer`/`busy`/`failed`/etc.) is captured two ways: the campaign runner polls Twilio's REST API directly (works with no public URL needed), and — if `PUBLIC_BASE_URL` is set — Twilio's own status webhook (`POST /api/webhooks/twilio/status`, signature-verified) updates the record independently in real time.

## Other notes

- Kokoro package requires Python **3.10–3.13**. On 3.14, the UI still runs; TTS calls return a clear unavailable error.
- Invalid spreadsheet rows are kept and labeled with validation errors.
