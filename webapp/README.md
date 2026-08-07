# Kokoro AI Calling Dashboard

Production-style operations UI for AI outbound calling, built on the existing Kokoro TTS + Asterisk AMI stack.

## Architecture

- **Backend:** Flask JSON API (`app.py`) + SQLite (`db.py`)
- **Services:** Excel parse/validate, campaigns, call runner
- **Voice:** [`voice.py`](voice.py) — Kokoro `KPipeline` (unchanged adapter boundary)
- **Telephony:** [`ami_client.py`](ami_client.py) — real AMI originate (never faked)
- **Frontend:** React + Vite + TypeScript in [`frontend/`](frontend/)

## Quick start

```bash
# Backend deps
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run build
cd ..

# Run API + SPA
python app.py
```

Open http://127.0.0.1:5000

**Demo login:** `demo` / `demo123`

### Development (hot reload UI)

```bash
# Terminal 1
python app.py

# Terminal 2
cd frontend
npm run dev
```

Vite proxies `/api` to port 5000.

## Notes

- Kokoro package requires Python **3.10–3.13**. On 3.14, the UI still runs; TTS calls return a clear unavailable error.
- Campaign Start uses real AMI. If Asterisk/`asterisk/.env` is missing, the live UI shows **Telephony unavailable** and does not invent successful dials.
- Invalid spreadsheet rows are kept and labeled with validation errors.
