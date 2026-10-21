# Component 4 – Plan: live forecasts for real future dates, a better UI, and staff logins

Written 15 Oct 2026. Branch: `feature/component-4-live-ux` (from `feature/component-4-entry-control`, commit `7076bfb`).

**Status 15 Oct:** Phase 1 (live mode) and Phase 2 (FastAPI + logins) **done and tested** (47 tests).
Booking 24 Nov 2026 (Il Poya): outlook ~867 visitors (666–1,104), crowd level 4; 210 bookable + 63 walk-in
places on the loop. Phase 3 (Flutter) waits for the Flutter SDK on this laptop and agreement on shared app files.

---

## 1. Why the app cannot forecast future dates today

Tested on 15 Oct 2026:

| Feature | 24 Nov 2026 | Why |
|---|---|---|
| Book a slot (backend) | **works** (210 places on the loop, code issued) | Tickets per slot only need the trail graph, capacity and *typical* rain for that week |
| Book a slot (page) | blocked | The page's "Today is" box defaults to 2025 (demo mode) and limits the date to 90 days after it |
| 90-day outlook | **fails** | Needs the calendar, typical weather and the last 28 days of visitor numbers *up to today*; all stop on 31 Dec 2025 |
| Daily forecast (ST-GNN) | **fails** ("outside the dataset") | Needs yesterday's hourly counts and tomorrow's weather; neither exists after 2025 in our files |

Underlying reasons, in plain words:
1. **The dataset is a fixed research dataset**: 2022–2025, built once (`configs/default.yaml → dates`). 2022–23 train,
   2024 validate, 2025 test. That is right for *evaluating* the models, but nothing feeds them new days.
2. **Calendar**: holidays and Poya days are only generated to the end of 2025 (the `holidays` package has 2026+).
3. **Weather**: we use the Open-Meteo *archive*, i.e. the past. Future days need the *forecast* service
   (16 days ahead) and, beyond that, typical weather for the time of year.
4. **Visitor history**: the planning model needs recent visitor numbers and the ST-GNN needs yesterday's counts.
   We have no real counts after 2025 (or before: they are simulated). In live use these must come from the park:
   DWC ticket totals, gate scans, or (until then) a clearly labelled simulated stand-in.

The models themselves do **not** need retraining for 2026: they need *today's inputs*. So the fix is a
**live mode** that refreshes the inputs every day, next to the existing **research mode** (2025 backtests,
which stay unchanged for the thesis).

---

## 2. Live mode

### 2.1 Daily refresh (one command, run automatically each evening)
`python -m src.live.refresh` (Windows Task Scheduler at 18:00, plus a "Refresh now" button for officers):

| Step | Source | Notes |
|---|---|---|
| 1. Calendar to today + 120 days | `holidays` (LK) | Poya and public holidays for 2026–27 are available |
| 2. Weather up to yesterday | Open-Meteo archive + forecast API's `past_days` | The archive lags a few days; the forecast API fills the gap |
| 3. Weather for the next 16 days | Open-Meteo forecast API (hourly) | Real forecast → used by the day-ahead model and slot plans |
| 4. Typical weather beyond 16 days | climatology from 2022–25 | Already computed; gives the planning range |
| 5. Visitor history up to yesterday | **priority:** (a) gate check-ins / ticket scans from our own booking system, (b) DWC daily totals when received, (c) simulated stand-in driven by the real weather | Every day is tagged with its source; screens say "estimated" for (c) |
| 6. Forecasts | planning model: next 90 days from today · ST-GNN: tomorrow, hourly per segment | No retraining; models are loaded from the latest run |
| 7. Slot plans | entry-control LP for each of the next 90 days | See freeze rule below |
| 8. Publish | `live/outlook.json`, `live/forecast_tomorrow.json`, `live/slots.json` + log of what changed | Small files: cached on gate devices and phones (offline-first) |

### 2.2 Rules that make live booking fair and safe
- **Freeze rule:** once a slot plan is published and people have booked, a re-plan may **never** drop a slot below
  its booked places. If tomorrow's weather forecast lowers capacity, walk-in places are cut first; if that is
  not enough, the officer gets an alert listing affected bookings (offer a change, never silently cancel).
- **Closures:** an officer can close a trail or a time window (storm, landslide, wildlife). Re-plan is
  immediate; affected bookings get alternatives.
- **Retraining:** monthly, or when real data arrives (DWC / field counts); the research results stay tied to their runs.

### 2.3 What this answers
- "Can I book 24 Nov 2026?" → yes, from any day up to 90 days before (from 26 Aug 2026).
- "How busy will it be?" → crowd level and range from the planning model; from 16 days before with the weather
  forecast; the day before, hourly per segment from the ST-GNN.

---

## 3. Users, roles and logins

| Role | Login | Can do |
|---|---|---|
| **Visitor** | none needed (booking code is the key); optional account later | See crowd outlook, book / change / cancel, get QR ticket, see suggestions |
| **Ranger** (gate / trail) | username + password | Check in tickets (QR or code), sell walk-in places, see live traffic lights, report a trail problem, record a headcount |
| **Park officer** (DWC) | username + password | Everything a ranger can, plus: next-90-day plans, capacity standard, close trails/slots, approve plans, reports and exports, see booking statistics |
| **Admin** | username + password | Manage staff accounts and roles; nothing else by default |
| **Research** (examiners) | open page, read-only | Model comparison, simulator, backtests (today's pages, moved into one section) |

Security (prototype level, stated honestly):
- Passwords stored only as salted hashes (Python `hashlib.scrypt`), never in git; accounts created with a command
  (`python -m src.live.users add --role ranger`); no default passwords.
- Lock after 5 failed attempts; session timeout; every staff action written to an **audit log**
  (who changed capacity, who checked in which code, closures).
- In Streamlit the role check runs in the same server as the pages: fine for a prototype on one machine.
  For real use, roles must be enforced by a backend API (phase 3).
- Still no personal data for visitors (NFR5): bookings hold a code, day, trail, slot, group size.

---

## 4. Better UI and UX

Today's dashboard is a research tool: many charts, technical words, one long menu for everybody.
The redesign gives each user one clear job per screen.

### 4.1 Visitor (mobile first)
1. **Pick a day**: a calendar coloured by crowd level (green → red) for the next 90 days, with Poya days marked.
2. **Pick a trail and time**: three trail cards (photo, length, difficulty, how busy) → time chips with places left.
3. **Confirm**: group size → booking code + **QR ticket** (save as image; works offline at the gate) +
   "arrive between 06:45 and 07:15".
4. If full: the next best options are shown immediately as one-tap cards, not as an error.
5. "My booking": change time, cancel, see tomorrow's forecast and weather warning.
Plain language, large touch targets, English / Sinhala / Tamil labels.

### 4.2 Ranger (tablet / phone at the gate)
- Home = **today**: a big "Check in" button (camera QR scan or type the code), walk-in places left per slot,
  live traffic lights per segment with the suggested action, "report a problem" and "record a headcount".
- Works with poor signal: today's plan and bookings are cached; check-ins sync when online.

### 4.3 Park officer (desktop)
- Home = **this week**: per trail and day, booked vs available, expected demand, weather warnings, alerts
  (freeze-rule conflicts, closures).
- **Plan editor**: capacity standard slider with an instant preview (admitted % vs overcrowding prevented),
  close a trail or slot, approve.
- **Reports**: daily/weekly CSV and PDF, no-shows, walk-ins, overcrowding prevented.

### 4.4 Design rules for all screens
One task per screen · traffic-light colours used the same everywhere · numbers rounded and labelled
("about 300 people", not 297.4) · every estimate carries its basis ("forecast", "typical weather",
"estimated from simulation") · no model names on visitor and ranger screens · accessible contrast and text size.

### 4.5 Technology: a choice to make
| Option | For | Against |
|---|---|---|
| **A. Redesign in Streamlit** (role-based pages, custom theme, components) | Fast; reuses all current code; fine for PP1 demo | Limited mobile UX and offline support; not a real product front-end |
| **B. FastAPI backend + Flutter app** | The team's repo *is* a Flutter app; real mobile UX, QR camera, offline; same API for gate devices, Module 3 and the dashboard | 2–3 weeks; must be coordinated with the team (shared app, Module 3 owns hiker guidance) |
| C. FastAPI + React web app | Good web UX | A third technology in the project; no mobile/offline story |

**Decision (15 Oct 2026): B, FastAPI + Flutter, now.** Order: live mode → FastAPI service (booking, forecasts,
logins, roles enforced server-side) → Flutter screens in `lib/features/component_4/` of the team's app.
The Streamlit dashboard stays as the **research / examiner view** and is not redesigned further.
Note: the Flutter SDK is not installed on the development laptop yet (`flutter` not found); install Flutter
(stable) to build and run the app. Python parts are tested here; Flutter code needs `flutter test` on a machine with the SDK.

---

## 5. Phases

### Phase 1 – Live mode (≈ 2 days, before PP1)
- `src/live/refresh.py`: calendar extension, archive + forecast weather, history stand-in with source tags,
  planning outlook from today, ST-GNN for tomorrow, slot plans for 90 days with the freeze rule.
- Booking uses the real date by default; demo mode (2025) stays available as a switch for the research pages.
- Tests: no dates outside the inputs, freeze rule never drops below booked, refresh is repeatable.

### Phase 2 – FastAPI service with logins (≈ 2 days)
- Staff accounts (scrypt hashes, SQLite), token login, roles enforced on every endpoint, audit log.
- `/outlook`, `/slots/{day}`, `/bookings` (create / view / cancel), `/checkin`, `/walkins`, `/live/status`,
  `/admin/closures`, `/admin/capacity`; OpenAPI docs for Module 3; API tests.

### Phase 3 – Flutter screens (≈ 1–2 weeks, partly after PP1, with the team)
- `lib/features/component_4/`: visitor flow (calendar → trail cards → confirm → QR ticket), ranger home
  (check-in, walk-ins, traffic lights, offline queue), officer home (week view, closures, capacity standard).
- Agree navigation and shared widgets with the team; Module 3 reads the same API.
- Real data hooks: DWC totals import, gate scans as visitor history, ranger headcounts into the nowcast.

### Phase 4 – Hardening (Feb–Mar)
- Notifications (SMS/email optional, still no stored personal data unless the visitor opts in), PDF reports,
  Sinhala/Tamil translation review, load test of booking, security review.

---

## 6. Risks and limits

| Risk | Answer |
|---|---|
| Live "history" is simulated until DWC / gate data exist | Tag every day's source; show "estimated" on screens; replace automatically as real data arrives |
| Weather API unavailable | NFR2 fallback already exists (historical average + typical weather) |
| Re-planning breaks existing bookings | Freeze rule + officer alert; never silent cancellation |
| Streamlit login is not production security | Stated openly; phase 3 moves enforcement to the API |
| Scope before PP1 | Phase 1 is required to answer the question; phase 2 can be partial (logins + visitor flow first) |
| Overlap with Module 3 (hiker guidance) and the shared Flutter app | Component 4 owns forecasts, capacity, slots and booking; agree UI ownership with the team |

## 7. Decisions
1. ~~UI technology~~: **decided 15 Oct: FastAPI + Flutter now; live mode first.**
2. Visitor accounts: code-only (recommended, no personal data) or optional accounts.
3. Who issues staff accounts (DWC admin?) and whether rangers sell walk-in tickets in the app or on paper.
4. Live-history stand-in: acceptable for the PP1 demo if labelled "simulated"?
