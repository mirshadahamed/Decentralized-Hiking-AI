# Component 4 – Roadmap v3: 3-month crowd planning, alternative routes, and everything still to do

Written 15 Oct 2026, about 6 days before PP1. Replaces `next_phase_plan.md` and `development_plan.md` as the
working plan; those stay as history. Branch: `feature/component-4-dashboard`.

---

## 1. The request, and the short answer

> A user picks any date up to 3 months ahead and sees the expected crowd, forecast from historical counts,
> plus suggestions for nearby trails or other routes that avoid the crowd.

**Yes, it can be built, with three conditions:**

1. **It needs a second model.** The current ST-GNN is a *day-ahead* model. It needs yesterday's hourly counts
   and tomorrow's weather, and neither exists 3 months ahead. A long-range "planning" model has to
   work from the calendar, typical weather for that time of year, and the historical counts.
2. **It gives a range, not one number.** 60 days ahead nobody knows if it will rain. The honest output is
   "likely 700 visitors (range 450–1,000); World's End busy 07:00–10:00", with the range getting wider the further
   ahead the date is.
3. **Its quality depends on real historical counts.** Today the "history" is our simulator. To be credible
   the planning model needs DWC's daily ticket totals for Horton Plains (request them now; see section 6).

---

## 2. What the user will see

A new dashboard page, **Plan a visit**:

```
┌ Plan a visit ──────────────────────────────────────────────────────────────┐
│ Date: [ Sat 13 Dec 2025 ▼ ]   (any day in the next 90 days)                 │
│ Forecast made on: Mon 15 Sep 2025 (89 days ahead) · confidence: low (calendar only)
│                                                                              │
│ Expected visitors  ~1,150  (range 780 – 1,520)    Crowd level: ●●●●○ HIGH     │
│ Busiest: World's End 07:00–10:00 · Mini World's End 06:30–08:30              │
│                                                                              │
│ [hour × segment heat map, with low / likely / high toggle]                  │
│                                                                              │
│ Suggestions to avoid the crowd                                               │
│  1. Go on Tue 16 Dec instead: ~380 visitors (−67 %)              [date]     │
│  2. Walk the loop in reverse (Baker's Falls first): World's End peak        │
│     ~40 % lower when you get there                               [route]    │
│  3. Start after 10:30: past the peak, but World's End is often misty  [time] │
│  4. Hike Thotupola Kanda instead: ~90 visitors, short (1.3 km), 3.7 km drive  │
│     from the Visitor Center                                      [trail]    │
│  5. Kirigalpotta: ~60 visitors, long (6 km each way). Check if open    [trail] │
└──────────────────────────────────────────────────────────────────────────────┘
```

Same data for the park officer (quota planning weeks ahead for Poya weekends) and as a JSON file for Module 3.
It works **offline**: the 90-day outlook is computed once a week (or day) and cached on the device.

---

## 3. How the forecast works: three horizons

| Lead time | What we know about the target day | Model | Output |
|---|---|---|---|
| **Tomorrow** (1 day) | yesterday's counts, tomorrow's weather forecast, calendar | current **ST-GNN** (day-ahead) | hourly per segment, one number |
| **2–16 days** | weather forecast (Open-Meteo gives 16 days), calendar, latest counts | **planning model** with the weather forecast | hourly per segment, narrower range |
| **17–90 days** | calendar + *typical* weather for that week (climatology from 2022–25) | **planning model**, weather as scenarios (dry / typical / wet) | hourly per segment, wide range (P10–P90) |

### The planning model (new): two steps
1. **How many visitors that day.** A quantile model (e.g. gradient boosting, or a small network) predicts the
   10th, 50th and 90th percentile of daily visitors. Inputs: day of week, holiday, **Poya**, long weekend,
   school holiday, month, trend, typical rain for that week (or the weather forecast if within 16 days), and
   recent level (e.g. last 4 weeks' average). Trained on historical daily counts: simulated now, DWC totals later.
2. **Where and when they will be.** Spread the daily number over segments and hours. Two options, compared:
   - (a) learned profiles: average hourly share per segment for that day type and rain level (simple, robust);
   - (b) the ST-GNN *without* recent-count input, given the daily number and the day's conditions
     (uses the graph: tests whether crowding spreads along the trail as the model expects).

### Why this is also research
It adds a clear, testable question: **how far ahead is each model useful?** We plot error against lead time
(1 → 90 days) for historical average, planning model and ST-GNN. The likely answer is that the graph model wins
only at short lead times and the calendar dominates beyond about 2 weeks. That is a useful finding for park
management either way.

---

## 4. The recommendations

Four kinds, from easy to hard:

| Kind | Example | What it needs | Ready when |
|---|---|---|---|
| **Another date** | "Tue 16 Dec: 67 % fewer people" | planning forecast for ±7 days around the chosen date | with the planning model |
| **Another start time** | "Start after 10:30" (with a note that World's End mists over late morning) | hourly forecast | with the planning model |
| **Reverse direction** | "Do the loop Baker's Falls first" | simulator already has reverse walkers; estimate peak occupancy met by a reverse walker | +1 day |
| **Another trail in the park** | Thotupola Kanda, Kirigalpotta | 3-trail network in graph + simulator + capacity per trail (Roadmap 6.3) | after PP1 |
| **Nearby trails outside the park** | e.g. Lanka Ella / Bambarakanda waterfall trails (in OSM) | only listed, **without a crowd forecast**: we have no data for them | optional, low priority |

**Ranking rule (v1):** score = predicted crowd at the place and time the visitor would be there, relative to
that place's capacity; then travel effort (extra drive, length) and attraction (World's End is why most people
come). Show the top 3, each with a one-line reason. Never suggest an option that would push *that* trail over
its own Cifuentes capacity (avoid just moving the damage).

**Can we show that the advice works?** Yes, with the simulator: re-run a crowded day where X % of visitors
follow the advice (shift date, reverse, other trail) and measure the drop in peak occupancy at World's End.
Report it for X = 10, 20, 30 %. The real acceptance rate comes from the hiker survey.

**Who owns what:** the proposal gives *route recommendation for individual hikers* to Module 3 (Ahamed M.M).
Component 4 produces the forecasts, capacities and the ranked option list in the JSON. Module 3 decides how to
show them to a hiker. **Agree this with the team before building section 4 beyond the dashboard.**

---

## 5. How we test it

| Test | Method | Pass mark (proposal) |
|---|---|---|
| Accuracy by lead time | backtest on 2025: issue a forecast on day t for days t+1 … t+90; MAE/RMSE per lead time, vs historical average | beats historical average at each lead time it is used for; paired t-test p < 0.05 |
| Range is honest | share of real (simulated) values inside the P10–P90 band | 75–85 % (should be ~80 %) |
| Peaks are right | does it flag the right days as "high" (Poya, long weekends)? precision / recall of top-10 % days | report |
| Advice reduces crowding | simulator what-if, section 4 | report the reduction |
| No leakage | forecast issued on day t uses only data before t; climatology built from training years only | unit test |

---

## 6. Data we need (start now: these take weeks)

| Data | From | Use | Status |
|---|---|---|---|
| **Daily ticket totals, Horton Plains, 3+ years** (by entry hour if possible) | DWC | train/check the daily-visitor model; replaces the simulator's daily totals | **request now** |
| Field headcounts at checkpoints, incl. a Poya weekend | own visits | calibrate segment/hour profiles | Dec–Jan |
| Kirigalpotta / Thotupola: open? permits? guides? their visitor numbers | DWC / rangers | alternative-trail suggestions | ask at the same time |
| Hiker survey: "would you change date / direction / trail if crowded?" | survey (already drafted) | acceptance rates for the what-if | add the question |

Until DWC data arrives, everything runs on the simulator. That is fine for PP1 if it is said clearly.

---

## 7. Full roadmap

### 7.1 Done so far
| Item | Where |
|---|---|
| Trail graph (26 segments), terrain, weather, calendar | `src/data/` |
| Occupancy simulator + assumptions | `src/sim/`, `docs/assumptions.md` |
| Day-ahead models: HA, SARIMA, LSTM, GRU, ST-GNN; benchmark with t-tests and spatial CV | `src/models/`, `src/run_benchmark.py` |
| Cifuentes capacity + forecast JSON (+ no-weather fallback) | `src/capacity/`, `src/serve/` |
| Dashboard: 6 pages | `dashboard/` |
| Kirigalpotta and Thotupola on the map (layer only) | `src/data/extension_trails.py` |
| 14 tests | `tests/` |

**Open result:** ST-GNN beats HA (−14 %) and SARIMA (−32 %) but is not better than the no-graph models yet.

### 7.2 Before PP1 (~6 days)
Status 15 Oct (branch `feature/component-4-network-planning`): items 1–3 **done**, plus the three-trail network
(Kirigalpotta + Thotupola in the graph, simulator and capacity) and trail suggestions, brought forward from 7.3.
The full benchmark on the 48-node network is running.

| # | Task | Effort | Why |
|---|---|---|---|
| 1 | **Graph-layer fix**: average only over segments that have counts; rerun spatial CV with 3 seeds (background) | done (code); benchmark running | main research claim |
| 2 | **Planning mode "lite"**: daily-visitor quantile model (calendar + climatology), learned hourly profiles, "another date" and "later start" suggestions, **Plan a visit** page | done | shows the feature works (proof of concept) |
| 3 | Lead-time backtest (2–90 days) for planning model vs HA, one chart | done: crowd per segment-hour 13 % better at every lead (p < 0.001); daily totals no better; range covers 77–79 % | research evidence |
| 4 | Supervisor meeting: Cifuentes link and parameters, planning-mode scope, ownership split with Module 3 | 1 meeting | pending decisions |
| 5 | Request DWC data (section 6) | 1 hour | long lead time |
| 6 | Slides built on the dashboard; rehearse Q&A (simulator assumptions, why no graph gain yet) | 1.5 days | 15 % of the mark |

Dropped from the pre-PP1 list to make room: METR-LA pretraining test and the simulator total check (both after PP1).
If time runs short, cut #3 first, then the suggestions in #2 (keep the forecast).

### 7.3 After PP1
| Window | Work | Objective |
|---|---|---|
| Dec–Jan | Field visits: headcounts (incl. a Poya weekend), viewpoint platform areas, alternative-trail rules | Obj 2 |
| Dec–Jan | Retrain planning model on DWC totals when they arrive; compare simulated vs real | Obj 2 |
| Jan | ~~3-trail network~~ (done 15 Oct). Remaining: diversion what-if (simulator `route_share` override: share of visitors who accept the suggestion → peak reduction at World's End) | FR3/FR4 extension |
| Jan | 2–16 day tier with Open-Meteo forecasts (archived forecasts for backtesting) | realism |
| Jan–Feb | METR-LA / PEMS-BAY pretraining → fine-tune; scratch vs pretrained | Obj 3 |
| Feb | Quantise (int8, ONNX), phone latency < 2 s; offline cache of the 90-day outlook | Obj 6, NFR1 |
| Feb–Mar | JSON schema v2 (day-ahead + 90-day outlook + options) agreed with the team; shown in the shared Flutter app | FR4, integration |
| Mar | What-if evaluation of the advice; survey acceptance rates | evaluation |
| Mar–Apr | Final benchmark, field validation report, thesis chapters | WBS 11–12 |

---

## 8. Risks

| Risk | Effect | What we do |
|---|---|---|
| No DWC data | 3-month forecast only reflects the simulator's calendar rules | say so on screen; push the request early; field counts as a minimum |
| Long-range forecasts look precise when they are not | wrong decisions | always show the range and a confidence label; test interval coverage |
| Advice sends everyone to the same "quiet" day or trail | new crowding there | cap suggestions by the alternative's capacity; spread suggestions over several options |
| Alternative trails closed / need guides | bad advice | only suggest what DWC confirms is open; show conditions |
| Overlap with Module 3 | duplicated work, unclear marks | agree the split (section 4) with the team and supervisor |
| Scope creep before PP1 | core work unfinished | keep to the "lite" scope in 7.2 |

---

## 9. Decisions to confirm with the supervisor
1. Adding a 90-day planning mode to the scope (the proposal's FR2 mentions "e.g. next 24 hours").
2. Quantile ranges (P10–P90) as the output for long lead times.
3. Ownership: Component 4 = forecasts + capacity + ranked options; Module 3 = advice to the hiker.
4. The Cifuentes link and placeholder parameters (still pending from `decisions.md`).
5. Whether nearby trails outside the park should be listed without a crowd forecast.
