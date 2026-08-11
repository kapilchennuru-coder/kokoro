# Outreach — Phase 3: Implementation Summary

Work performed: 2026-08-10. Status: **both the calling bug and the logo are fixed/shipped and verified.** The original spec follows below this summary, preserved as-is for reference.

## Root cause: Start Calling silently didn't call anyone

The request chain itself was never broken — `POST /api/calling/start` always returned `200`, the campaign always transitioned to `running`. The actual failure was two real, separate bugs discovered by tracing an actual real call rather than trusting the `200` response, exactly as the spec's own Section 26 demanded ("do not declare fixed merely because the API returns HTTP 200"):

1. **`GET /api/audio/<id>.wav` was crashing with a 500 on every request.** `app.py`'s audio-serving route had a leftover SQLite-style query — `"SELECT audio_filename FROM calls WHERE id = ?"` — that was never converted to PostgreSQL's `%s` placeholder when the database was migrated off SQLite earlier in this project. Every real call since that migration fetched this URL for `<Play>`, got a 500/crash instead of audio, and Twilio played its own generic "an application error has occurred" fallback. **This means no call since the Postgres migration had ever successfully played the real Kokoro message** - confirmed by two real calls placed during this investigation, both of which produced exactly that generic error on the receiving end.
2. **The Twilio status webhook rejected every real callback with a 403.** `services.telephony`'s signature check validated against Flask's `request.url`, which reflects the local `http://localhost:5000/...` address the request actually arrived on behind the ngrok tunnel — not the public `https://.../...ngrok-free.dev/...` URL Twilio actually signed. The signature could never match. Call outcomes were still being captured correctly (the campaign runner polls Twilio's REST API directly, independent of the webhook, by design from earlier work), so this bug didn't block calling itself, but it meant the webhook path documented in the spec's Section 15 was silently non-functional the whole time.

A third, contributing issue made both of the above hard to notice from the UI: **Calling Hours was enabled with the timezone defaulted to `America/New_York`**, while the account's actual patients/test numbers are in India. Outside that window, a campaign just sits at `agent_state: waiting_for_hours` forever with no call attempted - and the **Settings page's timezone dropdown had no India/Asia option in it at all**, so there was no way to even select the correct zone from the UI. This made "Start Calling does nothing" look like the calling pipeline itself was broken, when it was actually the audio/webhook bugs above plus a silent, un-escapable scheduling gate.

## Fixes

| # | File | Fix |
|---|---|---|
| 1 | `webapp/app.py` (`api_call_audio`) | `WHERE id = ?` → `WHERE id = %s` (psycopg placeholder) |
| 2 | `webapp/app.py` (`api_twilio_status_webhook`) | Validate the Twilio signature against `PUBLIC_BASE_URL` + `request.full_path` instead of `request.url` when `PUBLIC_BASE_URL` is set |
| 3 | `webapp/frontend/src/pages/SettingsPage.tsx` | `COMMON_TIMEZONES` list expanded from 6 US-only zones to include `Asia/Kolkata`, `Asia/Dubai`, `Asia/Singapore`, `Europe/London`, `Europe/Berlin`, `Australia/Sydney` |
| 4 | Live org setting (via the real `PUT /api/settings` API, not a DB edit) | `timezone` corrected from `America/New_York` to `Asia/Kolkata` so calling hours actually cover the account's real working hours |
| 5 | `webapp/frontend/src/pages/LiveCallingPage.tsx` | The "current call" panel showed a bare `—` with zero explanation whenever there was no contact selected yet - exactly the state a campaign sits in while blocked on calling hours or a scheduled retry. Now shows the real `agent_state` label (e.g. "Waiting for calling hours") in that case instead of a silent dash. |
| 6 | `webapp/frontend/src/pages/DashboardPage.tsx` | The Start Calling confirmation modal now proactively computes, client-side, whether *right now* falls inside the configured calling window (using the real settings + `Intl.DateTimeFormat` against the configured timezone) and shows an explicit warning before the user clicks Start, instead of only finding out after nothing happens. |

**Both fixes were verified for real, not assumed from a clean HTTP response:** fetched `/api/audio/<id>.wav` directly after the fix and got back a genuine 11.9-second WAV (previously a 500/crash); computed a real Twilio-style signature with the `twilio` SDK's own `RequestValidator.compute_signature` and POSTed it through the actual ngrok tunnel, which returned `{"ok": true}` (previously a 403 on every attempt, real or synthetic).

**Full test suite**: `python -m unittest discover -s tests` → 17/17 passing after every fix in this phase.

### A note on the two real calls placed during this investigation

Two real calls went out to the account's own authorized test numbers while tracing this bug (both received the "application error" message, which is exactly what confirmed root cause #1). Both campaigns were stopped as soon as this was noticed, before any retry could fire again automatically. No further calls were placed without being explicitly flagged first.

## New logo: Connection Ring

Three concepts (all fusing O + a phone/connection cue in different ways) were designed and reviewed side-by-side, rendered at real sizes from 64px down to 16px favicon scale on the app's actual sidebar color - **not just described, but actually tested for legibility at the sizes the spec requires** (Section 21: "render crisply at 16/24/32/48/64px"). Two of the three concepts tried to literally fuse the letters O and R with a phone glyph into one small shape; both lost their phone-icon detail below ~32px. The third — a ringing connection node (circle, center point, two signal arcs radiating out, like a phone mid-ring) paired with the OUTREACH wordmark — stayed crisp at every size, including 16px, and was the one selected.

### Files changed

- **`webapp/frontend/src/components/BrandMark.tsx`** — rewritten. Was a fixed 24×24 glyph with no configuration; now exports a proper component with `size`, `variant` (`'full' | 'mark' | 'text'`), and `className` props, matching the spec's Section 21 requirement. The icon uses `currentColor` for its stroke/fill (not a hard-coded color), so it can be recolored per context via CSS rather than needing separate light/dark SVG variants. Stroke widths are tuned per size tier (thicker at small sizes) so the ring stays visually consistent rather than thinning into invisibility as it shrinks.
- **`webapp/frontend/src/components/shell.css`** (`.brand-mark`) — the old teal gradient square badge behind the previous icon was removed. The new mark was designed and approved rendered directly on flat backgrounds (the sidebar's actual navy, the login card's white), not inside a filled box; keeping the old badge would have muddied a teal ring against a teal-gradient square. Color set to `#14b8a6`, the exact shade validated in the review.
- **`webapp/frontend/public/favicon.svg`** — rebuilt to the same Connection Ring mark on the sidebar's real navy (`#0b1220`), so the browser tab matches the in-app mark exactly.
- **`Sidebar.tsx`** and **`LoginPage.tsx`** needed no changes — both already called `<BrandMark />` with defaults, which now render the new design automatically.

### Verified

Built the frontend (`tsc -b && vite build`, clean) and screenshotted the real running app via headless Chromium: confirmed the new mark renders correctly on both the login page (white background) and the sidebar (navy background, alongside the "Outreach / Workspace" wordmark), matching the approved concept exactly.

### Not yet applied

Per the spec's own Section 20/22 guidance, the mark is now live everywhere the previous one was (login, sidebar, favicon/browser tab). Not yet done: a dedicated loading-screen or error-page treatment (no such dedicated screens currently exist as separate components in this app to brand), and no landing/marketing page exists in this project to apply the full lockup to.

## Login page redesign: branded split-screen layout

Follow-up request: the login page's logo was too small and the background was plain white. Redesigned it into a two-column layout — a dark branded panel on the left, the existing sign-in card on the right — instead of a single centered card on a flat background.

### Files changed

- **`webapp/frontend/src/pages/LoginPage.tsx`** — added a `WatermarkRing` component (a large, low-opacity outline version of the Connection Ring mark, `stroke="currentColor"`, drawn from the same path/circle geometry as `BrandMark`). Restructured the page JSX from a single `.login-card` into `.login-page > (.login-brand, .login-form-panel)`. `.login-brand` contains the `WatermarkRing`, a `<BrandMark variant="mark" size={72} />`, an "OUTREACH" wordmark, a one-line product tagline, and a three-item "proof" row (Kokoro TTS / Twilio Voice / Live tracking — real product capabilities, not placeholder stats). `.login-form-panel` wraps the pre-existing `.login-card` unchanged.
- **`webapp/frontend/src/components/shell.css`** — added `.login-brand` (dark navy `#0b1220` background with two teal radial gradients), `.login-brand .watermark` (the ring SVG absolutely positioned at 780px/7% opacity as a background texture), `.login-brand-content`, `.login-brand .wordmark/.tagline/.proof`, `.login-form-panel`, and a `@media (max-width: 900px)` rule that collapses back to a single column and hides the brand panel on narrow screens. `.login-page` changed from a centered single column to `display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr)`.

### Bug found and fixed during verification

First build+screenshot pass showed the brand panel's logo/wordmark/tagline rendering almost invisibly, inside a washed-out light rectangle sitting on the dark background instead of directly on it. Root cause: the new inner wrapper was named `.content`, which collided with a **pre-existing, unrelated global `.content` class** in `shell.css` (used for the main authenticated-app shell's content area — `padding: 28px`, `background: var(--bg)` light gradient, `min-height: calc(100vh - var(--topbar-h))`). The login page's more specific `.login-brand .content` rule only set `display/flex-direction/gap/max-width`, so it never overrode the global class's `background`/`padding`/`min-height` — those bled through as a light box on top of the dark panel. Fixed by renaming the wrapper class to `.login-brand-content` (both in the CSS selector and the JSX `className`), which has no collision anywhere else in the codebase (checked via grep for `wordmark`/`tagline`/`proof`/`watermark` too — all unique).

### Verified

Rebuilt (`tsc -b && vite build`, clean) and re-screenshotted the running login page via headless Chromium. Confirmed: dark panel renders correctly with the large (72px) logo, "OUTREACH" wordmark, tagline, and proof row visible in light text over the faint watermark ring, teal radial-gradient glow in the corners; the sign-in card on the right is unchanged and fully functional.

### Copy update: tagline and motto

Follow-up: swapped the tagline for the chosen option from a list of alternatives, and replaced the three-item "proof" row (Kokoro TTS / Twilio Voice / Live tracking) with a single short motto line.

- **`webapp/frontend/src/pages/LoginPage.tsx`** — `.tagline` text changed to "Making Every Call Count." The `.proof` `<div>` (three feature callouts) was removed and replaced with a single `<p className="motto">Connect. Communicate. Collect.</p>`.
- **`webapp/frontend/src/components/shell.css`** — `.login-brand .proof`/`.proof strong`/`.proof span` rules (flex row, per-item heading + caption styling) removed and replaced with a single `.login-brand .motto` rule: keeps the same top border/divider as the old proof row, set in the teal accent color (`#5eead4`) with `font-family: var(--font-display)` for a short, confident punch line under the tagline.

Rebuilt and re-screenshotted; confirmed the brand panel now reads logo → "OUTREACH" → "Making Every Call Count." → divider → "Connect. Communicate. Collect." with no leftover proof-row styling.

## Manual "add one patient" option on the dashboard

Follow-up request: the Import Patients block only supported bulk Excel upload. Added a way to add a single patient by hand (Name, Phone Number, Balance, Hospital) without building a spreadsheet.

### Files changed

- **`webapp/services/contact_service.py`** — added `add_contact(user_id, data)`. Reuses the exact same validation/normalization the Excel import path already uses (`excel_parser.parse_balance`, `excel_parser.normalize_phone`, `excel_parser.validate_patient`) so a manually-added patient is held to the same bar as an imported one (valid phone, non-empty name/hospital, parseable balance). Also rejects a phone number that already exists in the organization's contacts (`db.get_existing_phones`), same duplicate rule the bulk importer applies. On success, inserts via `db.insert_contacts(organization_id, None, [patient])` — passing `list_id=None` since a manually-added patient isn't tied to any uploaded file/list — and returns the persisted row.
- **`webapp/app.py`** — added `POST /api/contacts` (`api_create_contact`), gated by the existing `import_patients` permission (the same permission that already gates the Excel upload flow — adding one patient by hand is the same category of action as importing many). Writes a `patient_create` audit log entry on success, matching the pattern used by `patient_update`/`patient_delete`.
- **`webapp/frontend/src/api/client.ts`** — added `api.createContact(data)` → `POST /api/contacts`.
- **`webapp/frontend/src/pages/DashboardPage.tsx`** — the "Import Patients" card now has a `+ Add one patient manually` toggle below the Excel drop zone. Expands into an inline form (Name, Phone Number, Balance, Hospital) using the app's existing `.field`/`.label`/`.input` form styles. On submit, calls `api.createContact`, shows a toast, collapses the form, and reloads the dashboard KPIs so the new patient is reflected immediately (Patients/Ready counts).

### Verified

Rebuilt (`tsc -b && vite build`, clean). Logged into the real running app via headless Chromium (`demo`/`demo123`), opened the manual-add form, submitted a test patient, and confirmed: a success toast, the Patients KPI going from 1 → 2 and Ready from 0 → 1, and the form collapsing back to the toggle button. The test record was then deleted directly from the database to avoid leaving fabricated patient data behind.

## Call audio fix: 3 seconds of dead air after pickup

Follow-up bug report: after the callee picks up, there's a noticeable ~3 second silence before the Kokoro message starts playing.

**Root cause**: `services/twilio_client.py` (`build_twiml`) deliberately opens every call's TwiML with `response.pause(length=2)` — a fix from earlier in this project for a different problem (some PSTN/landline routes report "answered" to Twilio a beat before the two-way audio path is actually cut through, clipping the start of playback if it starts immediately). On top of that 2-second pause, Twilio's media server still has to fetch the `<Play>` URL (`GET /api/audio/<call_id>.wav`) over the public tunnel before it can start playing — which adds roughly another second. The two stack into the ~3 seconds the callee actually hears. (Audio generation itself is not the cause — `call_runner.py` already generates the Kokoro WAV and saves `audio_filename` on the call row *before* dialing, specifically so the file is ready the instant Twilio requests it.)

**Fix**: `services/twilio_client.py` — `response.pause(length=2)` → `response.pause(length=1)`. Keeps enough of a buffer to avoid reintroducing the original clipping problem, while cutting the perceived dead air roughly in half.

### Verified

`python -m unittest discover -s tests` → 17/17 passing after the change.

## Call script: placeholders not substituting, "ZEBL" spelled out letter-by-letter

Follow-up bug report: the spoken message wasn't filling in the patient's name/balance, and "ZEBL" was being read out as "Z-E-B-L" instead of as a word.

**Root cause #1 — placeholders**: the organization's `opening_message` setting (Settings → Greeting / message) had been typed using `{{name}}` / `{{balance_display}}` / `{{hospital}}` (double-brace, Handlebars-style). `services/call_runner.py`'s `_render_script` renders the script with Python's `str.format(**values)`, which treats `{{` / `}}` as an *escaped literal brace*, not a placeholder — so `"{{name}}".format(name="John")` produces the literal text `"{name}"` rather than `"John"`. The Settings page already documents the correct single-brace syntax (the helper text under the textarea reads "You can use `{name}`, `{balance_display}`, and `{hospital}`"), but nothing stopped a double-brace template from being saved and silently failing at call time.

**Root cause #2 — pronunciation**: the template read `"...automated call from ZEBL."` All-caps short tokens like `ZEBL` get read by Kokoro as a spelled-out acronym ("Z-E-B-L") rather than as a word, because there's no dictionary entry or lowercase-vowel pattern for the TTS model to pronounce it as one. Writing it in mixed case (`Zebl`) makes the model treat it as an ordinary word instead.

**Fixes**:
- `services/call_runner.py` (`_render_script`) — now normalizes `{{key}}` (with optional inner whitespace, e.g. `{{ name }}`) to `{key}` via regex before calling `.format(...)`, so a double-brace template substitutes correctly instead of silently leaving literal `{name}` text in the spoken script. This is defensive going forward — the correct single-brace syntax still works exactly as before, and is still what the Settings page documents.
- The organization's live `opening_message` setting was corrected through the real Settings UI (`PUT /api/settings`, not a direct DB edit): `{{name}}` → `{name}` etc., and `ZEBL` → `Zebl AR team` for correct pronunciation. New text:

  > Hello {name}, this is an automated call from the Zebl AR team.
  >
  > Our records show an outstanding balance of {balance_display} for healthcare services you received at {hospital}.
  >
  > We are calling to notify you about this balance. Thank you for taking the call, and have a great day.

### Verified

Called `_render_script` directly with a sample contact (`name="John Smith"`, `balance=245.5`, `hospital="City General Hospital"`) against both the corrected single-brace template and a synthetic double-brace one — both substituted every field correctly (`$245.50`, full name, hospital). `python -m unittest discover -s tests` → 17/17 passing.

## Call audio, round 2: 6 seconds of dead air remained after the pause fix

Follow-up report: even after trimming the `<Pause>` to 1 second, the callee was still hearing about 6 seconds of silence after picking up. The 1-second pause alone couldn't explain that — traced the rest of it to the audio file itself.

**Root cause**: Kokoro's `generate_call_audio` was writing the WAV at its native **24,000 Hz**, 16-bit mono. For a ~25-second message that's roughly **930 KB**. Twilio's `<Play>` doesn't just stream that file — it first has to `GET` it in full from our public tunnel (`PUBLIC_BASE_URL`, a **free-tier ngrok domain**) before it can start playing. Reproduced this directly: fetched the real public audio URL for an existing call exactly as Twilio's media fetcher would, and timed it —

```
curl -D - -o /dev/null https://<tunnel>.ngrok-free.dev/api/audio/25.wav
→ 932,444 bytes, 4.38 seconds
```

That ~4.4s download, stacked on top of the 1s `<Pause>`, accounts for the ~6 seconds the callee actually heard. (The free ngrok tier itself is part of the cost here — it has real bandwidth limits — but the file being 3x larger than it needs to be for a phone call was the part in our control.)

**Fix**: phone calls only carry ~8,000 Hz of audio bandwidth to begin with (standard narrowband PSTN telephony) — serving Kokoro's 24kHz output over a voice call was spending 3x the bytes on resolution the call can't use anyway. `voice.py`'s `generate_call_audio` now downsamples the generated audio from 24,000 Hz → **8,000 Hz** (`scipy.signal.resample_poly`, a clean 1:3 ratio) before writing the WAV, and serves it at that rate. `requirements.txt` gained `scipy>=1.10.0` (it was already installed locally, just undeclared).

### Verified

Generated a real test message through the actual Kokoro pipeline with the new code — file came out at 8,000 Hz / 256 KB for ~16 seconds of audio (previously ~24,000 Hz / ~930 KB for ~25 seconds — consistent with the expected ~3x reduction once normalized for length). Inserted a temporary call row pointing at that file and fetched it through the real public tunnel the same way as before:

```
curl -D - -o /dev/null https://<tunnel>.ngrok-free.dev/api/audio/26.wav
→ 256,844 bytes, 1.70 seconds  (was 4.38s for a comparably-sized file)
```

Deleted the temporary call row and test audio file afterward. `python -m unittest discover -s tests` → 17/17 passing. Combined with the 1-second `<Pause>`, total dead air after pickup should now be roughly **2.5–3.5 seconds**, down from ~6 seconds — most of the remaining gap is the ngrok free-tier tunnel's own latency, which is the next lever if it needs to come down further (a paid ngrok tier or hosting the audio directly on the app's own domain instead of a tunnel).

---



Fix the existing Outreach application so that clicking **Start Calling** from the UI actually starts the existing real outbound calling workflow.

The application already has a working backend calling pipeline when invoked correctly:

Excel → Flask API → campaign → background call runner → message template → Kokoro TTS → Twilio Voice → real outbound call → Twilio status → database → React UI.

The problem currently is:

> Clicking **Start Calling** from the UI does not place the call.

Do not assume the problem is in Twilio. Trace the complete request chain and identify the actual failure.

Also redesign the product branding with a new **OUTREACH** logo based on:
- Letter O
- Letter R
- Phone/telephone/communication symbol
- Professional B2B SaaS appearance
- Clean and recognizable at small sizes
- Suitable for login, sidebar, favicon, browser tab, landing page and dashboard

---

# 1. CRITICAL RULE

Do not replace the working Twilio/Kokoro calling implementation.

Do not create a fake calling implementation.

Do not simulate a successful call in the frontend.

The goal is to make:

```text
UI Start Calling
      ↓
Real API request
      ↓
Flask campaign start endpoint
      ↓
Campaign state changes
      ↓
Real call runner starts
      ↓
Patient is selected
      ↓
Calling-hours validation
      ↓
Phone validation
      ↓
Message template rendered
      ↓
Kokoro TTS
      ↓
Twilio Voice
      ↓
REAL outbound call
      ↓
Twilio status
      ↓
Database
      ↓
React UI
```

actually work.

---

# 2. FIRST: INSPECT THE EXISTING REPOSITORY

Before changing anything, inspect:

### Frontend

- Start Calling button component
- Campaign page
- Live Calling page
- API client
- fetch/request implementation
- authentication/session handling
- campaign state management
- error handling
- toast notifications

### Backend

- Flask route responsible for starting a campaign
- campaign_service.py
- call_runner.py
- twilio_client.py
- voice.py
- database access
- campaign tables
- campaign_contacts
- calls
- authentication/RBAC decorators
- logging

### Configuration

Inspect:

```text
.env
.env.example
Twilio configuration
PUBLIC_BASE_URL
TWILIO_MODE
Kokoro configuration
database configuration
```

Never expose or print secret values.

---

# 3. TRACE THE START CALLING REQUEST

Find the exact frontend handler.

For example:

```javascript
startCampaign(campaignId)
```

or equivalent.

Verify:

1. Button click fires.
2. Correct campaign ID is available.
3. API client sends the request.
4. HTTP method is correct.
5. URL is correct.
6. Authentication/session is included.
7. CSRF requirements, if present, are satisfied.
8. Backend route receives the request.
9. Backend returns a meaningful response.
10. Frontend handles success/error correctly.

Add temporary diagnostic logging where necessary.

Do not leave sensitive information in logs.

---

# 4. VERIFY THE API CONTRACT

Compare the frontend request with the actual Flask route.

Example:

Frontend:

```text
POST /api/campaigns/123/start
```

Backend must actually expose the expected route.

Check:

- URL
- HTTP method
- request body
- campaign ID
- authentication
- required permissions
- response format

If the backend expects:

```json
{
  "campaign_id": 123
}
```

but the frontend sends nothing or sends a different structure, fix the mismatch.

Do not create duplicate endpoints unnecessarily.

---

# 5. VERIFY AUTHENTICATION AND RBAC

The Start Calling action must be allowed only to roles with the correct permission.

Inspect the existing permission system.

Do not bypass:

```text
@require_permission(...)
```

or equivalent security controls merely to make the button work.

If the current user lacks permission, the UI should show a clear message:

```text
You do not have permission to start this campaign.
```

Do not silently fail.

---

# 6. VERIFY CAMPAIGN STATE

When Start Calling is clicked, verify the campaign is in a valid state.

For example:

```text
DRAFT
  ↓
READY
  ↓
START
  ↓
RUNNING
```

Do not allow:

```text
COMPLETED → START
STOPPED → START
RUNNING → START
```

unless the existing product explicitly supports those transitions.

Prevent duplicate runners.

The backend must protect against multiple simultaneous Start requests.

---

# 7. VERIFY CAMPAIGN CONTACTS

Before starting the runner, confirm that the campaign actually contains callable contacts.

Check:

```text
campaign_contacts
```

and verify:

- contacts exist
- contacts belong to the correct organization
- contacts have valid phone numbers
- contacts are in a callable state
- campaign is not empty

If zero contacts exist, return a useful error:

```text
This campaign has no callable patients.
```

The UI should display that message.

---

# 8. VERIFY CALL RUNNER STARTUP

Inspect:

```text
services/call_runner.py
```

Confirm that the Flask Start endpoint actually starts the runner.

Current architecture uses Python threading.

Verify:

```text
Start Campaign
    ↓
thread created
    ↓
thread starts
    ↓
call runner executes
```

Do not silently swallow thread exceptions.

Add structured logging around:

```text
campaign start
runner start
patient selected
TTS generation
Twilio request
call SID
call result
runner completion
```

Do not log:

- passwords
- Twilio Auth Token
- database passwords
- full sensitive patient information

---

# 9. VERIFY DATABASE TRANSACTION

Check whether the Start endpoint changes campaign status correctly.

Example:

```text
Before:
READY

After:
RUNNING
```

Verify that the transaction is committed.

A common failure could be:

```text
UPDATE campaigns
SET status = 'RUNNING'
...
```

without a commit.

Confirm the actual database state after clicking Start.

---

# 10. VERIFY KOKORO TTS

The runner should render the final message using actual patient data.

Example template:

```text
Hello {{patient_name}}.

This is an automated call from {{hospital}}.

We are contacting you regarding your outstanding
balance of ${{balance}}.

Thank you.
```

For:

```text
Patient: Kapil
Hospital: Apollo Hospitals
Balance: $500
```

the final text should become the correct patient-specific message.

Then:

```text
Final text
   ↓
Kokoro
   ↓
WAV
```

Verify the WAV is actually generated.

Do not generate a fake audio path.

---

# 11. VERIFY PUBLIC AUDIO URL

If Twilio uses:

```xml
<Play>PUBLIC_AUDIO_URL</Play>
```

verify:

```text
PUBLIC_BASE_URL
```

is configured correctly.

The Twilio server must be able to access the audio file over the public internet.

During local development, an ngrok tunnel may be used.

Example flow:

```text
Kokoro WAV
    ↓
Public URL
    ↓
Twilio
    ↓
<Play>
```

If the audio URL is invalid:

- log the error
- show a meaningful backend error
- do not silently fall back unless the existing application intentionally supports fallback

Preserve the existing Twilio `<Say>` fallback if it is already implemented.

---

# 12. VERIFY TWILIO CONFIGURATION

Inspect:

```text
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER
TWILIO_MODE
PUBLIC_BASE_URL
```

Do not print secret values.

Confirm:

```text
TWILIO_MODE=live
```

when performing an authorized real-call test.

Make sure the selected Twilio From number is valid and capable of outbound voice calls.

Do not hard-code credentials.

---

# 13. VERIFY TWILIO CALL CREATION

Inspect:

```text
client.calls.create(...)
```

Confirm:

- `to` is correct
- `from_` is correct
- TwiML is valid
- public audio URL is reachable
- Twilio client is initialized correctly

Capture the returned:

```text
Call SID
```

and save it to the database.

Example:

```text
CAxxxxxxxxxxxxxxxx
```

Do not expose the full SID unnecessarily in normal UI logs.

---

# 14. VERIFY CALL STATUS

After Twilio creates the call, verify the existing status handling.

Expected flow:

```text
QUEUED
   ↓
CALLING/RINGING
   ↓
ANSWERED
   ↓
COMPLETED
```

or:

```text
QUEUED
   ↓
RINGING
   ↓
NO ANSWER
```

or:

```text
QUEUED
   ↓
RINGING
   ↓
BUSY
```

or:

```text
QUEUED
   ↓
FAILED
```

Use actual Twilio results.

Do not fake these transitions in React.

---

# 15. VERIFY WEBHOOK

Inspect the Twilio status webhook.

Verify:

- public webhook URL
- HTTP method
- Twilio signature validation
- route exists
- webhook can reach Flask
- status is persisted
- duration is persisted
- call SID is matched correctly

Do not disable signature validation just for convenience.

---

# 16. VERIFY FRONTEND LIVE STATUS

After the call starts, the React UI must update.

Example:

```text
John Wick       Queued
John Wick       Ringing
John Wick       Answered
John Wick       Completed     01:42
```

The UI must use real API/database data.

Do not use:

```javascript
setTimeout(...)
```

to fake the lifecycle.

---

# 17. Error Handling

The current problem may be caused by an error that is being swallowed.

Every failure should produce:

### Backend log

Example:

```text
Campaign 123 start requested
Campaign 123 runner started
Campaign 123 contact 45 selected
Kokoro audio generated
Twilio call creation failed: ...
```

### Frontend message

Example:

```text
Unable to start campaign.

Reason:
No callable patients found.
```

or:

```text
Unable to place call.

Please check Twilio configuration.
```

Do not expose secrets or internal stack traces to the client.

---

# 18. Manual End-to-End Test

After fixing the issue, use the existing mock Excel data.

Example:

```text
Patient Name | Phone Number   | Balance | Hospital
Test Patient | +91XXXXXXXXXX  | 500     | Apollo Hospitals
Test Patient | +91XXXXXXXXXX  | 700     | KIMS Hospitals
```

Use only authorized numbers for real testing.

Then:

1. Login.
2. Upload Excel.
3. Validate.
4. Confirm import.
5. Verify patients appear.
6. Create campaign.
7. Select voice.
8. Enter message template.
9. Preview message/audio.
10. Confirm campaign.
11. Click Start Calling.
12. Verify campaign becomes RUNNING.
13. Verify first contact becomes QUEUED.
14. Verify Twilio call is actually created.
15. Verify the phone rings.
16. Answer the authorized test call.
17. Verify UI shows Answered.
18. Verify final duration.
19. Verify database call record.
20. Verify next contact starts according to calling rules.
21. Verify retry behavior for applicable outcomes.

---

# 19. New OUTREACH Logo

Redesign the logo.

Brand name:

# OUTREACH

The visual identity should combine:

- Letter O
- Letter R
- Telephone/phone/communication symbol

Concept direction:

```text
    ______
   /        |  OR    )  ← phone/communication gesture
   \______/
```

This is only conceptual. Create a polished professional logo rather than literally copying this sketch.

The logo should communicate:

- communication
- outbound calling
- connection
- professionalism
- SaaS/technology
- reliability

Avoid:
- cartoon-style phone icons
- overly complex illustrations
- generic stock icons
- excessive gradients
- cluttered symbols
- misleading AI imagery

---

# 20. Logo Variants

Create/use a consistent logo system:

### Full logo

```text
[ O/R PHONE MARK ] OUTREACH
```

### Compact logo

```text
[ O/R PHONE MARK ]
```

### Text-only fallback

```text
OUTREACH
```

Use the compact mark for:

- Favicon
- Sidebar collapsed mode
- Browser tab
- Mobile navigation

Use the full logo for:

- Login
- Landing page
- Dashboard sidebar expanded
- Marketing materials

If the repository already contains a logo asset, inspect it before replacing it.

Do not overwrite official company assets without confirmation.

If no official asset exists, create an SVG logo locally.

---

# 21. Logo Technical Requirements

Prefer SVG for the logo.

Create an accessible logo component, for example:

```text
OutreachLogo.tsx
```

or use the project's existing component system.

Support:

```text
size
variant
className
```

Possible variants:

```text
full
mark
text
```

The logo should render crisply at:

- 16px
- 24px
- 32px
- 48px
- 64px
- large landing-page sizes

Do not use a raster image when SVG is practical.

---

# 22. Apply Branding Everywhere

Update:

- Login page
- Sidebar
- Dashboard
- Browser title
- Favicon
- Loading state
- Error pages
- Landing page if present
- Request Demo page if present

Browser title:

```text
Outreach
```

or a suitable product title such as:

```text
Outreach — Automated Outbound Calling
```

---

# 23. Visual UI Improvements

While fixing Start Calling, correct obvious UI problems.

Ensure:

- buttons have proper hover/disabled states
- loading indicators appear during API requests
- toast messages are useful
- tables do not overflow unexpectedly
- cards align consistently
- sidebar works correctly
- responsive layout works
- logo has correct spacing
- status badges are consistent
- live calling page is visually clear
- current call is prominent
- errors are understandable

Do not redesign unrelated features unless needed for consistency.

---

# 24. No Unnecessary Technology Changes

Do not:
- replace Flask
- replace React
- replace Twilio
- replace Kokoro
- introduce LLM/AI
- introduce LangChain
- introduce LangGraph
- rewrite the whole frontend
- replace the existing database solely for this task

This phase is about fixing the real call trigger and improving the UI/branding.

---

# 25. Acceptance Criteria

The task is complete only when:

### Calling

- Start Calling button triggers the correct API.
- Backend receives the request.
- Campaign transitions correctly.
- Runner actually starts.
- Patient is selected.
- Kokoro audio is generated.
- Twilio call is created.
- Real authorized test phone rings.
- Audio plays correctly.
- Twilio status is persisted.
- UI shows live status.
- Final duration appears.
- Retry behavior still works.
- Pause/resume/stop still works.
- Duplicate starts are prevented.

### UI

- No major UI glitches remain.
- Start Calling shows proper loading state.
- API errors are displayed clearly.
- Live call information is visible.
- Campaign progress updates.
- OUTREACH branding is consistent.
- New O/R/phone logo is used.
- Favicon/browser title are updated.
- Responsive layout remains functional.

### Security

- No credentials are exposed.
- Existing RBAC remains enforced.
- Existing Twilio webhook signature validation remains enabled.
- No fake status logic is introduced.

---

# 26. Final Developer Instruction

Before modifying code:

1. Inspect the complete repository.
2. Reproduce the Start Calling failure.
3. Identify exactly where the request/call chain breaks.
4. Show the root cause.
5. Implement the smallest reliable fix.
6. Test the full real call flow.
7. Implement the new Outreach logo.
8. Apply the logo consistently.
9. Run the existing test suite.
10. Run an authorized end-to-end calling test.
11. Report:
   - Root cause
   - Files changed
   - Fix implemented
   - How the call was verified
   - UI changes
   - Logo files/components created
   - Tests performed
   - Any remaining limitations

Do not declare the feature fixed merely because the API returns HTTP 200.

The final verification must confirm that the Twilio call was actually created and the authorized test phone received the call.

## End of Phase 3 Specification
