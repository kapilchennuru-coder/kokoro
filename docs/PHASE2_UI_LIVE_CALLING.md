# Phase 2 — UI + Live Calling Status — Summary

Work performed: 2026-08-10, on top of the PostgreSQL migration (see `docs/POSTGRESQL_MIGRATION.md`). Status: **complete for the prioritized scope, verified against real backend data on a live running server.** Flask, React, Kokoro TTS, Twilio, campaigns, retry engine, auth, RBAC, and the database were all preserved — nothing in this pass replaced or rewrote them.

## What changed

- **Real call-status data was actually incomplete.** `busy` outcomes were being silently folded into the generic `failed` bucket everywhere (counters, live view). Added a genuine `busy_calls` counter, separate from `failed_calls`, and fixed the counting logic that fills it.
- **Live Calling page rebuilt** with the full status breakdown the spec asked for (Queued / Calling / Answered / No Answer / Busy / Failed / Completed, plus Simulated when in test mode), a live elapsed timer for the call currently in progress (replaced by the real backend duration the instant the call ends — never a substitute for it), attempt number, and a TEST/LIVE mode badge sourced from the real Twilio settings.
- **Start Calling previously fired with zero confirmation.** Added a confirmation modal showing real patient count, voice, calling-hours window, retry count, and an explicit LIVE/TEST warning before anything is dialed. Stop Campaign gained the same treatment (was instant before).
- **Calls page**: outcome filter (Answered / No Answer / Busy / Failed / Invalid Number / Simulated — the actual backend vocabulary, nothing invented), duration and attempt columns, Twilio Call SID surfaced in the detail drawer.
- **Patients page**: added Last Call, Duration, Last Called, and Attempts columns, computed via a real join against call history — not a second, competing status system.
- **Branding** was already in place from earlier work (title, favicon, sidebar, login) — checked, no changes needed.
- **Not done this pass, on purpose**: no new Campaigns/Voices/Reports pages. Those don't exist yet in this app; building them is new scope, not "improve existing UI," which is what this phase asked for. Flagged for you to decide rather than silently expanded.

## Code changes, file by file

### `webapp/db.py`

- **New column `campaigns.busy_calls`** (`INTEGER NOT NULL DEFAULT 0`) — added live via `ALTER TABLE` to both `outreach` and `outreach_test`, and added to `migrations/001_initial_postgres_schema.sql` for fresh installs going forward.
- **`get_calls(...)`**: gained an `outcome` filter parameter (`clauses.append("calls.outcome = %s")`) — the granular Answered/No Answer/Busy/Failed buckets the Calls page filter needs map to `outcome`, not the coarser `status` column that was the only filter before. Also joined `campaign_contacts` to compute `attempt_number` (`COALESCE(cc.retry_count, 0) + 1`) per call.
- **`get_call(...)`** (single-call fetch, used for `campaign.current_call` on the Live Calling page): same `attempt_number` join added; also added `contacts.hospital`/`contacts.balance` to the `SELECT` and a `balance_display` computation — these were present in `get_calls` (the list) but missing from `get_call` (the detail fetch), an inconsistency fixed while touching this function for the same reason.
- **`get_contacts(...)`**: rewritten to `LEFT JOIN LATERAL` against `calls` for each contact's most recent call (`last_call_status`, `last_call_outcome`, `last_call_duration_sec`, `last_call_at`), and `LEFT JOIN campaign_contacts` (via `contacts.last_campaign_id`) for `attempt_count`. Because the query now joins multiple tables, every column reference in the dynamic `WHERE`/`ORDER BY` clause-builder had to be qualified with `contacts.` — an unqualified `id`/`created_at` would otherwise be ambiguous between `contacts` and the joined tables and Postgres would reject the query outright (caught and fixed before it ever reached the live server).

### `webapp/services/call_runner.py`

- Counter-update branch: was `if outcome == "answered": ... elif call_status == "no_answer": ... else: failed += 1` (this `else` is what silently absorbed `busy` into `failed`). Now explicitly branches `outcome == "busy"` into its own `busy` counter before the generic `else`, and `campaigns.busy_calls` is included in the `db.update_campaign(...)` call alongside the existing counters.

### `webapp/app.py`

- `/api/calls` route: reads `request.args.get("outcome", "")` and passes it through to `db.get_calls(...)`.

### Frontend

**`types.ts`**: `Patient` gained `last_call_status`, `last_call_outcome`, `last_call_duration_sec`, `last_call_at`, `attempt_count`. `Campaign` gained `busy_calls`. `Call` gained `provider_call_sid`, `attempt_number`.

**`api/client.ts`**: `liveCampaign(id)`'s return type widened to include `telephony` (previously only typed `{campaign}`, even though the backend always returned `telephony`/`tts` alongside it) — needed so the Live Calling page can read the real `mode` (test/live) for its badge.

**`components/ConfirmDialog.tsx`**: `message` prop widened from `string` to `ReactNode` — backward compatible (every existing caller still passes a plain string), needed so the new Start Calling confirmation can show a structured, multi-line summary instead of one line of text.

**`components/ui.tsx`** (`StatusBadge`): added color-map entries for `invalid_number` and `stopped`, which had no explicit styling before (fell through to the generic default).

**`lib/labels.ts`**: added human-readable labels for `invalid_number` and `stopped`.

**`pages/LiveCallingPage.tsx`** — rewritten:
- Full status-breakdown grid computed from real campaign fields: `queued = total_contacts - completed_calls - in_progress_calls`, `calling = in_progress_calls`, `answered = successful_calls`, `no_answer = no_answer_calls`, `busy = busy_calls`, `failed = failed_calls`, `completed = completed_calls`, `simulated = simulated_calls` (shown only when > 0).
- Live elapsed-timer `useEffect`: ticks locally once per second from `current_call.started_at` only while `agent_state` is one of the in-progress states (`connecting`/`speaking`/`listening`/`thinking`); resets to 0 and stops the moment the call is no longer in progress, so the real backend duration (once available) is always what's actually shown for a finished call, never the local timer.
- TEST/LIVE badge reads `telephony.mode` from the (now correctly typed) live-campaign response.
- Stop Campaign now goes through a `ConfirmDialog` instead of firing immediately.

**`pages/DashboardPage.tsx`**:
- New `openStartConfirm()`: fetches `api.settings()` + `api.voices()`, resolves the voice label, builds a calling-window string (or "No restriction" if calling hours aren't enabled), and opens a confirmation modal before `startCalling()` is ever called. Both "Start Calling" buttons (the post-import success state and the idle-state header button) now call `openStartConfirm` instead of `startCalling` directly.
- New `ConfirmDialog` with a structured message: patient count, voice, calling window, retry count, and a colored LIVE/TEST banner (red for live, blue for test) built from the real `twilio_mode` setting.

**`pages/CallsPage.tsx`** — rewritten:
- Outcome filter `<select>` (All / Answered / No Answer / Busy / Failed / Invalid Number / Simulated), refetches on change.
- Table gained Duration and Attempt columns (`formatDuration` helper, mm:ss from `duration_sec`).
- Detail drawer gained Duration, Attempt, Ended, and — when present — Twilio Call SID.
- Status badges throughout now show `outcome` when available (falling back to `status`), since `outcome` is the more specific/useful value for a completed call.

**`pages/PatientsPage.tsx`**:
- Table gained Last Call (badge, from `last_call_outcome`), Duration, Last Called, and Attempts columns.

## Testing

- `python -m unittest discover -s tests` → **17/17 passed** after every backend change in this phase (schema addition, counter logic, query rewrites).
- `tsc -b && vite build` → clean, zero errors, after every frontend change.
- Live walkthrough against the real running server (not just tests): confirmed `busy_calls` field present and correct on `GET /api/campaigns`; confirmed `GET /api/calls?outcome=answered` correctly filtered to real answered calls with real Twilio Call SIDs and attempt numbers; confirmed `GET /api/contacts` returned real `last_call_outcome`/`duration`/`attempt_count` per patient (verified against James Anderson's actual call history from earlier live Twilio tests this session).
- Caught and fixed a real duration-tracking gap in `scripts/test_live_call.py` (the manual Twilio diagnostic tool, not the app itself) while verifying the new duration column — it never recorded `duration_sec` on the calls it created, so every one of its calls showed `00:00`. Now pulls Twilio's own reported duration from the final status poll.

## What's left / explicitly deferred

- **New pages** (Campaigns list/management, Voices, Reports) — not built. These are net-new features, not improvements to what exists; the spec's own instruction was to improve the existing UI, and expanding into brand-new pages without being asked would be scope creep.
- **Deep UI-glitch audit** (overflow, z-index, spacing, duplicate toasts, etc. from the spec's cleanup checklist) — not systematically hunted through; only the concrete, verifiable gaps found while doing the priority-1 work (status data, duration, confirmation modals) were fixed. A dedicated visual QA pass would need to be its own task.
- **Responsive design** — not deeply audited beyond confirming the existing horizontal-scroll table pattern is still in place; no new breakpoints or layout work done.
- **`Rejected` as a distinct outcome** — the spec's example table includes it, but Twilio's actual call-status vocabulary (and this app's `outcome` column) doesn't produce a status separate from `busy`/`failed` for a rejected call. Rather than invent a fake bucket with no real data behind it (which the spec explicitly warns against — "map backend/Twilio values cleanly to user-facing labels," "do not create a competing status system"), it was left out. If Twilio ever reports something more specific here, it can be added the same way `busy` was.
