# PP1 viva preparation – Component 4 (Weerasekera J.V, IT23343948, J26-IT-363)

One page per topic. Read sections 1–3 the night before; rehearse section 4 twice with the app open; keep section 6
next to you. Every number below is in `results/` (simulation, 2025 test year, 3 seeds unless stated).

---

## 1. Where the data comes from (say this without notes)

| Data | Source | How it is fetched | Used for |
|---|---|---|---|
| Trails, jeep tracks, viewpoints, gates, tanks | **OpenStreetMap** (© OpenStreetMap contributors, ODbL) | Overpass API through the OSMnx library | The trail graphs of all three parks |
| Elevation, 30 m | **Copernicus GLO-30 DEM** (ESA / EU) | AWS Open Data bucket `copernicus-dem-30m`, tiles N06 E080 and N06 E081 | Slope, wetness (TWI), walking time |
| Past weather, hourly | **Open-Meteo historical API** (ERA5 reanalysis from ECMWF / Copernicus) | `archive-api.open-meteo.com` | Model inputs 2022–2025; rain in the simulator |
| Weather forecast, 16 days | **Open-Meteo forecast API** | `api.open-meteo.com` | Live forecasts in the app |
| Rain cross-check | **NASA POWER** daily point data | `power.larc.nasa.gov` | Checked against Open-Meteo (agrees on wet days) |
| Holidays and Poya days | Python **`holidays`** package (Sri Lanka); Poya after 2026 estimated from the full moon | – | Calendar inputs |
| City traffic (pretraining) | **METR-LA, PEMS-BAY** (Li et al., DCRNN, ICLR 2018) | Hugging Face mirror TorchSpatiotemporal/ProcessedDatasets | Transfer learning (RQ5) |
| Visitor statistics (problem) | News 1st (Nov 2025), Daily News (Apr 2024), sripada.org | Proposal refs [8]–[10] | Problem statement |
| Capacity method | **Cifuentes (1992)**, CATIE Technical Report 194 | – | Carrying capacity |
| Walking speed | **Tobler's hiking function** (1993) | – | Simulator, walking times |
| **Crowd counts per section** | **None exist anywhere in Sri Lanka.** A calibrated simulator generates them; every parameter is in `configs/*.yaml` and justified in `docs/assumptions*.md` | – | Training and test target |

**The sentence to have ready:** "The maps, terrain, weather and calendar are real open data. The crowd numbers per
section are simulated, because no such counts exist – that is part of the research gap. They will be checked against
field counts in December with criteria I fixed in advance, and DWC's daily totals have been requested."

---

## 2. How the work answers the research gap

**The gap (proposal 1.3), split into five checkable claims:**

| Claim | What the evidence shows | Verdict |
|---|---|---|
| **C1** Graph learning adds value on a trail | Horton, sections without counts: ST-GNN **2.54** vs LSTM 2.59 vs same network without graph 2.61 vs historical average 4.20 (p < 10⁻¹², ~2 %). Every section counted: a tie (1.42). **Realistic world (S1)**, every section counted: ST-GNN best, −0.019 vs LSTM (p = 0.002), −0.013 vs no-graph (p = 0.007). Yala: no gain over no-graph. Adam's Peak: worse at the summit queue | **Partly** – small, only where some sections are counted |
| **C2** Urban-traffic pretraining + domain adaptation helps | Pretrained on METR-LA → PEMS-BAY. Helps Horton with 30–90 days (−5 % / −12 %). Freezing the core: +2 % at 365 days. No help at Adam's Peak. Traffic weights unchanged are 4–5× worse than a historical average | **Mostly no – a clear answer** |
| **C3** A defensible *bottleneck* forecast | Over-capacity F1 **0.80** (Horton) / **0.85** (Adam's Peak) with counts; on uncounted sections the ST-GNN smooths peaks (F1 0.29 vs LSTM 0.32) → the app shows a calibrated "% chance of crowding" | **Shown with counts** |
| **C4** Works with no sensor record | Gate counts only: interior error 1.45 vs 1.42 with every section counted (base world). Realistic world: gate-only is only 3 % better than the historical average, counting every section 7 % → a few ranger-counted sections recover most of it | **Feasible, with a limit** |
| **C5** Forecast → capacity beats a static quota | Same visitors admitted: **−27 %** over-capacity time (Horton), **−24 %** (Adam's Peak, significant vs static, weather-only and historical-average quotas). At Horton a historical-average forecast does as well | **Shown** |
| Main objective: field-validated trail | Criteria A1–A3 fixed 20 Oct; counting tool in the app; visits in December | **December** |

**The answer in three sentences (memorise):**
1. "An ST-GNN of the family proven on city traffic runs on tiny, sensor-free trail graphs, offline on a phone, and its
   forecast turns into a carrying capacity that cuts overcrowding by about a quarter compared with a fixed quota."
2. "Two parts of the gap got honest, mostly negative answers: the graph adds little unless some sections are counted,
   and urban-traffic pretraining helps only with a few months of data."
3. "Most of the overcrowding is about *when* people walk, so the forecast also drives timed entry slots (−99.6 %) and
   start-time advice at Adam's Peak (−42 % waiting)."

**What goes beyond the proposal (say it as extensions, not as the gap):** timed entry tickets, Adam's Peak start
times and halfway holds, a 90-day planner, ranger counting, Yala jeep safaris with leopard-sighting management.

---

## 3. How it was developed (method and timeline)

**Method – quantitative design science, iterative:**
1. **Plan, then build, then measure.** Each step started as a written plan in `docs/` (old ones in `docs/archive/`),
   decisions logged in `docs/decisions.md`.
2. **Open data → graph.** OSM paths split into ~300 m sections (Yala ~1.2 km), terrain from the DEM, weather and calendar per hour.
3. **Simulator → training target.** Groups of hikers (or jeeps) walk the graph: demand from calendar, season and rain;
   arrival times; route choice; Tobler speed; slow-down in crowds and rain; stops at viewpoints. Every number in YAML.
4. **Models.** Historical average, SARIMA, LSTM, GRU without graph, ST-GNN (GCN + GRU). Same code, so "graph vs no graph" changes only the graph.
5. **Evaluation without leakage.** Train 2022–23, validate 2024, test 2025; spatial block cross-validation; paired
   tests over days with Holm correction; 3 seeds; every run saved with its config and git hash.
6. **From forecast to decision.** Cifuentes PCC → RCC → ECC with the forecast in the RCC step; linear programme for
   slot tickets; replays of 2025 to measure overcrowding.
7. **Product.** FastAPI service per park with roles and audit log; Flutter app (visitor, ranger, officer); the ST-GNN
   re-written in Dart so it runs on the phone; daily offline pack.
8. **Quality.** 116 Python tests, 37 app tests, lint (ruff), GitHub Actions CI, model and data card, requirements traced to tests.

**Timeline (git history):**
| Date (2026) | Step |
|---|---|
| 9 Oct | Team Flutter project |
| 14 Oct | Workspace, OSM graph, DEM, weather, calendar, simulator, models, first benchmark |
| 15–16 Oct | Three trails, planning model, entry control, booking, live mode, API, first app screens; Adam's Peak |
| 19–20 Oct | Team layout; 3 seeds; traffic pretraining (RQ5); on-device ST-GNN; field-validation protocol |
| 21 Oct | Research-gap study: bottleneck events, gate-only sensors, forecast-driven quota; officer and ranger tools; realistic world |
| 22 Oct | Gate-only live forecast; spot-count updates; Yala; UI polish; PP1 slides |

**AI tools (be ready – it is in your proposal's Appendix 3):** "I used an AI coding assistant for drafting and coding.
Every result is produced by code in the repository and re-run from saved configs; I tested it and can explain each
part. Responsibility stays with me." Then show that you can explain: the GCN formula, the masked first layer, the
Cifuentes cascade, why paired tests are over days.

---

## 4. How to demonstrate the app

### 4.1 Before the viva (30 minutes before)
1. **Close every old Chrome window opened by Flutter**, and stop old servers:
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object CommandLine -match 'src.api' | ForEach-Object { Stop-Process -Id $_.ProcessId }
   ```
2. **Adam's Peak officer account** (not created yet – needed for the Adam's Peak officer demo):
   ```powershell
   cd D:\Documents\SLIIT\Research\Decentralized-Hiking-AI\research\component_4
   $env:C4_PARK = "adams_peak"; .venv\Scripts\python.exe -m src.api.users add --username officer1 --role officer; Remove-Item Env:C4_PARK
   ```
3. **Refresh the forecasts** for today:
   ```powershell
   foreach ($p in "horton_plains","adams_peak","yala") { $env:C4_PARK = $p; .venv\Scripts\python.exe -m src.live.refresh }
   Remove-Item Env:C4_PARK
   ```
4. **Terminal 1 – servers:** `.venv\Scripts\python.exe -m src.api.serve_all --host 0.0.0.0` (wait for "Uvicorn running").
5. **Terminal 2 – app:** `cd ..\..` then `flutter run -d chrome --dart-define=C4_API=http://localhost:8000`.
6. **Phone (optional):** if the Wi-Fi changed, `ipconfig` → rebuild the APK with that address (RUN_APP.md, Option B);
   open `http://<address>:8000/parks` on the phone first.
7. **Backup:** have the slide screenshots (`docs/slides/screens/`) and a 1–2 min screen recording ready in case the network fails.

### 4.2 The 60-second demo (inside your 2 minutes, or when the panel asks "show us")
1. **Plan your visit → Horton Plains → Crowding.** "Every section coloured by tomorrow's forecast – computed on this
   phone." Drag the hour slider to **08:00**: World's End and Baker's Falls turn red.
2. **Safe numbers** tab: "One number per trail from Cifuentes, set by the most limiting section."
3. **Staff → officer1 → Daily quota**: "Forecast-driven quota next to weather-only and the fixed number, and why."
4. **Airplane mode / disconnect Wi-Fi** → Crowding still works: "offline – the model runs here."

### 4.3 The 5-minute demo (if the panel wants more)
| Who | Steps | What to say |
|---|---|---|
| Visitor | Trip planner → Horton Plains → calendar → **24 Nov 2026** → see "~870 people expected", safe limit, "Why this limit?" → book 07:00 → QR ticket | Quiet days, the safe limit changes with rain and crowding, a ticket fixes trail + time |
| Ranger (Horton) | Staff → `ranger1` → **Now** → 24 Nov 07:00 → Check in the ticket code → **Live** (gate advice) → **Count** (+1, Save, works offline; ★ sections update today's forecast) | No sensors on the trail: gate counts + spot counts |
| Officer (Horton) | `officer1` → Daily quota → Forecast check → Trail condition (Muddy → limits drop at once) | Officer decides; every change audited |
| Adam's Peak | Start times for **25 Dec 2026** (evening start, wait table) → Staff ranger → Halfway check → record 500 three times → **HOLD** | Nobody is refused; advice is spread so it does not create a new peak |
| Yala | Trip planner → **Safari** → Yala → Staff `ranger1` → **Sightings** → Heenwewa Tank, leopard → Report → rule "at most 10 jeeps, 10 min" | Same pipeline, a new park by one config file; a bottleneck no calendar predicts |

### 4.4 If something goes wrong
| Problem | Fix in 10 seconds |
|---|---|
| "Cannot reach the park server" | Terminal 1 stopped → restart `serve_all` |
| Yala shows Horton trails | You are in an **old** browser window → use the one opened by the latest `flutter run` |
| Staff login fails at a park | Each park has its own accounts (section 4.1 step 2) |
| Check-in "Too early / Too late" | Set the ranger **Now** demo time within 15 min of the slot |
| Anything else | Switch to the slide screenshots and keep talking – the panel marks understanding, not the click |

---

## 5. Where the files are

All paths below are under `research/component_4/` unless they start with `lib/` or `test/`.

| What | Where |
|---|---|
| Overview and run commands | `README.md`, `RUN_APP.md` |
| This prep, full explanation, Q&A | `docs/viva_prep.md`, `docs/pp1_guide.md`, `docs/qa_pp1.md` |
| Every result with numbers | `docs/evaluation_results.md` |
| The gap claim by claim, the plan | `docs/research_gap_study.md`, `docs/improvement_plan.md` |
| Architecture, model internals | `docs/technical_design.md` |
| Requirements → code → test; risks | `docs/requirements.md` |
| Data sources, licences, limits | `docs/model_card.md` |
| Assumptions of each park | `docs/assumptions.md`, `docs/assumptions_adams_peak.md`, `docs/assumptions_yala.md` |
| Decision log, field protocol | `docs/decisions.md`, `docs/field_validation_protocol.md` |
| Slides | `docs/slides/PP1_Component4.pptx` (own deck), `docs/slides/PP1_team_component4.pptx` (team deck slides 15–17), `docs/pp1_template_slides.md` (script) |
| Park settings | `configs/default.yaml`, `configs/parks/adams_peak.yaml`, `configs/parks/yala.yaml` |
| Graph, terrain, weather, calendar | `src/data/graph.py`, `terrain.py`, `weather.py`, `calendar_features.py`, `build_dataset.py` |
| Simulator | `src/sim/simulator.py` |
| ST-GNN and baselines | `src/models/stgnn.py`, `src/models/baselines.py`, `src/train/trainer.py` |
| Benchmark and research questions | `src/run_benchmark.py`, `src/eval/` (`bottlenecks.py`, `sparse_sensors.py`, `pretrain_transfer.py`, …) |
| Traffic pretraining | `src/pretrain/traffic.py` |
| Cifuentes capacity | `src/capacity/cifuentes.py` |
| Entry control, booking, gate advice, Adam's Peak advice, quota replay, sightings | `src/control/` |
| Live refresh, phone pack, API | `src/live/refresh.py`, `src/edge/pack.py`, `src/api/app.py`, `src/api/serve_all.py` |
| Results of every run | `results/<time>_<tag>/` (Adam's Peak: `results/adams_peak/`, Yala: `results/yala/`) |
| App (Flutter) | `lib/features/component_4/` – `domain/edge_forecaster.dart` is the ST-GNN on the phone |
| Tests | `tests/` (Python), `test/component_4/` (app) |

---

## 6. Sample questions and answers

Short answer first, then the evidence. More in `docs/qa_pp1.md`.

### Problem and gap
1. **What is the problem?** – A fixed daily quota (Horton Plains) or none (Adam's Peak, Yala). Nobody knows where on the trail or when it overloads, and no section counts exist.
2. **What is novel?** – ST-GNNs are proven on 200–300-sensor city networks. I test one on 35–57-section trail graphs with no sensor record, and judge it by the decisions it improves, not only its error.
3. **Did you prove the gap?** – Partly, honestly: it works offline from open data and its forecast beats a fixed quota (−24 to −27 %); the graph adds little unless some sections are counted; traffic pretraining helps only with a few months of data. Field validation in December.

### Data
4. **Your target is simulated – isn't the model just learning your simulator?** – That is the main risk. Every assumption is in YAML and documented; a realistic world adds what a calendar cannot predict (bus groups, busy spells, incidents, forecast errors); December counts are judged by criteria fixed in advance (A1 error ÷ peak ≤ 0.25, A2 rank correlation ≥ 0.6, A3 peak hour ±1 h).
5. **How did you calibrate it?** – Not yet with real counts: base demand is an estimate (Horton ~240k visitors a year), with known patterns (weekends, Poya, rain). DWC totals are requested; field counts in December.
6. **Why not install counters?** – Cost, power, maintenance, and the proposal promises open data only. The app's ranger count tab builds a record cheaply.

### Model
7. **Explain the ST-GNN.** – Each section is a node. Two graph-convolution layers mix neighbouring sections, a GRU reads the last 24 hours, another graph layer spreads that memory, and a decoder adds tomorrow's weather and calendar. Output: people per section per hour. 13,665 parameters.
8. **What is a GCN layer?** – H' = D̃^−½ (A + I) D̃^−½ H W: each section averages itself and its neighbours (normalised by degree), then a learned linear map.
9. **How do you handle sections without counts?** – Fed as zero with a "not counted" flag, and in the first layer they only receive messages, so a missing count is never read as "empty".
10. **Why GRU, not LSTM or a Transformer?** – Smaller, same job; an LSTM-cell version was significantly worse. Attention needs far more data than a 48-node graph gives.
11. **Why only 2 % better on uncounted sections?** – In the base simulator crowds follow the calendar, so neighbours add little. In the realistic world the graph is significantly better with counts; with gate counts only, no model can recover what never reaches the gate.

### Evaluation
12. **How do you avoid leakage?** – Time split (train 2022–23, validate 2024, test 2025), scalers on training data only, contiguous spatial blocks, tests that check it.
13. **Why test over days, not hours?** – Hours inside a day are correlated; testing 8,760 hours would make tiny differences look significant. Paired t-test and Wilcoxon over 365 days, Holm correction.
14. **Why is ARIMA worse?** – It cannot use the calendar (Poya, holidays) or the weather forecast, which drive trail crowds.

### Capacity and control
15. **Explain Cifuentes.** – Physical capacity (space and time) × correction factors (spacing, erosion, steepness, rain, wet ground, condition, and my forecast-crowding factor) × management capacity 0.7; the most limiting section sets the trail's number.
16. **Where does the forecast enter?** – The crowding factor: the share of open hours in which the forecast exceeds what a section holds at once.
17. **Why do slot tickets work so much better?** – Crowding is about when people walk; a daily total cannot spread arrivals, tickets per 30-minute slot can.
18. **Why no tickets at Adam's Peak?** – Pilgrims are never refused, so start-time advice and halfway holds: −42 % waiting from start times; the final steps cleared with holds.

### Transfer, edge, integration
19. **Did traffic pretraining help?** – Only at Horton with 30–90 days (−5 / −12 %). It is a research answer: the architecture transfers, the traffic knowledge mostly doesn't.
20. **Does it really run on a phone?** – Yes: the same forward pass in Dart from a daily pack, equal to PyTorch to 0.0001 people, ~150 ms; 2 ms in ONNX on a laptop. int8 was tested and rejected (+25 % error at Adam's Peak).
21. **How does Module 3 use your output?** – A versioned JSON feed (`c4-module3-feed-1`) with a schema and contract tests; it is also inside the phone's offline pack.
22. **What does the live service read?** – Only gate counts (and ranger spot counts during the day), not simulated counts for every section – matching the "no sensor record" condition.

### Yala and the system
23. **Why Yala?** – To show the pipeline generalises (one config file) and to test a bottleneck no calendar predicts: leopard-sighting jams. Networks beat the historical average by ~20 %; entry slots −99.8 %; a 10-jeep / 10-minute cap at sightings cuts jams by a third while 65 % of passing jeeps still stop.
24. **Is Yala part of your research gap?** – No, it is an extension (scalability, NFR3, commercialisation). The core results are C1–C5 at Horton Plains and Adam's Peak.

### Process, requirements, risk, commercialisation
25. **Are requirements validated?** – Not yet with DWC: surveys and interviews are planned; requirements are marked provisional and traced to code and tests (`docs/requirements.md`).
26. **Biggest risk?** – No real counts yet. Mitigation: realistic world, robustness checks, pre-registered field criteria, counting tool.
27. **Are you on schedule?** – Ahead: the Gantt gives Component 4 months 3–8; field validation and integration are in December–February as planned.
28. **Who pays?** – DWC / Sri Pada Trust per site licence, a small booking fee per ticket, tour operators for planning; no sensors to buy, a new site is one config file.
29. **What did AI tools do?** – Drafting and coding help, declared in the proposal; every result is reproducible from the repository and I can explain each part.
30. **What will you do next?** – Field counts in December, pretraining with sparse sensors, a peak-aware loss for bottleneck detection, stakeholder surveys, Module 3 sign-off.

### If you do not know
"I have not tested that yet. I would test it by … (name the script or experiment), and I will report the result either way."
