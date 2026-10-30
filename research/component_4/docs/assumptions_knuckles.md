# Knuckles Range: data and assumptions

*Config: `configs/parks/knuckles.yaml`. Plan: `knuckles_and_next_steps_plan.md`, section 4. Built 30 Oct 2026.*

Every number below is **(A) assumed** unless marked (M) measured or (O) taken from OpenStreetMap. None of the
Forest Department's rules or visitor records have been received yet (plan, section 7). Replace the (A) values as they
arrive, then rebuild:

```powershell
$env:C4_PARK = "knuckles"
.venv\Scripts\python.exe -m src.data.build_dataset
.venv\Scripts\python.exe -m src.live.refresh
```

## 1. Trails and how they were drawn

OpenStreetMap is thin in the range. It has the protected area (relation 10491478), 14 named peaks, viewpoints,
waterfalls, 9 campsites and 4 car parks, but only a few named trails (probe of 30 Oct 2026).

Each trail is a list of waypoints. Between two waypoints, the builder (`src/data/waypoint_graph.py`) follows the OSM
walk network only when both of these hold:
- both waypoints are within 1 km of the network;
- the OSM route is at most 3 × the straight distance.

Otherwise the leg is a straight line, counted 1.3 × longer for the bends of a mountain path. **Approximate share** =
straight legs and straight connectors to the network (`data/processed/graph_quality.json`):

| Trail | Mode | Waypoints (OSM node) | km | Approx. share | Sections |
|---|---|---|---|---|---|
| Pitawala Pathana | open_viewpoint | car park (O 5043035581) → plateau edge (A, placed by hand) | 1.0 | 93 % | 1 |
| Sera Ella | open_viewpoint | roadside start (A) → Sera Ella Water Fall (O 5043038322) | 0.9 | 98 % | 1 |
| Maningala trek | guided_permit | Knuckles Nature Camp (O 5107267912) → Manigala Camp Site (O 5106705620) → Maningala (O 4840490592) | 4.1 | 100 % | 5 |
| Gombaniya trek | guided_permit | Riverston (O 4112028263) → Knuckles-Kirigalpotta (O 7090910867) → Gombaniya (O 7090910868) | 11.0 | 100 % | 14 |
| Knuckles Waterfall trail | gate_slots | Deanston (A: Venture Camps area, O 5081166469) → Knuckles Waterfall (O 11133963006) | 3.6 | 5 % | 4 |
| Knuckles five peaks trek | guided_permit | Deanston (A) → Knuckles peak (O 1290267083) | 7.2 | 7 % | 9 |
| Dothalugala nature trail | gate_slots | Mini World's End (O 4840460417) → Dothalugala (O 7090910862) | 4.4 | 40 % | 6 |
| Duwili Ella trek | guided_permit | Kalupahana (O 6632682803) → Duwili Ella (O 13098242417) | 3.1 | 100 % | 4 |
| Lakegala trek | guided_permit | Meemure (O 14316293601) → Lakegala (O 5747559422) | 3.6 | 100 % | 5 |

**Not included yet:**
- Nitro Cave: no OSM feature found.
- Corbet's Gap: not named in OSM.
- Meemure village walks.
- Bambarella / Thangappuwa.

Add them once their trailheads are known. **Replace the approximate trails with GPS tracks** from the December visit
or from guides (plan K2). Section lengths matter: they set each section's capacity.

## 2. Visitors (simulator)

| What | Value | Why (A) |
|---|---|---|
| Visitors, ordinary weekday in season, all trails | 260 | Order of magnitude between Horton Plains (450) and Pekoe (120) |
| Weekend multipliers (Sat, Sun) | 2.4, 2.2 | Day trips by car and van from Kandy and Matale |
| Month multipliers | dry Jan–Apr and Jul–Sep, low Oct–Nov | Two monsoons over the range |
| Share per trail | Pitawala 30 %, Sera Ella 12 %, guided treks 4–10 % each | Open viewpoints draw most day visitors |
| Group size | 1 + Poisson(3) | Families and van groups |
| Last start of long treks | 07:30–10:00 | To be out before dark and the afternoon rain |
| Dwell at viewpoints / falls | 15–40 min | Photos, bathing at the falls |

Result: about 418 visitors a day on average, 1,012 at the 95th percentile and 2,244 at most (2022–2025 simulated with
real weather). **Field check:** weekend counts at Pitawala Pathana and Sera Ella in December.

## 3. Control

| Mechanism | Setting | Value |
|---|---|---|
| Guided permits | Guides on duty: Riverston / Deanston / Kalupahana / Meemure | 6 / 6 / 4 / 5 |
| | Group size limit, mean | 12, 6 |
| | Walking times (h): Maningala, Gombaniya, five peaks, Duwili Ella, Lakegala | 5, 8, 6.5, 5, 4 |
| | Slower: +2 % per person above 4; +25 % on a fully rainy day | |
| Overdue alarm | Late by more than max(45 min, 2.3 × 15 % of the trek time), up to 30 min sooner in rain | |
| Open viewpoints | Car park spaces: Pitawala 60, Sera Ella 20; 4 people per vehicle | |
| | A viewpoint section holds at least 40 people at once | |
| Campsites | Pitches: Knuckles Nature Camp 15, Manigala 10, Duwili Ella cave 6, Meemure Ganga Addara 12 | |
| Slot tickets | Knuckles Waterfall trail and Dothalugala nature trail, 06:00–12:00 | |

**To confirm with the Forest Department:**
- Which trails need a permit or a guide, and the fees.
- How many guides are registered per entry area.
- Opening hours.
- Rain closures (river crossings at Duwili Ella).
- Campsite rules.
- Parking at Riverston and Pitawala.

## 4. Known limits

- The simulator gives every trail the same group-size distribution. Guided groups (4–12 with a guide) and walk-up
  families are not told apart.
- Parking is estimated as people on the walk ÷ people per vehicle. Cars waiting on the road are not modelled.
- Weather is one point for the whole range (7.45 N, 80.80 E), although the eastern (Meemure) and western (Riverston)
  sides get different monsoons.
