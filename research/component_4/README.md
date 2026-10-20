# Component 4: Spatio-Temporal GNN for Bottleneck Forecasting
Owner: Weerasekera J.V (IT23343948)

Forecasts hiker occupancy on each ~300 m segment of the three Horton Plains trails (World's End loop,
Kirigalpotta, Thotupola Kanda): hourly for tomorrow, and as a range for any day up to 90 days ahead.
Turns the forecast into a carrying capacity and quota per trail (Cifuentes cascade) and suggests quieter
days, start times or trails.
Built from open data only: OpenStreetMap, Copernicus DEM, Open-Meteo weather, Sri Lankan holiday/Poya calendar.

## Pipeline
```
OSM trails -> 48-segment network (3 trails) -> DEM slope/TWI/Tobler time -> weather + calendar
           -> synthetic occupancy simulator with trail choice (calibrated target)
           -> day-ahead: HA / SARIMA / LSTM / GRU / ST-GNN (GCN+GRU) -> RMSE, MAE, paired t-test
           -> 2-90 days: planning model (calendar + climatology + recent level, P10/P50/P90)
           -> Cifuentes PCC -> RCC -> ECC per trail -> suggestions
           -> forecast_<date>.json, outlook_<issue>.json, plan_<issue>_<target>.json (Module 3, dashboard)
```

## Run (PowerShell, from `research/component_4`)
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m src.data.build_dataset        # downloads + simulation (~1 min after first run)
.venv\Scripts\python.exe -m pytest -q                     # shape, leakage and seed tests
.venv\Scripts\python.exe -m src.run_benchmark             # all models, both protocols (long, CPU)
.venv\Scripts\python.exe -m src.serve.predict --date 2025-05-12
.venv\Scripts\python.exe -m src.planning.backtest                 # planning accuracy by lead time
.venv\Scripts\python.exe -m src.serve.outlook --issue 2025-03-01 --target 2025-05-12
.venv\Scripts\python.exe -m src.control.evaluate --sweep          # entry control: 4 policies + capacity trade-off
.venv\Scripts\python.exe -m src.report.figures --date 2025-05-12
```
`--quick` on `run_benchmark` runs 1 epoch and 1 seed to check the pipeline.

## Live mode and API (real dates)
```powershell
.venv\Scripts\python.exe -m src.live.refresh                     # every evening: weather, history, outlook, slot plans
.venv\Scripts\python.exe -m src.api.users add --username ranger1 --role ranger   # staff accounts (password prompted)
.venv\Scripts\python.exe -m uvicorn src.api.app:app --port 8000  # API, docs at http://localhost:8000/docs
```
Weather: observed to yesterday, Open-Meteo forecast for 16 days, typical weather after. Visitor history after
2025 is simulated with the real weather until DWC totals (`data/live/dwc_daily_totals.csv`) or gate data are
connected; every day carries its source. Published plans follow the freeze rule (never fewer places than
already booked). Roles: ranger < officer < admin, checked by the API on every call; actions are audited.

## Several parks (Horton Plains, Adam's Peak)
Each park has a config in `configs/parks/<park>.yaml` that overrides `configs/default.yaml`; `C4_PARK` picks the
park (default `horton_plains`). Other parks keep their data in `data/<park>/` and results in `results/<park>/`.
```powershell
$env:C4_PARK = "adams_peak"
.venv\Scripts\python.exe -m src.data.build_dataset         # graph, terrain, calendar, simulated history
.venv\Scripts\python.exe -m src.control.evaluate_advisory  # start times / halfway checks on the 2025 season
.venv\Scripts\python.exe -m src.live.refresh               # outlook + advisory.json
Remove-Item Env:C4_PARK                                    # back to Horton Plains
.venv\Scripts\python.exe -m src.api.serve_all              # one API per park + gateway on http://localhost:8000
```
Gateway: `GET /parks`, and `/parks/<park>/...` forwards to that park's API (ports 8101, 8102, …).
Adam's Peak assumptions: `docs/assumptions_adams_peak.md`.

**Adding a destination** (no app change needed: the app's trip planner lists whatever `/parks` returns):
1. Copy `configs/parks/adams_peak.yaml` to `configs/parks/<new_id>.yaml`; set `destination` (kind, region,
   summary, elevation, best_time, getting_there, facts, accent), `area` (bbox, routes, trail names) and
   `simulator` / `control` (`booking_mode: required` = slot tickets, `advisory` = recommended start times).
   A new `kind` (e.g. `waterfall`) becomes a new filter chip in the app.
2. `$env:C4_PARK = "<new_id>"`, then `src.data.build_dataset`, `src.live.refresh` and staff accounts (`src.api.users`).
3. Restart `src.api.serve_all`: the new park gets the next port and appears in the app.

## Dashboard (research / examiner view)
```powershell
.venv\Scripts\python.exe -m streamlit run dashboard/app.py      # opens http://localhost:8501
```
Pages: Overview · Plan a visit (90-day outlook, range, suggestions) · Book a slot (reserve an entry time,
alternatives when full, gate check) · Daily forecast (map, hour-by-hour crowding, quota per trail, JSON download,
no-weather fallback) · Entry control (tickets per slot, before/after, live traffic lights, year-long evaluation) ·
Trail and data · Simulator · Model comparison · Capacity method.

## How overcrowding is prevented
Tickets per trail and 30-minute entry slot. A ticket fixes a trail and an entry time, so the simulator tells us
where its holder will be. A linear programme issues tickets only while every segment stays under its safe capacity
in every half hour (`src/control/slots.py`). When a slot is full, visitors get a later slot, another trail with room
or another day, and can book weeks ahead (`src/control/booking.py`). On the 2025 test year (simulation), this removes
> 99 % of the person-hours over capacity; a daily quota alone removes 73 % (`results/*_entry_control/`). Without model checkpoints on the machine,
the forecast page uses the historical-average fallback.

**Adam's Peak (no tickets).** The danger is the queue on the final steps below the summit (~25 people/min reach
the terrace). Pilgrims get **recommended start times** per route (expected wait ≤ 20 min, summit before sunrise,
spread so the advice does not create a new peak), and officers at each route's **halfway checkpoint** count
passers and hold groups when the expected queue is too long (`src/control/advisory.py`, `GET /advisory/{day}`,
`POST /checkpoints`). 2025 season (simulation): start times cut waiting by 22 %; halfway checks remove the waiting
on the final steps (`results/adams_peak/*_advisory/`).

## Research evaluation
RQ1 graph vs no graph, RQ2 transfer between parks, RQ3 value of the forecast for crowd control, RQ4 sensitivity:
`docs/evaluation_results.md`. Scripts: `src.run_benchmark`, `src.eval.transfer`,
`src.control.evaluate_forecast_value`, `src.control.evaluate_advisory --sweep`.

RQ5 traffic pretraining, RQ6 on-device inference, RQ7 field validation:
```powershell
.venv\Scripts\python.exe -m src.pretrain.traffic                # METR-LA -> PEMS-BAY (data/external/traffic/*.h5)
.venv\Scripts\python.exe -m src.eval.pretrain_transfer          # RQ5: pretrained vs scratch, both parks (hours)
.venv\Scripts\python.exe -m src.edge.export                     # RQ6: ONNX, int8, latency, memory
.venv\Scripts\python.exe -m src.edge.pack --fixture             # test pack for the Flutter engine test
.venv\Scripts\python.exe -m src.eval.field_validation data/field/horton_plains/*.csv   # RQ7, after the visits
```
Protocol and pre-registered criteria: `docs/field_validation_protocol.md`. The live refresh also publishes
`edge_pack.json` (`GET /edge/pack`), which the app runs on the phone for tomorrow's forecast.

## Layout
| Path | What |
|---|---|
| `configs/default.yaml` | every parameter (seed, dates, simulator, training, capacity) |
| `configs/parks/` | per-park overrides (`adams_peak.yaml`) |
| `src/data/` | graph, terrain, weather, calendar, dataset builder |
| `src/sim/simulator.py` | synthetic occupancy simulator |
| `src/eval/` | windows, temporal + spatial-block splits, metrics, t-tests |
| `src/models/` | ST-GNN (GCN+GRU), LSTM / no-graph variants, HA, SARIMA |
| `src/capacity/cifuentes.py` | carrying-capacity cascade, per trail |
| `src/planning/` | 90-day planning model, suggestions, lead-time backtest |
| `src/control/` | entry control: slot tickets (LP), live nowcast, booking, policy evaluation; `advisory.py` start times + halfway checks (pilgrim sites) |
| `src/live/` | live mode: real-date inputs, live dataset, daily refresh and publishing |
| `src/api/` | FastAPI service, staff accounts, roles, audit log; `gateway.py` + `serve_all.py` for several parks |
| `src/serve/predict.py` | forecast JSON (with historical-average fallback) |
| `dashboard/` | Streamlit dashboard (`app.py` + one file per page in `views/`) |
| `docs/` | development plan, assumptions, decision log |
| `results/` | one folder per run (config, git hash, log, metrics, stats) + figures |

`data/` and model checkpoints are not committed.

## Results
See the newest `results/<run>/metrics_temporal.csv`, `metrics_spatial.csv` and `stats.json`.

## Limitations
The training target is synthetic (no segment counts exist for the park). Every assumption is listed in
`docs/assumptions.md`, and field counts will be used to calibrate it. Weather for the forecast day is
currently the observed weather (a perfect forecast).
