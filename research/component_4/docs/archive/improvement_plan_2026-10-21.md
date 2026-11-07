# Component 4 – Plan to complete the component

21 Oct 2026. Checked against:
- the proposal report (IT23343948, Sept 2026): sections 1.3, 2, 3, 4.3–4.4, 5, 6, 8, 9 and Appendix 2;
- the PP1 mark sheet (LO1–LO5);
- the code, tests and every run in `results/` up to `20261021_172706_sparse_s1` (still running).

This file is the **single plan**. Detail for the research-gap work is in `research_gap_study.md` (G1–G8, S1–S4,
A1–A6). The older plans (`development_plan`, `next_phase_plan`, `next_steps_plan`, `upgrade_plan`, `roadmap`,
`proposal_alignment_plan`, `live_and_ux_plan`, `restructure_plan`, `adams_peak_plan`) are history (see P3).

---

## 1. Where we are

**Built, tested and running** (91 Python tests, Flutter tests in `test/component_4/`, CI workflow
`.github/workflows/component4.yml`):

| Proposal part | State |
|---|---|
| Trail graph from OSM + DEM slope / TWI + Open-Meteo weather + Poya calendar (FR1, O1) | Done, 2 parks (Horton Plains 48 segments, Adam's Peak) |
| Calibrated synthetic target (O2) | Simulator done, plus a realistic world (S1). **Field calibration pending (December)** |
| ST-GNN (GCN + GRU), traffic pretraining METR-LA → PEMS-BAY, fine-tuning and frozen core (O3) | Done. PeMS04/08 and adversarial alignment open |
| Benchmark vs HA, SARIMA, LSTM (+ GRU without graph), RMSE / MAE, paired t-tests with Holm, spatial block CV (O4) | Done, 3 seeds, both parks |
| Cifuentes PCC → RCC → ECC per segment, forecast in the RCC step (O5, FR3) | Done; forecast-driven quota now drives the ticket plan |
| ONNX export, int8 test, Dart engine on the phone, offline pack (O6, NFR1) | Done on laptop / test runner. **Real phone pending** |
| Output for the dashboard and Module 3 (FR4) | JSON Schema `c4-module3-feed-1`, `GET /module3/feed`, feed inside the offline pack. **Module 3 sign-off pending** |
| Limitation note with every output (FR5), fallback (NFR2), other parks (NFR3), plain safe number (NFR4), no personal data (NFR5) | Done |
| Beyond the proposal | Slot tickets (LP), booking, gate advice, ranger spot counts, forecast check, officer records, 90-day planner, Adam's Peak start-time advice, FastAPI with roles and audit log, Streamlit dashboard, Flutter app |

Against the proposal Gantt (Component 4 = months 3–8, we are in month 2) the build is **ahead of plan**.
What is left is mainly **evidence**, not features.

### The research gap, claim by claim (from `research_gap_study.md`)
| Claim in section 1.3 | Evidence now | Status |
|---|---|---|
| C1 Graph learning adds value on a trail | Horton, uncounted segments: ST-GNN 2.54 vs LSTM 2.59 MAE (p_Holm < 10⁻¹²), but only ~2 %, one block carries it; tie with counts; worse at the Adam's Peak summit | Partly |
| C2 Traffic pretraining + domain adaptation helps | Helps Horton with 30–90 days (−5 / −12 %); frozen core 1.65 vs scratch 1.69 at 365 days; no help at Adam's Peak; never tested with sparse sensors | Partly |
| C3 Defensible **bottleneck** forecast | Over-capacity F1 0.80 (Horton) / 0.85 (Adam's Peak) with counts; on held-out segments F1 ≤ 0.56 (Horton 0.29–0.35) and the ST-GNN is below the LSTM / GRU | Shown with counts only |
| C4 Tiny, sparse graph, no sensor record | Gate-only and zero-sensor runs: interior MAE 1.43–1.46, same as with counts. In the default simulator the graph and gate counts have nothing to detect. S1 re-run in progress | Feasible; graph's value open |
| C5 Forecast → capacity that beats a static quota | Forecast-driven quota cuts over-capacity person-hours by 27 % (Horton) / 24 % (Adam's Peak) vs static at equal visitors. Horton: ST-GNN 93 % of oracle gain, HA 94 %, weather-only 81 % | Shown; ST-GNN ≈ HA at Horton |
| Main objective: "field-validated pilot trail" | Protocol and criteria A1–A3 fixed; counting tool in the app | December |

### Progress 21 Oct (evening)
| Item | State | Where |
|---|---|---|
| P1 problem from the product | **Done**: slide 16 (officer quota 261 / 347 / 287 + limiting section) and slide 10 (RQ9) | `src/report/slides.py` |
| P2 demo script | **Done** (talk track + demo order); rehearsal is yours | `docs/pp1_guide.md` Part 6 |
| P3 one plan in `docs/` | **Done**: 9 older plans in `docs/archive/`, references updated | `docs/archive/` |
| P4 technical design | **Done** | `docs/technical_design.md` |
| P5 Q&A | **Done** (39 questions) | `docs/qa_pp1.md` |
| P6 requirements traceability | **Done** (FR1–FR13, NFR1–NFR8) | `docs/requirements.md` |
| P7 risk register | **Done** | `docs/requirements.md`, slide 19 |
| W10b standards | **Mostly done**: `ruff.toml` + fixes (unused code, exception chaining, undefined name), lint step in CI, model + data card, data credits in README. CI green run waits for your push | `ruff.toml`, `docs/model_card.md` |
| Slides | **Updated**: gap claim-by-claim, RQ9, RQ10, staff tools; RQ1 / RQ5 / requirements / risks / WBS / next steps refreshed; 22 main slides, rest as backups | `docs/slides/PP1_Component4.pptx` |
| Staff screenshots | **Done**: `src.report.app_fixtures` + 4 new screenshot tests | `docs/slides/screens/15–18_*.png` |
| S2 (realistic world, sparse sensors) | Running | `results/20261021_172706_sparse_s1` |

### Re-check 21 Oct (night): everything left to complete the component
Checked again against the proposal, the mark sheet, the code and `results/`. Found 4 items the plan did not list
(marked **new**). "Me" = code / runs that can start now; "You" = needs people, permits or a phone.

| # | Work | Why it is needed | Who | Blocked by |
|---|---|---|---|---|
| R1 | **Done 21 Oct**: RQ3 / RQ4 re-run with the current advice model (start times −42 %, P90 advice −56 %, 115 % of perfect) | `evaluation_results.md` flags their numbers as from the old model (before crowd-dependent climb times) | Me | – |
| R2 | **new** RQ2 park-to-park transfer with 3 seeds | the only result still on one seed | Me | – |
| R3 | **new** Retrain and redeploy the app's model after G8, and rebuild the phone pack | the app still serves the 15 Oct checkpoint (seed 42) | Me | G8 |
| R4 | **new** Planning model: beat the calendar average on daily totals, or say plainly it does not | backup slide: daily MAE 110 vs 108 | Me | – |
| S2 | **Done 22 Oct**: realistic world – graph significant with counts everywhere (−0.013 vs no-graph, p_Holm 0.007); gate counts only ≈ HA + 3 %, graph adds nothing. Next: gates + a few ranger-counted sections | C1, C4 | Me | – |
| C5b | RQ9 quota replay on the realistic world | ST-GNN vs historical-average quota at Horton | Me | S2 |
| G6 | **Done 21 Oct**: live forecast from gate counts only (`live.model_input: gate`, model from `LATEST_SPARSE`; phone pack ships gate counts only; Dart = PyTorch re-checked) | deployment must match the "no sensor record" claim | Me | – |
| G8 | Peak-aware loss: **code done** (`trainer.masked_l1(peak=...)`, `src.eval.peak_loss`, pipeline checked); full 3-seed spatial run waits for free CPU. Periodic inputs after | RQ1b: peaks smoothed on unseen sections | Me | CPU |
| G4, W3 | Pretraining with sparse sensors; PeMS04/08; one adversarial method (DANN-style) | O3 wording, C2 | Me | PeMS04/08 download |
| G5 | Robustness of conclusions to simulator assumptions | F5 | Me | – |
| W5 | CHIRPS rain | O1 | Me | – |
| W1 | Field counts + recalibration + re-runs | main objective | You (+ me for the analysis) | permits |
| W6 | DWC / SLTDA data request | demand calibration | You | supervisor letter |
| W8 | Surveys, 2–3 interviews, SUS test | requirements validation | You | – |
| W9 | Confirm Cifuentes parameters | capacity numbers | You | DWC |
| W4 | Real Android timing | NFR1 | You (release build ready) | a phone |
| W7 | Module 3 sign-off, shared dashboard | FR4, WBS 10 | You + Ahamed M.M | team |
| W10 | Green CI run | standards | You | push |
| W11 | Letters of interest, cost per park | commercialisation | You | – |
| W13 | Thesis chapters, paper (RQ9 + RQ10 + RQ8) | final deliverable | You + me for drafts | results above |
| Y | **Yala National Park** as a third park (jeep safaris) | NFR3, commercialisation, a bottleneck no calendar predicts | Me | branch `feature/component-4-yala` |

Order for "Me": R1, R2, G6 now → S2 / C5b when the run ends → G8 → R3 → G4 / W3 → G5 → W5 → R4.

---

## 2. What is still missing, by mark-sheet row

| Mark-sheet row (weight) | What examiners look for | Gap today | Action (work package) |
|---|---|---|---|
| **LO1 Problem definition** (3 % of total) | Problem shown *through* the current implementation | The static quota is described, not shown with real numbers | P1: one demo step "static quota vs forecast-driven quota" on the officer Daily-quota tab, with the RQ9 table; quote DWC's real quota once W6 answers |
| **LO1 Proof of concept** (7 %) | Implementation clearly proves the solution | Strong end to end, but all on simulated history | P2 demo script; G7 field data later; S2 result on the realistic world |
| **LO2 Key pillars** (7.5 %) | Right research areas applied | ST-GNN, transfer learning, carrying capacity, edge AI, decision-focused evaluation all applied | Keep; show the pillar → code map in P4 |
| **LO2 Technologies** (17.5 %) | In-depth knowledge of the technologies | Biggest single row. Depth lives in code, not in one explainable place | **P4 technical brief**: GCN normalisation and tensor shapes, why GCN + GRU (vs DCRNN / STGCN / ASTGCN), loss and masks, transfer schemes, Cifuentes factors, LP for slots, ONNX → Dart, int8 rejection reason. **P5 Q&A sheet** |
| **LO3 Design excellence** (8 %) | Clear design features | Layered `src/`, park configs, schema contract exist, but proposal Figure 2 is out of date | P4: as-built component diagram + live-refresh sequence diagram; data-flow from inputs to `edge_pack.json` |
| **LO3 Completion** (12 %) | ~50 %, no delay | Ahead of plan | Show proposal Gantt vs actual (one slide) |
| **LO3 Standards / best practice** (8 %) | Clear evidence | Tests, seeds logged, run folders with git hash, JSON Schema, roles, audit log, CI file. **Missing:** a green CI run, lint, model / data cards, licence attribution (OSM ODbL, Copernicus DEM, Open-Meteo CC-BY) is not shown in the app or docs | W10b |
| **LO3 Requirements** (8 %) | Comprehensive, realistic, well described | FR1–5 / NFR1–5 met, but requirements are **not validated with stakeholders**, and the many new features have no FR | W8 + P6 requirements traceability matrix (FR → code → test → result) with new FR6–FR12 |
| **LO3 Risk mitigation** (4 %) | Risks, measures, actions under way | Risks scattered across docs | P7 risk register (section 4 below) |
| **LO4 Communication / presentation** (15 %) | Structure, flow, Q&A, visuals, time | `docs/slides/PP1_Component4.pptx` exists | P2 rehearse to time; P5 Q&A |
| **LO5 Commercialisation** (10 %) | Evidence of business potential | Model described in the proposal only | W11 |

---

## 3. Work packages

### Before PP1 (now, 1 day)
| ID | Work | Done when |
|---|---|---|
| **P1** | Problem slide from the product: officer tab "Daily quota" (same-all-year vs forecast, limiting section and hours) + RQ9 table (−27 % / −24 %, ST-GNN 93 % of oracle) | Slide + live demo step |
| **P2** | Demo script, 6–7 min: offline phone → 7-day bottleneck map → chance of crowding → officer quota → gate advice → ranger count → results (RQ1, RQ5, RQ6, RQ8, RQ9). **Screen recording as backup** | Rehearsed twice to time |
| **P5** | Q&A sheet: 25 likely questions with 2-line answers and the evidence file. Must include: "is the target real?", "why is the graph gain only 2 %?", "why does HA match the ST-GNN on the quota?", "what if DWC refuses data?", "why GCN not attention?", "how is leakage prevented?", "what did AI tools do?" | `docs/qa_pp1.md` |
| — | Say plainly: results are in simulation; graph gain is small; C1–C4 work and December field counts are the corrective plan (this scores on risk and completion rows) | In the slides |

### Research core (26 Oct – mid-Dec), in priority order
| ID | Work | Closes | Done when |
|---|---|---|---|
| **S2** | Finish gate-only / zero-sensor runs and bottleneck events on the S1 world, both parks, incl. forecasts made during the day (08 / 10 / 12 h) from gate counts | C1, C3, C4 | Table in `evaluation_results.md` (RQ10 on S1); a clear sentence either way |
| **G6 / A1** | Live service and phone model use only data that exist (gate counts, halfway counts), not simulated per-segment counts; on-device update from gate counts every 15 min **if S2 shows it helps** | F1 in deployment | App forecast basis = real inputs only |
| **G4** | RQ5 in the sparse-sensor setting: scratch vs fine-tuned vs frozen core; add PeMS04/08 as sources | C2, O3 | RQ5 answered for scarce sensors |
| **W3b** | One genuine domain-adaptation method beyond fine-tuning: adversarial domain alignment (DASTNet-style, App. 2) **or** gradual unfreezing; pick the cheaper after G4 | O3 wording | Row in RQ5, kept even if it does not help |
| **G8 / W2** | Only where S2 / G3 show errors: queue / capacity-aware input for the summit block; daily + weekly periodic inputs (ASTGCN); peak-weighted loss for under-called peaks | C1, C3 | Paired tests vs LSTM re-run; reported either way |
| **G5** | Robustness table: demand ±30 %, arrivals ±1 h, route shares, dwell, summit flow; which conclusions survive | F5 | Table + list of assumptions the December counts must check |
| **C5b** | Re-run RQ9 on S1 so the forecast has something to add over HA | C5 | ST-GNN vs HA quota answered on the realistic world |

### Validation and evidence (Nov – Jan)
| ID | Work | Done when |
|---|---|---|
| **W1 / G7** | Field counts: Horton Plains 2–3 days, Adam's Peak 23 Dec, using the ranger Count tab. Run `src.eval.field_validation`; check A1–A3; recalibrate on all days but one; re-run RQ1–RQ10 | Main objective's "field-validated pilot trail" met or honestly reported |
| **W6** | DWC / SLTDA data request through the supervisor (send in the week of 26 Oct). Use park totals to calibrate daily demand | Demand calibrated, or request and answer documented |
| **W8** | Surveys (officials, rangers / operators, hikers) collected; 2–3 interviews (warden, Sri Pada trust) using the app; SUS usability test 10–15 users | Requirements confirmed / changed in P6; SUS score |
| **W9** | Confirm Cifuentes parameters (group size, gap, management capacity, condition levels) with DWC / supervisor | Marked "confirmed" in `assumptions.md` |
| **W4** | Release build on 2 Android phones: ms per forecast, memory; Module 1/2 timings from the team | RQ6 row "Android phone" |
| **W5** | CHIRPS daily rain for both parks; compare with Open-Meteo; feature only if it differs (NASA POWER done) | O1 closed |

### Engineering, design and documentation
| ID | Work | Done when |
|---|---|---|
| **W10b** | Green CI run on a pull request; add `ruff` lint; model card (`docs/model_card.md`: data, metrics, limits, intended use); data card (sources, licences, simulated vs real); **attribution** "© OpenStreetMap contributors (ODbL)", Copernicus DEM and Open-Meteo in the app's About screen and README | All present; CI badge green |
| **P3** | Merge the 9 older plan files into `docs/history.md` (or move to `docs/archive/`); keep this plan, `research_gap_study`, `evaluation_results`, `assumptions*`, `decisions`, `user_guide` | `docs/` has one plan |
| **P4** | `docs/technical_design.md`: as-built architecture, component and sequence diagrams, model internals with shapes, why each technology | Linked from README |
| **P6** | Requirements traceability matrix: FR1–FR5, NFR1–NFR5 plus new FR6 slot tickets, FR7 booking, FR8 gate advice, FR9 spot counts / forecast check, FR10 chance of crowding, FR11 officer records, FR12 roles / audit → code path → test → result | `docs/requirements.md` |
| **P7** | Risk register with owner, trigger and action (section 4) kept in `docs/decisions.md` or its own file | Updated at each milestone |

### Integration, product, write-up (Feb – Jun)
| ID | Work | Done when |
|---|---|---|
| **W7** | Ahamed M.M signs off the Module 3 schema and reads the feed offline; authority view moved into the team dashboard; Module 2 damage cross-reference live; one shared app build | Integrated demo (WBS 10) |
| **W11** | 1–2 letters of interest (tour operator, DWC or Sri Pada trust); running cost per park per year (hosting, daily refresh, support); price sketch per segment B2G / B2B / B2C | `docs/commercialisation.md` |
| **W12** | Extensions only after the above: Knuckles as a third park; Sinhala / Tamil text review | Each with a result or a decision |
| **W13** | Thesis chapters (core = C1–C5 + field validation; system and extensions separate); research paper on RQ9 + RQ10 + RQ8 | Drafts to the supervisor |

---

## 4. Risk register

| Risk | Likelihood / impact | Mitigation | Status |
|---|---|---|---|
| No permission or bad weather for field counts | Medium / high | Request permits now; two windows (Dec, Jan); Adam's Peak season as backup; app counting tool so volunteers can help | Protocol ready |
| DWC / SLTDA refuse visitation data | High / medium | Use published park totals and news figures; document the request and refusal (decision log) | Request not sent |
| Graph adds nothing even on S1 world | Medium / high | Report as the C1 answer; the contribution moves to C5 (forecast → capacity) and sparse-sensor feasibility | S2 running |
| Results depend on the simulator | High / high | S1 realistic world, G5 robustness, field calibration | S1 done |
| Module 3 / team integration late | Medium / medium | Versioned schema, contract tests, feed in the offline pack, so Module 3 can read it without us | Contract done |
| Phone slower or bigger than expected | Low / medium | ONNX 2 ms, Dart ~150 ms; small model; HA fallback | W4 |
| Long CPU runs delay results | Medium / low | `--quick` checks; run overnight; Colab budget in proposal | Ongoing |

---

## 5. Timeline (PP2 assumed mid-January 2027)

| When | Work |
|---|---|
| 21–22 Oct | **PP1**: P1, P2, P5 |
| 26 Oct – 8 Nov | S2 finish; G6 / A1; send W6 request and W8 surveys; W10b; P3, P4, P6, P7 |
| 9 – 22 Nov | G4, W3b, C5b; W4 |
| 23 Nov – 6 Dec | G8 / W2 (only where needed), G5; W5, W9; field permits |
| 7 – 24 Dec | **W1 field visits** (Horton Plains; Adam's Peak 23 Dec) |
| 28 Dec – 10 Jan | Recalibration and re-runs of RQ1–RQ10; survey summary; update `evaluation_results.md` |
| ~15 Jan | **PP2** |
| Feb – Apr | W7 integration, W8 SUS study, W11, W12 |
| May – Jun | Final testing, W13 thesis and paper, final presentation |

## 6. Definition of "complete"
Component 4 is complete when:
1. every specific objective O1–O6 has a result file in `results/` and a row in `evaluation_results.md`;
2. C1–C5 each have a one-sentence answer backed by a paired test, including the negative ones;
3. field counts from at least one pilot trail are compared with the target and the model (A1–A3);
4. requirements are confirmed by at least one DWC / park stakeholder and traced to code and tests;
5. Module 3 and the team dashboard consume the feed in one integrated build;
6. it runs offline on a real Android phone within NFR1.

## 7. PP1 panel feedback (27 Oct): weather for the chosen date, and the Pekoe Trail

### 7.1 Weather for a specific date (≈ 2–3 days)
**Today:** the weather is used inside the model and the safe limit (rain share, wet ground), but a visitor or
officer never sees it.

**Goal:** wherever a date is chosen, show that date's weather and what it does to the crowd and the safe limit,
and say which kind of weather it is.

| # | Work | Where |
|---|---|---|
| W-a | `GET /weather/{day}`: hourly rain, temperature, wind, cloud and humidity for the open hours; a summary (chance of rain in open hours, total mm, min–max °C, a dry window); the basis: **observed** (past), **forecast** (up to 16 days, Open-Meteo) or **typical** (climatology of 2022–25, given as a range, not a value) | `src/live/inputs.py` already holds `weather` + `weather_source`; new `src/serve/weather_day.py`, `api/app.py` |
| W-b | Link weather to the decisions: the rain factor of the safe limit (FCpre), wet ground from earlier days, and the crowd forecast's rain effect ("rain usually keeps ~x % of visitors away") | `capacity_panel.py`, `/capacity/{day}` |
| W-c | App: a weather card on the visitor **day screen** (hourly strip: rain bars, temperature line, best dry hours for walking) and on the **Crowding** day picker (an icon per day); a weather line on the officer **Daily quota** panel | `day_screen.dart`, `bottleneck_screen.dart`, `capacity_screen.dart` |
| W-d | Offline: the week's weather goes into the edge pack, so the card also works in airplane mode | `edge/pack.py` (`map.days[].weather`) |
| W-e | Tests: basis switches observed → forecast → typical by date; card and offline pack | `tests/test_weather_day.py`, `c4_test.dart` |

For the Pekoe Trail, the same card is shown **per stage**, because stages span different altitudes and weather (§7.2).

### 7.2 The Pekoe Trail as a new destination (≈ 2–3 weeks)
**What it is:** a ~300 km long-distance trail through the tea country, in 22 stages, walked over several days by
some and as single stages by day-trippers. Some stages overlap busy day-visit spots (e.g. around Ella).
To verify from OSM and the trail's own route data.

**Why it fits the research gap:** it is open access, with **no gate and no counts**. That is the gap's
"no historical sensor record" condition exactly: the zero-sensor and spot-count settings of RQ10 / RQ11b apply
directly. It is also a **third, different trail type** (linear, multi-day, many entry points), which tests
whether the method transfers beyond Horton Plains (a loop) and Adam's Peak (a summit queue).

| Phase | Work | Done when |
|---|---|---|
| **P1 Data (3–4 days)** | `configs/parks/pekoe_trail.yaml` (the per-park pattern of Adam's Peak / Yala). Stages from OSM route relations (one walk per stage); trail graph of ~1–2 km sections; DEM slope / wetness; stage start-end points and villages as access points; tourist hotspots on the trail as viewpoints. **Weather at several points** (one per group of stages) | Graph and map of all stages; `build_dataset` runs |
| **P2 Demand and simulator (3–4 days)** | Assumptions (A) to document in `docs/assumptions_pekoe_trail.md`: walkers per stage by season (Dec–Apr peak in the hill country), day-trippers at hotspot stages, multi-day walkers moving one stage a day (flow carried from stage k to k+1 the next day), start times, stage times from Tobler + stops. Calibrate against what exists (trail organisation figures, guesthouse/booking listings, reviews) | Simulated year looks plausible per stage; assumptions listed |
| **P3 Model and evaluation (3–4 days + runs)** | Benchmark (temporal + spatial CV); **zero-sensor and spot-count settings** (counts at stage ends / hotspots); bottleneck events; transfer from Horton / Adam's Peak (RQ2-style) | One results table per setting; RQ1 / RQ10 / RQ11b rows for a third trail |
| **P4 Capacity and advice (2 days)** | Cifuentes per section; advisory mode, no tickets: **best day and start time per stage**, quieter stages nearby, a weather warning per stage; Module 3 feed for the route planner | `/advisory`-style endpoint for stages |
| **P5 App (3–4 days)** | Pekoe Trail in the trip planner (kind: long-distance trail); a **stage picker** (map of 22 stages, length, climb, time, crowd for the chosen date) → stage day screen with the weather card (§7.1), crowding per section, best start time; offline pack per stage (or the stages of the coming days); a multi-day plan ("stages 18–22 from <date>": crowd and weather each day) | Works offline on the phone; screenshots |
| **P6 Docs** | Results in `evaluation_results.md`, run guide, slides | – |

**Risks:**
- No visitor data exists. Make that the point: it is the zero-record case. State every demand number as an assumption, and plan a short field count at one or two hotspot stages, together with the December visit.
- ~300 km gives a larger graph (~200–300 sections) than the 48 / 57 so far. Check training time and the phone pack size (one pack per stage if needed).
- Stage geometry in OSM may be incomplete; fall back to the official GPX files.

**Order:** W-a → W-c → W-d (weather is quick and also needed per stage) → P1 → P2 → P3 → P4 → P5.

## 8. Next level: closed-loop crowd control (27 Oct)

**Goal:** from forecasting and advice to *control*. The loop: measure (gate counts, spot counts) → update (ST-GNN,
calibrated chances) → decide (MPC) → act (gate caps, holds, redirects, nudges) → learn (recalibrate).

| # | Work | Status |
|---|---|---|
| N1 | **MPC at the gate**: caps per trail and slot re-planned every slot from the gate counts, a feedback-corrected demand forecast and the response table; holds and redirects | **Done (RQ13):** 99.3 % over-capacity cut vs 62.7 % for a static quota, with more people admitted; booking (D) still better. Cost: 4 in 10 wait ~1.5 h at the gate. Live `GET /gate/control/{day}`; ranger card "Let in now" |
| N2 | Recalibration loop: each day's counts vs forecast and the advice compliance update the model and the controller | **Done (28 Oct):** per-section factors from the last 14 days of spot counts (shrunk to the park factor, clipped 0.5–2) correct the saved forecasts; raw kept for checking; `GET /admin/recalibration` with a leakage-free backtest; officer sees the corrected error. Compliance not yet used |
| N3 | Personal nudges with incentives and a compliance model (RQ8 spread). **Next, from RQ13:** send the controller's start time to visitors' phones before they travel, so the gate wait becomes a later start | **Done (RQ13b, 28–29 Oct):** start-time card with a held code; the gate check-in accepts the code (on time = let in first, counted as an entry); morning re-check from the gate counts and incidents, with "Move to HH:MM" |
| N4 | Network level: redirect demand across parks / Pekoe stages / days in the trip planner | **Partly:** gate advice sends groups to a trail with room (A3); Pekoe `GET /stages/{day}` gives each stage's busiest place / hour, when to start and a quieter neighbouring stage (P4). Cross-park: gateway `GET /network/{day}?park=` gives every park's load (expected ÷ safe limit), other parks with room (same kind first) and quieter days ±3; the visitor day screen shows it when the park is busy (30 Oct) |
| N5 | Phone-to-phone sync of counts and advice without a signal (Bluetooth / Wi-Fi Direct) | **Done without radio code (30 Oct):** a ranger shows the waiting counts as a QR code; another ranger scans it into their own queue; whichever phone gets a signal first sends them, each stored once (client id). Bluetooth / Wi-Fi Direct not used |
| E1 | Events: a ranger reports a problem on a trail (`POST /incident`, today only); gate control, start times and today's tickets use the lower capacity at once, and the gate card shows the alert | **Done (29 Oct)** |
| E2 | Stress tests of the controllers: demand surge, forecast ±30 %, rain not planned for (`evaluate_mpc --stress`) | **Done (29 Oct)**, results in `evaluation_results.md` |
| E3 | End-of-day report for the park office (`GET /admin/day-report/{day}`, printable HTML; officer tab "Day report") | **Done (29 Oct)** |
| E4 | Whole-day heatmap: every section that fills up × every open hour, tap a square for that section and hour (crowding screen, tab "All day") | **Done (30 Oct)** |

**Inputs needed for more accurate tests (priority order):**
1. DWC daily ticket totals (past years).
2. Ticket sale / scan times.
3. Counts at 3–5 sections for 2–4 weeks: manual counts, infrared counters, an on-device camera counter, or Wi-Fi / Bluetooth counters.
4. GPS tracks: walking and stop times.
5. Gate survey: group size, trail and direction.
6. Archived weather forecasts and Met Department station data.
7. Section widths and viewpoint platform sizes.
8. DWC capacity policy.
9. Advice compliance (app pilot).
10. Tour bus / school trip bookings and the incident log.
11. Adam's Peak checkpoint counts and summit queue times on Poya nights.
12. Pekoe Trail registrations and guesthouse occupancy.

**Strongest evidence:** a field pilot at one park, with control **on and off on alternate days**, measured with
inputs 3 and 5.