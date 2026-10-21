# Component 4 – Technical design (as built, 21 Oct 2026)

How the component is put together, how each part works inside, and why each technology was chosen.
Replaces Figure 2 of the proposal, which showed the plan before the build.

---

## 1. Architecture

```
                         ┌───────────────────────── offline (research, once per run) ─────────────────────────┐
 OpenStreetMap ─┐        │                                                                                     │
 Copernicus DEM ├─► src/data  ──► trail graph (48 / 57 segments) + static features [N, 13]                     │
 Open-Meteo     ├─►          ──► hourly covariates [T, 17] (calendar, Poya, weather)                         │
 holidays/Poya ─┘        │                     │                                                               │
                         │                     ▼                                                               │
                         │   src/sim  ──► synthetic occupancy target [T, N]  (groups walk the graph)            │
                         │                     │                                                               │
 METR-LA, PEMS-BAY ──►   │   src/pretrain ─► pretrained GCN+GRU core ──┐                                       │
                         │                     ▼                       ▼                                       │
                         │   src/train + src/models ──► HA · SARIMA · LSTM · GRU-no-graph · ST-GNN             │
                         │                     │                                                               │
                         │   src/eval ──► RMSE / MAE, paired tests (Holm), spatial-block CV, bottleneck F1,    │
                         │                sparse sensors, transfer, pretraining  ──► results/<time>_<tag>/     │
                         └─────────────────────┬───────────────────────────────────────────────────────────────┘
                                               ▼
                         ┌───────────────────────── live (every evening: src.live.refresh) ───────────────────┐
                         │ real dates: observed weather + 16-day forecast + calendar                           │
                         │ day-ahead ST-GNN forecast [24 h, N]  ·  2–90-day planning model (P10/P50/P90)      │
                         │ src/capacity  Cifuentes PCC → RCC → ECC per segment, quota per trail                │
                         │ src/control   slot tickets (LP) · booking · gate advice · Adam's Peak start times   │
                         │ publish: forecast JSON, outlook, edge_pack.json (weights + inputs), Module 3 feed   │
                         └─────────────────────┬───────────────────────────────────────────────────────────────┘
                                               ▼
              src/api (FastAPI per park + gateway, roles, audit)  ──►  Flutter app (lib/features/component_4)
                                                                       visitor · ranger · officer · admin
                                                                       ST-GNN runs on the phone in Dart (offline)
              dashboard/ (Streamlit research view)                     Module 3 reads /module3/feed (JSON Schema)
```

Every park-specific number is in `configs/default.yaml` + `configs/parks/<park>.yaml`. `C4_PARK` selects the park.

### Code layout and responsibilities
| Package | Responsibility | Key files |
|---|---|---|
| `src/data` | OSM graph, DEM terrain, weather, calendar, dataset builder | `graph.py`, `terrain.py`, `weather.py`, `calendar_features.py`, `build_dataset.py` |
| `src/sim` | Synthetic occupancy (training target), default and realistic (S1) world | `simulator.py` |
| `src/models` | ST-GNN (and its no-graph / LSTM variants), historical average, SARIMA | `stgnn.py`, `baselines.py` |
| `src/train` | Masked training loop, early stopping, freezing for transfer | `trainer.py` |
| `src/eval` | Windows and splits, metrics, paired tests, every research question | `data.py`, `metrics.py`, `bottlenecks.py`, `sparse_sensors.py`, `transfer.py`, `pretrain_transfer.py`, `uncertainty.py`, `field_validation.py` |
| `src/pretrain` | METR-LA / PEMS-BAY pretraining of the same core | `traffic.py` |
| `src/capacity` | Cifuentes cascade | `cifuentes.py` |
| `src/planning` | 2–90-day outlook, suggestions, lead-time backtest | `model.py`, `planner.py`, `backtest.py` |
| `src/control` | Slot LP, booking, gate advice, quota rules, Adam's Peak advisory, policy replays | `slots.py`, `booking.py`, `gate_advice.py`, `advisory.py`, `evaluate_*.py` |
| `src/live` | Real-date inputs and the nightly refresh | `inputs.py`, `dataset.py`, `refresh.py` |
| `src/serve` | JSON outputs: forecast, outlook, Module 3 feed, records, capacity panel, field counts | `predict.py`, `outlook.py`, `module3.py`, … |
| `src/edge` | ONNX export, latency / memory, phone pack | `export.py`, `pack.py` |
| `src/api` | FastAPI app, accounts, roles, audit, gateway for several parks | `app.py`, `auth.py`, `gateway.py`, `serve_all.py` |
| `src/report` | Figures, PP1 slides (numbers read from `results/`), screenshot fixtures | `figures.py`, `slides.py`, `app_fixtures.py` |
| `lib/features/component_4` | Flutter app: `models`, `data` (API client), `services` (offline stores), `domain` (Dart ST-GNN, bottleneck maths, walk advice), `presentation` (screens) | `domain/edge_forecaster.dart` |

### Design principles
1. **Configuration, not code, per park.** Adding Adam's Peak needed one YAML file; the app lists whatever `/parks` returns.
2. **One source of truth for numbers.** Slides and docs read `results/`; every run folder stores config, seed, git hash.
3. **Contracts between modules.** Module 3 gets a versioned JSON (`docs/schema/c4_module3_feed.schema.json`) checked by tests.
4. **Offline first.** The phone keeps the last pack and runs the network itself; every screen says what its numbers are based on.
5. **Honest fallbacks.** No weather forecast → historical average; no model checkpoint → historical average; labelled in the output (FR5, NFR2).

---

## 2. Data and graph

- **Graph.** OSM footpaths inside the park's bounding box are split into ~300 m (Horton Plains) / ~500 m (Adam's
  Peak) segments. Each segment is a **node**; walking connections are **edges** (102 directed edges at Horton). A
  road link between two trailheads (4.2 km drive) is an edge with weight 0.5, so the model knows it is weaker.
- **Static features per node (13):** length, mean |grade|, slope, TWI (wetness), elevation, Tobler walking time
  both ways, viewpoint flag, access-point flag, dwell minutes, minutes from trailhead, passes per visit, visitor
  share. Segments are **described, not named**, so the same network shape fits any park (needed for transfer).
- **Covariates per hour (17):** hour / day-of-week / month as sin–cos, open flag, weekend, public holiday, Poya,
  long weekend, school holiday, rain (log1p), temperature, humidity, cloud, wind.
- **Terrain.** Copernicus 30 m DEM → slope, TWI = ln(a / tan β) (a = upslope area, β = slope), Tobler's hiking
  function v = 6·e^(−3.5·|grade + 0.05|) km/h.
- **Splits.** Train 2022–23, validate 2024, test 2025. Scalers are fitted on training years and sensed segments only.

## 3. Training target: the simulator
Every group is simulated: daily demand (calendar × season × morning rain × noise) → groups (1 + Poisson(2.2)) →
gate arrival time → trail choice → walk segment by segment (Tobler × rain slowdown × crowd slowdown) + dwell at
viewpoints. Occupancy = mean people on a segment in an hour. Each day is simulated twice so the crowd slowdown
uses the first pass's density. Every number is in YAML and justified in `assumptions.md`.

**S1 realistic world** (`build_dataset --world s1`): persistent busy / quiet spells (AR(1), φ = 0.7), tour-bus
bursts (0.4 per day, 30–90 people), shifted arrival peaks (sd 40 min), changing route shares, incidents that slow
one segment, and a **forecast** instead of observed weather as model input. It exists because in the default world
the calendar explains everything, so sensors and the graph had nothing to add (RQ10).

## 4. The ST-GNN (`src/models/stgnn.py`)

Input window L = 24 h, horizon H = 24 h, hidden size 32, **13,665 parameters** (~100 KB).

| Step | Operation | Shape |
|---|---|---|
| Inputs | past counts + sensed flag + covariates + static features | x_past [B, 24, N, Fp] |
| Embed | Linear → ReLU | [B, 24, N, 32] |
| Space 1 | DenseGCNConv with **adjacency masked to sensed senders** (residual) | [B, 24, N, 32] |
| Space 2 | DenseGCNConv on the full graph (residual) | [B, 24, N, 32] |
| Time | GRU over the 24 h, one sequence per node; keep the last state | [B, N, 32] |
| Space 3 | DenseGCNConv spreads the temporal state (residual) | [B, N, 32] |
| Future | Linear on next-24-h covariates (weather forecast, calendar) | [B, 24, N, 32] |
| Head | concat → Linear → ReLU → Linear | ŷ [B, 24, N] |

- **GCN layer:** H' = D̃^(−½) Ã D̃^(−½) H W, Ã = A + I (each segment averages itself and its neighbours, weighted
  by edge strength). Dense form because N ≤ 57: faster than sparse message passing and identical.
- **Missing counts:** a segment without counts is fed zeros; in the first layer its column of A is zeroed, so it
  only *receives*. Otherwise zeros would look like "empty" to the neighbours.
- **Loss:** masked L1 (MAE) over open hours (06–18) and over segments with a target; Adam, lr 0.002, batch 64,
  20 epochs, early stopping (patience 4) on 2024.
- **Ablations from the same class:** `use_graph=False` replaces each GCN with a per-node Linear (GRU-no-graph);
  `rnn="lstm"` gives the LSTM baseline. So "graph vs no graph" changes only the graph.
- **Why GCN + GRU** and not DCRNN / STGCN / ASTGCN: a 48-node graph and a few thousand training windows cannot
  support attention (ASTGCN) or diffusion over many hops (DCRNN) without overfitting; GCN + GRU is the smallest model
  of the family that still has the two parts (space, time) needed for the ablation, and it exports to ONNX and to a
  short Dart loop. ASTGCN's periodic inputs are a planned improvement (G8).

### Baselines
- **Historical average:** mean by day type (3) × hour × segment from the training years (what a static rule knows).
- **SARIMA(1,0,1)(1,1,1)₂₄:** per segment, fitted on the last 60 days of the training period, then filtered on the
  14 days before each forecast.
- **LSTM / GRU-no-graph:** the same network with the graph removed.

### Transfer and domain adaptation
- **Pretraining** on METR-LA (207 sensors) then PEMS-BAY (325): target = congestion (1 − speed / free flow), same core.
- **Fine-tuning:** start from the pretrained weights, train everything.
- **Frozen core:** keep `g1, g2, rnn, g_out` fixed, train only input, future and head layers (`trainer.FREEZE_CORE`).
- **Zero-shot:** pretrained weights, only the output scale fitted on 30 days.

## 5. Evaluation
| Protocol | What it tests |
|---|---|
| Temporal | Every segment counted; test 2025 day-ahead from midnight |
| Spatial block CV | 4 contiguous blocks; one held out at a time: no history and no training loss there |
| Sparse sensors (RQ10) | Only gate counts (or none) as input; the target trains every segment |
| Bottleneck events (RQ1b) | Over-capacity segment-hours: precision, recall, F1, with bootstrap intervals over days |
| Decision replays (RQ3, RQ8, RQ9) | The 2025 visitors replayed under each policy; over-capacity person-hours |
| Statistics | Paired t-test and Wilcoxon over **days** (hours are correlated), Holm correction, effect size d_z |
| Seeds | 42, 43, 44; every run stores config + git hash |

## 6. Capacity: Cifuentes cascade (`src/capacity/cifuentes.py`)
Per segment s, visits per day:
- PCC_s = (L_s / 1 m) × (open minutes / visit minutes_s)
- RCC_s = PCC_s × (1−FCsoc)(1−FCero)(1−FCacc)(1−FCpre)(1−FCwet)(1−FCcond) × **(1−FCcrowd_s)**
- ECC_s = RCC_s × MC (management capacity 0.7)
- Trail quota = min_s ECC_s (the most limiting segment); park quota = sum over trails.

FCsoc: space kept empty between groups (groups of 10, 50 m apart). FCero: share of wet-prone ground (TWI). FCacc:
share of 10–20 % and > 20 % grades. FCpre: share of open hours with forecast rain. **FCcrowd_s (this project): share
of open hours in which the forecast occupancy exceeds what the segment holds at once** – this is where the ST-GNN
enters the cascade (objective O5). FCwet, FCcond: ground still wet, officer-reported condition.

**Quota rules** (officer panel, `booking.resolve_quota`): forecast-driven (default), weather only, same all year
(static), or the officer's own number. RQ9 compares them.

## 7. Control
- **Slot tickets (Horton Plains):** for each trail and 30-min slot, the simulator gives where a ticket-holder will
  be in each half hour (a response matrix). A linear programme (SciPy HiGHS) maximises tickets subject to every
  segment staying under 90 % of its capacity in every half hour, within the daily quota, keeping 20 % for walk-ins.
- **Gate advice:** from the people already through the gate and the coming slots, walk everyone forward at usual
  speeds; if a section goes over capacity in the next 2 h, say "hold entries to X for N min" or "send the next
  groups to Y".
- **Adam's Peak:** recommended start times per route (wait ≤ 20 min, summit before sunrise, spread so the advice
  does not create a new peak) and holds at halfway checkpoints from rangers' counts.
- **Walk advice on the phone:** each phone draws one of the good options weighted by room left (spread, RQ8).

## 8. On the phone
`src.edge.pack` publishes `edge_pack.json` each evening (weights + scaled inputs, ~175 KB). The app stores it;
`domain/edge_forecaster.dart` runs the same forward pass in plain Dart (≤ 0.0001 people from PyTorch; ~150 ms in
the test runner). ONNX export runs in 2 ms on one laptop core; int8 quantisation was tested and rejected (saves 2 KB,
error +25 % at Adam's Peak, −0.3 % at Horton Plains). A calibration table P(really over | forecast fullness) gives "% chance of crowding".

## 9. Service and security
FastAPI, one process per park plus a gateway (`/parks/<park>/...`). Roles ranger < officer < admin checked on every
call; salted scrypt password hashes, lockout for 15 min after 5 failed logins, audit log of every staff action, SQLite storage.
No personal visitor data: bookings carry a code, not a name (NFR5).

## 10. Technologies and why
| Area | Technology | Why this one |
|---|---|---|
| Graph learning | PyTorch 2 + PyTorch Geometric (`DenseGCNConv`) | standard for ST-GNNs; dense layer is exact and fast for N ≤ 57 |
| Baselines | statsmodels SARIMAX, LSTM / GRU in PyTorch | the proposal's mandatory comparisons |
| Geo | OSMnx, GeoPandas, Shapely, Rasterio, PyProj | open data, reproducible downloads |
| Planning | scikit-learn gradient-boosted quantile regression (P10 / P50 / P90) | inputs that exist weeks ahead; honest ranges |
| Optimisation | SciPy `linprog` (HiGHS) | exact LP, no licence |
| Edge | ONNX Runtime, pure-Dart forward pass | offline on any phone, no native plugin |
| Service | FastAPI, Uvicorn, SQLite | typed, self-documenting API (`/docs`); no server to install |
| App | Flutter (Android / web) | one code base; team's framework |
| Research view | Streamlit | examiner dashboard in Python |
| Quality | pytest, ruff, flutter analyze / test, GitHub Actions | tests, lint and CI on every change |
