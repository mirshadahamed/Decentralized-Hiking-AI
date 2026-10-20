# Component 4 – Plan: a second site (Adam's Peak / Sri Pada) and a better app

Written 16 Oct 2026. Branch: `feature/component-4-multi-park` (from `feature/component-4-live-ux`, commit `0a8bb11`).

---

## 1. Short answer

**Yes, the framework can be used for Adam's Peak**, and it is a better test of the research question than Horton
Plains: several trails meet at **one summit**, so crowding really does spread along the network, which is what
a graph model is for. The proposal already names Adam's Peak queues (ref. [10]) as the problem, and NFR3 asks
that the pipeline "generalise to other OSM-mapped parks without architectural changes".

But four things are genuinely different and must be modelled, not just configured:

| | Horton Plains (now) | Adam's Peak |
|---|---|---|
| Shape | 3 separate trails sharing an entrance | 6 routes that **converge on one summit** |
| When people walk | day, gate 06:00–13:00 | **night**, mostly 00:00–04:00 to reach the summit for sunrise; descent in the morning |
| The bottleneck | World's End viewpoint | the **last flights of steps and the summit terrace**: people **queue** for hours on Poya weekends |
| Season | all year | pilgrimage season **Unduvap Poya (Dec) to Vesak Poya (May)**; few climbers in the off-season |
| Terrain | paths, moderate slopes | thousands of **steps**, 1,000 m+ of climb |
| Access | ticketed national park | **pilgrimage**: no ticket today; turning pilgrims away is not acceptable |

---

## 2. What we found in OpenStreetMap (16 Oct 2026)

| Route (start town) | In OSM? | Named length found | Notes |
|---|---|---|---|
| Hatton – **Nallathanniya** (Dalhousie) | yes, "Nallathanniya - Sri Pada Foot-path" | ~5 km incl. shared top part | the busiest route; mostly steps |
| Ratnapura – **Palabaddala** | yes, "Palabaddala - Sri Pada Foot-path" | ~7 km | shares the top section with Nallathanniya in OSM |
| Kuruwita – **Erathna** | yes, "Erathna - Sri Pada Foot-path" | ~9 km | long, quieter |
| **Dikelikanda** route | yes, "Dikelikanda - Sri Padaya Foot-path" | ~8 km | confirm which traditional route this is |
| Murraywatte / Mookuwatte / Malimboda (commonly cited minor routes) | **not found by name** | – | may be unnamed paths or missing; need GPS tracks |

Also: about 5.6 km of the paths are tagged as **steps**. Some sections are unnamed, so route lengths above are
partial. The DEM tile we already use (Copernicus N06 E080) covers Adam's Peak, so terrain features need no new download.

**To confirm with you / DWC:** the exact six routes you mean (3 main + 3 sub) and where each starts.

---

## 3. What has to change in the models

### 3.1 Trail network
- Same pipeline: OSM → chains → ~300 m segments → graph. New: routes that **meet** at the summit (shared top
  segments), and **stair segments** marked as such.
- Routes that are missing or incomplete in OSM: add **GPS tracks** (GPX) from a field visit or from Module 1's
  offline trajectories (an integration point with Ahamed M.N.I's module).

### 3.2 Walking speed on steps
Tobler's function is for slopes, not stairs. Use a **stair model** for `steps` segments (vertical speed, e.g.
metres climbed per minute, slower going up than down, slower when crowded) and keep Tobler on the rest.
Parameters to calibrate on a field visit (time a few groups between rest halts).

### 3.3 The summit queue (new)
On busy nights the problem is not walking speed but a **queue**: the final steps and the summit terrace let only
so many people through per minute. The simulator needs a **bottleneck with a fixed flow capacity**
(people per minute) and a waiting line that grows back down the trail. That is exactly the "congestion propagating
along a connected trail" in the proposal's abstract. Outputs: queue length per segment and **expected waiting time**.

### 3.4 Night-time arrivals and the season
- Arrival profile: most climbers start between 23:00 and 03:00 so they reach the summit for sunrise
  (sunrise time per date, computed); some climb by day.
- Calendar: **season flag** (Unduvap Poya → Vesak Poya), Poya and long weekends much stronger than at Horton
  Plains; school holidays; off-season low (and closed sections in monsoon).
- Group behaviour: many pilgrims arrive in large groups by bus at the same time; long **summit dwell** (waiting
  for sunrise, worship), then descent; some go up one route and down another.
- The forecast day must run **from midday to midday** (a "night" spans two dates), and all hours are open.

### 3.5 Weather
Same Open-Meteo pipeline, new grid point; the south-west monsoon matters more (rain, wind, cold at the summit).

### 3.6 Capacity
Cifuentes per segment still applies, plus the **summit terrace area** and the **queue's safe length** (people
standing on steps in the dark is the main safety risk). Values come from a field visit and the authorities.

---

## 4. Preventing overcrowding at a pilgrimage site

At Horton Plains we can say "no ticket left: choose another time". For pilgrims that is not acceptable.
So the same logic is used, but **advisory first**:

| Lever | Horton Plains | Adam's Peak |
|---|---|---|
| Entry | timed tickets (required) | **recommended start time** per route + optional free registration; config `booking_mode: advisory` |
| Route choice | other trail if it has room | other route when Nallathanniya's queue is forecast long (with honest travel times: Palabaddala/Erathna are longer) |
| On the night | rangers see traffic lights | police/rangers see **queue length and wait time**; can **hold groups at a lower rest halt** to keep the final steps flowing (a "metering" lever) |
| Information | forecast + suggestions | "If you start at 01:30 from Nallathanniya, expected wait near the summit about 40 min; start at 23:30 and it is about 90 min" |

The time-slot linear programme stays the same, but its output becomes **recommended start windows** (how many
pilgrims each window can take without the summit queue exceeding its safe length) instead of tickets.
Where registration exists, check-ins at the trailheads feed the live estimate; without it, counts at checkpoints
(rangers, police) do.

**Not decided by us:** whether any form of registration is acceptable. That is for the temple authorities, DWC,
police and the local councils. The system must work with none.

---

## 5. Making the software multi-site

Today several things are hard-coded for Horton Plains. Plan:

| Area | Change |
|---|---|
| Config | `configs/parks/horton_plains.yaml`, `configs/parks/adams_peak.yaml` (area, POIs, routes, opening pattern, season, walking model, capacity, booking mode); `--park` option everywhere |
| Data | one folder per park: `data/<park>/raw, processed, live`; results tagged with the park |
| Code with Horton constants | `VIEWPOINTS/ACCESS` sets, `TRAIL_INFO` texts, POI labels (dashboard, figures, Flutter), the special "main loop" in the simulator, open hours 06–18 and slots 06:00–12:30, the 4 spatial blocks → all read from the park config |
| Simulator | stair speed, summit queue, night arrivals, up-one-route-down-another |
| API | `/parks` list; every endpoint under `/parks/{park}/…`; bookings and staff roles per park |
| Flutter | park picker; texts and trail info from the API, not hard-coded |
| Tests | the whole test suite runs for both parks |

### Research value
- **Transfer test:** train on Horton Plains, apply to Adam's Peak **without retraining** (the segment features
  were made transferable on 15 Oct), then fine-tune with a little Adam's Peak data. That directly tests the
  proposal's research gap: does spatio-temporal graph learning transfer to small, sparse trail networks?
- **Does the graph matter more where trails converge?** Compare ST-GNN vs no-graph models on Adam's Peak, where
  queues spill back along the routes.

---

## 6. App upgrade (Flutter)

| Area | Upgrade |
|---|---|
| Start | **park picker** with photos: Horton Plains, Adam's Peak; season status ("Pilgrim season open") |
| Map | interactive map (`flutter_map` + OpenStreetMap tiles) with trails coloured by forecast crowd; tap a segment for its hourly curve; offline map for the trail area |
| Charts | hourly crowd per trail and **expected wait at the summit by start time** (`fl_chart`); week view for officers |
| Sunrise planner (Adam's Peak) | pick a route and your pace (easy / average / fit) → recommended start time to reach the summit for sunrise with the shortest wait |
| Night mode | dark theme with large text for night climbs (and battery saving) |
| Languages | **Sinhala, Tamil, English** (`flutter_localizations` + ARB files); most pilgrims are Sri Lankan |
| Design system | one theme file (colours, type scale, spacing), consistent cards and buttons, loading skeletons, friendly empty and error states, pull to refresh |
| Accessibility | contrast checks, screen-reader labels, text scaling, big touch targets |
| Ranger / police | tablet layout (navigation rail), queue-length entry ("people waiting at …"), hold/release groups button, works offline and syncs |
| Officer | season dashboard, recommended windows per route, capacity standard with instant preview, CSV/PDF export |
| Notifications (later) | reminder before your start time; warning if the forecast changes (opt-in, still no personal data stored on the server) |

The Streamlit research dashboard gets a park selector so examiners can compare both sites.

---

## 7. Phases

| Phase | Work | Effort |
|---|---|---|
| **0. Before PP1** | No Adam's Peak build. Present it as the next step: this plan, the OSM findings and the transfer test idea. Keep PP1 focused on Horton Plains | – |
| **1. Multi-park refactor** | park configs, per-park data folders, remove hard-coded constants, `--park` option, API `/parks/{park}`; Horton Plains results must stay identical (tests) | 3–4 days |
| **2. Adam's Peak network** | OSM routes + GPS tracks for missing routes, stair segments, summit and rest halts as POIs, terrain, weather | 2–3 days + field data |
| **3. Simulator for pilgrimage** | night arrivals, season calendar, bus groups, stair speed, summit queue with flow capacity, up/down different routes; assumptions documented | 4–5 days |
| **4. Forecasts and benchmark** | dataset, day-ahead models, planning model, spatial CV; **transfer test** Horton → Adam's Peak (zero-shot vs fine-tuned) | 3–4 days + CPU |
| **5. Advisory control** | recommended start windows (LP with queue limit), wait-time forecast, route suggestions, metering lever, `booking_mode` | 3 days |
| **6. App upgrade** | design system, park picker, map, charts, sunrise planner, night mode, Sinhala/Tamil, ranger tablet layout | 1.5–2 weeks |
| **7. Field validation** | a Poya night at Nallathanniya: counts at 3–4 points, stair timing, summit throughput | 1 night + analysis |

Order: 1 → 2 → 3 → 4 → 5, with 6 in parallel once the API has `/parks`. Realistic window: Nov 2026 – Feb 2027.

---

## 8. Risks

| Risk | Answer |
|---|---|
| Minor routes missing in OSM | GPS tracks from a field visit or Module 1 trajectories; mark them "approximate" |
| No visitor numbers at all | Season and Poya patterns from news reports and police/temple estimates; field counts on one Poya night; everything labelled "simulated" until then |
| Restricting pilgrims is culturally and politically sensitive | Advisory mode by default; no one is ever refused by the system; decisions stay with the authorities |
| Night-time safety (cold, dark, crowded steps) | Queue-length limits are a safety measure first; link to Module 3 safety advice |
| Scope growth before PP1 and the thesis deadline | Phase 0 only before PP1; Adam's Peak is an extension chapter, Horton Plains remains the field-validated pilot (main objective) |
| Many stakeholders (temple, DWC, police, councils) | Map them early; one meeting to learn what data and levers exist |
| UI work overlaps with the team's app | Shared design system agreed with the team; Component 4 screens stay in `lib/features/component_4/` |

## 9. Decisions (16 Oct 2026)
1. **Routes:** the four found in OpenStreetMap: Nallathanniya, Palabaddala, Erathna, Dikelikanda.
2. **Timing:** Adam's Peak is built **before PP1** (overrides phase 0 above).
3. **Crowd control:** **recommended start times** + **halfway checks** by officers who hold and release groups
   so the queue never builds on the final steps near the summit. No tickets for pilgrims.
4. **App first:** map + design system + languages (English, Sinhala, Tamil).
5. **Contacts:** DWC Peak Wilderness office, temple, police (student to arrange).

## 10. Build order before PP1 (replaces the phase table for now)
| # | Work | Done when |
|---|---|---|
| 1 | Multi-park core: `C4_PARK` selects the park; `configs/parks/adams_peak.yaml` overrides the defaults; data in `data/adams_peak/`; Horton-specific constants moved into the config | Horton Plains tests unchanged and green |
| 2 | Adam's Peak network from the 4 OSM routes (trailhead → summit), stair segments, ~500 m segments | graph builds, routes reach the summit |
| 3 | Simulator: night arrivals, pilgrim season, stair speed, **summit queue** (people/min through the final steps), **halfway hold** | queue forms on Poya nights, documented assumptions |
| 4 | Dataset + day-ahead benchmark (temporal, 1 seed if CPU is short) + planning model | results file |
| 5 | Control: recommended start windows per route (LP with a summit-flow limit), expected wait by start time, halfway release rates; evaluation of 4 policies (none / start times / halfway hold / both) | table: people waiting on the final steps |
| 6 | Live mode + API for both parks (`/parks`, `/parks/{park}/…`), checkpoint counts, release guidance | API tests for both parks |
| 7 | Flutter: design system, park picker, map, English/Sinhala/Tamil, Adam's Peak start-time planner, ranger halfway-check screen | `flutter test` green |
| 8 | Docs, RUN_APP update, results for slides | – |

Sinhala and Tamil texts will be drafted and must be checked by a native speaker before any public use.
