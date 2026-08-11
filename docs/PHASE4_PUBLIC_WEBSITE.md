# Outreach — Phase 4: Public Marketing Website (Implementation Summary)

Work performed: 2026-08-10. Status: **MVP scope shipped and verified end-to-end** (real form submission → database → internal admin dashboard, confirmed via the actual running app, not assumed from a clean HTTP response). Scope was explicitly agreed with the user before implementation (see "Scope decisions" below) rather than attempting the full spec in one pass. The original spec follows this summary, preserved as-is for reference.

## Scope decisions

The pasted spec (`OUTREACH_PUBLIC_MARKETING_WEBSITE.md`, preserved below) covers ~15 routes, a full lead CRM, email notifications, CAPTCHA, and more — too much to land safely in one pass. Two decisions were confirmed with the user up front:

1. **MVP-first scope**: Home (Platform/Solutions/Features/Industries folded in as in-page sections rather than separate routes), dedicated `/how-it-works`, `/security`, `/request-demo`, and placeholder `/privacy`/`/terms` pages, the demo-request backend + database table, and a basic admin lead list with status updates. `sitemap.xml`/`robots.txt` included. No CAPTCHA (honeypot + rate-limit only), no email notifications, no blog/case-studies/docs (nothing real to put in them).
2. **Fully separate app**: a new `website/` folder at the repo root, independent from `webapp/`, rather than mounting under the existing Flask catch-all. `webapp/app.py`'s `/` route already serves the internal dashboard's SPA, and a repo-wide search turned up **no existing production deployment config** (no Docker, no nginx, no CI/CD — `webapp/README.md`'s own "Quick start" is dev-only `python app.py` on `127.0.0.1:5000`). Keeping the marketing site independent means zero risk to the working dashboard; in production it's meant to sit on the real root domain later, with the dashboard moved to a subdomain — a deploy-time decision, not something hardcoded into this work.

Every feature claim on the site was checked against the real product before being written: voice count comes from `webapp/services/voice_catalog.py` (27 voices — 11 US female, 8 US male, 4 UK female, 4 UK male; not 26 as initially estimated in conversation, corrected here), call outcomes from `call_runner.py`, retry/calling-hours behavior from the same, roles from `webapp/services/rbac.py` (5 roles), and the calling pipeline from `voice.py`/`services/twilio_client.py`. No "AI agent" language, no HIPAA/compliance claims, no fake logos or testimonials.

## New project: `website/`

Independent Vite + React 19 + TypeScript project, mirroring `webapp/frontend`'s tooling exactly (`tsconfig.*.json`, `.oxlintrc.json`, `.gitignore`) so it's a familiar shape to maintain, but with its own `package.json` and dev server on **port 5174** (`/api` proxied to `http://127.0.0.1:5000`, same pattern as `webapp/frontend/vite.config.ts`).

### Structure

- **`src/components/BrandMark.tsx`** — the Connection Ring mark recreated standalone (same geometry/props as `webapp/frontend/src/components/BrandMark.tsx`), since the two projects don't share code.
- **`src/components/Nav.tsx`, `Footer.tsx`, `Layout.tsx`** — sticky nav with in-page anchors (`/#platform`, `/#solutions`, `/#features`, `/#industries`) plus real routes (`/how-it-works`, `/security`), mobile hamburger menu; multi-column dark footer.
- **`src/components/Reveal.tsx`** — scroll-reveal wrapper (IntersectionObserver-driven fade/slide-in), used throughout for the "premium SaaS" feel the spec asked for.
- **`src/components/Icons.tsx`** — a dozen small hand-authored line icons for feature/security cards (no icon library dependency).
- **`src/content/facts.ts`, `countries.ts`** — the single source of truth for real numbers used in copy (voice count, role count, call outcomes) and the curated country/dial-code list, industry list, company-size and call-volume options used on the demo form.
- **`src/styles/tokens.css`, `marketing.css`** — a marketing-specific design system (navy `#0b1220` / teal `#14b8a6`, matching the existing brand; DM Sans display + IBM Plex Sans body, the same pairing `webapp/frontend` already uses) — deliberately more editorial than the internal dashboard's utilitarian tokens (pill buttons, generous section padding, alternating light/dark sections) since this is a landing page, not an admin tool.
- **Pages** (`src/pages/`): `HomePage.tsx` (composes `src/components/home/*`: `Hero`, `TrustStrip`, `ProductOverview`, `Features`, `HowItWorksFlow`, `HealthcareSection`, `IndustriesSection`, `SecuritySummary`, `FinalCta`), `HowItWorksPage.tsx`, `SecurityPage.tsx`, `RequestDemoPage.tsx`, `PrivacyPage.tsx`, `TermsPage.tsx`, `NotFoundPage.tsx`.
- **`public/favicon.svg`** — same mark as the internal app's, on the same navy background. **`public/robots.txt`**, **`public/sitemap.xml`** — the sitemap uses a placeholder domain (`outreach.example.com`) since no real production domain exists yet; called out in `website/README.md` as something to replace before deploying.
- **`src/api/client.ts`** — a single `api.submitDemoRequest(payload)` calling `POST /api/demo-requests` on the existing Flask backend.

### Request Demo form

All fields from the spec's section 19 (identity, company, optional address, business requirements, consent), a lightweight country + dial-code selector (curated ~20-country list, not a new i18n/phone-number library dependency — flagged in `website/README.md` as a lighter-weight version of the spec's "international phone input"), inline per-field validation that doesn't clear the whole form on one error, a hidden honeypot field, and loading/success/error states.

## Backend (existing `webapp/` Flask app — reused, not a new stack)

- **`webapp/migrations/002_demo_requests.sql`** — new `demo_requests` table. Deliberately **not** scoped to `organization_id` — leads are prospective customers, not tenant data. Includes `GRANT SELECT, INSERT, UPDATE, DELETE ON demo_requests TO outreach_app` (see bug #3 below for why this line exists).
- **`webapp/db.py`** — added `count_recent_demo_requests`, `create_demo_request`, `get_demo_requests`, `get_demo_request`, `update_demo_request`, following the exact patterns already used for contacts/audit logs (`get_conn()`, `row_to_dict`/`rows_to_list`, parameterized queries).
- **`webapp/services/demo_request_service.py`** (new) — `submit()` validates required fields, email shape, phone shape, and consent; checks the honeypot field; rate-limits by IP (reusing the same "count recent rows in a time window" pattern as `app.py`'s existing login-failure rate limit — 5 submissions per IP per 60 minutes — no new dependency like `flask-limiter` needed). `list_requests()`/`update_status()` back the admin view.
- **`webapp/app.py`** — three new routes:
  - `POST /api/demo-requests` — **public, no session required** (the first unauthenticated write route in this app).
  - `GET /api/demo-requests` and `PUT /api/demo-requests/<id>` — gated by a new `manage_leads` permission, writes an audit log entry (`demo_request_status_update`) on status change.
- **`webapp/services/rbac.py`** — added `manage_leads` to `SUPER_ADMIN`/`ADMIN` in the `PERMISSIONS` dict.

## Internal dashboard admin UI (existing `webapp/frontend/`)

- **`src/pages/admin/DemoRequestsPage.tsx`** (new) — table of leads with a status filter and a per-row status dropdown, following `AuditLogsPage.tsx`'s exact structure (`LoadingState`/`ErrorState`/`EmptyState`/`Pagination`).
- **`src/api/client.ts`** — added `api.admin.demoRequests(...)` and `api.admin.updateDemoRequest(...)`.
- **`src/types.ts`** — added the `DemoRequest` type.
- **`src/App.tsx`** — new `admin/demo-requests` route, gated by the existing `<AdminOnly>` wrapper.
- **`src/components/Sidebar.tsx`** — added "Demo Requests" to the Administration nav section.

## Bugs found and fixed during verification

Per the standing rule in this project (never declare something fixed just because it returned 200 / rendered once) — three real bugs were found by actually running the site and screenshotting it, not assumed away:

1. **Scroll-reveal content was permanently invisible in some cases.** `Reveal.tsx`'s `IntersectionObserver` only flips content to visible once it scrolls into view — but a first full-page screenshot showed most of the Home page as blank white space below the hero. Root cause: content gated entirely behind JS/observer timing with no fallback means anything that doesn't get observed in time (a fast page load, a crawler, a print/PDF capture, this exact screenshot tool) stays invisible forever, not just unanimated. **Fix**: `Reveal.tsx` now also sets a 1-second fallback `setTimeout` that forces visibility regardless of the observer, so content is never permanently gated behind JS timing.
2. **Heading text was unreadable on every dark section** (`.hero`, `.demo-hero`, `.final-cta`) — a global `h1, h2, h3, h4 { color: var(--ink) }` rule (dark navy) overrode the light color those sections need, because a heading's own `color` always wins over an inherited one from its container. `.section-on-dark` already had an explicit override for this; `.hero`/`.demo-hero`/`.final-cta` didn't. **Fix**: `marketing.css` now applies the same light-heading override to all four dark-background container classes.
3. **Real form submission failed with `permission denied for table demo_requests`.** The migration was applied by connecting as the `postgres` superuser, but the Flask app connects as a separate, restricted role (`outreach_app`, per `webapp/.env`'s `DATABASE_USER`) that has no implicit access to a table it didn't create. **Fix**: added explicit `GRANT` statements to the migration file and applied them live to both `outreach` and `outreach_test` databases.

## Follow-up: vendor names removed from site copy

Follow-up request: "Twilio Voice" and "Kokoro TTS" are both open-source/third-party names and shouldn't appear on the public site — replace with generic language, and make clear Outreach provides the calling line/number itself (not something the customer has to bring or set up).

- **`website/src/components/home/Hero.tsx`** — hero meta row: "Kokoro TTS voice generation" → "Advanced TTS voice generation"; "Twilio Voice calling infrastructure" → "Calling line included — no separate setup".
- **`website/src/components/home/Features.tsx`** — "Automated Outbound Calling" card body now reads "...through our managed calling infrastructure — we provide the line, so there's no manual dialing and nothing extra to set up." "27 Configured Voices" card body: "Kokoro TTS voices" → "advanced TTS voices".
- **`website/src/pages/HowItWorksPage.tsx`** — pipeline strip: "Kokoro TTS" → "Advanced TTS", "Twilio Voice" → "Calling line". Step 04 ("Launch") body and the "Voice technology" dark-section copy both reworded to "our managed calling line" / "our advanced TTS engine", explicitly stating Outreach provides the number.

No other files referenced either name (confirmed via a full-project grep after the edit). Rebuilt (`npm run build`, clean) and re-screenshotted the Home hero and How It Works page to confirm the new copy renders correctly.

## Verified

- `cd website && npm install && npm run build` — clean, no TypeScript errors.
- `cd webapp/frontend && npm run build` — clean after adding `DemoRequestsPage.tsx`.
- Ran the real Vite dev server (`website/`, port 5174) alongside the real Flask server (port 5000) and screenshotted every page (Home, How It Works, Security, Request Demo, Privacy, 404) at desktop and mobile widths via headless Chromium — caught bugs #1 and #2 above this way.
- Submitted a **real** demo request through the actual running form (not a mocked API call) — hit bug #3, fixed it, resubmitted, confirmed the "Thank you" success state.
- Logged into the internal dashboard as the real `demo` user and confirmed the submitted lead appears correctly on the new **Demo Requests** admin page; changed its status from `NEW` → `CONTACTED` through the real UI and confirmed the toast, the updated dropdown, and a real `demo_request_status_update` audit log row.
- Deleted the test lead and its audit log entry afterward — no fabricated data left in the database.
- `python -m unittest discover -s tests` (in `webapp/`) → 17/17 passing after every backend change.
- Confirmed `localhost:5000/` (the internal dashboard) is untouched — `webapp/app.py`'s catch-all route was not modified.

## Not built this pass (deferred, not silently skipped)

Dedicated `/platform`, `/solutions/*`, `/features`, `/industries`, `/about`, `/contact` routes (currently sections on Home); email notifications on new leads (spec: only wire this if an approved provider exists — none does); CAPTCHA (honeypot + IP rate-limit only); a blog/case-studies/docs resource center (nothing real to put in them yet); full carrier-grade international phone validation (a curated country/dial-code list is used instead of a new library dependency).

---

# OUTREACH — Public Marketing Website & Request Demo Development Specification

## Objective

Build a premium, dynamic, production-quality public marketing website for **OUTREACH**, the company's automated outbound voice calling platform.

The website should have the polish and product storytelling quality of leading global communication SaaS companies, including Twilio, but must have its **own original design, copy, layout, animations, illustrations, and branding**. Do not copy Twilio's exact design, text, source code, or proprietary branding.

The site should be suitable for:
- US healthcare organizations
- RCM companies
- Hospitals
- Medical billing companies
- Enterprise customers
- Investors
- Business partners
- Prospective clients

It must feel like a serious commercial B2B SaaS product, not a basic student landing page.

---

## 1. Product Positioning

OUTREACH is an automated outbound voice communication platform.

Current workflow:

```text
Excel/CSV upload
      ↓
Contact validation
      ↓
Campaign
      ↓
Custom script + patient variables
      ↓
Voice selection
      ↓
Kokoro TTS
      ↓
Twilio Voice
      ↓
Real outbound call
      ↓
Call status + duration
      ↓
Dashboard analytics
```

Current/product capabilities may include:
- Excel/CSV contact import
- Validation and duplicate detection
- Campaign management
- Custom scripts
- Dynamic variables such as `{{name}}`, `{{balance}}`, `{{hospital}}`
- Multiple configured voices
- Kokoro TTS
- Twilio Voice
- Real outbound calls
- Calling schedules
- Retry rules
- Live call status
- Call duration
- Call history
- Campaign analytics
- Role-based access
- Audit logs
- Multi-tenant architecture

Do not claim a feature is available unless it actually exists. If a feature is planned, label it **Coming Soon**.

---

# 2. Main Website Goal

Within the first few seconds, visitors should understand:

1. What Outreach is
2. Who it is for
3. What it does
4. How it works
5. Why it is useful
6. How it connects to calling infrastructure
7. How to request a demo

Primary CTA:

```text
Request a Demo
```

Secondary CTA:

```text
Explore the Platform
```

---

# 3. Recommended Technology

Preferred stack:

- Next.js
- React
- TypeScript
- Tailwind CSS
- Framer Motion
- SVG
- Responsive design

If the existing public frontend already uses React + Vite, continue with it rather than migrating unnecessarily.

Do not introduce a framework migration just for the marketing website.

---

# 4. Website Pages

Recommended structure:

```text
/
├── Home
├── Platform
├── Solutions
├── How It Works
├── Features
├── Industries
├── Security
├── About
├── Contact
├── Request Demo
├── Privacy Policy
├── Terms
```

Create only pages that have useful content. Unapproved legal/company information should use placeholders rather than invented claims.

---

# 5. Navigation

Desktop navigation:

```text
OUTREACH

Platform
Solutions
How It Works
Features
Industries
Security

[ Request a Demo ]
```

Possible dropdowns:

### Platform
- Automated Calling
- Campaigns
- Voice
- Call Management
- Analytics

### Solutions
- Healthcare
- Revenue Cycle Management
- Enterprise Communication

### Resources
- Documentation
- FAQ
- Case Studies
- Blog

Only link to pages that actually exist.

---

# 6. Hero Section

Create a high-impact hero.

Suggested copy direction:

```text
AUTOMATE EVERY OUTBOUND CALL

Powerful outbound calling
for modern organizations.

Create personalized voice campaigns,
reach contacts at scale, and track every
call from one powerful platform.

[ Request a Demo ]    [ Explore Platform ]
```

Do not overuse generic "AI" language. The current product is an automated outbound voice platform, not a conversational AI agent.

---

# 7. Hero Product Animation

Create an interactive product visualization instead of a generic stock image.

Example:

```text
             OUTREACH

      Automated Calling Platform

┌────────────────────────────────────┐
│ Campaign: Balance Reminder          │
│                                      │
│ ● RINGING                           │
│                                      │
│ John Wick                            │
│ +1 XXX XXX XXXX                      │
│                                      │
│ Voice: Professional 04              │
│ Duration: 01:24                     │
└────────────────────────────────────┘
```

Animate:
- Campaign progress
- Status changes
- Dashboard cards
- Connection lines
- Call activity
- Metrics

These are visual demonstrations only. Do not pretend to make real calls from the public site.

---

# 8. Trust / Audience Section

If approved customer logos exist, show them.

If not, do not invent customer logos.

Instead use:

```text
BUILT FOR MODERN COMMUNICATION TEAMS

Healthcare
RCM
Enterprise Operations
Customer Communication
Financial Services
```

Never use fake testimonials or fake customer statistics.

---

# 9. Product Overview

Create a strong section:

```text
ONE PLATFORM.
EVERY OUTBOUND CALL.

From contact upload to final call analytics,
Outreach gives teams one place to manage
their outbound communication workflow.
```

Show a polished dashboard mockup containing:

```text
Dashboard
Patients
Campaigns
Live Calling
Calls
Voices
Reports
Settings
```

Clearly label sample dashboard data as demo/sample data.

---

# 10. Feature Showcase

Create animated feature cards for:

### Automated Outbound Calling
Launch outbound campaigns through configured voice infrastructure.

### Personalized Scripts
Use variables:

```text
{{name}}
{{balance}}
{{hospital}}
```

Example:

```text
Hello {{name}}, this is an automated call
from ZEBL.

Our records show an outstanding balance of
{{balance}} for services received at {{hospital}}.

Thank you for taking the call.
```

### Multiple Voices
Select from configured voice options.

### Campaign Management
Create, start, pause, resume and stop campaigns.

### Live Call Monitoring
Track:

```text
Queued
Calling
Ringing
Answered
No Answer
Busy
Rejected
Failed
Completed
```

### Call Analytics
Show available metrics such as:
- Total calls
- Answer rate
- No-answer rate
- Busy rate
- Failed calls
- Average duration
- Campaign completion

### Excel / CSV Import
Upload and validate contact lists.

### Retry Rules
Configure retries for eligible outcomes.

### Calling Hours
Control when calls are allowed.

### Role-Based Access
Control user permissions.

### Auditability
Track important administrative and campaign activity.

---

# 11. How It Works

Create a large animated five-step flow:

```text
01  UPLOAD
Import your contacts.

      ↓

02  PERSONALIZE
Create your script and variables.

      ↓

03  CONFIGURE
Choose voice, calling rules and retries.

      ↓

04  LAUNCH
Start your outbound campaign.

      ↓

05  ANALYZE
Track status, duration and outcomes.
```

Animate each step as the user scrolls.

---

# 12. Interactive Product Demo

Create a safe browser-only demonstration:

```text
Campaign Preview

Patient
[ John Wick ]

Balance
[ $245 ]

Hospital
[ Demo Hospital ]

Voice
[ Voice 04 ]

Message
Hello John Wick...
```

Buttons:

```text
[ Preview Experience ]
```

This public demo must **never place real calls**.

---

# 13. Voice Technology Section

Explain the actual voice pipeline:

```text
YOUR MESSAGE.
OUR VOICE PIPELINE.

Message Template
      ↓
Patient Data
      ↓
Personalized Text
      ↓
Kokoro TTS
      ↓
Audio
      ↓
Twilio Voice
      ↓
Recipient
```

Avoid unsupported claims such as "indistinguishable from a human."

---

# 14. Communication Infrastructure Section

Explain that Outreach integrates with voice communication infrastructure such as Twilio where applicable.

Do not imply that Outreach is owned, operated, or endorsed by Twilio.

Use wording such as:

```text
POWERED BY PROVEN COMMUNICATION INFRASTRUCTURE

Connect your campaign workflow to reliable
voice communication infrastructure for outbound calling.
```

Only use third-party logos according to applicable brand guidelines and authorization.

---

# 15. Healthcare / RCM Section

Create a prominent section:

```text
BUILT FOR HIGH-VOLUME HEALTHCARE COMMUNICATION
```

Use cases:
- Balance reminders
- Payment notifications
- Appointment reminders
- Insurance follow-ups
- Patient outreach
- RCM workflows
- Administrative notifications

Do not claim HIPAA compliance unless formally verified and approved.

Use safer wording:

```text
Designed with security, access control and auditability in mind.
```

---

# 16. Industry Sections

Create polished cards:

### Healthcare
Automate routine patient communications.

### Revenue Cycle Management
Support high-volume billing and balance-notification workflows.

### Enterprise Operations
Scale repetitive outbound communication.

### Financial Services
Support approved customer notification workflows.

Avoid unsupported regulatory claims.

---

# 17. Security Section

Create a professional security page/section covering:

- Authentication
- Role-based access
- Password hashing
- Audit logs
- Access controls
- Encrypted connections
- Secrets management
- Database security
- Webhook validation
- Data retention

Do not claim certifications that have not been verified.

---

# 18. Architecture Visualization

Create an attractive technical diagram:

```text
                 OUTREACH PLATFORM

                     React UI
                        │
                        ▼
                    Flask API
                        │
          ┌─────────────┼─────────────┐
          │             │             │
          ▼             ▼             ▼
      PostgreSQL      Kokoro        Twilio
          │             │             │
          │             ▼             ▼
          │           Audio         Calls
          │
          ▼
       Analytics
```

Keep infrastructure details high-level.

---

# 19. Request Demo — Major Feature

Build a dedicated `/request-demo` page and a reusable demo-request modal.

Every major CTA should lead to it.

## Required fields

```text
First Name *
Last Name *
Work Email *
Company Name *
Job Title
Country *
Phone Number *
Company Website
Industry *
Company Size
```

## Address

```text
Address Line 1
Address Line 2
City
State / Province
Postal / ZIP Code
Country
```

## Business requirements

```text
What are you looking to automate?
Expected monthly call volume
Current communication process
Preferred demo date
Preferred demo time
Timezone
```

## Message

```text
Tell us about your requirements
```

## Consent

```text
[ ] I agree to be contacted regarding my demo request
and understand that my information will be handled
according to the Privacy Policy.
```

CTA:

```text
[ Request a Demo ]
```

Success:

```text
Thank you.

Your demo request has been received.
Our team will contact you shortly.
```

Do not promise a response time unless approved.

---

# 20. Demo Form UX

The form must feel premium.

Use:
- Multi-column layout on desktop
- Single-column layout on mobile
- Floating/focused labels or clear labels
- Inline validation
- Loading state
- Success state
- Error state
- Accessible focus states
- Helpful placeholder examples
- Country selector
- International phone input

Do not clear the whole form because of one validation error.

---

# 21. Phone Number

Use an international phone-number component.

Requirements:
- Country selector
- Country calling code
- Formatting
- Validation
- E.164-compatible backend storage

Do not assume all customers are from the United States.

---

# 22. Country Selector

Use a searchable country dropdown.

Store a stable country code where possible.

Example:

```text
United States → US
India → IN
United Kingdom → GB
Canada → CA
Australia → AU
Germany → DE
```

---

# 23. Demo Request Backend

Do not submit the form only to browser console/local state.

Create a secure endpoint such as:

```text
POST /api/demo-requests
```

Possible request data:

```json
{
  "first_name": "...",
  "last_name": "...",
  "email": "...",
  "company_name": "...",
  "job_title": "...",
  "country": "...",
  "phone": "...",
  "website": "...",
  "industry": "...",
  "company_size": "...",
  "address": {
    "line1": "...",
    "line2": "...",
    "city": "...",
    "state": "...",
    "postal_code": "...",
    "country": "..."
  },
  "automation_need": "...",
  "monthly_call_volume": "...",
  "current_process": "...",
  "preferred_demo_date": "...",
  "preferred_demo_time": "...",
  "timezone": "...",
  "message": "...",
  "consent": true
}
```

Use the existing backend architecture rather than creating an unrelated API stack.

---

# 24. Demo Request Database

If demo requests are stored in PostgreSQL, create a dedicated table:

```text
demo_requests
```

Possible columns:

```text
id
first_name
last_name
email
company_name
job_title
country
phone
website
industry
company_size
address_line1
address_line2
city
state
postal_code
automation_need
monthly_call_volume
current_process
preferred_demo_date
preferred_demo_time
timezone
message
consent
status
created_at
updated_at
```

Suggested statuses:

```text
NEW
CONTACTED
QUALIFIED
DEMO_SCHEDULED
CLOSED
```

Never expose demo-request records publicly.

---

# 25. Admin Lead Management

If the internal dashboard supports administration, add:

```text
Demo Requests
```

Show:
- Name
- Company
- Email
- Phone
- Country
- Industry
- Estimated call volume
- Status
- Created date
- Notes
- Contacted date

Allow authorized admins to update status.

Audit sensitive changes.

---

# 26. Email Notification

If company email infrastructure exists, a new demo request may trigger an internal notification.

Use:

```env
DEMO_NOTIFICATION_EMAIL=
```

Do not hard-code an employee email address.

Do not send confirmation emails unless an approved email provider/template is configured.

---

# 27. SEO

Implement:

- Page titles
- Meta descriptions
- Open Graph
- Canonical URLs
- Sitemap
- Robots.txt
- Semantic HTML
- Correct heading hierarchy

Suggested homepage:

```text
Title:
Outreach — Automated Outbound Calling Platform

Description:
Automate personalized outbound voice campaigns,
track calls in real time, and manage communication
from one powerful platform.
```

Do not keyword-stuff.

---

# 28. Performance

Use:
- Optimized SVG
- Lazy-loaded images
- Responsive images
- Code splitting
- Efficient animations
- Font optimization
- Caching
- Minimal JavaScript where possible

Do not put huge video assets on the initial page unnecessarily.

---

# 29. Animation & Interaction

Use premium but restrained animation:

- Scroll reveals
- Dashboard card motion
- Number counters
- Hover effects
- Product UI transitions
- Architecture connection animations
- Subtle background motion
- CTA micro-interactions

Respect:

```text
prefers-reduced-motion
```

Animations should support the story rather than distract from it.

---

# 30. Outreach Brand Identity

Brand:

```text
OUTREACH
```

Tagline:

```text
Making Every Call Count.
```

Logo concept:

```text
O + R + phone / communication symbol
```

Use the same identity on:
- Public website
- Internal dashboard
- Login
- Favicon
- Email templates
- Demo forms

---

# 31. Design Direction

Create an original premium SaaS visual system:

- Strong typography
- Generous whitespace
- Modern rounded cards
- Fine borders
- Subtle gradients
- Professional dark/light sections
- Polished dashboard mockups
- Smooth transitions
- Clear hierarchy
- High-quality responsive design

Do not blindly reproduce Twilio's colors or layouts.

The site should clearly look like **OUTREACH**.

---

# 32. Footer

Create a professional multi-column footer:

```text
OUTREACH
Making Every Call Count.

Platform
  Automated Calling
  Campaigns
  Voice
  Analytics

Solutions
  Healthcare
  RCM
  Enterprise

Company
  About
  Contact
  Request a Demo

Resources
  Documentation
  Security
  FAQ

Legal
  Privacy Policy
  Terms

© Outreach
```

Do not invent legal/company information.

---

# 33. Contact Section

Include:

```text
Have questions?

Talk to our team about your outbound
communication workflow.

[ Request a Demo ]
```

Use approved company contact details if available.

Never invent company email, address, phone or registration information.

---

# 34. Accessibility

Support:
- Keyboard navigation
- Screen readers
- Visible focus states
- Semantic HTML
- Accessible labels
- Accessible form errors
- Adequate contrast
- Reduced motion
- Proper button/link semantics

---

# 35. Public Website Security

Implement:
- HTTPS in production
- Server-side validation
- Rate limiting on demo submission
- CAPTCHA/bot protection if necessary
- CSRF protection where applicable
- Input sanitization
- Parameterized database queries
- No secrets in frontend
- No internal API credentials in browser
- No detailed server errors
- Audit sensitive admin actions

The public website must not expose patient/contact/campaign APIs.

---

# 36. Demo Data

All public product dashboards and charts should use clearly labeled demo/sample data.

For example:

```text
Demo Campaign
1,248 Calls
82% Answered
01:36 Avg. Duration
```

Do not present sample numbers as real company results.

Do not invent customer testimonials.

---

# 37. Responsive Design

Support:
- Mobile
- Tablet
- Laptop
- Desktop
- Large desktop

On mobile:
- Navigation collapses cleanly
- Demo form becomes single-column
- Cards stack
- Tables scroll appropriately
- Hero remains readable
- CTA remains accessible

---

# 38. URL Structure

Recommended:

```text
/
/platform
/solutions
/solutions/healthcare
/solutions/rcm
/how-it-works
/features
/industries
/security
/about
/contact
/request-demo
/privacy
/terms
```

---

# 39. CTA Strategy

Primary:

```text
Request a Demo
```

Secondary:

```text
Explore Platform
```

Contextual:

```text
See How Outreach Works
```

Final CTA:

```text
Ready to automate your outbound communication?

[ Request a Demo ]
```

---

# 40. Compliance / Healthcare Messaging

Do not write unsupported claims such as:

```text
HIPAA Certified
HIPAA Compliant
100% Secure
100% Reliable
Zero Risk
Guaranteed Results
```

unless formally verified and approved.

Prefer:

```text
Designed with security, access control and auditability in mind.
```

Similarly, do not guarantee call connection, answer rates, or outcomes.

---

# 41. Production Architecture

Prefer keeping the public website isolated from internal application APIs.

Concept:

```text
Public Website
      ↓
Public Demo Request API
      ↓
PostgreSQL

Internal Outreach Dashboard
      ↓
Protected Flask API
      ↓
PostgreSQL
```

The marketing website must not expose:
- Patient data
- Contact data
- Campaign data
- Call history
- Twilio credentials
- Internal admin APIs

---

# 42. Final Acceptance Criteria

The website is complete when:

- It looks like a premium global B2B SaaS website.
- It has an original OUTREACH identity.
- O/R/phone logo is implemented.
- Homepage is dynamic and animated.
- Navigation works.
- Platform/features are clearly explained.
- Healthcare/RCM use cases are clearly explained.
- How It Works is visually clear.
- Product dashboard visualization is polished.
- Request Demo CTA appears throughout.
- Request Demo form includes name, company, country, phone, address, email and business requirements.
- International phone validation works.
- Country selector works.
- Form validation works.
- Consent works.
- Server-side validation works.
- Demo requests are stored securely.
- Spam/rate limiting is addressed.
- Success and error states work.
- Public site cannot access internal patient/campaign APIs.
- SEO metadata exists.
- Sitemap/robots exist.
- Mobile layout works.
- Accessibility is addressed.
- Reduced-motion support exists.
- Performance is acceptable.
- No fake customer claims exist.
- No unsupported compliance claims exist.
- No secrets are exposed.

---

# 43. Developer Instruction

Before writing the website:

1. Inspect the existing Outreach repository.
2. Inspect the existing React frontend.
3. Inspect existing branding assets.
4. Inspect existing API architecture.
5. Inspect the current database architecture.
6. Determine whether the public site belongs inside the existing frontend or should be a separate application.
7. Report the recommended architecture before implementation.
8. Do not break the internal Outreach dashboard.
9. Do not expose internal patient/contact/campaign APIs.

Then implement incrementally.

Priority:

```text
1. Brand identity
2. Navigation
3. Hero
4. Product story
5. Features
6. How It Works
7. Interactive product visualization
8. Healthcare/RCM solutions
9. Security
10. Request Demo
11. Demo-request backend
12. SEO
13. Accessibility
14. Performance
15. Responsive design
```

The final experience should communicate:

> OUTREACH — Making Every Call Count.

It should feel like a serious B2B communication SaaS platform ready to showcase to potential customers worldwide.

## End of Specification

