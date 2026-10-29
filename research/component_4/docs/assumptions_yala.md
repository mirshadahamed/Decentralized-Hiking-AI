# Yala National Park (Block 1) – assumptions (21 Oct 2026)

Third park, on branch `feature/component-4-yala`. Config: `configs/parks/yala.yaml`; data in `data/yala/`, results in
`results/yala/`. Run anything with `$env:C4_PARK = "yala"`.

## Why Yala fits the component
- **Same problem, worse:** DWC caps nothing per track; on a leopard sighting dozens of jeeps gather on one stretch
  within minutes, and the Palatupana entrance queues at 06:00. Crowding is again **where** and **when**, not the daily total.
- **Same method:** a road graph from OSM, a forecast per section and hour, a Cifuentes capacity, entry slots per circuit.
- **What is new for the research:** vehicles instead of walkers, two daily sessions, an annual closure, and a
  bottleneck that **no calendar can predict** (sightings) – a direct test of what counts and the graph add (C1, C4).

## Graph (from OpenStreetMap, 21 Oct 2026)
- Jeep tracks and park roads (`highway = track | unclassified | tertiary | service | path`) in Block 1
  (81.36–81.56 E, 6.25–6.42 N); only the largest connected network is kept (OSM has unconnected track pieces).
- Landmarks are OSM tanks, lagoons and the two entrances. **35 sections of ~1.2 km**, 3 circuits:

| Circuit | Stops (OSM names) | Share (A) |
|---|---|---|
| Patanangala and Buthawa | Palatupana → Seethala Pokuna → Heenwewa → Gonagala → Buthawa → Patanangala, and back | 60 % |
| Southern tanks | Palatupana → Bembewa → Maliththa → Seethala → Palatupana (loop, either way) | 25 % |
| Katagamuwa circuit | Katagamuwa entrance → Arangamuwa → Panagammana → Heenwewa → back | 15 % |

- **Limitation:** OSM has no connected coastal track from Palatupana to Buthawa, so the classic coastal drive is
  approximated through the inland tanks. Real jeeps roam freely; circuits are the typical paths, to be checked with
  trackers / GPS logs on a field visit.

## Simulator (A = assumption to calibrate)
| Item | Value | Basis / how to calibrate |
|---|---|---|
| Unit | a jeep = 1 + Poisson(3.5) ≈ 4.5 people | (A) gate records give jeeps and tickets per day |
| Demand | 900 people on an ordinary weekday; weekend ×1.6–1.7, holiday ×1.6, Poya ×1.5; months ×0.7–1.3 | (A) gives ~420k visitors a year, busiest days ~3,800 people (~800 jeeps); **calibrate with DWC Yala gate totals** |
| Closure | 1 Sep – 15 Oct, no visitors | (A) DWC announces the drought closure each year |
| Sessions | 65 % at opening (06:00, queue before), 35 % between 14:00 and 15:30 | (A) |
| Speed | 15 km/h on the track (limit 25 km/h), ±15 % between jeeps; rain slows | (A) |
| Crowding | speed halves at 0.08 people per metre of track (~1 jeep per 55 m), never below 30 % | (A) |
| Beach stop | 25 min median at Patanangala | (A) |
| Sightings | 5 a day (Poisson), in 06:00–09:30 or 15:00–17:30, 4× more likely near Heenwewa, Gonagala, Seethala, Maliththa, Bembewa, Buthawa; visible ~30 min; each passing jeep stops ~12 min | (A) trackers' sighting logs; the key unknown |

## Capacity (Cifuentes, adapted to vehicles)
- Social factor with **jeeps** as groups: 5 people per jeep, 150 m between jeeps, 2 m of track per person (a jeep's
  footprint) → about 37 people (8 jeeps) on a 1.2 km section at once. (A) – DWC's own jeep-spacing rule replaces it.
- Beach stop and tank bunds hold more (60 people at once). Management capacity 0.7 as elsewhere.

## Control
Entry tickets per circuit and 30-min slot (06:00–15:30), 30 % kept for jeeps without booking. Gate advice: hold a
circuit or send the next jeeps to another one. Sighting jams cannot be planned; the live map and rangers' spot counts
are what reveal them.

## Sighting management (new for Yala)
Rangers / trackers report an animal (`POST /sightings`, app tab "Sightings"); the server answers with the rule and the
jeeps estimated near it from the gate entries, and names the circuits that avoid it (`GET /sightings/{day}`).
Rule (config `control.sighting_rule`, (A)): at most 10 jeeps stopped at once, 10 min each, first come first served;
a jeep that finds it full is moved on.

## Results (2025 season, simulation)
**Entry control** (`src.control.evaluate`, run `results/yala/20261021_231156_entry_control`):

| Policy | Over-capacity person-h | Admitted |
|---|---|---|
| No limit | 491,736 | 100 % |
| Daily quota (Cifuentes) | 87,844 (−82 %) | 55 % |
| Slot tickets | 427 (−99.9 %) | 29 % |
| Slot tickets + moving to a later slot / other circuit | 963 (−99.8 %) | 56 % |

All p < 10⁻⁵³ (Wilcoxon over days). The low admission share comes from the assumed jeep spacing (about 8 jeeps on a
1.2 km section at once): DWC's own spacing rule decides how many jeeps Block 1 can take, so it is the parameter to
confirm first. Sightings are not in this replay (they are below).

**Sighting management** (`src.control.evaluate_sightings`, run `results/yala/20261021_230925_sightings`):

| Rule at a sighting | Over-capacity person-h at sightings | Cut | Jeeps passing that got to stop |
|---|---|---|---|
| None (today) | 14,889 | – | 100 % |
| Cap 15 jeeps, 15 min | 11,549 | −22 % | 72 % |
| Cap 10 jeeps, 10 min | 9,976 | −33 % | 65 % |
| Cap 5 jeeps, 10 min | 8,345 | −44 % | 45 % |

All p < 10⁻³⁴ vs none (Wilcoxon over days). Sightings are ~3 % of the park's over-capacity time; the rest is the
06:00 convoy on the Palatupana trunk and the Patanangala stop, which slot tickets address. The cap is a trade-off
between crowding at the animal and the share of visitors who see it; 10 jeeps / 10 min is the default.

**Forecast benchmark (RQ1 for Yala)** (`src.run_benchmark`, run `results/yala/20261021_214852_benchmark`, 3 seeds
temporal, spatial CV 4 blocks × 1 seed). MAE in people per section per hour:

| Model | Every section counted | Held-out sections (spatial CV) |
|---|---|---|
| Historical average | 5.02 | 10.58 |
| SARIMA | 4.80 | – |
| LSTM | 3.93 | 8.89 |
| GRU (no graph) | **3.82** | 8.51 |
| ST-GNN | 3.87 | **8.51** |

Paired tests (Holm), ST-GNN vs: historical average −1.15 / −2.08 (p < 10⁻¹⁰); LSTM −0.06 / −0.38 (p < 10⁻⁵, better);
GRU without graph +0.05 (p < 10⁻⁶, worse) with counts, −0.003 (p = 0.93, tie) on held-out sections.
**Reading:** the networks beat the historical average by 23 % (counted) and 20 % (held out); the graph itself adds
nothing measurable at Yala, as in the base worlds of the other parks. Sighting jams are random in place and time, so
neither neighbours nor the calendar foresee them – they are handled by the sighting rule, not by the forecast.

## Not yet done for Yala
whether gate counts and the graph detect sighting jams (sparse-sensor
protocol on Yala), the RQ9 quota replay, calibration with DWC totals, and a field visit.
