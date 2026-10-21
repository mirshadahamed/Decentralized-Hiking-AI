# Component 4 – Next steps: commit, pull request, daily capacity, Knuckles, Teams planner

Written 19 Oct 2026 on branch `feature/component-4-restructure`.

---

## 1. The 157 uncommitted changes – commit them (nothing to discard)

What they are:

| Count | Change | Why | Action |
|---|---|---|---|
| 154 | `D ml/component_4/...` | Your move commit (`4e7c6e1`) **copied** the files to `research/component_4/` but did not record that the old copies are gone, so the branch currently has Component 4 **twice** (and the PowerPoint lock file `~$PP1_Component4.pptx`). These deletions finish the move. | commit |
| 1 | `M research/component_4/RUN_APP.md` | new troubleshooting row for the old path | commit |
| 2 | `M linux/…/generated_plugins.cmake`, `M windows/…/generated_plugins.cmake` | Flutter added the `jni` plugin (needed by a package in `pubspec.lock`) to the Linux/Windows builds | commit |

Commands (PowerShell, repo root):
```powershell
git add -A ml
git commit -m "Component 4: remove the old ml/component_4 copy (finishes the move to research/component_4)"
git add research/component_4/RUN_APP.md linux/flutter/generated_plugins.cmake windows/flutter/generated_plugins.cmake
git commit -m "Run guide: note the new folder; Flutter plugin registrants (jni)"
git push origin feature/component-4-restructure
```
Check afterwards: `git status` shows nothing to commit and `git ls-tree -r --name-only HEAD ml` prints nothing.

If you ever *do* want to throw away a change instead: `git restore <file>` (modified file) or `git restore --staged <file>`
then `git restore <file>` (staged). Do **not** use it on the 154 `D` lines – that would bring the duplicate copy back.

---

## 2. Can you open the pull request? – Yes, after step 1 and one conversation

Checked on 19 Oct 2026 (working tree = what the branch will contain after step 1):

| Check | Result |
|---|---|
| Up to date with `main` | yes – 0 commits behind, so no merge conflicts |
| Python tests (`research\component_4`) | 56 passed, 4 skipped |
| Flutter analyzer | no issues |
| Flutter tests | 17 passed (16 Component 4 + `widget_test.dart`) |
| Data / API answers after the move | identical to before (restructure_plan.md) |
| Teammate's files | identical to his branch |
| Secrets / personal data in git | none: `auth.sqlite`, `bookings.sqlite`, `data/` and model checkpoints are ignored |
| Largest files | his RAG database 6.9 MB and a 6.3 MB PDF; your slides 1.2 MB – all under GitHub's limits |

**The one thing to agree first:** the pull request contains **23 commits, 20 of them are your teammate's**
(`ai-hiking-assistant`: Knuckles dataset, recommendation model, offline RAG). Merging it puts his work into
`main` too. Ask him either to (a) approve this pull request as the way his branch reaches `main`, or (b) open his
own pull request first; after his is merged, yours shrinks to your 3 commits. Either is fine – just not without
him knowing.

Pull request text (copy into GitHub):
```
Title: Component 4: move into the team folder structure

- Merges ai-hiking-assistant (team research/ structure) – please confirm, @mirshadahamed
- ml/component_4 → research/component_4 (one folder; paths, docs and .gitignore updated)
- lib/features/component_4 re-layered: models / data / services / domain / presentation
- No behaviour change: 56 Python tests, 17 Flutter tests, identical datasets and API responses,
  8/9 screenshots pixel-identical (the 9th differs only in today's date). Details: research/component_4/docs/restructure_plan.md
- Fix: `run_benchmark --quick` no longer replaces the model the app uses
```

---

## 3. Feature A – "Safe limit today" for every Horton Plains trail (dynamic capacity)

**Status 19 Oct 2026: done on `feature/component-4-capacity` (not committed).** A1–A6 built: `/capacity/{day}`,
`/conditions/{day}`, `POST /admin/conditions`; wet-ground and condition factors; tickets re-planned on a report;
day-screen card with "Why this limit?"; officer "Trail condition" tab. Tests: 59 Python passed (4 skipped), 19
Flutter passed. Deviation: the limit is shown for every day 1–90 days ahead (not only "today").

**What exists already:** the server computes a Cifuentes carrying capacity per trail **for every day** and sends it
in `/plan/{day}` and `/forecast/tomorrow` as `recommended_daily_quota`. It already changes with:
rain (forecast weather for the next 16 days, typical weather after), the forecast crowding, and fixed terrain
factors (erosion-prone ground, steep grades). **The app never shows it** – the day screen shows only the expected crowd.

**What to add:**

| # | Change | Where |
|---|---|---|
| A1 | Day screen card per trail: *Expected about 870 · Safe limit today 520* with a bar, red when expected > limit, and a "Why this limit?" sheet listing the factors (e.g. *rain −35 %*, *wet ground −12 %*, *crowding −8 %*, *trail condition: muddy −20 %*) | `presentation/screens/visitor/day_screen.dart`, `models/models.dart` (`TrailCapacity` gets `factors`, `limitingSegment`) |
| A2 | **Ground wetness from the days before** (soil stays wet after rain): the erosion factor grows with the last 3 days' rain on waterlogging-prone segments (TWI) | `src/capacity/cifuentes.py` (`trail_factors` gets `antecedent_rain_mm`), `src/live/refresh.py`, `src/planning/planner.py` |
| A3 | **Trail condition set by an officer** (good / muddy / partly closed / closed) per trail and day range → a condition factor (0 / 20 / 50 / 100 %); closed = no tickets | new table in `src/control/booking.py`, `POST /admin/conditions` (officer), `GET /conditions/{day}`; officer screen "Trail condition" in `presentation/screens/staff/officer_home.dart` |
| A4 | Tickets follow the limit: the slot plan for a day uses the same daily quota (already wired via `use_daily_quota`); re-plan when the condition changes, keep existing bookings (freeze rule) and raise an alert | `src/control/slots.py`, `src/live/refresh.py` |
| A5 | Basis shown with the number: *forecast weather* (≤ 16 days) or *typical weather for the time of year* (later) | API + day screen |
| A6 | Tests: limit falls with rain / wet ground / condition; closed trail sells 0 tickets; app shows the card | `tests/test_control.py`, `tests/test_api.py`, `test/component_4/c4_test.dart` |

Effort: about 3 days. Adam's Peak gets the same card later (summit flow limit instead of tickets).

---

## 4. Feature B – Knuckles as the 3rd destination

Thanks to the config-per-park design (`configs/parks/*.yaml`), a new destination needs no app change: the
trip planner, map, calendar and staff tools appear by themselves once the server knows the park.

| # | Step | Detail |
|---|---|---|
| B1 | **Pick the trails that exist in OpenStreetMap** | Candidates: Dothalugala nature trail, Nitro Cave, Pitawala Pathana / Mini World's End, Corbett's Gap – Meemure, Bambarella / Knuckles peaks, Sera Ella. Query OSM by name inside the Knuckles box (about 80.70–80.85 E, 7.35–7.50 N). Your teammate's dataset has Knuckles as its **primary area** with candidate paths and weather points – compare with his list first so both components use the same trails |
| B2 | `configs/parks/knuckles.yaml` | `destination` (kind `forest_reserve` → new filter chip "Forest reserve", region, summary, best time, getting there, facts), `area` (bbox, routes, trail names), `simulator` (visitors per day, weekend/holiday pattern, start times), `control.booking_mode: required` (entry permits at the Deanston / Riverston conservation centres – **confirm with the Forest Department**) |
| B3 | Build the data | `$env:C4_PARK = "knuckles"; python -m src.data.build_dataset` (OSM graph, DEM, Open-Meteo, calendar, simulated history) |
| B4 | Models and checks | `run_benchmark` (HA, ARIMA, LSTM, GRU, ST-GNN; spatial CV); entry-control evaluation; add Knuckles to the transfer experiment (RQ2 gets a third park) |
| B5 | Live | `live.refresh` for Knuckles; staff accounts; `serve_all` gives it the next port (8103) automatically |
| B6 | Docs + tests | `assumptions_knuckles.md`, README, RUN_APP; a test like `test_adams_peak.py` |

Effort: about 1 week (most of it checking which trails are really mapped, and the visitor assumptions – there are
no published per-trail counts for Knuckles).

---

## 4b. Feature C – Adam's Peak: start the evening before and rest at a community hall

**Status 19 Oct 2026: C1, C4, C5, C7, C8 done on `feature/component-4-adams-peak-crowd` (not committed), plus
crowd-dependent climb times and the real sunrise per date.** Open: C2–C3 (hall locations from OSM and a
walk-with-rest inside the research simulator – the advice uses the halfway checkpoints as the halls), C6
(re-run RQ3/RQ4 with the new advice).

**Why:** today the recommended start times only run from **00:00**. In reality many pilgrims start the **evening
before**, walk part of the way and **rest in community halls / rest halts (ambalama)** along the route, then
continue so they reach the summit for sunrise. That is a second way to avoid the queue: arrive at a hall early,
rest, and leave the hall at a recommended time. *(Note the source of this suggestion in
`assumptions_adams_peak.md`.)*

**What the advice would look like:**
- *Start 00:30, walk straight up* – reach the summit about 03:47 (what exists now)
- *Start Fri 20:00, rest at the halfway hall until 01:30, continue* – reach the summit about 04:00 (new)

| # | Change | Where |
|---|---|---|
| C1 | **A "night" runs from 12:00 the day before to 12:00 on the day** (the date of the sunrise), so starts from e.g. 18:00 the evening before belong to the same night. Start windows from 18:00 (previous day) to 12:30 | `configs/parks/adams_peak.yaml` (`first_slot_h: -6`), `src/control/advisory.py` (time axis with an offset), `src/sim/simulator.py` (a night-long day) |
| C2 | **Rest halls on each route**: where they are (OpenStreetMap `amenity=shelter` / named halts; otherwise the existing halfway checkpoints), and **how many people each can hold** (assumption until counted) | `configs/parks/adams_peak.yaml` (`rest_halls`), `src/data/graph.py` (tag `hall_<route>` segments) |
| C3 | **Walk with a rest** in the simulator: walk to the hall, rest for a chosen time, continue; a hall that is full sends people on | `src/sim/simulator.py` (`_walk` with a rest stop) |
| C4 | **Two kinds of advice**: straight starts (as now) and *evening start + rest until HH:MM*. The rest end times are spread like the start times (herding-aware), and limited by each hall's capacity | `src/control/advisory.py` (`recommend`, `spread`) |
| C5 | **Demand assumption**: a share of pilgrims already start in the evening (e.g. 20 %, to confirm) – the simulator's start-time distribution gets an evening part | `configs/parks/adams_peak.yaml` (`arrival_evening_share`, `arrival_evening_mean_h`), `docs/assumptions_adams_peak.md` |
| C6 | **Evaluation**: rerun policies A–D with the evening option added (policy E: evening start + timed rest) and the sensitivity sweep; does it cut waiting on the final steps beyond what start times do now? | `src/control/evaluate_advisory.py` |
| C7 | **App**: start-times screen shows the evening option (*Fri 20:00 → rest at the halfway hall until 01:30 → summit ~04:00*); chart axis from 18:00 the day before; officer night plan shows expected people at each hall | `presentation/screens/visitor/start_times_screen.dart`, `presentation/screens/staff/advisory_officer_home.dart`, `models/models.dart` |
| C8 | Tests: a night spans midnight correctly; nobody is advised to rest in a full hall; evening advice never reaches the summit after sunrise | `tests/test_adams_peak.py`, `test/component_4/c4_test.dart` |

Effort: about 4–5 days (the night-long time axis touches the simulator, the advisory and the app).

---

## 5. Microsoft Teams Planner – buckets, tasks and dates

Assumed dates (please confirm and shift): **PP1 21–22 Oct 2026**, **PP2 mid-January 2027**, **final submission
and viva April 2027** (the proposal's project period is Nov 2026 – Apr 2027). Today is Mon 19 Oct 2026.

| Bucket | Task | Start | Due |
|---|---|---|---|
| **1. PP1** | Commit the 157 changes (section 1) | 19 Oct | 19 Oct |
| | Agree the pull request with the teammate, open it, review, merge | 19 Oct | 20 Oct |
| | Rehearse the slides (timed, 10–15 min) + live demo from the new folder | 20 Oct | 21 Oct |
| | **PP1 presentation** | 21 Oct | 22 Oct |
| **2. Daily capacity (Feature A)** | A1 safe-limit card on the day screen | 26 Oct | 28 Oct |
| | A2 ground wetness from previous rain | 27 Oct | 29 Oct |
| | A3 officer trail condition + API | 28 Oct | 31 Oct |
| | A4–A6 tickets follow the limit, tests | 30 Oct | 2 Nov |
| **3. Knuckles (Feature B)** | B1 trails in OSM – agree the list with the teammate | 3 Nov | 5 Nov |
| | B2–B3 config + dataset | 5 Nov | 9 Nov |
| | B4 benchmark, control evaluation, add to transfer study | 9 Nov | 13 Nov |
| | B5–B6 live, staff accounts, docs, tests | 12 Nov | 16 Nov |
| **3b. Adam's Peak evening starts (Feature C)** | C1 night from 12:00 the day before (simulator + advisory time axis) | 17 Nov | 19 Nov |
| | C2–C3 rest halls on each route + walk-with-rest in the simulator | 18 Nov | 21 Nov |
| | C4–C5 evening advice with timed rests; evening demand assumption | 20 Nov | 23 Nov |
| | C6 evaluation (policy E) + sensitivity | 23 Nov | 25 Nov |
| | C7–C8 app screens + tests | 24 Nov | 27 Nov |
| **4. Research depth** | ST-GNN with LSTM cell; 3 seeds at Adam's Peak (overnight runs) | 26 Oct | 6 Nov |
| | Learning curve: days of counts a new park needs (RQ2) | 16 Nov | 22 Nov |
| | Agreement metric for field validation defined *before* the visits | 16 Nov | 20 Nov |
| **5. Field work** | Permits / permission (DWC, Sri Pada Trust) | 2 Nov | 30 Nov |
| | Horton Plains counts at World's End (2–3 days, weekday + weekend) | 1 Dec | 20 Dec |
| | Adam's Peak final-steps flow on the **Unduvap Poya night (23 Dec 2026)** – season opening | 23 Dec | 24 Dec |
| | Calibrate the simulator with the counts + DWC totals; re-run RQ1–RQ4 | 28 Dec | 15 Jan |
| **6. Users & integration** | Native-speaker review of Sinhala / Tamil | 2 Nov | 30 Nov |
| | Usability study (SUS, 10–15 users) + ranger / officer interviews | 4 Jan | 22 Jan |
| | Integration with the team app (shared data, Module 3 suggestions) | 1 Feb | 28 Feb |
| **7. Milestones & writing** | **PP2** (assumed) | 11 Jan | 15 Jan |
| | Research paper draft | 1 Feb | 15 Mar |
| | Final report / thesis chapters | 1 Mar | 10 Apr |
| | **Final presentation / viva** (assumed) | 15 Apr | 30 Apr |

### 5b. Completed work (add these as tasks marked **Completed**)

Dates are from the git history (`git log --author=JaniduVirunaka`). The proposal tasks have no commits – fill in
your own dates for those.

| Bucket | Task | Start | Due | Evidence |
|---|---|---|---|---|
| **0. Proposal** | Proposal report (IT23343948) | *your date* | *your date* | `Proposal Report_IT23343948.pdf` |
| | Proposal presentation | *your date* | *your date* | `Janidu - Proposal Presentation.pdf` |
| **A. Data & simulator** (PR #1, #2) | Workspace, config, pinned requirements, seeding and run logging | 14 Oct | 14 Oct | `feature/component-4-ml-core` |
| | Horton Plains trail graph from OSM + DEM slope, TWI, Tobler time | 14 Oct | 14 Oct | |
| | Open-Meteo weather + Sri Lankan holiday / Poya calendar | 14 Oct | 14 Oct | |
| | Synthetic occupancy simulator + dataset builder + assumptions | 14 Oct | 14 Oct | |
| **B. Models & evaluation** (PR #2) | Temporal and spatial-block splits, metrics, paired t-tests | 14 Oct | 14 Oct | |
| | ST-GNN (GCN + GRU), LSTM / no-graph variants, HA and SARIMA baselines | 14 Oct | 14 Oct | |
| | Benchmark runner + first full benchmark results | 14 Oct | 14 Oct | |
| | Cifuentes capacity + day-ahead forecast JSON with fallback | 14 Oct | 14 Oct | |
| | Shape, leakage and reproducibility tests; figures | 14 Oct | 14 Oct | |
| **C. Three-trail network & planning** (PR #4) | Streamlit dashboard (6 pages) + render tests | 14 Oct | 14 Oct | |
| | Kirigalpotta + Thotupola joined with World's End into one network | 14 Oct | 15 Oct | `feature/component-4-network-planning` |
| | Graph layer that ignores segments without counts | 15 Oct | 15 Oct | |
| | 90-day planning model, suggestions, lead-time backtest | 15 Oct | 15 Oct | |
| | Transferable segment features; benchmark: ST-GNN best on unseen segments | 15 Oct | 15 Oct | |
| **D. Entry control & booking** (PR #5) | Slot-ticket linear programme, response table, live nowcast | 15 Oct | 15 Oct | `feature/component-4-entry-control` |
| | Policy evaluation 2025: slot tickets remove > 99 % of overcrowding | 15 Oct | 15 Oct | |
| | Slot booking with alternatives, walk-ins, gate check | 15 Oct | 15 Oct | |
| **E. Live mode, API & app** (PR #5, #6) | Live mode with real dates, daily refresh and publishing | 15 Oct | 15 Oct | `feature/component-4-live-ux` |
| | FastAPI service, staff logins, roles, audit log | 15 Oct | 15 Oct | |
| | Flutter app: plan & book, QR tickets, staff login, gate and office tools | 15 Oct | 15 Oct | |
| | Run guide (RUN_APP.md) | 15 Oct | 15 Oct | |
| **F. Adam's Peak & multi-park** (PR #7) | One config per park; Adam's Peak routes, stairs, season, estimated Poya days | 16 Oct | 16 Oct | `feature/component-4-multi-park` |
| | Summit queue + halfway holds in the simulator | 16 Oct | 16 Oct | |
| | Recommended start times + halfway checks; advisory API; gateway for several parks | 16 Oct | 16 Oct | |
| | App: map, theme, Sinhala / Tamil, start times, halfway checks | 16 Oct | 16 Oct | |
| | Trip planner (destinations, overview) + Adam's Peak officer console | 16 Oct | 16 Oct | |
| **G. Research evaluation** (PR #7) | RQ2 transfer between parks, RQ3 forecast value, RQ4 sensitivity | 16 Oct | 16 Oct | `docs/evaluation_results.md` |
| **H. PP1 material** (PR #9) | PP1 slides (21) with speaker notes + app screenshots; wait-chart fix | 16 Oct | 18 Oct | `docs/slides/` |
| **I. Team structure** | Plan the move into the team structure | 18 Oct | 18 Oct | `docs/restructure_plan.md` |
| | Merge the teammate's branch; move to `research/component_4`; re-layer the Flutter feature; verify (12 checks) | 18 Oct | 19 Oct | `feature/component-4-restructure` |
| | Plan for capacity, Knuckles, pull request and planner (this file) | 19 Oct | 19 Oct | `docs/next_steps_plan.md` |

Step 1 above (commit the 157 changes) is **done** (commits on 19 Oct, 01:04 and 01:05).

---

## 6. Where everything is now (after the move)

| What | Location |
|---|---|
| This plan | `research/component_4/docs/next_steps_plan.md` |
| Run guide | `research/component_4/RUN_APP.md` |
| Move plan + check results | `research/component_4/docs/restructure_plan.md` |
| Research results write-up | `research/component_4/docs/evaluation_results.md` |
| PP1 slides, charts, screenshots | `research/component_4/docs/slides/` (`PP1_Component4.pptx`, `fig/`, `screens/`) |
| Assumptions, decisions, older plans | `research/component_4/docs/` |
| Python code / configs / tests | `research/component_4/src`, `configs`, `tests`, `dashboard` |
| Data, models, bookings, staff accounts (not in git) | `research/component_4/data`, `research/component_4/results` |
| Flutter app (Component 4) | `lib/features/component_4/{models,data,services,domain,presentation}` |
| Flutter tests | `test/component_4/` |
