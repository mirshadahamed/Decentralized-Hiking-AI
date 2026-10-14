# Component 4: Spatio-Temporal GNN for Bottleneck Forecasting
Owner: Weerasekera J.V (IT23343948)

Forecasts hourly hiker occupancy on each ~300 m segment of the Horton Plains loop for the next day,
then turns the forecast into a segment-level carrying capacity and a daily quota (Cifuentes cascade).
Built from open data only: OpenStreetMap, Copernicus DEM, Open-Meteo weather, Sri Lankan holiday/Poya calendar.

## Pipeline
```
OSM trail -> 26 segment graph -> DEM slope/TWI/Tobler time -> weather + calendar
          -> synthetic occupancy simulator (calibrated target)
          -> HA / SARIMA / LSTM / GRU / ST-GNN (GCN+GRU) -> RMSE, MAE, paired t-test
          -> Cifuentes PCC -> RCC -> ECC -> forecast_<date>.json for Module 3 and the dashboard
```

## Run (PowerShell, from `ml/component_4`)
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m src.data.build_dataset        # downloads + simulation (~1 min after first run)
.venv\Scripts\python.exe -m pytest -q                     # shape, leakage and seed tests
.venv\Scripts\python.exe -m src.run_benchmark             # all models, both protocols (long, CPU)
.venv\Scripts\python.exe -m src.serve.predict --date 2025-05-12
.venv\Scripts\python.exe -m src.report.figures --date 2025-05-12
```
`--quick` on `run_benchmark` runs 1 epoch and 1 seed to check the pipeline.

## Dashboard
```powershell
.venv\Scripts\python.exe -m streamlit run dashboard/app.py      # opens http://localhost:8501
```
Pages: Overview · Daily forecast (map, hour-by-hour crowding, quota, JSON download, no-weather fallback) ·
Trail and data · Simulator · Model comparison · Capacity method. Without model checkpoints on the machine,
the forecast page uses the historical-average fallback.

## Layout
| Path | What |
|---|---|
| `configs/default.yaml` | every parameter (seed, dates, simulator, training, capacity) |
| `src/data/` | graph, terrain, weather, calendar, dataset builder |
| `src/sim/simulator.py` | synthetic occupancy simulator |
| `src/eval/` | windows, temporal + spatial-block splits, metrics, t-tests |
| `src/models/` | ST-GNN (GCN+GRU), LSTM / no-graph variants, HA, SARIMA |
| `src/capacity/cifuentes.py` | carrying-capacity cascade |
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
