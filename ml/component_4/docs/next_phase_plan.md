# Component 4 – Where we are and what comes next

Branch: `feature/component-4-dashboard` (created from `feature/component-4-ml-core` at commit `a628ec8`).
Written 14 Oct 2026, about 7 days before PP1. The earlier, longer plan is still in `development_plan.md`.

---

## 1. What has been built (in plain words)

The goal of the component: **predict how crowded each part of the Horton Plains trail will be tomorrow,
hour by hour, and turn that into a safe number of visitors for the day.**

The pipeline has seven steps. Each one is a file you can open and run.

| # | Step | What it does | Where | Status |
|---|---|---|---|---|
| 1 | Trail map | Downloads the Horton Plains paths from OpenStreetMap and cuts the main loop (Visitor Center → Mini World's End → World's End → Baker's Falls → back, 8.3 km) into **26 pieces of ~300 m**. Each piece is a graph node; touching pieces are linked. | `src/data/graph.py` | done |
| 2 | Terrain | Uses satellite elevation data (Copernicus DEM) to get slope, wetness (TWI) and walking time (Tobler's hiking function) for every piece. | `src/data/terrain.py` | done |
| 3 | Weather and calendar | Hourly rain, temperature, cloud and wind for 2022–2025 (Open-Meteo), plus weekends, public holidays, **Poya days**, long weekends and school holidays. | `src/data/weather.py`, `calendar_features.py` | done |
| 4 | Simulator | No one counts hikers per trail piece, so we **simulate** them: how many come each day (calendar, season, morning rain), when they arrive, how fast they walk (slope, rain, crowding), where they stop. Output: people on each piece, every hour, for 4 years. Every assumption is written down. | `src/sim/simulator.py`, `docs/assumptions.md` | done (v1, not yet checked against field counts) |
| 5 | Forecasting models | Five models predict tomorrow's 24 hours from the last 24 hours plus tomorrow's calendar and weather: historical average, SARIMA, LSTM, GRU without graph, and the **ST-GNN (graph + GRU)**. | `src/models/`, `src/train/` | done (trained from scratch, no pretraining yet) |
| 6 | Evaluation | Train on 2022–23, tune on 2024, test on 2025. A second test hides whole stretches of trail (spatial block CV). Error measures RMSE and MAE; paired t-test per day. | `src/eval/`, `src/run_benchmark.py` | done |
| 7 | Capacity | Cifuentes method (PCC → RCC → ECC). The forecast adds two daily corrections: rain hours and **crowded hours per segment**. Output: a daily quota, the limiting segment, and a JSON file other modules can read. | `src/capacity/cifuentes.py`, `src/serve/predict.py` | done (v1, needs supervisor agreement) |

Also done: config file, seeds, run logs, 8 automated tests, decision log, figures.

### First results (test year 2025)
| Model | MAE (persons) | |
|---|---|---|
| Historical average | 2.83 | what the static quota logic resembles |
| SARIMA | 3.57 | |
| LSTM | 2.43 | |
| GRU, no graph | 2.41 | |
| **ST-GNN** | **2.43** | 14 % better than historical average, 32 % better than SARIMA (both p < 1e-12) |

**Honest reading:** deep learning clearly beats the simple baselines, but **the graph does not help yet**.
When segments have no history (spatial test), the ST-GNN beats historical average and LSTM, but the no-graph GRU
is better still. The likely reason is a fixable design flaw: hidden segments are fed as zeros, and the graph
layer averages those zeros into their neighbours.

Example output (Vesak Poya, 12 May 2025): 985 visitors expected; recommended quota 150 (classic Cifuentes 257);
World's End, Mini World's End and Baker's Falls flagged as bottlenecks.

---

## 2. What still has to be done

### Before PP1 (about 7 days)
| Priority | Task | Why it matters for PP1 | Effort |
|---|---|---|---|
| **P1** | **Dashboard (frontend)** – section 3 | Examiners must *see* the proof of concept (70 % of the LO1 mark) | **done (v1)**: 6 pages, render tests pass |
| **P1** | Fix the graph layer so it only averages over segments with counts; rerun spatial CV with 3 seeds | Without it the main research claim (the graph helps) is not shown | 0.5 day + ~2 h CPU |
| **P1** | Supervisor meeting: Cifuentes link, quota parameters (group 10, gap 50 m, MC 0.7), forecast task | These are marked *pending* in `decisions.md`; examiners will ask | 1 meeting |
| P2 | Check simulator totals against any published Horton Plains visitor numbers; adjust `base_daily_visitors` | Makes the synthetic target defensible | 0.5 day |
| P2 | Small METR-LA pretraining test on Colab | Shows the transfer-learning step exists, even if not tuned | 1 day |
| P2 | Slides and Q&A rehearsal | 15 % of the mark is communication | 1–2 days |

### After PP1 (Dec 2026 – Apr 2027)
| Task | Proposal objective |
|---|---|
| Field visits: manual headcounts at 3–5 checkpoints; recalibrate the simulator; measure viewpoint platform areas | Obj 2 |
| **Alternative-trail diversion (Kirigalpotta, Thotupola): section 4** | FR3/FR4 extension, strengthens the graph research question |
| Full pretraining on METR-LA / PEMS-BAY, then fine-tune on the trail graph; compare with the scratch model | Obj 3 |
| Use real weather *forecasts* instead of the actual weather | realism |
| Quantise the model (int8, ONNX), measure phone latency (< 2 s) | Obj 6, NFR1 |
| Agree the JSON format with the team; show it in the shared Flutter app (Module 3 / authority dashboard) | FR4, integration |
| Stakeholder survey results → update requirements | Section 5 of the proposal |
| Thesis chapters | WBS 12 |

---

## 3. The dashboard

### Technology: Streamlit (Python)
The forecasts, metrics and maps already live in Python and the `results/` folder, so a Streamlit app can show
them directly with no API or second codebase. It runs locally with one command and works offline after the
first map load. The shared Flutter app (repo root) stays untouched. Later it reads the same
`forecast_<date>.json`, which is already the agreed hand-off format (FR4).

Location: `ml/component_4/dashboard/` · Run: `.venv\Scripts\python.exe -m streamlit run dashboard/app.py`

### Pages
| Page | Who it is for | Shows |
|---|---|---|
| **1. Overview** | Examiners, supervisor | The problem in one paragraph, the 7-step pipeline with done / to-do status, headline numbers |
| **2. Daily forecast** (main demo) | Park officer (DWC / SLTDA) | Pick a date in 2025 → map coloured by crowding; hour × segment heat map; bottleneck list; expected visitors vs recommended quota vs classic Cifuentes; rain hours; switch to "no weather forecast" mode (NFR2 fallback); disclaimer (FR5); download the JSON |
| **3. Trail and data** | Examiners | Trail graph map with segment numbers and POIs, plus the Kirigalpotta and Thotupola trails drawn as "planned extension"; slope, TWI and walking time per segment; weather and calendar for the chosen month |
| **4. Simulator** | Examiners (the most attacked part) | Daily profiles (weekday, weekend, Poya, rainy day); yearly visitor totals; assumptions table from `assumptions.md` |
| **5. Model comparison** | Examiners | Metrics table and bars; t-test table with p-values and effect sizes; forecast vs actual at a chosen segment; spatial CV results; plain-English "what this means" box |
| **6. Capacity method** | Supervisor, officers | Cifuentes formula, the correction factors and their values, how the forecast enters (crowding and rain factors) |

### Build order
1. Shared data loading (cached) + Overview page
2. Daily forecast page (map, heat map, quota card, fallback switch)
3. Model comparison page
4. Trail and Simulator pages
5. Capacity page, styling, README instructions, a quick test that every page loads

### Done when
- One command starts it, and every page loads without errors from the committed results
- The daily forecast for any 2025 date appears in a few seconds on this laptop
- Every number on screen comes from `results/` or `data/processed/`, never typed in by hand

---

## 4. Extension: send visitors to other trails when World's End is crowded

**Idea.** Horton Plains has two other main trails. When the forecast says the World's End loop will be crowded,
suggest them to some visitors before they enter, so the load is spread.

### Can it be built? Yes. Both trails are already in OpenStreetMap
| Trail | In OSM | Length (one way, approx.) | Start | Notes |
|---|---|---|---|---|
| World's End loop (current) | yes | 8.3 km loop | Visitor Center | the main attraction |
| **Kirigalpotta** (2,388 m, 2nd highest peak) | "Kirigalpotta Trail" | ~6 km, out and back | Visitor Center side, heading west | long; out-and-back means two-way traffic |
| **Thotupola Kanda** (2,359 m, 3rd highest peak) | "Thotupola Trail (2km)" + "Thotupola Trailhead" | ~1.3 km, out and back | trailhead ~3.7 km north of the Visitor Center on the Pattipola road | needs a short drive, so it is not a walk-in alternative |

### Does it need internet? Not on the trail
The decision is made **before people start walking**, at the ticket counter or the Visitor Center,
not in the middle of the trail. So:
| Part | When | Connectivity needed |
|---|---|---|
| Day-ahead forecast and capacity for all three trails | once a day, the evening before | short internet access (weather forecast), e.g. at the park office; already how `predict.py` works |
| Diversion decision ("World's End full from 07:00–09:00; offer Kirigalpotta / Thotupola") | at the gate, as tickets are sold | **none**, if the daily plan is cached on the counter device; optional live correction using the gate's own ticket count |
| Hiker's phone | before entering | the plan is downloaded with the ticket / at the Visitor Center (offline-first, as in the proposal); no signal needed on the trail |

"Real time" here means correcting the plan through the day with the **number of tickets already sold**.
That number exists at the gate, so no trail sensors or mobile signal are needed.

### What has to be built
| # | Work | Where | Effort |
|---|---|---|---|
| 1 | Add both trails to the graph: one connected park network (~50 segment nodes at 300 m, or ~40 at 400 m) | `src/data/graph.py`, config | 1 day |
| 2 | Terrain for the new segments (already automatic once they are in the graph) | `terrain.py` | — |
| 3 | Simulator: each visitor chooses a trail (e.g. 85 % World's End, 10 % Kirigalpotta, 5 % Thotupola, an assumption to check) and a **diversion scenario** (a share of offered visitors accept the alternative) | `simulator.py`, `assumptions.md` | 1–2 days |
| 4 | Retrain and re-evaluate on the larger graph | existing pipeline | ~0.5 day + CPU time |
| 5 | Capacity per trail (Cifuentes for each), then a **diversion recommendation**: per entry hour, how many visitors the main loop can take, and how many to offer each alternative without exceeding *its* capacity | `src/capacity/diversion.py` (new) | 1–2 days |
| 6 | Extend the JSON: a `trails` list and an hourly `diversion` plan | `predict.py` (schema v1.1) | 0.5 day |
| 7 | Dashboard: three-trail map, "where to send people" table per hour | dashboard | 1 day |
| 8 | Optional: intraday update from the live ticket count | `src/serve/intraday.py` | 1 day |

### Things to check first (risks)
- **Is it allowed?** Confirm with DWC that Kirigalpotta and Thotupola are open to visitors, and whether they need a
  guide, a separate permit or limited hours. Access to these trails has been restricted at times; do not assume it.
- **Do not just move the damage.** These trails pass sensitive grassland and cloud forest. Diversion must stay
  within each trail's own Cifuentes capacity, which is why step 5 computes it per trail.
- **Will visitors accept it?** Most people come for World's End. The share who accept another trail is unknown.
  Add a question to the hiker survey ("If World's End were crowded, would you hike Kirigalpotta or Thotupola instead?")
  and use the answer in the simulator.
- **No counts for these trails either.** They are simulated like the main loop and need field counts later.
- **Who owns what.** The proposal gives *hiker route recommendation* to Module 3 (Ahamed M.M). Component 4 provides
  the trail-level forecast, capacity and park-level diversion plan. Module 3 turns it into advice for each hiker.
  Agree this split with the team.

### Research value
The current graph is a single loop, so neighbouring segments add little; that is one reason the graph does
not help yet. A park network where three trails share an entrance and visitors spill from one trail to another
is a much better test of whether a **graph** model is useful. That makes this extension part of the research
question, not just a feature.

### When
- **Before PP1:** show the three trails on the dashboard map and present diversion as the next step
  (design + this section). Do not start the full build; the 7-day plan is already full.
- **After PP1 (Dec–Jan):** steps 1–7, together with the first field visit (counts on all three trails, plus DWC rules).

---

## 5. Order of work from today

| Day | Work |
|---|---|
| 1 | This plan; dashboard steps 1–2 |
| 2 | Dashboard steps 3–5 |
| 3 | Graph-layer fix; start the 3-seed spatial rerun in the background; refresh the dashboard with the new results |
| 4 | Supervisor meeting; update `decisions.md` |
| 5 | Simulator total check; optional METR-LA test |
| 6 | Slides built around the dashboard |
| 7 | Rehearse; fresh-clone rerun to prove reproducibility |
