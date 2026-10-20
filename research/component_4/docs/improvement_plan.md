# Component 4 – Plan to deliver the full proposed component

Checked line by line on 21 Oct 2026 against:
- the proposal report (IT23343948, Sept 2026): abstract, sections 1.3, 2, 3, 4.3–4.4, 5, 6, 8, 9, Appendix 2;
- the PP1 mark sheet.

Replaces the plans of 19–20 Oct. App-specific history: `proposal_alignment_plan.md`.

**Where we are.** Every part of the proposal now exists in working, tested form (29 Flutter + 72 Python tests).
1. ST-GNN segment forecast.
2. Cifuentes per segment.
3. Traffic pretraining.
4. On-device inference.
5. Benchmark with paired tests.
6. Module 3 data contract.
7. Authority view.
8. Offline app with a 7-day bottleneck map.

**What separates it from the proposal as written:**
1. **Field validation**: the main objective says "on at least one *field-validated* pilot trail".
2. **A significant win over the LSTM**: significant only on segments without counts, a tie elsewhere, and worse
   at the Adam's Peak summit queue.
3. **Domain adaptation beyond fine-tuning, and PeMS04/08.**
4. **CHIRPS / NASA POWER weather.**
5. **DWC / SLTDA visitation data.**
6. **Stakeholder evidence**: surveys, interviews, user study.
7. **Team integration**: Module 3, the shared dashboard, the team app.
8. **A real-phone performance figure** "comparable to Module 1/2".

---

## 1. Proposal element by element

### Main objective (2.1)
> *Offline, edge-deployable ST-GNN … micro-spatial bottlenecks … dynamic, segment-level carrying-capacity
> recommendation … significant improvement over historical-average, ARIMA and LSTM (paired t-test, p < 0.05) on at
> least one field-validated pilot trail.*

| Part | Status 21 Oct | Remaining |
|---|---|---|
| Offline, edge-deployable | **Done**: ST-GNN runs in Dart on the phone; the whole app works offline; Crowding shows today + 6 days with no signal | Real-phone timing (W4) |
| Micro-spatial bottlenecks | **Done**: per-segment hourly forecast, bottleneck map, "avoid hours" | – |
| Segment-level capacity recommendation | **Done**: Cifuentes PCC → RCC → ECC per segment, safe number per trail and park | Confirm placeholder parameters with DWC (W9) |
| Better than HA, ARIMA | **Done**: p_Holm < 0.001, both parks | – |
| Better than LSTM | **Partly**: Horton Plains segments without counts significant (2.48 vs 2.59); tie when counted (3 seeds); Adam's Peak summit worse | W2 |
| Field-validated pilot trail | **Pending**: protocol and criteria A1–A3 fixed; tool built | W1 (December) |

### Specific objectives (2.2)
| # | Objective | Status | Remaining |
|---|---|---|---|
| O1 | Trail graph from OSM; slope + TWI from DEM; weather from Open-Meteo/ERA5, **CHIRPS, NASA POWER** | Graph, DEM, Open-Meteo done (2 parks) | **CHIRPS + NASA POWER** (W5) |
| O2 | Calibrated synthetic target, **validated with field counts** at an agreed level | Simulator + assumptions; agreement level fixed (A1–A3) | **Counts, recalibration, re-runs** (W1) |
| O3 | Pretrain on METR-LA, PEMS-BAY, **PeMS04/08**; **domain-adapt** | METR-LA → PEMS-BAY + fine-tuning; RQ5 answered (helps Horton with 30–90 days) | **PeMS04/08; layer freezing, gradual unfreezing, adversarial domain alignment (DASTNet-style, App. 2)** (W3) |
| O4 | Benchmark vs HA, ARIMA, LSTM; RMSE, MAE; paired t-test | Done (3 seeds temporal; spatial CV 3 seeds Adam's Peak, 1 seed Horton) | Horton spatial CV 3 seeds; RMSE target vs LSTM (W2) |
| O5 | Cifuentes cascade, forecast in the RCC step, segment capacity | Done (+ wet ground, trail condition) | Parameter confirmation (W9) |
| O6 | Quantise + package; latency and memory within limits | ONNX 2 ms, int8 tested (rejected), Dart engine ~150 ms in tests | **Real Android phone; comparison with Module 1/2 times** (W4) |

### Methodology commitments (3.2–3.6)
| Item | Status | Remaining |
|---|---|---|
| Inputs: OSM, DEM, weather | Done | CHIRPS / NASA POWER (W5) |
| Inputs: **DWC permit records, SLTDA seasonality** | Not used: history is simulated | **Request; calibrate daily demand with park totals** (W6) |
| Inputs: pretraining benchmarks | METR-LA, PEMS-BAY | PeMS04/08 (W3) |
| Inputs: field counts | Protocol ready | W1 |
| Baselines HA, ARIMA, LSTM | Done (+ GRU without graph as ablation) | – |
| Metrics RMSE, MAE, paired t, field agreement, on-device latency | All implemented | Field agreement and phone latency need data (W1, W4) |
| Spatial block CV | Done | 3 seeds at Horton (W2) |
| Iterative, prototype-driven | Followed (plans + decision log in `docs/`) | – |

### Requirements (5.1, 5.2)
| ID | Status | Remaining |
|---|---|---|
| FR1 graph + features | Done | – |
| FR2 24-h segment forecast with the ST-GNN | Done (and today + 6 days in the app) | – |
| FR3 Cifuentes capacity per segment | Done | – |
| FR4 output for dashboard **and Module 3** | Contract done: JSON Schema `c4-module3-feed-1`, `GET /module3/feed`, contract tests | **Module 3 adopts it; feed also in the offline pack** (W7) |
| FR5 limitation logged with every output | Done | – |
| NFR1 on-device < 2 s | Done on laptop and test runner | Real phone (W4) |
| NFR2 graceful fallback | Done | – |
| NFR3 other OSM parks | Done (Adam's Peak = one config) | Third park (Knuckles) optional (W12) |
| NFR4 actionable for officials | Done (safe number per segment + note) | Check with officials (W8) |
| NFR5 no personal data | Done | – |
| Requirements validated with stakeholders | **Not done** | W8 |

### Integration, product, commercial (4.3, 4.4, 6, 8, 9)
| Item | Status | Remaining |
|---|---|---|
| Shared local / synced data layer (shared) | Versioned feed + offline pack on the phone | Agree sync with the team; Module 3 reads it offline (W7) |
| Shared authority dashboard front-end (shared) | Streamlit page "Bottlenecks (authority)" + Module 2 damage cross-reference | Move into the team dashboard (W7) |
| Hiker route guidance (Module 3's logic) | Our offline walk advice is a demonstrator; RQ8 shows that spreading advice matters | Hand the method and RQ8 to Module 3 (W7) |
| WBS 11: system / QA testing | 29 + 72 automated tests | CI on every pull request (W10) |
| Gantt: human evaluation / user study (months 10–11) | Not started | W8 |
| Commercialisation evidence | Model described | Letters / meetings, running cost per park (W11) |
| Thesis, research paper | Docs in `docs/` | W13 |

---

## 2. Work packages

| ID | Work | How | Done when |
|---|---|---|---|
| **W1** | **Field validation (O2, main objective)** | Horton Plains 2–3 days, Adam's Peak 23 Dec (protocol, counting sheets); run `src.eval.field_validation`; recalibrate the simulator on all but one day; re-run RQ1–RQ8 | RQ7 report with A1–A3; calibrated `configs/*.yaml`; updated results |
| **W2** | **Beat the LSTM where it matters** | (a) queue state / capacity input or a separate summit head (fixes the Adam's Peak summit block); (b) daily and weekly periodic inputs (ASTGCN, ref. [5]); (c) small hyper-parameter search; (d) Horton spatial CV with 3 seeds; (e) report RMSE as well as MAE | Paired tests vs LSTM per park and protocol, reported either way |
| **W3** | **Domain adaptation (O3)** | PeMS04 / PeMS08 as extra sources; freeze GCN+GRU and train the input/decoder; gradual unfreezing; adversarial domain alignment as in DASTNet | RQ5 extended: which adaptation helps, at 30 / 90 / 365 days |
| **W4** | **Real-phone performance (O6, NFR1)** | Release build on 2 Android phones; the app already shows ms per forecast; log memory; get Module 1/2 timings from the team | RQ6 row "Android phone", compared with Modules 1/2 |
| **W5** | **CHIRPS + NASA POWER (O1)** | Daily rain for both parks; compare with Open-Meteo; add as a feature if it differs | O1 closed; ablation shows its effect |
| **W6** | **DWC / SLTDA visitation data (3.2)** | Formal request (letter via supervisor); use monthly park totals to calibrate the simulator's daily demand; never segment counts | Demand calibrated, or the request and refusal documented |
| **W7** | **Team integration (FR4, WBS 10)** | Ahamed M.M signs off the schema; put the feed in the offline pack so Module 3 reads it with no signal; move the authority view into the team dashboard; one shared app build | Module 3 shows our bottlenecks; integrated build demo |
| **W8** | **Stakeholders and user study** | Collect the surveys (DWC, rangers / operators, hikers); 2–3 interviews (warden, Sri Pada trust); show them the bottleneck map; SUS usability test with 10–15 users | Survey summary; requirements confirmed or changed; SUS score |
| **W9** | **Capacity parameters** | Confirm with DWC / supervisor: group size and gap, management capacity, viewpoint area, condition levels | Parameters marked "confirmed" in `assumptions.md` |
| **W10** | **Engineering standards** | GitHub Actions (pytest + flutter test + analyze on Component 4 paths); model card; data card | Green CI on every PR |
| **W11** | **Commercial evidence** | 1–2 letters of interest (tour operator, DWC); running cost per park (hosting, daily refresh, support) | `docs/commercialisation.md` |
| **W12** | **Extensions (only after W1–W9)** | Feature ablation + bottleneck lead-time metric; real weather forecasts instead of observed weather in tests; Knuckles as a third park; Sinhala / Tamil review | Each with a result or a decision |
| **W13** | **Write-up** | Thesis chapters, research paper (RQ1, RQ5, RQ8 are the publishable results) | Drafts to the supervisor |

---

## 3. Timeline (proposal Gantt: Component 4 months 3–8, integration 8–10, validation 10–11; PP2 assumed mid-January 2027)

| When | Work packages |
|---|---|
| 21–22 Oct | **PP1**: show the proposal's output first (bottleneck map, safe numbers, offline week, RQ1, RQ5, RQ6, RQ8) |
| 26 Oct – 8 Nov | W2 (a, d), W4, W10; send surveys + DWC data request (W8, W6) |
| 9 – 22 Nov | W2 (b, c, e), W3 |
| 23 Nov – 6 Dec | W5, W7 (schema sign-off, feed in the pack), W9 |
| 7 – 24 Dec | **W1 field visits** (Horton Plains; Adam's Peak 23 Dec) |
| 28 Dec – 10 Jan | W1 recalibration and re-runs; survey summary (W8) |
| ~15 Jan | **PP2** |
| Feb – Apr | W7 team integration, W8 user study, W11, W12 |
| May – Jun | Final testing, W13 thesis and paper, final presentation |

---

## 4. Research questions

| RQ | Question | Answer on 21 Oct | Next |
|---|---|---|---|
| RQ1 | Does the graph improve segment forecasts? | Yes on ordinary trail without counts; not at the summit queue; tie with counts everywhere | W2 |
| RQ2 | Do models transfer between parks? | Not unchanged; pretraining helps few-shot; historical average wins ≤ 90 days | after W1 |
| RQ3 | Does a better forecast give better control? | Only with the right rule (P90) | re-run after W1 |
| RQ4 | Are the Adam's Peak policies robust? | Halfway checks yes; start times when flow ≤ 25/min | W1 measures the flow |
| RQ5 | Does traffic pretraining help a tiny trail graph? | Only Horton with 30–90 days (−5 / −12 %) | W3 |
| RQ6 | Offline on a phone < 2 s? | Yes (2 ms ONNX, ~150 ms Dart) | W4 |
| RQ7 | Is the synthetic target close to real counts? | Method fixed; counts in December | W1 |
| RQ8 | Can offline advice prevent overcrowding? | Yes if spread: −73 % with nobody turned away; herd advice backfires; limit + advice −95 % | Real compliance from W8 |
