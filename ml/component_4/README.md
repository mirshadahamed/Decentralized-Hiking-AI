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

## Run (PowerShell, from `ml/component_4`)
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

## Layout
| Path | What |
|---|---|
| `configs/default.yaml` | every parameter (seed, dates, simulator, training, capacity) |
| `src/data/` | graph, terrain, weather, calendar, dataset builder |
| `src/sim/simulator.py` | synthetic occupancy simulator |
| `src/eval/` | windows, temporal + spatial-block splits, metrics, t-tests |
| `src/models/` | ST-GNN (GCN+GRU), LSTM / no-graph variants, HA, SARIMA |
| `src/capacity/cifuentes.py` | carrying-capacity cascade, per trail |
| `src/planning/` | 90-day planning model, suggestions, lead-time backtest |
| `src/control/` | entry control: slot tickets (LP), live nowcast, booking, policy evaluation |
| `src/live/` | live mode: real-date inputs, live dataset, daily refresh and publishing |
| `src/api/` | FastAPI service, staff accounts, roles, audit log |
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
