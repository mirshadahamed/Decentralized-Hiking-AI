# Component 4 – Review and plan to a solid component (7 Nov 2026)

Checked against:
- the proposal (IT23343948, Sept 2026): sections 1.3, 2, 3, 5, 6, 8 and Appendix 2;
- the FoC research-project guidelines (Oct 2024): IT checklist, learning outcomes LO1–LO5;
- the code, the 174 Python and 56 Flutter tests, and every run in `results/` up to `20261101_234356_benchmark_dir`.

This is the **single current plan**. The 21 Oct plan is in `archive/improvement_plan_2026-10-21.md`; the 30 Oct
progress log is `knuckles_and_next_steps_plan.md`.

---

## 1. Verdict in one paragraph

The **build is far ahead** of the proposal. Every specific objective has working code, tests and a result, and there
are many extras: five places, tickets, gate control, start times, the offline phone forecast, and calibrated ranges.
What is **not solid yet is the evidence**:
- every number comes from a simulator we wrote;
- no stakeholder has confirmed the requirements;
- the phone timing is from a laptop;
- three parts of the proposal's method are only partly done: PeMS04/08, domain adaptation, and CHIRPS.

The graph's advantage is real but small. It does not hold at the Adam's Peak summit. The plan below therefore
**stops new features** and spends the next ten weeks on evidence, consolidation and the mandatory submissions.

## 2. What has been developed, against the proposal

| Proposal item | Built | Evidence | Solid? |
|---|---|---|---|
| O1 Trail graph from OSM, DEM slope / TWI, weather (FR1) | 5 places: Horton Plains 48, Adam's Peak 57, Knuckles 49 sections, plus Pekoe Trail and Yala | Tests; maps in the app | **Yes**. CHIRPS (named in O1) not added; NASA POWER cross-check done |
| O2 Calibrated synthetic target, checked with field counts | Simulator + realistic world S1; field-validation tool and protocol; ranger Count tab | `field_validation_protocol.md`, `src/eval/field_validation.py` | **No: no field counts yet** (main objective) |
| O3 Pretrain on METR-LA, PEMS-BAY, PeMS04/08 and domain-adapt | METR-LA → PEMS-BAY pretraining; fine-tune and frozen core (RQ5); multi-park joint source (§6.1.3b) | Helps Horton with 30–90 days (−5 to −12 %); no help at Adam's Peak | **Partly**: no PeMS04/08; no adaptation method beyond fine-tuning; not tested with sparse sensors |
| O4 Benchmark vs HA, ARIMA, LSTM; RMSE / MAE; paired t-test; spatial block CV | All baselines (ARIMA as SARIMAX), GRU without graph, 3 seeds, Holm correction | RQ1, RQ1b, RQ10, RQ11, RQ11b–d | **Mostly**. The graph beats the LSTM where sections are not counted (Horton −2 %, Adam's Peak −4 % with spot counts). It ties with counts everywhere and loses at the summit block. RQ2 still has 1 seed |
| O5 Cifuentes PCC → RCC → ECC with the forecast in RCC (FR3) | Per section, per day; quota rules; forecast ranges and cautious quota | RQ9: −27 % / −24 % over-capacity vs static at equal visitors | **Yes**, but the ST-GNN quota = HA quota at Horton. The realistic-world (S1) replay is not done |
| O6 On-device inference (NFR1) | ONNX 2 ms; pure-Dart engine = PyTorch to 0.0001; offline pack; APK | RQ6 | **Partly**: never timed on a real phone |
| FR4 Output for Module 3 and the dashboard | Versioned schema, `/module3/feed`, contract tests, feed in the pack | `test_module3` | **Partly**: no Module 3 sign-off |
| FR5, NFR2–NFR5 | Disclaimer, fallback, park configs, safe number + plain note + 90 % range, no personal data | Tests | **Yes**; NFR4 not checked with an official |
| Beyond the proposal | Tickets (LP), MPC gate control, start times, chance constraint, fairness, rain re-planning, Knuckles permits, Pekoe stages, trip planner, SOS, notices, records, day report, backups, load test, conformal ranges, sensor placement | RQ3, RQ4, RQ8, RQ9, RQ12–RQ15 | Strong; belongs in the "system" and "extensions" chapters |

### The research gap, claim by claim (as of today)
| Claim (proposal 1.3) | Answer now | Still needed |
|---|---|---|
| C1 The graph adds value on a small trail graph | Yes on uncounted sections (Horton, ordinary Adam's Peak trail); tie with full counts; **no at the summit** (LSTM best, even with direction-aware diffusion). **G5 (7 Nov): survives most wrong assumptions** (30 of 36 comparisons) | Field check |
| C2 Traffic pretraining + adaptation helps | Only Horton with 30–90 days; joint multi-park source helps Knuckles at every k | Sparse-sensor setting (G4); PeMS04/08; one adaptation method (W3b) |
| C3 A defensible bottleneck forecast | F1 0.80 / 0.85 with counts; weak on held-out sections; calibrated 90 % ranges hold at busy hours (78 % / 86 %) | Peak-aware loss run (G8) |
| C4 Works with no sensor record | Gates + a few spot counts recover 1/3 (Horton) to 80 % (Adam's Peak) of the gain from counting everything; greedy placement beats rangers' places | Field counts at the ranked places |
| C5 Forecast → capacity beats a static quota | −27 % / −24 %; MPC −99 %; start times −42 % waiting. **RQ9b (7 Nov), realistic world:** ST-GNN quota −25 % / −19 % vs static; beats the HA quota at Adam's Peak (96 % vs 45 % of perfect, p = 3·10⁻⁵), level at Horton | – |

## 3. Weak points an examiner will find

1. **All results are simulated, and the simulator is ours.** No field data yet. Robustness (G5, 7 Nov): the graph result survives most wrong assumptions; at Horton the network beats the park's own average only when arrival times and trail shares are right.
2. **The graph gain is small**, and it is negative at the summit. The thesis must say this plainly and show where the graph pays off: uncounted sections, and few counts.
3. **The proposal's method is not fully followed:**
   - PeMS04/08 not used;
   - "domain adaptation" is only fine-tuning;
   - CHIRPS missing.

   Either do these or record the decision with its reason in `decisions.md`.
4. **Requirements are provisional.** No survey, interview or SUS score yet (LO3 requirements row, NFR4).
5. **Scope sprawl:**
   - 5 places, about 20 RQs, and a second plan file written after the "single plan";
   - `evaluation_results.md` still says "results of 16 Oct" and its summary table stops at RQ8;
   - RQ7 is missing from the numbering.
6. **Mismatched documents:**
   - `model_card.md` (21 Oct) says the app uses the gate-only model. The live ranger forecast now uses the placement model.
   - The root `README.md` on main (rewritten 30 Oct) has a placeholder for Component 4 ("should be added"). That README is the IT checklist's PP1 Git item.
7. **Reproducibility after the field visit.** Once the simulator is recalibrated, every core table must be re-run, and today that is about 15 separate commands.

## 4. The plan

"Me" = code and runs that can start now; "You" = needs people, permits, a phone or the team.

### A. Evidence that decides the grade (start now)

| # | Work | Who | Done when |
|---|---|---|---|
| A1 | **Field validation (W1 / G7).** Permit letter through the supervisor this week. Horton Plains 2–3 days in December. Adam's Peak on 23 Dec (Unduvap Poya, season opens). Count with the ranger Count tab at the **#1–#5 ranked places** (RQ11d) plus the gates. Then `src.eval.field_validation` against criteria A1–A3, recalibrate on all days but one, re-run the core (C1) | You (counts), Me (analysis) | Main objective met, or honestly reported with the numbers |
| A2 | **Stakeholders (W8).** Send the drafted surveys (officials, rangers / operators, hikers). Interview 2–3 people (Horton Plains warden, Sri Pada trust) with the app in hand. **SUS test** with 10–15 users on the APK | You | `requirements.md` rows marked confirmed / changed; SUS score; NFR4 checked |
| A3 | **Real phone (W4).** Install the new APK on 2 Android phones; note the ms shown on the "Forecast made on this phone" card (10 runs each) and the app's memory | You (30 min) | RQ6 row "Android phone"; NFR1 closed |
| A4 | **DWC / SLTDA data request (W6).** Send it, or record that it was sent and refused | You + supervisor | Letter and answer in `decisions.md`; daily totals into `data/live/dwc_daily_totals.csv` if received |
| A5 | **Module 3 sign-off (W7)** with Ahamed M.M: he reads `/module3/feed` (now with ranges and the cautious quota) offline; agree on one shared app build | You + Ahamed M.M | Integrated demo (WBS 10) |

### B. Close the open research items (Me, in this order)

| # | Work | Closes | Effort |
|---|---|---|---|
| B1 | **Done 7 Nov** (`evaluation_results.md` G5). **Robustness (G5):** train on the default world, test on worlds that break one assumption each: demand ±30 %, arrivals ±1 h, route shares, dwell, summit flow. Report which conclusions survive (C1, C4, C5). Gives the field visit its target list | Weak point 1 | 3–4 days + runs |
| B2 | **Done 7 Nov** (RQ9b). **Quota replay on the realistic world (C5b):** RQ9 on S1 for both parks. Does the ST-GNN quota beat the HA quota where the graph has something to add? | C5 | 1 day + runs |
| B3 | **Pretraining in the sparse setting (G4) + PeMS04/08 + one adaptation method (W3b):** gradual unfreezing (cheap), or a DANN-style adversarial alignment. Keep the row even if it does not help | O3, C2 | 4–5 days + runs |
| B4 | **Peak-aware loss, full 3-seed run (G8):** the code exists (`src/eval/peak_loss.py`) | C3 | 1 day + runs |
| B5 | **Three seeds everywhere:** RQ2 park-to-park transfer; any Adam's Peak table still on one seed | Limitation 2 | runs only |
| B6 | **CHIRPS (W5):** daily rain for each park next to Open-Meteo and NASA POWER; a feature only if it differs | O1 | 1 day |
| B7 | Summit block (optional, only if time): a queue / capacity-aware input, or let the model choose per section between graph and no graph. Otherwise keep it as a clear finding (Limitation 5) | C1 | 3 days |

### C. Consolidate (Me, alongside B)

| # | Work | Done when |
|---|---|---|
| C1 | **One command re-runs the core results** (`src/run_core.py`): benchmark, sparse / spot, placement, quota, conformal, edge, with seeds and run folders. This is needed again after A1 | One command; times listed in the README |
| C2 | **Rewrite the top of `evaluation_results.md`:** C1–C5 each with a one-line answer, the number, the test and the run. Then RQ details renumbered (no gap at RQ7). Move extensions (Knuckles, Pekoe, Yala, MPC, fairness) to a second part | The first page answers the research gap |
| C3 | **Thesis scope:** core = Horton Plains + Adam's Peak, C1–C5, field validation. System chapter = app, API, control. Extensions = Knuckles, Pekoe, Yala, transfer, placement. **No new parks or features until PP2** | Chapter outline to the supervisor |
| C4 | **Bring docs up to date:** `model_card.md` (deployed models, ranges, placement model), `technical_design.md` (directed diffusion, conformal, placement), `requirements.md` (FR14 ranges / cautious quota, FR15 count where it helps) | Dates and numbers match `results/` |
| C5 | **Decision log:** one row each for what was dropped or changed from the proposal (int8, PeMS04/08 if dropped, SARIMA for ARIMA, gate-only deployment, directed model not deployed) | `decisions.md` |

### D. Mandatory submissions (FoC guidelines, IT specialization)

| Checkpoint | Item | State | Action |
|---|---|---|---|
| PP1 (done) | Git repository with README: overview, architecture diagram, dependencies; full history | Root README's Component 4 section is a placeholder | **Fill section 13 of the root README** from `research/component_4/README.md` (diagram, stack, how to run); agree with the team, since it is a shared file |
| PP2 | Evidence of using a PM tool (MS Planner export) | Unknown | Put sections A–E of this plan into Planner as tasks; export before PP2 (group) |
| PP2 | Status document 2 | – | Use section 2 of this plan as the base |
| Final | Demo, presentation, viva; thesis; logbook with reflective statement | `viva_prep.md`, `qa_pp1.md` exist | Update the Q&A with RQ11c/d, ranges and joint transfer; keep the logbook weekly |
| LO5 (10 %) | Commercial viability | Only in the proposal | **E3** below |

### E. Product and commercial (after A–C, or in gaps)

| # | Work | Who |
|---|---|---|
| E1 | Re-run the load test with the `/network` cache; release build over HTTPS for a real pilot | Me |
| E2 | Sinhala / Tamil review by native speakers | You |
| E3 | `docs/commercialisation.md`: running cost per park per year (server, daily refresh, SMS, support), price sketch B2G / B2B / B2C, 1–2 letters of interest (tour operator, DWC or Sri Pada trust) | You + me for the cost sheet |
| E4 | Real push notifications (needs a Firebase project); today the in-app notices are enough for the research | Later |

## 5. Timeline (PP2 assumed mid-January 2027)

| When | Work |
|---|---|
| 7–14 Nov | A3 phone timing; A4 data request; permit letter for A1; send A2 surveys. Me: B2, B4, B5 (runs), C1 |
| 15–28 Nov | Me: B1 robustness, B3 pretraining / adaptation, B6 CHIRPS; C2, C4, C5. You: A2 interviews, A5 Module 3, root README (D) |
| 29 Nov – 6 Dec | A2 SUS test; C3 outline to the supervisor; field kit ready (APK, count places #1–#5 printed) |
| 7–24 Dec | **A1 field visits** (Horton Plains; Adam's Peak 23 Dec) |
| 26 Dec – 10 Jan | Field analysis, recalibration, re-run with C1, update results and slides; Planner export |
| ~15 Jan | **PP2** |
| Feb – Jun | E1–E3, integration, thesis and paper (RQ9 + RQ11b/d + RQ8), final evaluation |

## 6. Definition of "solid"

Component 4 is solid when:
1. C1–C5 each have a one-sentence answer, a number, a paired test and a run folder, including the negative ones.
2. Field counts from at least one park are compared with the simulator and the model (A1–A3).
3. The conclusions are shown to survive the robustness worlds, or the ones that do not are named (B1).
4. Every proposal method item is done or has a recorded decision (B3, B6, C5).
5. At least one DWC / park stakeholder has confirmed the requirements, and the SUS score is reported.
6. The forecast is timed on a real Android phone within NFR1.
7. Module 3 consumes the feed in one shared build.
8. One command reproduces every core table.
