# Model card and data card – Component 4 ST-GNN (21 Oct 2026)

## Model card

| | |
|---|---|
| **Model** | ST-GNN: GCN (space) + GRU (time) + decoder on future covariates; `src/models/stgnn.py` |
| **Version in the app** | Gate-only ST-GNN from the latest sparse-sensor run (`LATEST_SPARSE`, seed 42) at each park; `live.model_input: all` switches back to the benchmark model |
| **Size** | 13,665 parameters (Horton Plains), ~100 KB ONNX / ~175 KB daily phone pack with inputs |
| **Task** | Day-ahead (00:00) forecast of people on each trail segment for each hour of the next 24 h |
| **Inputs** | Deployed (G6): last 24 h of **gate counts only**, sensed flag, 17 hourly covariates (calendar, Poya, weather), 13 segment descriptions. Research benchmark: counts of every segment |
| **Output** | People per segment per hour; with Cifuentes: safe number per trail, sections over capacity, % chance of crowding |
| **Training data** | Synthetic occupancy 2022–23 from the calibrated simulator (validation 2024, test 2025) |
| **Training** | Masked L1 over open hours, Adam lr 0.002, batch 64, ≤ 20 epochs, early stopping on 2024; seeds 42–44 |
| **Intended use** | Planning aid for park officers (quota, slots, gate holds) and advice to hikers; always with a human decision |
| **Not intended for** | Safety-critical real-time decisions on its own; parks without a calibrated simulator; counting individuals |
| **Users** | DWC officers, rangers, tour operators, hikers / pilgrims; Module 3 (safety assistant) |

### Performance (test year 2025, simulation)
| Measure | Horton Plains | Adam's Peak |
|---|---|---|
| MAE, every segment counted (3 seeds) | 1.42 (LSTM 1.42, HA 1.60) | 3.80 (LSTM 3.83, HA 10.89) |
| MAE, held-out segments (spatial CV, 3 seeds) | **2.54** (LSTM 2.59, HA 4.20; p < 10⁻¹²) | 9.63 (LSTM 8.23; worse at the summit block) |
| MAE, interior segments with gate counts only | 1.45 (LSTM 1.44, HA 1.63) | 4.00 (LSTM 3.87, HA 11.28) |
| Over-capacity F1, all counted / held out | 0.80 / 0.29 | 0.85 / 0.54 |
| Quota from its forecast vs static (equal visitors) | −27 % over-capacity person-h | −24 % (p < 10⁻⁷) |
| Latency | 2 ms ONNX (1 laptop core); ~150 ms Dart | same |

### Known limitations
1. **Synthetic target.** All numbers are against the simulator; field counts in December check it (criteria A1–A3,
   `field_validation_protocol.md`).
2. **Peaks are under-forecast** on segments without counts (recall ≤ 0.33 at Horton Plains). Decisions use the
   busy case (P90) or the calibrated chance of crowding.
3. **Graph gain is small** (2 % on held-out segments at Horton Plains) and absent with every segment counted.
4. **Summit queue (Adam's Peak):** the graph hurts there; the queue depends on the final steps' capacity.
5. **Weather:** day-ahead tests use observed weather (an upper bound) except in the S1 world.
6. **Transfer:** a model from one park fails on another unchanged; pretraining helps only with 30–90 days at Horton.

### Ethical considerations
No personal data; bookings are codes; counts are numbers. Advice is spread across phones so it does not create a
new crowd (RQ8). Officers can override every quota (audited). Every output states what it is based on.

---

## Data card

| Source | What | Licence / terms | Where in the code | Personal data |
|---|---|---|---|---|
| OpenStreetMap (via Overpass / OSMnx) | Footpaths, viewpoints, trailheads | ODbL 1.0 – "© OpenStreetMap contributors" (shown on every map in the app) | `src/data/graph.py` | None |
| Copernicus GLO-30 DEM | Elevation → slope, TWI, Tobler time | Copernicus DEM licence (free, attribution: "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA") | `src/data/terrain.py` | None |
| Open-Meteo (ERA5 archive, forecast) | Hourly weather | CC BY 4.0 – "Weather data by Open-Meteo.com" | `src/data/weather.py`, `src/live/inputs.py` | None |
| NASA POWER | Daily rain (cross-check) | Public, NASA attribution | `src/data/rain_check.py` | None |
| `holidays` package + estimated Poya days | Calendar | MIT (package); Poya estimated after 2026 | `src/data/calendar_features.py` | None |
| METR-LA, PEMS-BAY | Traffic speeds for pretraining | Public research datasets (DCRNN release) | `src/pretrain/traffic.py` | None |
| Simulator output | Training / test target | Generated; parameters in `configs/` | `src/sim/simulator.py` | None |
| Ranger spot counts, gate check-ins | Live counts | Collected by the park | `src/serve/field_counts.py`, `src/control/booking.py` | None (numbers and staff usernames only) |
| DWC daily totals (optional) | Real daily visitors | On request from DWC | `data/live/dwc_daily_totals.csv` | None |

`data/` is not committed; `python -m src.data.build_dataset` downloads and rebuilds everything from these sources.
