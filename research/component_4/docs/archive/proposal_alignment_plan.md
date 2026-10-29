# Does the app deliver what the proposal promised? – Alignment plan

Written 20 Oct 2026 after a line-by-line read of the proposal (IT23343948, Sept 2026) against the app and the API.
It complements `improvement_plan.md`: that plan covers the research items, this one covers the **app**.

## 1. Verdict

**The research pipeline matches the proposal. The app tells a different story.** The proposal's product is:
- a **segment-level bottleneck forecast** and a **dynamic capacity number per segment**;
- used by **park authorities** on a dashboard;
- fed to **Module 3**, which guides hikers;
- running **offline / edge-native**.

The app we built leads with what the proposal never asked for:
- a visitor trip planner;
- slot booking with QR tickets;
- Adam's Peak start-time advice.

The proposal's core output exists in the API, but the app barely shows it:

| Proposal item | Exists in the backend | Shown in the app |
|---|---|---|
| Occupancy per **segment** per hour, next 24 h (FR2) | Yes: `/forecast/tomorrow` → `segments[].forecast_hourly`, `peak_hour`, `utilisation`, `status` | **No.** Only the 3 busiest sections in the on-device card; the map colours trails, not crowding |
| Capacity **per segment** via PCC → RCC → ECC (FR3) | Yes: `segments[].pcc_per_day`, `rcc_per_day`, `ecc_per_day`, `capacity_at_once`, `limiting_segment` | **No.** Only one safe limit per *trail* (`/capacity/{day}`) |
| "A single number per segment with a plain-language confidence / limitation note" (NFR4) | Yes (status + disclaimer) | **Partly.** Per trail, not per segment |
| Output consumable by the dashboard and Module 3 (FR4) | Versioned JSON (`schema_version`) | **No agreed contract** with Module 3 |
| Offline, edge-native (main objective, O6) | On-device ST-GNN from the edge pack | **Only one card** works offline; the app cannot even start without the server |
| Authority dashboard: dynamic permit capacity | Streamlit research dashboard; officer tabs: week, condition, closure, alerts | **No bottleneck map or segment view** for officers |
| Hiker guidance that avoids forecast bottlenecks (section 6, value proposition) | Planner suggestions (other trail / later / other day) | Online only; nothing on the trail |

**Beyond the proposal's scope** (keep it, but present it as an *extension*, not as the product):
slot tickets and booking, the 90-day planner, Adam's Peak (second park), start-time advice, halfway holds,
Sinhala / Tamil. These are useful and well tested. But a demo that opens with booking makes examiners ask
"where is the ST-GNN bottleneck forecast?"

**Scope boundary to respect** (proposal 4.4): *hiker safety assistant and route recommendation logic* belongs to
**Ahamed M.M (Module 3)**. Component 4 supplies the **signal**: which segment, when, how full, what capacity.
Any route advice in our app is a **demonstrator of that signal** and must be offered to Module 3, not compete
with it.

---

## 2. Can offline alternative-route suggestions solve the overcrowding?

**Short answer: they reduce it, they do not solve it.** Use them as the *hiker-side* half. The other half is the
proposal's own answer: a **dynamic capacity limit on how many enter** (authority side).

| Why route advice alone falls short | Evidence |
|---|---|
| **Few real alternatives.** At Horton Plains 86 % walk the World's End loop. Kirigalpotta (long, exposed, last start 09:30) and Thotupola (a drive away) are different trips, not detours. At Adam's Peak all four routes end at the **same summit steps**, so changing route does not change the bottleneck | `configs/default.yaml` route shares; Adam's Peak routes |
| **The bottleneck is fixed by how many enter and when.** Once 1,000 people are inside, advice can only move them around a little | Entry control on 2025: a daily quota cuts over-capacity time by 73 %, slot tickets by > 99 % |
| **Offline advice is stale and uncoordinated.** Every phone gets the same forecast, so every phone gives the same advice: the crowd moves together to the "quiet" option and makes a new peak | Adam's Peak: naive start-time advice made queues **22 % worse** until advice was spread batch by batch |
| **Advice depends on compliance** | RQ4: start-time advice cuts waiting 6–25 % at 25–100 % compliance (at the assumed flow) |
| **Route choice for Adam's Peak is made at home** (Hatton vs Ratnapura are hours apart) | – |

**Where offline advice does help** (and is honest to claim):
1. **Timing:** start earlier or later. Time is the biggest free alternative: the World's End peak is 08:00–10:00.
2. **Direction of the loop:** walk it the other way (Baker's Falls first). This reaches World's End after the
   peak, with no new trail needed. The simulator already models it (`standard_direction_share` 0.85).
3. **On-the-trail warnings:** "World's End will be full 08:00–09:30; spend longer at Baker's Falls first." This
   works with no signal, because the ST-GNN runs on the phone.
4. **Spread, not herd:** each phone picks among the good options at random, weighted by spare capacity. Then 30 %
   of users do not all move to the same place. This needs no connection and no coordination.

**This is a research question we can answer before PP2 with the existing simulator (proposed RQ8):**
*"How much overcrowding does offline, forecast-based advice remove, compared with a dynamic entry limit, and
both together?"*
- Policies:
  - none;
  - static quota;
  - dynamic Cifuentes limit;
  - offline advice (time / direction / trail, herd vs spread);
  - limit + advice.
- Compliance 25–100 %.
- Metric: over-capacity person-hours per segment on the 2025 test year.

Expected outcome, to be tested rather than assumed: advice alone gives a moderate cut that depends on
compliance, while the dynamic limit plus spread advice is best. That would be a clear, defensible contribution.

---

## 3. Plan: make the app show the proposal

Ordered by how much each item moves the proposal and the PP mark sheet. **A** items make the proposal visible
with data that already exists. **B** items close real gaps. **C** items are extensions.

### A – Show the proposal's core output
**Status 20 Oct (branch `feature/component-4-bottleneck-map`):** A1, A2 and A3 are done.
- **Where:**
  - `presentation/screens/bottleneck_screen.dart` and `domain/bottleneck.dart`;
  - the pack's `map` block (`src/edge/pack.py: map_extras`);
  - entry points: the officer's first tab, Map → "Tomorrow's crowding", and the on-device card.
- **A4 (home by role):** done. Hikers get a "Crowding" tab, rangers a "Tomorrow" tab, officers "Bottlenecks" first.

**B1–B5 also done on 20–21 Oct:**

| Item | Where |
|---|---|
| B1 offline-first | Every GET is stored on the phone and used with no connection; offline banner; the park's screens and the forecast pack are prefetched when it opens online (`data/api_client.dart`) |
| B2 offline walk advice, spread | "Your walk" tab (`domain/walk_advice.dart`) |
| B3 RQ8 | `src/control/evaluate_advice.py`, results in `evaluation_results.md`: spread advice −73 %, herd advice backfires, limit + spread −95 % |
| B4 Module 3 contract | `docs/schema/c4_module3_feed.schema.json`, sample, `GET /module3/feed`, `tests/test_module3.py`. Still needs Ahamed M.M's sign-off |
| B5 authority dashboard | Streamlit page "Bottlenecks (authority)", with an optional Module 2 damage cross-reference |
| ID | Work | Proposal link | Data already there |
|---|---|---|---|
| A1 | **Bottleneck map.** The trail map coloured **by segment** for tomorrow: green / amber / red = forecast people ÷ segment capacity, with an **hour slider** (06:00–18:00) and peak segments marked. Tap a segment → hourly forecast, capacity, status | FR2, title "micro-spatial bottleneck forecasting" | `segments[].forecast_hourly`, `capacity_at_once`, `utilisation`, `status`; geometry already in the app |
| A2 | **Works offline.** Draw the same map from the **on-device** ST-GNN forecast. Add `capacity_at_once` and segment geometry to the edge pack | Main objective (offline, edge), O6 | Edge pack + Dart engine exist; ~10 KB more in the pack |
| A3 | **Authority "Capacity" screen.** Per **segment**: PCC → RCC → ECC, the limiting segment, the single recommended number per trail and park, and the plain-language limitation note. Replaces the static quota | FR3, NFR4, O5 | `pcc/rcc/ecc_per_day`, `limiting_segment`, `recommended_daily_quota`, `classic_cifuentes_quota` |
| A4 | **Re-order the home screen by the proposal's users.** **Park authority** (bottleneck map, capacity, conditions) · **Ranger / tour operator** (today's bottlenecks, gate) · **Hiker** (tomorrow's crowding, advice). Booking and the 90-day planner move under "More / extensions" | Section 5 stakeholders | – |

### B – Close the remaining proposal gaps (Nov)
| ID | Work | Proposal link |
|---|---|---|
| B1 | **Offline-first app.** Cache the last outlook, plan, capacity and geometry. The app starts and shows the last data with a "data from <time>" label when there is no connection | Main objective, section 1.1 ("cloud apps unusable when signal drops") |
| B2 | **Hiker guidance, offline**, as a demonstrator for Module 3: "World's End busy 08:00–09:30 → start at 07:00 or walk the loop the other way / Baker's Falls first". Options are spread at random weighted by spare capacity. Computed on the phone from the on-device forecast | Section 6 value proposition; feeds Module 3 |
| B3 | **RQ8 experiment** (section 2 above): advice vs dynamic limit vs both, compliance sweep, herd vs spread | Gives B2 evidence; strengthens the "replace the static quota" claim |
| B4 | **Module 3 data contract**: JSON Schema for the per-segment forecast, capacity, status and advice; a sample file; contract tests; a read-only file in the shared data layer. Agree it with Ahamed M.M | FR4, section 4.3, WBS 10 |
| B5 | **Authority dashboard view** in the shared front-end (or the Streamlit dashboard): bottleneck map + capacity table, cross-referenced with Module 2 damage when available | Section 4.3, Figure 2 "Authority dashboard – dynamic permit capacity" |

### C – Extensions (keep, freeze, present honestly)
Slot booking, the 90-day planner, Adam's Peak start times and halfway holds, Sinhala / Tamil. Present them as:
"the same forecast drives two control styles: tickets at a park with a gate, advice at a pilgrimage site."
No new work until A and B are done.

### Research items still open (see `improvement_plan.md`)
Field counts (Dec), the ST-GNN vs LSTM gap at the summit queue, layer-freezing adaptation and PeMS04/08,
CHIRPS / NASA POWER, real-phone timing, surveys.

---

## 4. Timeline
| Dates | Work |
|---|---|
| 21–22 Oct (PP1) | Reorder the demo (section 5); say what is extension and what is the proposal |
| 26 Oct – 8 Nov | A1 bottleneck map, A3 capacity screen, A4 home by role |
| 9 – 22 Nov | A2 offline map, B1 offline-first, B2 offline hiker guidance |
| 23 Nov – 6 Dec | B3 RQ8 experiment, B4 Module 3 contract with Ahamed M.M, B5 dashboard view |
| 7 – 24 Dec | Field counts; show the bottleneck map to the warden / rangers for feedback (also survey evidence) |

---

## 5. What to say and show at PP1 (no new code needed)
1. **Problem:** a static quota is blind to *where* and *when*.
2. **Proof of concept, in the proposal's order:**
   - **ST-GNN forecast per segment.** Show the forecast JSON / the on-device card, and RQ1 (better than HA and
     ARIMA; better than the LSTM on ordinary trail without counts).
   - **Cifuentes capacity per segment.** Safe limit + "Why this limit?"; per segment in the forecast JSON.
   - **Offline.** Airplane-mode demo, RQ6.
   - **Pretraining.** RQ5.
3. **Extension:** "the same signal already drives booking and pilgrim advice". 1 minute, not 5.
4. **Next:** the bottleneck map for authorities, offline hiker guidance for Module 3, field counts. That is this
   plan.
