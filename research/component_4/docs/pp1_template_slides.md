# PP1 – Component 4 slide content (SLIIT PP1 template)

The template gives each member **one title slide + two content slides, delivered in exactly 2 minutes**. The group
slides (proposal comments, problem, design of the overall solution, 1–2 min video, commercialisation) are shared;
Component 4's input to them is in Part B. Numbers are from `results/` (simulation, 2025 test year) unless marked.

---

## Part A – Individual slides

### Slide 1 – Title (template page 3)
- **Photo:** professional photo in the black box (top right) – required.
- **Title of the Individual Component (9 words):**
  **Forecasting Trail Bottlenecks and Dynamic Carrying Capacity with Spatio-Temporal GNNs**
- **Specialization:** Information Technology
- **Footer:** IT23343948 | Weerasekera J.V | J26-IT-363

### Slide 2 – How the solution addresses the sub-problem, and the user requirements
**Top of slide:** Forecasting Trail Bottlenecks and Dynamic Carrying Capacity with Spatio-Temporal GNNs

**Left: the sub-problem → the solution (one line each)**
| Sub-problem (today) | What the prototype does |
|---|---|
| One fixed daily quota per park (Horton Plains), none at Adam's Peak | Daily safe number per trail from the Cifuentes cascade, driven by the forecast |
| Nobody knows **where** or **when** a trail section overloads | ST-GNN forecasts people on every ~300 m section, every hour, a day ahead |
| No sensors and no section counts exist | Works from open data (OpenStreetMap, Copernicus DEM, Open-Meteo, Poya calendar) and gate counts |
| Phones lose signal on the trail | The model runs on the phone, offline |

**Right: proof (2025 season, simulation)**
- Forecast-driven quota vs static quota, same visitors: **−27 %** over-capacity time (Horton), **−24 %** (Adam's Peak)
- Timed entry slots: **−99.6 %**; Adam's Peak start-time advice: **−42 %** waiting on the summit steps
- Runs on the phone: 2 ms (ONNX), ~150 ms in Dart, < 2 s target met

**Bottom strip: user requirements addressed**
FR1 trail graph · FR2 24-h section forecast · FR3 Cifuentes capacity · FR4 output for Module 3 + authority dashboard ·
FR5 "simulated target" note on every output · NFR1 < 2 s on device · NFR2 fallback · NFR3 new parks by config
(Adam's Peak, Yala) · NFR4 one number + "why" for officials · NFR5 no personal data
*(all traced to code and tests: docs/requirements.md)*

**Visual:** screenshot `11_bottleneck_map.png` (sections coloured by tomorrow's forecast) next to
`15_daily_quota.png` (forecast 261 vs static 287 vs weather-only 347 for one busy Sunday).

### Slide 3 – Design excellence / contribution, and user feedback
**Top of slide:** Forecasting Trail Bottlenecks and Dynamic Carrying Capacity with Spatio-Temporal GNNs

**Design excellence / contribution**
- **Research contribution:** first test of an urban-traffic ST-GNN (GCN + GRU) on tiny, sensor-free trail graphs,
  judged by the **decisions** it improves, not only its error. Honest answer to the gap:
  - works with no sensor record (gate counts only ≈ every section counted in the base world);
  - the graph helps only where sections are counted (significant on the realistic world, ≤ 1 %);
  - urban-traffic pretraining helps only with 30–90 days of data at Horton Plains.
- **Engineering:** one config file per park (Horton Plains, Adam's Peak, Yala); versioned JSON contract for Module 3;
  offline phone pack; role-based API with audit; 101 Python + 35 Flutter tests, lint, CI; every result reproducible
  (seed, config, git hash).
- **Creative control:** slot tickets (Horton), start times + halfway holds (Adam's Peak, nobody refused), jeep cap at
  wildlife sightings (Yala).

**User feedback on prototype** – *must be real; fill before PP1 (see Part C)*
| Who | What they said | What I changed / will change |
|---|---|---|
| (e.g. hiker who visited Horton Plains) | … | … |
| (e.g. tour operator / guide) | … | … |
| (e.g. ranger / DWC contact, or supervisor) | … | … |

If no feedback is collected in time, say so plainly on the slide: "Surveys and a usability test (SUS) are scheduled for
Nov; prototype shown to the supervisor on <date>" – do not invent feedback.

**Visual:** phone screenshots of the officer quota panel and the ranger Count tab (`15`, `17`).

### Speaker script (≈ 260 words = 2 minutes; time it)
> **[Slide 2]** My component is the crowd and capacity forecast. Today Horton Plains has one fixed daily quota and
> Adam's Peak none. Nobody knows where on the trail, or when, the crowd builds up – and there are no sensors.
> I turned each trail into a graph of 300-metre sections and built a spatio-temporal graph neural network that forecasts
> how many people will be on every section, every hour, tomorrow – from open maps, terrain, weather and the Poya
> calendar. That forecast goes into the Cifuentes carrying-capacity method, so the park gets a safe number per trail
> that changes with conditions. Replaying 2025, the forecast-driven quota cuts over-capacity time by about a quarter
> compared with a fixed quota, for the same number of visitors, and timed entry slots remove almost all of it. It all
> runs on the phone, offline. *(~1 min)*
>
> **[Slide 3]** The research question was whether a model from city traffic works on a tiny, sensor-free trail.
> The honest answer: the architecture works and runs from gate counts alone; the graph helps where some sections
> are counted; and traffic pretraining helps only with a few months of data. The design is one config per park –
> it already runs Horton Plains, Adam's Peak and now Yala – with a tested data contract for the safety assistant.
> Feedback so far: *<one real quote and what you changed>*. Next: field counts in December to validate the
> simulated target. *(~1 min)*

---

## Part B – Component 4 input to the group slides

### Comments for the proposal and how they were addressed (template page 1)
Fill with the **panel's actual comments** (from the proposal evaluation sheet / supervisor notes). Format:
| Comment | What we have done / how we addressed it |
|---|---|
| *(comment 1, verbatim)* | *(what changed, with evidence: file, result, screen)* |

Component 4 changes that answer the usual questions: synthetic target → pre-registered field criteria + counting tool;
"is a graph justified?" → benchmark with paired tests and the no-graph ablation (RQ1, RQ10); "is the capacity
defensible?" → Cifuentes with the forecast in the RCC step, compared with a static quota (RQ9).

### Problem, impact / gravity – credible statistics (template page 2)
- National parks: 1.8 M → 1.9 M visitors (Jan–Sep 2024 → 2025, +5 %; foreign +22 %) – News 1st, 25 Nov 2025 (proposal [8]).
- National parks earned a record Rs 2 bn in Q1 2024 from 200,000+ foreign visitors – Daily News, 12 Apr 2024 ([9]).
- Adam's Peak: ~20,000 climbers on a pilgrimage weekend, multi-hour queues on Poya – sripada.org ([10]).
- Only park-level totals are published; no section-level counts exist (DWC / SLTDA).

### Who benefits
DWC / park management (dynamic quotas, slot plans), Sri Pada Trust and police (when to hold), rangers (gate
advice, counting), visitors and pilgrims (quiet days, start times, guaranteed slot), tour operators / SLTDA (planning).

### Design excellence of the overall solution – Component 4's place
Module 4 needs no live data from Modules 1–3; it publishes a versioned feed (`c4-module3-feed-1`) that Module 3's
safety assistant and the shared dashboard read offline.

### 1–2 minute video – Component 4 shot list (~20 s)
Phone in airplane mode → Crowding tab: drag the hour, World's End turns red at 08:00 → officer Daily quota:
forecast 261 vs static 287 → ranger Count tab. Record with a screen recorder; no AI-generated images (template note).

### Last slide – commercialisation (entire project; Component 4 lines)
- **Customer persona:** DWC park warden deciding tomorrow's permit numbers; tour operator planning group days.
- **Market size:** Sri Lanka's national parks ~1.9 M visits in 9 months (2025) and Rs 2 bn per quarter in foreign
  revenue; a first wave of ~6 sites (Horton Plains, Adam's Peak, Yala, Ella Rock, Knuckles, Sigiriya).
- **Unique:** forecasts **where and when** crowds build up from open data, with no sensors, offline on a phone, and
  turns it into a defensible capacity (Cifuentes).
- **Cost recovery:** licence per site (DWC / Sri Pada Trust) + a small booking fee per ticket; a new site costs one
  config file and one small server (cost per park: to be estimated, plan W11).

---

## Part C – Getting real user feedback before PP1 (the template circles it: "engage with the user")
1. Show the app (Crowding tab, Daily quota, Count) to **3–5 people**: hikers who have visited Horton Plains or
   Adam's Peak, a guide or tour operator, and your supervisor; a ranger or DWC contact if reachable by phone.
2. Ask, and write down the answers word for word:
   - "Would you change your visit if the app said a section is crowded at 08:00?" (yes / no / why)
   - "Is the safe number and the reason for it clear?" (1–5)
   - "What is missing or confusing?"
   - "Would you book a timed entry slot?" (yes / no)
3. Put the best 2–3 answers on Slide 3, each with what you changed.
4. Keep the notes with the date (evidence for the "user feedback" and "requirements" rows of the mark sheet).

---

## Backup slide – where the data comes from
| Data | Source | Access | Used for |
|---|---|---|---|
| Trails, tracks, viewpoints, gates, tanks | OpenStreetMap (© OpenStreetMap contributors, ODbL 1.0) | Overpass API via OSMnx | Trail graphs of all three parks |
| Elevation (30 m) | Copernicus GLO-30 DEM (ESA / EU Copernicus) | AWS Open Data, `copernicus-dem-30m` tiles N06 E080 / E081 | Slope, TWI (wetness), walking time |
| Weather, past (hourly) | Open-Meteo historical API (ERA5 reanalysis, ECMWF / Copernicus) | `archive-api.open-meteo.com` | Model inputs 2022–2025, simulator rain |
| Weather, next 16 days | Open-Meteo forecast API | `api.open-meteo.com` | Live forecasts |
| Rain cross-check | NASA POWER daily point data | `power.larc.nasa.gov` | O1 check against Open-Meteo |
| Holidays, Poya days | Python `holidays` package (Sri Lanka); Poya after 2026 estimated from the full moon | – | Calendar inputs |
| City traffic for pretraining | METR-LA, PEMS-BAY (Li et al., DCRNN, ICLR 2018) | Hugging Face mirror TorchSpatiotemporal/ProcessedDatasets | RQ5 |
| Visitor figures for the problem | News 1st (Nov 2025), Daily News (Apr 2024), sripada.org | proposal refs [8]–[10] | Problem statement |
| **Crowd / occupancy data** | **None exists.** A simulator generates it; its parameters are estimates listed in `assumptions*.md` | – | Training and test target |
| Capacity method | Cifuentes (1992), CATIE Technical Report 194 | proposal ref [7] | Carrying capacity |
| Walking speed | Tobler's hiking function (1993) | – | Simulator, walking times |
