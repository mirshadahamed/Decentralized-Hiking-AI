# Component 4 – Proposal vs. what is built, and the plan from here

Re-checked 20 Oct 2026 against the proposal report (IT23343948, Sept 2026, sections 2, 3, 5, 8, 9) and the PP1
mark sheet, after branch `feature/component-4-research-gaps`. First version: 19 Oct 2026.

**Bottom line.** All six proposal objectives now have working code and results. The 19 Oct gaps are closed:
pretraining, on-device inference, field-validation method and 3 seeds. Four things are still open:
1. **Field counts** (Dec): the main objective says "on at least one *field-validated* pilot trail".
2. **A significant win over the LSTM.** It holds only on segments without counts; it is a tie elsewhere.
3. **The Module 3 data contract (FR4).**
4. **Stakeholder answers** to the surveys.

The booking, start-time advice and second park (Adam's Peak) go **beyond the proposal's scope**. They are
presented as extensions. No new app features until the open items are done.

---

## 1. Requirement-by-requirement check

### Main objective (proposal 2.1)
| Part | Status | Evidence |
|---|---|---|
| Offline, edge-deployable ST-GNN | **Done** | Pure-Dart forecast on the phone from a 175 KB daily pack, works offline (RQ6) |
| Segment-level dynamic capacity recommendation | **Done** | Cifuentes PCC→RCC→ECC per segment/trail, with weather, wet ground, crowding, trail condition |
| Significant improvement over HA and ARIMA (paired t, p < 0.05) | **Done** | Both parks, p_Holm < 0.001 |
| Significant improvement over LSTM | **Partly** | Horton Plains, segments without counts (spatial CV): ST-GNN 2.48 vs LSTM 2.59, significant. Adam's Peak, segments without counts: better on ordinary trail, worse at the summit queue → worse overall (9.63 vs 8.23). Every segment counted: tie at both parks (3 seeds, p ≈ 0.1) |
| On a field-validated pilot trail | **Pending** | Protocol and criteria fixed (`field_validation_protocol.md`); visits Dec 2026 |

### Specific objectives (proposal 2.2)
| # | Objective | Status | Evidence / what is missing |
|---|---|---|---|
| O1 | Trail graph from OSM; slope, TWI from Copernicus DEM; weather from Open-Meteo/ERA5, **CHIRPS, NASA POWER** | **Done, one gap** | 2 parks (48 / 57 segments). CHIRPS / NASA POWER not used yet |
| O2 | Calibrated synthetic target, **validated against field counts** with a defined agreement level | **Method done; counts pending** | Simulator + assumptions; criteria A1–A3 fixed 20 Oct; tool `src/eval/field_validation.py` |
| O3 | Pretrain on METR-LA / PEMS-BAY / **PeMS04/08**, domain-adapt to the trail | **Done (2 of 4 datasets)** | RQ5: METR-LA → PEMS-BAY, fine-tuning. Helps Horton Plains with 30–90 days of counts; no help at Adam's Peak. PeMS04/08 and a real domain-adaptation method (not only fine-tuning) are open |
| O4 | Benchmark vs HA, ARIMA, LSTM; RMSE, MAE; paired t-test | **Done** | RQ1, 3 seeds, Holm. RMSE target "lower than all three baselines": met for HA/ARIMA. vs LSTM, met on unseen segments (6.92 vs 7.69); not met with every segment counted (4.94 vs 4.79) |
| O5 | Cifuentes cascade with the forecast in the RCC step | **Done** | `src/capacity/cifuentes.py`, `/capacity/{day}`, app "safe limit" card |
| O6 | Quantise and package for on-device inference; latency, memory within limits | **Done; phone figure pending** | ONNX 1.9–2.2 ms, ~2 MB extra memory, 103–111 KB model; int8 tested and rejected (+25 % error at Adam's Peak); Dart engine ~140 ms in the test runner. **Real Android phone not measured yet** |

### Requirements (proposal 5.1, 5.2)
| ID | Requirement | Status | Evidence / gap |
|---|---|---|---|
| FR1 | Trail graph with terrain + weather per node | Done | `src/data/` |
| FR2 | 24-h segment forecast with the ST-GNN | Done | `/forecast/tomorrow`, on-device card |
| FR3 | Cifuentes capacity per segment | Done | `/capacity/{day}` |
| FR4 | Output consumable by the dashboard **and Module 3** | **Half** | Versioned JSON + REST; **no agreed schema / contract with Module 3** |
| FR5 | Synthetic-target limitation logged with every output | Done | `disclaimer` in every forecast JSON |
| NFR1 | On-device inference < 2 s | **Done on laptop; phone pending** | RQ6 |
| NFR2 | Graceful fallback without a weather forecast | Done | Historical-average fallback + typical weather |
| NFR3 | Other OSM parks without architectural change | Done | Adam's Peak = 1 config file |
| NFR4 | Plain-language, actionable output for officials | Done | "Safe limit" + "Why this limit?", night plan |
| NFR5 | No personal data | Done | Booking code only |

### Other proposal commitments
| Item | Section | Status |
|---|---|---|
| Spatial block cross-validation | 3.5 | Done (4 blocks; Adam's Peak 3 seeds on 20 Oct; Horton 1 seed – re-run with 3) |
| Stakeholder surveys / interviews (DWC, rangers, operators, hikers) | 5, App. 2 | **Pending**: no responses recorded |
| Shared data layer with the team (WBS 10) | 4.3, 8 | **Pending**: agree format with Ahamed M.M (Module 3) |
| System/QA testing (WBS 11) | 8 | 65 Python + 24 Flutter tests; no CI yet |
| Commercialisation evidence | 6 | Model described; no letters / meetings yet |
| Gantt: Component 4 months 3–8, integration months 8–10 | 9 | Ahead of plan on build; validation on plan |

---

## 2. Development plan from here

**A. Before PP1 (20–21 Oct)**
| ID | Work | Done when |
|---|---|---|
| A1 | Update PP1 slides with RQ5, RQ6, field-validation method, 3-seed results, proposal-numbered requirements, corrective actions | `docs/slides/PP1_Component4.pptx` rebuilt by `src.report.slides` |
| A2 | Demo rehearsal with `docs/user_guide.md` (Horton day screen → on-device card; Adam's Peak start times; officer) | Demo runs end to end in < 4 min |

**B. Research gaps (26 Oct – 10 Jan)**
| ID | Work | How | Done when | When |
|---|---|---|---|---|
| B1 | **Beat the LSTM where it matters** | (0) Adam's Peak summit: queue state as an input or a separate summit head – the ST-GNN loses only on the queue block; (a) daily / weekly periodic inputs (ASTGCN-style, proposal ref. [5]); (b) attention over the 24 h window; (c) small hyper-parameter search (hidden size, GCN depth); (d) spatial CV 3 seeds at Horton Plains | paired t-test vs LSTM per park and protocol, reported either way | 26 Oct – 8 Nov |
| B2 | **Domain adaptation, not only fine-tuning (O3)** | (a) freeze the pretrained GCN+GRU, train only input and decoder layers; (b) gradual unfreezing; (c) PeMS04 / PeMS08 as extra sources | RQ5 table extended with these rows | 9 – 22 Nov |
| B3 | **Feature ablation + bottleneck lead time** | weather / terrain / calendar / graph removed one at a time; precision / recall of "segment over capacity" flagged 1–24 h ahead | RQ1b and lead-time tables | 9 – 22 Nov |
| B4 | **Real phone latency (NFR1)** | Release build on an Android phone; the card already shows the time on the device; record 20 runs + memory | RQ6 row "Android phone" | by 8 Nov |
| B5 | **CHIRPS / NASA POWER (O1)** | daily rain for both parks; compare with Open-Meteo; add as a feature if it differs | O1 closed | 23 Nov – 6 Dec |
| B6 | **Field validation (O2)** | Horton Plains 2–3 days (Dec), Adam's Peak Unduvap Poya 23 Dec; run `src.eval.field_validation`; recalibrate simulator on all but one day | RQ7 report; calibrated parameters | 7 – 24 Dec |
| B7 | **Re-run RQ1–RQ5 after calibration**; RQ3/RQ4 with the new Adam's Peak advice | overnight runs | updated `evaluation_results.md` | 28 Dec – 10 Jan |

**C. Integration, users, standards (Nov – Jan)**
| ID | Work | Done when | When |
|---|---|---|---|
| C1 | **FR4 data contract with Module 3**: JSON Schema for forecast, capacity, advice (`docs/schema/`), sample files, contract tests in pytest | Module 3 owner signs off the schema | 23 Nov – 6 Dec |
| C2 | **Surveys and interviews**: collect DWC / ranger / operator / hiker responses; 2–3 interviews; map answers to FR/NFR | survey summary in `docs/` | send by 1 Nov; summary 10 Jan |
| C3 | **CI**: GitHub Actions running pytest + `flutter test` on Component 4 paths; ruff | green check on every PR | by 8 Nov |
| C4 | Model card + data card (synthetic dataset) | `docs/model_card.md`, `docs/data_card.md` | by 22 Nov |
| C5 | Commercial evidence: meeting notes / letters (DWC, Sri Pada trust, 1–2 operators), running cost per park | `docs/commercialisation.md` | Dec – Jan |

**D. Product (after B and C)**: Knuckles as 3rd destination; rest halls from OSM; usability study (SUS,
10–15 users); Sinhala / Tamil review.

**Stop list until B1–B6 and C1–C2 are done:** no new screens, no new parks, no new booking features.

---

## 3. Mark-sheet view

| PP mark-sheet criterion | Weight | State on 20 Oct | Next items |
|---|---|---|---|
| Problem definition + proof of concept | 10 % | Strong; synthetic target is the weak point | B6 |
| Key pillars + technologies | 25 % | Pretraining, edge inference, GNN all demonstrated | B1, B2 |
| Design excellence | 8 % | Strong (per-park config, edge pack, API) | C1 |
| Completion (≈ 50 %, no delay) | 12 % | Ahead on build; validation on plan | corrective-action slide |
| Standards / best practices | 8 % | Tests, seeds, Holm, pre-registered criteria; no CI | C3, C4 |
| User / functional requirements | 8 % | All FR/NFR traced; not confirmed by users | C2 |
| Risk mitigation | 4 % | Table + actions under way | keep updated |
| Commercialisation | 10 % | Model described | C5 |

---

## 4. Timeline (PP2 assumed mid-January 2027, final April 2027)

| Weeks | Dates | Work |
|---|---|---|
| 0 | 20–22 Oct | A1, A2; **PP1** |
| 1–2 | 26 Oct – 8 Nov | B1, B4, C3; send surveys (C2); merge the research-gaps pull request |
| 3–4 | 9 – 22 Nov | B2, B3, C4 |
| 5–6 | 23 Nov – 6 Dec | C1 with Module 3, B5 |
| 7–9 | 7 – 24 Dec | **Field visits** (B6): Horton Plains; Adam's Peak 23 Dec |
| 10–11 | 28 Dec – 10 Jan | B7; survey summary; write-up |
| 12 | ~15 Jan | **PP2** |
| 13–20 | Jan – Mar | D items, team integration, usability study, paper draft |
| 21+ | Apr | Final report, viva |

---

## 5. Research questions

| RQ | Question | Answer on 20 Oct | Next |
|---|---|---|---|
| RQ1 | Does the graph improve segment forecasts? | Yes on segments without counts (Horton, ordinary Adam's Peak trail); not at the summit queue; tie with counts everywhere | B1, B3 |
| RQ2 | Does a model transfer between parks? | Not unchanged; pretraining helps few-shot, HA still wins ≤ 90 d | B7 |
| RQ3 | Does a better forecast give better control? | Only with the right rule (P90) | B7 |
| RQ4 | Are the policies robust? | Halfway checks yes; start times when flow ≤ 25/min | B6 measures the flow |
| RQ5 | Does traffic pretraining help a tiny trail graph? | Only Horton with 30–90 days (−5 to −12 %); not Adam's Peak | B2 |
| RQ6 | Can it run offline on a phone < 2 s? | Yes (2 ms ONNX; ~140 ms Dart) | B4 |
| RQ7 | Is the synthetic target close to real counts? | Method fixed; counts Dec | B6 |
