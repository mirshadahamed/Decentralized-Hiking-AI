# Component 4 – Improvement plan (proposal vs. what is built)

Written 19 Oct 2026, from the proposal report (IT23343948, Sept 2026), the PP1 mark sheet, and the current code
(`main` + branches `feature/component-4-capacity`, `feature/component-4-adams-peak-crowd`).

**Bottom line.** The *system* is well ahead of the proposal (two parks, live service, booking, pilgrim advice,
app). The *research* is behind on three things the proposal promised and examiners will check first:
**(1) pretraining on traffic benchmarks + domain adaptation, (2) on-device quantised inference (the framework is
"edge-native"), (3) field validation of the synthetic target.** The plan below puts those first and freezes new
app features until they are done.

### Progress (20 Oct 2026, branch `feature/component-4-research-gaps`)

| Item | State | Where |
|---|---|---|
| P0-1 pretraining | **Done** (RQ5): helps Horton Plains with 30–90 days of counts (−5 to −12 %), no help at Adam's Peak, zero-shot fails. Domain-adaptation variants (e.g. freezing the graph layer) not tried | `src/pretrain/traffic.py`, `src/eval/pretrain_transfer.py` |
| P0-2 edge | **Done**: ONNX 1.9–2.2 ms, int8 rejected; pure-Dart forecast on the phone, works offline | `src/edge/`, `domain/edge_forecaster.dart`, evaluation_results.md RQ6 |
| P0-3 field validation | Protocol and criteria **fixed**; comparison tool **ready**; visits in Dec | `docs/field_validation_protocol.md`, `src/eval/field_validation.py` |
| P0-4 vs LSTM | 3 seeds + LSTM-cell variant **done**: tie with every segment counted (p ≈ 0.1); Adam's Peak spatial CV with 3 seeds still to run | evaluation_results.md "RQ1 update" |
| P0-5 surveys | Not started | – |

---

## 1. Proposal objectives – where each one stands

| # | Proposal objective / requirement | Status | Evidence / gap |
|---|---|---|---|
| O1 | Trail graph from OSM + slope/TWI (Copernicus) + weather (Open-Meteo/ERA5, **CHIRPS, NASA POWER**) | **Done**, partly | Graph, DEM, Open-Meteo done for 2 parks. CHIRPS / NASA POWER not used (cross-check of rain) |
| O2 | Calibrated synthetic occupancy target, **validated against manual field counts** with an agreement metric | **Half** | Simulator done and documented; **no field counts, no agreement metric yet** |
| O3 | **Pretrain the ST-GNN on METR-LA / PEMS-BAY / PeMS04-08 and domain-adapt** to the trail | **Not done** | Postponed after PP1 (decisions.md). Park-to-park transfer (RQ2) done instead – a useful substitute, not the promised method |
| O4 | Benchmark vs HA, ARIMA, LSTM; RMSE/MAE; **paired t-test p < 0.05** | **Done**, mixed result | Horton, unseen segments: ST-GNN significantly better than LSTM, GRU, HA (p_Holm < 0.001). Horton, all segments: no significant difference from LSTM (p = 0.12). Adam's Peak: LSTM better than ST-GNN |
| O5 | Cifuentes PCC → RCC → ECC with the forecast in the RCC step; dynamic segment capacity | **Done** | Crowding factor; plus wet ground and trail condition (19 Oct); shown in the app |
| O6 | **Quantise and package for on-device inference; latency/memory within limits (NFR1 < 2 s)** | **Not done** | Model runs on a server (FastAPI); nothing on the phone, no latency measured |
| FR1–FR3 | Graph, 24-h segment forecast, capacity | Done | |
| FR4 | Output consumable by the dashboard **and Module 3** | **Half** | REST API + JSON; **no agreed, versioned schema with Module 3 / shared data layer** |
| FR5 | Synthetic-target limitation logged with every output | Done | Disclaimer in forecast and outlook JSON |
| NFR1 | On-device inference < 2 s | **Not measured** | see O6 |
| NFR2 | Graceful fallback without weather forecast | Done | Historical-average fallback, typical weather |
| NFR3 | Other OSM parks without architectural change | Done | Adam's Peak = one config file (RQ2 shows the *weights* do not transfer unchanged) |
| NFR4 | Plain-language, actionable output | Done | App cards, "why this limit", basis notes |
| NFR5 | No personal data | Done | Booking code only |
| Eval | Feature ablation (weather / terrain / calendar), bottleneck lead-time (proposal presentation) | **Not done** | |
| Users | Stakeholder surveys / interviews (Appendix 2: "pending") | **Not done** | No DWC / ranger / hiker responses recorded |

---

## 2. Priorities

**P0 – promised in the proposal, examiners will ask (do first, Oct–Dec)**

| ID | Work | How | Done when | Effort |
|---|---|---|---|---|
| P0-1 | **Pretraining + domain adaptation (O3)** | Download METR-LA and PEMS-BAY (public .h5); a loader that turns speed series into the same tensor layout (past window, sensed flag, calendar covariates; node descriptors = degree / position instead of trail features); pretrain the same GCN+GRU core; transfer to the trail with `load_weights` (already handles a different graph). Compare **scratch vs. traffic-pretrained vs. park-pretrained** at 30 / 90 / 365 days of trail data (reuses `src/eval/transfer.py`) | table + paired tests in `evaluation_results.md` (RQ5); answer the research-gap question either way | 1.5–2 weeks (GPU optional: Colab) |
| P0-2 | **Edge inference (O6, NFR1)** | Export the trained ST-GNN to **ONNX** (dense GCN makes this easy) → dynamic int8 quantisation (onnxruntime) → measure latency, memory and MAE change on laptop CPU and an Android phone; run it in Flutter with `onnxruntime` (or TFLite) so tomorrow's forecast works **offline on the phone** from the cached inputs | latency < 2 s, MAE loss < 2 %, offline demo | 1–1.5 weeks |
| P0-3 | **Field validation (O2)** | Fix the agreement metric *before* the visits (e.g. MAD ≤ 25 % of the peak, or within the P10–P90 band ≥ 70 % of counts); 2–3 visits to Horton Plains (World's End, Baker's Falls junction, entrance; weekday + weekend), one Poya night at Adam's Peak (final-steps flow, halfway counts, climb times); counting sheet + app; recalibrate the simulator; re-run RQ1–RQ4 | validation report, calibrated parameters | visits Dec; analysis 1 week |
| P0-4 | **Significant improvement over LSTM (main objective)** | (a) ST-GNN with an **LSTM cell** (one option in `trainer.py`); (b) temporal attention or ASTGCN-style daily/weekly periodic inputs (proposal ref. [5]); (c) small hyper-parameter search; (d) **3 seeds everywhere** (Adam's Peak and spatial CV still 1 seed) | paired t-test vs LSTM per park and protocol, reported honestly | 1 week + overnight runs |
| P0-5 | **Stakeholder evidence** | Send the drafted surveys (DWC officials, rangers / tour operators, hikers); 2–3 short interviews (Horton Plains warden, Sri Pada trust / police); map answers to FR/NFR; confirm the open decisions (capacity standard, condition levels, evening share, hall capacity) | survey summary, updated requirements | 2–3 weeks elapsed, ~3 days work |

**P1 – strengthens the research and the mark sheet (Nov–Jan)**

| ID | Work | Why |
|---|---|---|
| P1-1 | **Feature ablation**: weather / terrain / calendar / graph removed one at a time (RQ1b) | Promised in the proposal presentation; shows *why* the model works |
| P1-2 | **Bottleneck lead-time**: how many hours ahead a segment over capacity is flagged correctly (precision / recall / lead hours) | The proposal's "forecast bottlenecks ahead of time" claim needs its own metric, not only MAE |
| P1-3 | **Real weather forecasts** instead of observed weather in the day-ahead test (archived Open-Meteo forecasts or ERA5 + noise) | Removes the "perfect forecast" upper-bound caveat |
| P1-4 | **CHIRPS / NASA POWER** rain cross-check for both parks | Closes O1 as written |
| P1-5 | **Re-run RQ2–RQ4** with the new Adam's Peak advice (crowd-dependent climb times, evening starts, real sunrise) and 3 seeds | Current RQ3/RQ4 numbers come from the earlier advice model |
| P1-6 | **Shared data layer with Module 3 / dashboard (FR4)**: versioned JSON schema (forecast, capacity, advice), sample files, contract tests | Integration is in the WBS and Gantt (months 7–9) |
| P1-7 | **Engineering standards**: GitHub Actions running pytest + `flutter test` on every PR, `ruff` lint, model card per trained model, data card for the synthetic dataset | "Standards / best practices" (20 % of solution marks) needs visible evidence |

**P2 – product depth (only after P0)**

| ID | Work |
|---|---|
| P2-1 | Knuckles as 3rd destination (Feature B, `next_steps_plan.md`) – coordinate trails with the teammate's Knuckles dataset |
| P2-2 | Adam's Peak rest halls from OSM + walk-with-rest in the research simulator (Feature C remainder) |
| P2-3 | Usability study (SUS, 10–15 users) + ranger / officer task tests |
| P2-4 | Commercial evidence: letters of interest or meeting notes (DWC, Sri Pada trust, 1–2 tour operators); cost of running one park (hosting, refresh, support) |
| P2-5 | Native-speaker review of Sinhala / Tamil |

**Stop list until P0 is done:** no new screens, no new parks beyond Knuckles, no new booking features.

---

## 3. Mark-sheet view – what each item improves

| PP mark-sheet criterion | Weight | Current risk | Items that improve it |
|---|---|---|---|
| Proof of concept | 7 % | Synthetic target only | P0-3, P0-2 (offline demo) |
| Technologies in depth | 17.5 % | Good; transfer learning missing | P0-1, P0-2, P0-4 |
| Key research pillars | 7.5 % | Good | P1-1, P1-2 |
| Design excellence | 8 % | Strong | P1-6 |
| Completion (≈ 50 %, no delay) | 12 % | O3 / O6 delayed | P0-1, P0-2 + corrective-action slide |
| Standards / best practices | 8 % | Tests exist, no CI | P1-7 |
| User / functional requirements | 8 % | Not validated with users | P0-5, P2-3 |
| Risk mitigation | 4 % | Good table | keep updated with P0 status |
| Commercialisation | 10 % | Model described, no evidence | P2-4, P0-5 |

---

## 4. Timeline (dates assumed: PP2 mid-January 2027, final April 2027)

| Weeks | Dates | Work |
|---|---|---|
| 0 | 20–22 Oct | **PP1.** Present delayed items honestly as corrective actions: O3 pretraining (P0-1 from 26 Oct), O6 edge (P0-2), field visits booked (P0-3). Optional before PP1: ONNX export + laptop latency (2–3 h) as a first NFR1 number |
| 1–2 | 26 Oct – 8 Nov | P0-4 model variants + 3 seeds (overnight); P0-2 ONNX / int8 / latency; send surveys (P0-5); merge the open pull requests |
| 3–4 | 9 – 22 Nov | P0-1 traffic pretraining + domain adaptation (RQ5); P1-1 ablation |
| 5–6 | 23 Nov – 6 Dec | P0-2 on-phone inference in Flutter; P1-2 lead-time metric; P1-6 schema with Module 3; P1-7 CI |
| 7–8 | 7 – 20 Dec | **Field visits** Horton Plains (P0-3); P1-3 forecast weather; P1-4 CHIRPS |
| 9 | 23 – 24 Dec | **Adam's Peak, Unduvap Poya night** (season opening): flow, halfway counts, climb times |
| 10–11 | 28 Dec – 10 Jan | Recalibrate the simulator; re-run RQ1–RQ5 (P1-5); survey results; write-up |
| 12 | ~15 Jan | **PP2** |
| 13–20 | Jan – Mar | P2 items, integration with the team app, usability study, paper draft |
| 21+ | Apr | Final report, viva |

---

## 5. Research questions after this plan

| RQ | Question | Status after plan |
|---|---|---|
| RQ1 | Does the graph improve segment forecasts (esp. without counts)? | + LSTM-cell / attention variants, 3 seeds, ablation (P0-4, P1-1) |
| RQ2 | Does a model transfer between parks? | + 3 seeds, learning curve |
| RQ3 | Does a better forecast give better crowd control? | re-run with the new advice (P1-5) |
| RQ4 | Are the policies robust to wrong assumptions? | re-run, then calibrated with field data |
| **RQ5 (new)** | **Does pretraining on dense urban traffic help a tiny sparse trail graph?** – the proposal's central research gap | P0-1 |
| **RQ6 (new)** | **Can it run offline on a phone within 2 s without losing accuracy?** | P0-2 |
| **RQ7 (new)** | **How close is the synthetic target to real counts?** | P0-3 |
