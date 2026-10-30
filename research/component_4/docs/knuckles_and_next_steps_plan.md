# Plan: Knuckles, crowd control per area, and the next steps for Component 4

*Written 30 Oct 2026. Builds on `improvement_plan.md` (sections 7–8) and `evaluation_results.md` (RQ1–RQ13c).*

## Progress (30 Oct 2026, branch `feature/component-4-knuckles`)

| Item | Status |
|---|---|
| §3 Per-trail control modes | **Done.** `src/control/modes.py`. `/status` and `/destination` give `trail_modes`. Slots, bookings and start times only for ticketed trails; `/stages` only for `open_stages`. Pekoe is `open_stages`. The app builds its cards and tabs from the modes |
| K1 Assumptions | **Done, from OSM.** `assumptions_knuckles.md`. Forest Department rules and numbers still to request |
| K2 Graph | **Done.** `src/data/waypoint_graph.py`: 9 trails, 49 sections. Several trails approximate (straight legs) until GPS tracks; Nitro Cave and Corbet's Gap not in OSM |
| K3 Simulator | **Done.** Weekend day-trippers, two monsoons, dwell at falls and viewpoints; guided groups of 4–12 leaving together (`simulator.guided_groups`); Duwili Ella / Lakegala closed after heavy morning rain (`simulator.rain_closures`) |
| K4 Permits | **Done.** `src/control/permits.py`, `/permits`. First come first served within the cap and the free guides (RQ14); LP = guide roster suggestion |
| K5 Overdue check | **Done.** Out / back, `/overdue/{day}`, margin grows with trek time and shrinks in rain; ranger "Treks" tab |
| K6 Viewpoints and parking | **Done.** `/viewpoints/{day}`; "parking full" through `POST /incident` |
| K7 Campsites | **Done.** `/campsites` (pitches per night) |
| K8 App | **Done.** Permit, viewpoint and campsite cards; Treks tab; Tickets tab only where something is sold; Sinhala and Tamil labels (drafts, to be checked by native speakers) |
| K9 Evaluation | **Done.** RQ14 in `evaluation_results.md` |
| R1 / R2 Commit, RUN_APP | Commit: the user. RUN_APP updated (Knuckles and new screens) |
| R3 Field trial | December (visits) |
| R4 Compliance | **Done.** Held start times count as held × the recent on-time share (`start_times.on_time_share`); shown in `/admin/recalibration` |
| R5 Pekoe | **Done.** `open_stages`; viewpoint sections hold 30 at once; weather per stage (`src/live/stage_weather.py`). 3-seed benchmark: running (`run_benchmark --seeds 42 43 44 --tag benchmark_6km_3seeds`) |
| R6 Stage advice evaluation | **Done.** RQ14b: spread starts −53 to −74 %, "start early" worse; the live advice now spreads |
| R7 Gate priority, measured | **Done (tool).** Ranger switch "Joined the queue" scans groups at the back of the queue (`POST /gate/queue`); check-ins go to `gate_log`; the day report and `/admin/gate-waits/{day}` give the measured median wait of start-time holders vs others. Numbers come with the field trial |
| R8 DWC data | Waiting for DWC |
| §6.1.1 Chance constraint | **Done.** `src/control/chance.py`, RQ15: ≈ 20 % fewer over-capacity person-hours than a fixed margin at the same admissions; live off by default (`control.chance_eps`) |
| §6.1.2 Fairness | **Done (report).** RQ15: large groups and visitors without a start time are turned away more. Remedies (split groups, walk-in share for start times, kiosk / SMS) not built |
| §6.1.3 Transfer with few counts | Not done: needs Knuckles spot counts (December) |
| §6.1.4 Rain during the day | **Done.** `mpc.blend_rain_share` + `src/live/nowcast.py`: the gate re-plans with the rain so far and the next 2 hours (only towards caution); unplanned rain −31 % overcrowding |
| §6.2.5 Trip planner | **Done.** Gateway `GET /trip`; app "Plan a trip" (route icon on the destinations list) |
| §6.2.6 Parking | Partly: Knuckles car parks (K6). Redirecting arrivals not built |
| §6.2.7 Safety | **Partly.** Walk register at every park except Yala (`POST /walks/out`, "Out & back" tab, same overdue alarm). Weather warnings and SOS need push / GPS: not built |
| §6.2.8 Explain decisions | **Done.** Gate card's first line says why places are fewer or more (`why`); visitor day screen already lists the limit factors |
| §6.2.9 Push notifications | Not done: needs a Firebase project (team decision) |
| §6.2.10 Officer trends | **Done.** `GET /admin/trends`; "Last 4 weeks" under the day report |
| §6.3.11 Backups | **Done.** `src/api/backup.py`; nightly at 02:00 from `serve_all`, 14 days kept |
| §6.3.12 Load / cache | **Partly.** Gateway caches public forecasts 60 s. Load test not run |
| §6.3.13 CI | Already in place (`.github/workflows/component4.yml`); lint fixed. Benchmarks need data, so not in CI |
| §6.3.14 Privacy | **Done.** `docs/privacy.md` |

## 1. Summary

The app covers four places: Horton Plains, Adam's Peak, Yala and the Pekoe Trail. Each already uses a different way of
controlling crowds, but the choice is made **per park** (`control.booking_mode`). The Knuckles Range is the first place where
**one area needs several mechanisms at once**:

- short nature trails at the conservation centres;
- guided wilderness treks with permits;
- roadside viewpoints anyone can drive to;
- overnight camps.

So the plan has three parts:

1. **A per-trail control framework** (section 3). Each trail gets a control mode, and the server and the app pick the
   controller and the screens from it. This is a refactor of the code we have, not new science.
2. **Knuckles as the fifth destination** (section 4), using that framework, with two new mechanisms:
   - guided-trek permits with an overdue check;
   - campsite and parking caps.
3. **The remaining development and further improvements** (sections 5–6), in priority order. Section 7 lists the
   inputs needed, and section 8 gives the timeline up to PP2.

## 2. Crowd control today, per area

| Area | What crowds look like | Mechanism in the app now | Where in the code |
|---|---|---|---|
| Horton Plains | Day walkers on one loop, one gate; bottleneck at World's End mid-morning | Slot tickets per trail (LP plan, forecast-driven Cifuentes quota); closed-loop gate control (MPC); start times with gate priority; incidents lower limits | `slots.py`, `booking.py`, `mpc.py`, `start_times.py` |
| Adam's Peak | Pilgrims at night, queue on the final steps before sunrise; nobody may be refused | Recommended start windows per route; halfway checkpoints that release climbers (advisory) | `advisory.py`, `evaluate_advisory.py`, `booking_mode: advisory` |
| Yala Block 1 | Jeeps on tracks; jams at leopard sightings | Jeep tickets per circuit and session; sighting rule (at most 10 jeeps, rotate every 10 min) | `booking_mode: required`, `evaluate_sightings.py`, `sightings.py` |
| Pekoe Trail | Few walkers spread over 323 km; day visitors on the Ella / Haputale stages | Stage advice (busiest place and hour, start time, quieter neighbouring stage); no tickets | `stages.py`; config still says `required` |

**What is missing:** the mechanism belongs to the park, not to the trail. At Knuckles, Pekoe (open stages, but ticketed
sections inside Horton Plains on stages 10–11) and later sites, one area mixes mechanisms.

## 3. Per-trail control framework (do this first, ≈ 1 week)

### 3.1 Control modes

Each trail in a park config gets a `control_mode`. A park-wide default stays for older configs.

| Mode | For | Visitor sees | Ranger sees | Controller |
|---|---|---|---|---|
| `gate_slots` | Ticketed trail with one gate (Horton Plains, Knuckles nature trails) | Book a slot / start time | Check-in, walk-ins, "Let in now" | Slot LP + MPC (existing) |
| `advisory_windows` | Must never refuse (pilgrims) | Recommended start window | Halfway release rates | Advisory (existing) |
| `vehicle_caps` | Jeeps / vehicles | Session ticket | Sighting rule | Slot LP in vehicles + sighting rule (existing) |
| `open_stages` | Long open trail | Stage advice | Spot counts only | Stage outlook (existing, `stages.py`) |
| `guided_permit` **(new)** | Wilderness treks that need a guide | Request a permit for a day and a group; told which guide slot | Issue / check permits, check groups out and back | Daily permit cap per trek and guides available (LP); overdue alarm |
| `open_viewpoint` **(new)** | Roadside viewpoints and waterfalls, open access | "Busy around 10:00, quieter before 08:30" | Spot counts; parking full / free | Forecast + parking cap; advice only |
| `campsite` **(new)** | Overnight camps on multi-day treks | Book a pitch for a night | Campsite headcount | Pitches per night (simple cap) |

### 3.2 Code changes

- **Config:** `area.trails.<id>.control_mode` (plus parameters per mode). `src/config.py` checks every trail
  has a known mode and fills in `booking_mode` for older configs: `required` → `gate_slots`, `advisory` →
  `advisory_windows`.
- **Server:**
  - A small registry, `src/control/modes.py`, maps each mode to its functions: plan for a day, live caps, gate check and visitor advice.
  - The endpoints stay the same, but each one works only on the trails of the right mode. For example, `/slots/{day}` lists only `gate_slots` trails, and `/stages/{day}` only `open_stages` trails.
  - `GET /status` returns the mode of every trail.
- **App:**
  - The visitor day screen and the ranger home build their cards from the trail modes, not from one park flag.
  - Today `ParkHome` picks `advisory_officer_home.dart` or `officer_home.dart` for the whole park. Instead, it should show a tab per mode present in the park.
- **Tests:** every existing park must still pass unchanged. Add one mixed-mode fixture park (two `gate_slots` trails,
  one `open_viewpoint`).
- **Pekoe:**
  - Set `open_stages` for all stages.
  - Optionally use `gate_slots` for the part of stages 10–11 inside Horton Plains, where the Horton gate applies. A Pekoe walker entering Horton Plains still needs the Horton Plains ticket.

## 4. Knuckles Range (Knuckles Conservation Forest) as the fifth destination (≈ 3–4 weeks)

### 4.1 Why Knuckles is different

- **Managed by the Forest Department, not the DWC.** Entry is through conservation centres or ticket points, and
  longer treks need a registered guide. *(Verify the current rules with the Forest Department; see section 7.)*
- **Several entry areas, far apart by road:**
  - Riverston / Pitawala (Matale side);
  - Deanston / Rangala (Kandy side);
  - Corbet's Gap and Meemure (east).
- **Mist, heavy rain, leeches, river crossings and steep, slippery ground.** Safety (groups overdue or lost, rivers in
  flood) matters as much as crowding.
- **Weekend day-trippers by car and van** make roadside viewpoints, Pitawala Pathana and Corbet's Gap, busy. Parking and
  the narrow roads are often the real bottleneck.
- **Multi-day treks with camping**, for example towards Meemure. The local community (homestays, guides) depends on
  the visitors, so spreading them out is better than refusing them.

### 4.2 Candidate trails and their control mode

The list below is **to be confirmed** against OSM (route relations and named paths) and the Forest Department.
Names, lengths and access rules are not yet verified.

| Trail (candidate) | Entry area | Type | Proposed mode | Main bottleneck |
|---|---|---|---|---|
| Pitawala Pathana ("mini World's End") | Riverston | Short walk from the road | `open_viewpoint` | Edge viewpoint, parking |
| Sera Ella / Bambarakanda-side falls near Riverston | Riverston | Short walk | `open_viewpoint` | Pool and falls area |
| Bambarella / Gombaniya peak trail | Riverston | Half-day hike | `gate_slots` (permit point) | Summit area |
| Dothalugala nature trail | Deanston / Rangala | Marked nature trail | `gate_slots` | Narrow forest path |
| Nitro Cave trail | Matale side | Half-day hike | `guided_permit` | Cave entrance |
| Duwili Ella | Rangala side | Long day hike, river crossings | `guided_permit` | River crossings in rain |
| Knuckles peaks / Kalupahana trek | Deanston / Kalupahana | Long day or overnight | `guided_permit` + `campsite` | Ridge and campsite |
| Corbet's Gap viewpoint | Rangala–Meemure road | Roadside | `open_viewpoint` | Parking, road |
| Lakegala (from Meemure) | Meemure | Guided hike | `guided_permit` | Steep final section |
| Meemure village walks / homestay treks | Meemure | Community | `guided_permit` | Homestay and guide capacity |

### 4.3 Work packages

| # | Work | Output | Days |
|---|---|---|---|
| K1 | **Trail list and rules.** Get the list from the Forest Department (permits, guide rules, opening hours, closures in rain) and check it against OSM. Write `docs/assumptions_knuckles.md` with every number marked (A) = assumed or (M) = measured | Assumptions doc | 3 |
| K2 | **Graph.** `configs/parks/knuckles.yaml` with several entrances. Build trails from OSM route relations where they exist (`stage_graph.py` handles out-of-order ways); otherwise from named paths (`graph.py`). DEM tiles around N07 E080 (multi-tile stitching exists) | `segments.geojson`, a map per trail | 3 |
| K3 | **Simulator.** Add: <br>• guided groups (group size 4–12 with a guide, fixed start from the centre); <br>• day-trippers arriving by car at viewpoints (parking cap, stay 30–60 min); <br>• river crossings that close in rain (a section's capacity drops to 0 above a rain threshold); <br>• mist slowing walking; <br>• overnight groups at campsites; <br>• realism (bursts on long weekends and Poya) | `dataset.npz`, assumptions | 5 |
| K4 | **`guided_permit` controller.** A daily cap per trek from Cifuentes. Permits per start window limited by the guides on duty (LP: maximise groups served, subject to section capacity, guides and campsite pitches). Waiting list. Advice to move to another day or trek | `src/control/permits.py`, tests | 4 |
| K5 | **Overdue check (safety).** The ranger checks a group out with its expected return time from the trek's walking-time model. If the group is not checked back in by return time + margin, the ranger and officer apps show an alert. Rain or a closed river crossing shortens the margin | `/permits/{code}/out`, `/permits/{code}/back`, `/overdue`; app cards | 3 |
| K6 | **`open_viewpoint` and parking.** The forecast for each viewpoint by hour, plus a parking cap. Advice: "Corbet's Gap is busy 10:00–13:00 on Saturday; quieter before 08:30 or on Sunday". The ranger reports "parking full", which works like an incident (E1) | Viewpoint card; parking report | 3 |
| K7 | **`campsite`.** Pitches per night per site; a booking with a code; a headcount report | Small extension of `booking.py` | 2 |
| K8 | **App.** Destination card; trail picker grouped by entry area; one card per mode (permit request, viewpoint advice, campsite); ranger tabs for permits and overdue groups; Sinhala and Tamil labels for the new screens | Flutter screens and tests | 5 |
| K9 | **Evaluation (RQ14).** On a simulated year: <br>• permits + guide LP vs first come first served: over-capacity, groups served, guide use; <br>• overdue alarm: time to raise the alarm for simulated lost or late groups vs a fixed 2-hour rule; <br>• viewpoint advice: spread of the Saturday peak when 30 / 60 / 90 % follow it | `evaluation_results.md` RQ14 | 4 |

**Risks**
- Few or no official visitor numbers. Mitigation: simulate, then field counts on a weekend visit (December–January).
- OSM paths may be incomplete in the forest. Mitigation: draw the missing pieces from the guide's GPS track and mark them (A).
- Rules differ between entry areas. Mitigation: keep the rules in config per entry area, not in code.

## 5. Remaining development from the current work (priority order)

| # | Item | Why | Size |
|---|---|---|---|
| R1 | **Commit the three pending batches** (recalibration and gate codes; incidents, stages, stress tests and day report; network, QR sharing and heatmap). Restart `serve_all`, run a refresh for every park, rebuild the APK | Nothing is safe until committed | ½ day |
| R2 | **Update `RUN_APP.md` and the user guide** with: <br>• start-time code at the gate; <br>• morning re-check; <br>• incident report; <br>• day report; <br>• share by QR; <br>• "All day" heatmap; <br>• other parks card; <br>• Pekoe stages | Examiners and the team run the app from it | 1 day |
| R3 | **Field trial (December):** Horton Plains 2–3 visits and the Adam's Peak Poya night. Counts entered in the app → `recalibrate --export` → `field_validation` | The research gap is still supported by simulation only; this is the most important evidence | visits + 2 days |
| R4 | **N2 with compliance:** also learn from the share of start-time holders who came on time (`start_advice.arrived_at`), and feed it to `advise_starts(follow=…)` instead of the fixed 0.8 | Closes the loop for the advice, not only the forecast | 2 days |
| R5 | **Pekoe:** <br>• set `open_stages`; <br>• viewpoint sections (Lipton's Seat, Ella Rock and others from `hotspots`) get their own smaller capacity, so the stage advice is not always "quiet"; <br>• weather per stage (Open-Meteo at each stage's midpoint; the cache exists); <br>• benchmark with 3 seeds | Advice that says something; panel request (P5) | 4 days |
| R6 | **Pekoe stage control evaluation:** does stage advice spread the Ella / Haputale day-visitor peak? Simulate 30 / 60 / 90 % compliance | Evidence for the open-trail mechanism | 2 days |
| R7 | **Live evaluation of the gate-code priority:** <br>• log check-ins with `kind` and `priority`; <br>• the day report shows on-time vs others' waits measured at the gate; <br>• compare with the simulated RQ13b | Turns simulated RQ13b into a measured result in the field | 1 day |
| R8 | **Real visitor data:** DWC daily totals into `data/live/dwc_daily_totals.csv` (the hook exists); retrain the planning model; re-run RQ9 / RQ13 on real daily demand | Replaces the simulated daily totals | depends on DWC |
| R9 | **Tell the team about shared changes:** `configs/default.yaml` (`live.recalibrate`), the gateway, and the terrain / graph code used by other components | Avoid surprises in the integration | — |

## 6. Further improvements for Component 4

### 6.1 Research (strengthens the claims)

1. **Uncertainty in control, not only in the forecast.** Use the calibrated chance of over-capacity (RQ12) inside the
   MPC as a chance constraint: P(over) ≤ 5 %. The model then holds back more on days the model is unsure about,
   instead of using a fixed safety margin. Compare with the fixed margin (RQ15).
2. **Fairness.** Report who waits and who is refused: walk-ins vs bookers, early vs late arrivals, groups with
   and without the app. Add a fairness term to the LP (for example a cap on the wait of any group). The app should not
   favour only smartphone users.
3. **Transfer to a new site with few counts.** For Knuckles, train on Horton Plains + Pekoe, then fine-tune on a few
   weeks of spot counts (the transfer code exists, `transfer.py`). How many counts are needed before the ST-GNN beats the
   historical average?
4. **Rain the plan did not expect** (the weak spot in RQ13c). Re-plan during the day from the hourly rain nowcast
   (Open-Meteo 15-minute data), not only the evening forecast. Test it with the `sudden_rain` stress scenario.

### 6.2 Product (makes it useful to the park)

5. **Network-wide trip planner.** For a holiday weekend, suggest the order of places so each visit falls on a quiet day.
   For example: Horton Plains on Friday, Knuckles on Saturday, Pekoe stage 15 on Sunday. Built on `GET /network/{day}`.
6. **Transport and parking** as part of capacity: buses and vans at the Horton Plains, Riverston and Corbet's Gap car
   parks. A ranger reports "parking full", and the app redirects arrivals.
7. **Safety layer for all parks:**
   - the overdue check from K5 for long walks everywhere;
   - weather warnings (lightning, flooding) pushed to visitors who hold a ticket or code that day;
   - a simple SOS that shares the last known section offline.
8. **Explain each decision in one line**: why the limit is lower today (rain, mud, incident, more people than
   expected). The factor lists exist (`/capacity`). Show them on the gate card and the visitor screen.
9. **Push notifications** for start-time changes and incidents, instead of the visitor pressing "Check before you
   leave". Use Firebase Cloud Messaging; keep the polling as the offline fallback.
10. **Officer dashboard trends:** a week and season view of forecast error, corrected error, over-capacity hours,
    no-shows and compliance, built from the day reports.

### 6.3 Engineering

11. **One database per park with backups** (SQLite → nightly copy; Postgres if several gates write at once).
12. **Load test the gateway:** many phones at once on a Poya morning. Add a cache for `/capacity`, `/plan` and `/network`.
13. **CI:** the Python and Flutter tests run on every push. Keep the long benchmark runs out of CI, and run them weekly.
14. **Privacy review:** codes are random and no names are kept. Write this down for the ethics section, including
    the QR count share, which holds no personal data.

## 7. Inputs needed

| Input | From | For | Needed by |
|---|---|---|---|
| Knuckles trail list, entry points, permit and guide rules, opening hours, rain closures | Forest Department (Knuckles conservation centres) | K1, K4–K7 | mid-Nov |
| Knuckles visitor numbers by day and entry point (any year) | Forest Department ticket records | Calibrate K3; R8-style real demand | Dec |
| Guides on duty per day, maximum group size | Conservation centres, guide associations | K4 | Nov |
| Campsite pitches, parking spaces at Riverston, Corbet's Gap and Horton Plains | Field visit, Forest Department / DWC | K6, K7, improvement 6 | Dec |
| GPS tracks of the main treks (where OSM is incomplete) | Guides or own recording on a visit | K2 | Dec |
| DWC daily visitor totals for Horton Plains and Yala | DWC | R8 | as soon as possible |
| Spot counts on visit days (all parks) | Our field visits, entered in the app | R3, RQ7 | Dec–Jan |
| Share of visitors who would use the app and follow advice (survey) | Short anonymous survey at the gate | Realistic `app_share` / `follow` for RQ13b, RQ14 | Dec–Jan |

## 8. Timeline to PP2 (mid-January 2027)

| Weeks | Work |
|---|---|
| 31 Oct – 6 Nov | R1, R2; per-trail control framework (section 3); request the Forest Department data (K1) |
| 7 – 20 Nov | Knuckles K2, K3, K4, K5; Pekoe R5 |
| 21 Nov – 4 Dec | K6, K7, K8; R4; R6 |
| 5 – 23 Dec | Field visits (R3, Knuckles counts); K9 evaluation; R7 |
| 24 Dec – 10 Jan | Field-validation analysis (RQ7); re-run results with any real data (R8); update docs and slides |
| 11 Jan → | PP2 preparation |

**Definition of done for this plan:**
- Knuckles appears in the app with every confirmed trail in the right control mode.
- Each new mechanism (permits with the overdue check, viewpoint and parking advice, campsites) has tests and a
  simulated evaluation (RQ14).
- At least one park has field counts compared with the forecast, raw and corrected.
