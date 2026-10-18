# Component 4 – Development Plan

ST-GNN for micro-spatial bottleneck forecasting and dynamic carrying capacity, Horton Plains.
Source documents: Proposal Report (J26-IT-363, IT23343948) and the PP1 mark sheet (IT4010).

---

## 1. What has to exist, and by when

**Deliverables promised in the proposal (objectives 2.2, FR1–FR5, NFR1–NFR5)**

| # | Deliverable | Proposal ref |
|---|---|---|
| D1 | Trail graph (25–40 nodes) from OSM, with slope + TWI from DEM, weather and calendar features | Obj 1, FR1 |
| D2 | Calibrated synthetic hourly occupancy target, later checked against manual field counts | Obj 2 |
| D3 | Baselines: historical average, ARIMA, LSTM | Obj 4, §3.3 |
| D4 | ST-GNN pretrained on METR-LA / PEMS-BAY / PeMS04/08, domain-adapted to the trail graph | Obj 3 |
| D5 | Evaluation: RMSE, MAE, paired t-test (p < 0.05), spatial block cross-validation | Obj 4, §3.4–3.5 |
| D6 | Cifuentes PCC → RCC → ECC cascade fed by the forecast | Obj 5, FR3 |
| D7 | Quantised on-device model, latency < 2 s | Obj 6, NFR1 |
| D8 | Versioned JSON output for Module 3 and the dashboard, with the synthetic-target disclaimer | FR4, FR5 |
| D9 | Fallback to historical average when no fresh weather is available | NFR2 |

**Timeline anchor.** The Gantt chart gives Component 4 months 3–8. Taking month 1 as September 2026,
that is **November 2026 – April 2027**. Today is 14 Oct 2026. PP1's exact date is not in either
document; this plan assumes **early–mid December 2026**. Confirm the date and shift the weeks below.

**What PP1 rewards (mark sheet weights)**
- Solution Implementation (40%): ~50% completion with no delay (30% of that), design (20%), standards and
  best practices (20%), user requirements (20%), risk mitigation (10%).
- Knowledge and technologies (25%): show you understand GCN, GRU, transfer learning and Cifuentes in depth.
- Proven gap / proof of concept (10%, 70% of it is proof of concept).
- Communication (15%) and commercialisation (10%).

**So the strategy is: build a thin, working end-to-end slice first**
(graph → simulator → baselines → ST-GNN → metrics → Cifuentes number) before PP1, then deepen each stage.
A working pipeline with rough parts scores better on "proof of concept" and "completion" than
one polished stage and nothing after it.

---

## 1a. PP1 sprint (8 days, from 14 Oct 2026) – replaces the week numbers below until PP1

| Day | Work | Status |
|---|---|---|
| 1 | Graph (OSM, 26 segments), DEM terrain, weather, calendar, simulator, dataset | done |
| 1 | Evaluation splits, HA, SARIMA, LSTM, GRU-no-graph, ST-GNN, t-tests, Cifuentes v1, forecast JSON, tests | done (code) |
| 2 | Full benchmark run (both protocols, 3 seeds); read results; fix anything odd | |
| 3 | Figures; check the simulator against any public Horton Plains visitor figures; adjust `base_daily_visitors` | |
| 4 | Supervisor check-in: decisions marked *pending* in `decisions.md`, especially the Cifuentes link | |
| 5 | Optional: small METR-LA pretraining test on Colab (proof that transfer works mechanically) | |
| 6–7 | Slides (map → simulator → results → capacity JSON demo), rehearse the Q&A on assumptions | |
| 8 | Buffer; final rerun from a clean clone to prove reproducibility | |

What is deliberately left for after PP1: field counts, full pretraining/domain adaptation, quantisation, integration.

---

## 2. Target layout (`research/component_4/`)

```
src/
  config.py            # paths, seeds, constants (one place)
  utils/seed.py        # set_seed(): python, numpy, torch, cuDNN flags
  data/graph.py        # OSM -> densified trail graph (D1)
  data/terrain.py      # DEM -> slope, TWI per node
  data/weather.py      # Open-Meteo archive + forecast, cached
  data/calendar.py     # weekday, public/school holidays, Poya days
  sim/simulator.py     # synthetic occupancy (D2)
  sim/calibrate.py
  models/baselines.py  # HA, ARIMA, LSTM (D3)
  models/stgnn.py      # GCN + GRU (D4)
  train/pretrain.py    # METR-LA / PEMS-BAY
  train/finetune.py
  eval/cv.py           # spatio-temporal block splits (D5)
  eval/metrics.py      # RMSE, MAE, paired t-test
  capacity/cifuentes.py  # D6
  export/quantise.py   # D7
  serve/predict.py     # D8, D9: forecast + capacity JSON
configs/*.yaml         # one file per experiment
data/  (git-ignored)   raw/, interim/, processed/
results/               metrics CSV/JSON, figures, run logs
docs/                  assumptions.md, decisions.md, this plan
tests/                 shape and leakage tests
```

Libraries to add to `requirements.txt` as they are needed: `torch-geometric-temporal` (METR-LA/PEMS-BAY loaders),
`pysheds` or `richdem` (TWI), `requests-cache`, `pyyaml`, `scipy`, `onnx`, `onnxruntime`, `pytest`.
Pin exact versions once the environment works (best-practice evidence for PP1).

---

## 3. Phases

### Phase 0 – Foundations (week of 19 Oct, 2–3 days)
- [ ] Create `.venv`, install, pin versions; check `torch_geometric` imports on Windows (CPU build is fine for now).
- [ ] `config.py`, `utils/seed.py`, a YAML config loader, a simple run logger that writes config + seed + git hash into each `results/<run_id>/`.
- [ ] `docs/decisions.md`: carry over the proposal's decision log (Appendix 2) and keep adding to it. Examiners value this.
- [ ] Confirm `.gitignore` covers `data/`, `.venv/`, checkpoints.
- [ ] Send the stakeholder surveys (still pending per Appendix 2) now; replies take weeks.
- [ ] Ask DWC/SLTDA for Horton Plains daily visitor counts now (data-sharing agreement is slow). The plan does not depend on it.

### Phase 1 – Trail graph and features (weeks 1–2, ~19 Oct – 1 Nov) → D1
1. **Graph.** Pull footways/paths inside the Horton Plains boundary with osmnx. Keep the main loop:
   entrance (Farr Inn / ticket office) → Small World's End → World's End → Baker's Falls → back.
   The loop is about 9.5 km, so OSM will give too few junctions. **Densify by splitting segments every ~300 m**,
   which gives roughly 30–35 nodes, inside the 25–40 range. Tag POI nodes (viewpoints, falls, entrance).
   Save `nodes.parquet`, `edges.parquet`, `edge_index.pt`, and a map figure for the slides.
2. **Terrain.** Copernicus GLO-30 DEM tile → reproject to a metric CRS → slope per node and per edge (grade %)
   → TWI (`ln(a / tan β)`) from flow accumulation. Store static node features.
3. **Weather.** Open-Meteo historical archive (ERA5-based), hourly: precipitation, temperature, cloud cover, wind,
   for 2–3 years at one or a few points (the park is small, so per-node weather will barely vary;
   document this). Cache the raw responses. CHIRPS/NASA POWER: optional cross-check after PP1.
4. **Calendar.** Weekday, weekend, Sri Lankan public holidays, **Poya days** (hard-code the list for the date range
   from the official gazette), school holiday periods, long-weekend flag.
5. **Output:** one tensor builder that returns `X[T, N, F]`, `static[N, F_s]`, `edge_index`, `edge_weight`.
6. **Test:** shapes, no NaNs, graph connected, node count between 25 and 40.

Agent: `data-engineer`. Then run `reviewer`.

### Phase 2 – Synthetic occupancy simulator (weeks 2–4, ~26 Oct – 15 Nov) → D2
This is the most important and the most attackable part of the project. Every number must be justified in `docs/assumptions.md`.
1. **Daily arrivals** = base level × weekday/holiday/Poya multipliers × weather multiplier × seasonal curve.
   Anchor the totals to published park-level figures (proposal refs [8], [9]) and to DWC data if it arrives.
2. **Hourly arrival profile.** Strong early-morning peak (World's End is usually clouded in by late morning); park opening hours.
3. **Movement.** Agent-based or cohort-based walk around the loop. Walking speed from
   **Tobler's hiking function** `v = 6·exp(−3.5·|tan θ + 0.05|)` km/h on each edge's slope,
   scaled down when it rains, plus random variation between groups. Group sizes from a simple distribution.
4. **Dwell times** at World's End, Small World's End, Baker's Falls (log-normal).
5. **Output:** hourly occupancy per node `Y[T, N]`, plus noise (Poisson or negative binomial).
6. **Scenarios:** normal, Poya / long-weekend surge, heavy-rain day, school holidays. Keep one or two scenarios
   **out of training** to test generalisation.
7. **Calibration v1:** match total daily visitors and the morning peak shape. Calibration v2 (after PP1):
   adjust to the manual field counts.
8. **Sanity checks:** people are conserved (arrivals = departures over a day), no negative counts,
   plots of a typical day and a Poya day for the slides.

Agent: `simulator`.

### Phase 3 – Evaluation harness and baselines (weeks 3–5, ~2 – 22 Nov) → D3, D5
Build the evaluation **before** the ST-GNN, so every model goes through the same test.

**Task definition (fix this early and write it in decisions.md):**
input = last 24 hourly steps of occupancy + weather + calendar; output = next 1–24 hours per node (FR2).
Report horizons 1, 3, 6, 12 and 24 h.

**Splits – spatio-temporal blocks:**
- *Temporal:* train on the earlier period, validate on the middle, test on the last months. Never shuffle across time.
- *Spatial:* split the loop into 4–5 contiguous blocks of nodes. Each fold holds one block out of the loss and the metrics.
  Held-out nodes may appear as inputs only from their past, never as targets during training.
- Fit scalers on training nodes and training time only.
- Score only **opening hours**; night-time zeros make every model look good.

**Baselines:**
- *Historical average:* mean per node × hour-of-day × day-type from training data. This also becomes the NFR2 fallback.
- *ARIMA/SARIMA:* one per node (statsmodels, daily seasonality 24); auto-order on training data only.
- *LSTM:* one shared LSTM over all nodes with the **same features as the ST-GNN but no graph**. This keeps the comparison fair.

**Statistics:**
- RMSE, MAE per model, fold, horizon.
- Paired t-test of ST-GNN vs each baseline. Hourly errors are autocorrelated, so pair on **per-day mean errors**
  on the test set (more honest than per-hour pairs, more samples than per-fold pairs). Apply a Holm correction for
  the three comparisons and report effect size. Diebold–Mariano can be a secondary check.
- Save `results/<run_id>/metrics.csv` and `stats.json`.

Agent: `modeler`. Then `reviewer` on the split code; leakage here would invalidate the whole result.

### Phase 4 – ST-GNN (weeks 5–7, ~16 Nov – 6 Dec) → D4
1. **Model:** GCN layers on `edge_index` (edge weight = inverse length or travel time) → GRU over time →
   linear head producing 24 horizons. Keep it small (the graph has ~35 nodes; edge deployment).
2. **Step A – train from scratch** on the trail data. This is the first comparison and the PP1 safety net.
3. **Step B – pretrain** the same GCN+GRU core on METR-LA (then PEMS-BAY) with a separate input/output layer.
   Traffic speed and trail occupancy differ, so transfer only the GCN/GRU weights and learn new input and output layers.
4. **Step C – fine-tune** on the trail: freeze the core and train the new layers, then unfreeze with a low learning rate.
5. **Ablations** (strong evidence for the research question):
   scratch vs pretrained; graph vs identity adjacency (does the graph matter?); with vs without weather.
6. Early stopping on the validation period, fixed seeds, 3–5 seeds per configuration, report mean ± std.

Pretraining needs a GPU: use Colab/Kaggle (budget §7). Do Step A locally first.

### Phase 5 – Cifuentes cascade v1 and PP1 demo (weeks 7–8, ~30 Nov – PP1) → D6, D8
1. **PCC** = (trail length / space per visitor) × visits per day (open hours / visit duration), per segment.
2. **RCC** = PCC × Π(1 − Cf_i). Correction factors: social (group spacing), erodibility (from slope/TWI),
   accessibility (slope), precipitation (from forecast rain), sunlight/fog.
   **Where the forecast enters:** a crowding factor from forecast occupancy vs PCC, and the precipitation factor from the
   weather forecast. Write the exact formula in decisions.md and get supervisor agreement. Examiners will ask.
3. **ECC** = RCC × management capacity (a fixed value from park staff/infrastructure, documented as an assumption).
4. `serve/predict.py` writes `forecast_<date>.json`: per segment occupancy forecast, capacity number, bottleneck flag,
   confidence note, and the synthetic-target disclaimer (FR5). Falls back to HA when weather is missing (NFR2).
5. A small Streamlit or notebook view: map coloured by forecast load and ECC. Very good for the PP1 demo.

### After PP1 (Dec 2026 – Apr 2027)
| Window | Work |
|---|---|
| Dec – Jan | Field visits (3–4) for manual counts at 3–5 checkpoints; calibration v2; define the agreement metric (e.g. MAD within ±X persons) before the visits |
| Jan | Full pretraining on PEMS-BAY/PeMS04/08; transfer-strategy tuning; final benchmark run |
| Feb | Quantisation (PyTorch dynamic int8 → ONNX / TorchScript), latency and memory tests on a phone or Raspberry Pi-class device (NFR1) |
| Feb – Mar | Shared data layer with the team (JSON schema, versioning); integration with Module 3 and the dashboard |
| Mar – Apr | Field validation report, system tests, final results, thesis chapters |

---

## 4. PP1 checklist (mapped to the mark sheet)

| Criterion | Evidence to show |
|---|---|
| Problem definition | Static quota vs segment-level forecast; one slide with park-level numbers [8]–[10] |
| Proof of concept (70% of LO1) | Live run: graph map → simulated day → forecast → capacity per segment |
| Key pillars / technologies | GCN maths, GRU, transfer learning, Tobler, TWI, Cifuentes explained; why each was chosen |
| Design excellence | Architecture diagram, module layout, data flow, JSON schema |
| Completion ~50% | D1, D2 v1, D3, D5 harness, D4 scratch + first pretrain, D6 v1 done |
| Standards / best practices | Pinned env, seeds, configs, run logs, unit tests, spatio-temporal CV, git history of small commits, assumptions.md |
| User requirements | FR1–FR5, NFR1–NFR5 with status; survey status and early replies |
| Risk mitigation | Risk table below, with actions already taken |
| Commercialisation | B2G/B2B/B2C from proposal §6; per-segment capacity as the selling point |

---

## 5. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Synthetic target is circular (model just learns the simulator's rules) | Examiners question all results | Document every assumption; hold out scenarios; noise; field-count validation; state the limitation openly (FR5) |
| ST-GNN does not beat baselines significantly | Main objective not met | Ablations still answer the research question; a negative result on a tiny graph is a valid finding; report honestly |
| Transfer from traffic does not help | Obj 3 weak | Scratch model is already the baseline for this; report scratch vs pretrained as a result |
| OSM gives too few nodes | Graph too small | Densify by distance (Phase 1) |
| DWC data never arrives | Weaker calibration | Use public park-level figures; already designed as optional |
| Field visits blocked (weather, permits) | No validation | Schedule visits early (Dec–Jan), mix weekday/Poya; volunteer counters |
| Data leakage in CV | Invalid results | Spatio-temporal blocks, scalers on train only, `reviewer` agent, leakage unit tests |
| PyG install issues on Windows | Lost days | CPU wheels locally, Colab for GPU; pin versions |
| Few spatial folds → low statistical power | t-test not significant | Pair on per-day errors; multiple seeds; report effect sizes |

---

## 6. How to work each week

- One phase at a time; finish with a test, a result file, and a short commit.
- Use the agents: `data-engineer` (Phase 1) → `simulator` (Phase 2) → `modeler` (Phases 3–5) →
  `reviewer` after every model or split change → `docs-writer` at the end of each phase.
- Update `docs/assumptions.md` and `docs/decisions.md` as you go, not at the end.
- Weekly supervisor update: what was done, numbers, the next decision needed.

**Decisions to confirm with the supervisor early**
1. PP1 date and what "50%" means for this component.
2. Forecast task (24 h input → 1–24 h output, opening hours only).
3. How the forecast enters the Cifuentes RCC step.
4. Field-count agreement threshold, set before the visits.
5. Whether a negative transfer-learning result is acceptable if reported properly.

**Note:** the `modeler` agent currently covers baselines, ST-GNN, CV and the t-test, but not pretraining,
domain adaptation, Cifuentes or quantisation. Extend `.claude/agents/modeler.md` (or add an agent) before Phase 4.
