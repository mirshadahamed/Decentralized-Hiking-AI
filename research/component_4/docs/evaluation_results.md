# Component 4 – Research evaluation (results of 16 Oct 2026)

All results are from **simulation** (synthetic occupancy target; see `assumptions.md`, `assumptions_adams_peak.md`).
Test year 2025; day-ahead forecasts from midnight; errors are people per segment per hour (open hours).
Significance: paired tests over forecast days (or nights), Holm-corrected where several comparisons are made.

| RQ | Question | Short answer |
|---|---|---|
| RQ1 | Does the trail graph improve forecasts? | **On trail sections without counts, yes at Horton Plains**; with counts everywhere, no gain over a no-graph network. At Adam's Peak, the graph beats the same network without it, but an LSTM is better still |
| RQ2 | Does a model trained on one park work on another? | **Not as it is** (worse than a historical average). Pre-training **does** help a new park learn from little data, but with ≤ 90 days of counts a historical average is as good |
| RQ3 | Do better forecasts give better crowd control? | **Only with the right decision rule.** Advice from the median forecast captures ~20 % of what perfect knowledge would; advice from the **P90 (busy case)** captures all of it |
| RQ4 | Do the Adam's Peak policies hold if the assumptions are wrong? | **Halfway checks: yes at every flow tested. Start times: useful when the final steps are a real bottleneck (≤ 25 people/min), little effect above** |

---

## RQ1 – Graph vs no graph (`src.run_benchmark`)

**Horton Plains** (run `20261015_095519_benchmark`; temporal 3 seeds, spatial 4 folds × 1 seed)

| Model | Temporal MAE | Spatial-CV MAE (unseen sections) |
|---|---|---|
| Historical average | 1.60 | 4.20 |
| ARIMA | 1.93 | – |
| LSTM (no graph) | 1.42 ± 0.02 | 2.59 |
| GRU (no graph) | 1.42 ± 0.02 | 2.69 |
| **ST-GNN** | 1.42 ± 0.005 | **2.48** |

**Adam's Peak** (run `results/adams_peak/20261016_000119_benchmark`; 1 seed)

| Model | Temporal MAE | Spatial-CV MAE |
|---|---|---|
| Historical average | 10.89 | 17.25 |
| ARIMA | 7.14 | – |
| LSTM (no graph) | **3.73** | **8.02** |
| GRU (no graph) | 4.04 | 9.68 |
| ST-GNN (GRU + graph) | 3.83 | 8.92 |

ST-GNN vs the same network without the graph (GRU): better in both protocols (p_Holm < 0.001); vs LSTM: worse
(+0.09 temporal, +0.90 spatial).

**Reading:** the graph helps where it should – predicting segments that have no counts of their own – and the
clean ablation (same network, graph removed) shows the gain at both parks. The recurrent cell also matters: at
Adam's Peak an LSTM beats the GRU-based ST-GNN. **Next:** an ST-GNN with an LSTM cell (one line in
`train/trainer.py`), and 3 seeds at Adam's Peak.

---

## RQ2 – Transfer between parks (`src.eval.transfer`, run `20261016_101336_transfer`)

Both parks get the same inputs (17 shared covariates + 13 segment descriptions), so weights fit either graph.
Few-shot models train 15 epochs on the target's last k days, without using the target's validation year.

| Target | Historical avg (2 y) | In-domain ST-GNN | Zero-shot ST-GNN | HA, 30 d | Scratch 30 d | **Pre-trained + 30 d** | HA, 90 d | Scratch 90 d | **Pre-trained + 90 d** |
|---|---|---|---|---|---|---|---|---|---|
| Horton Plains | 1.60 | 1.42 | 3.40 | 2.06 | 3.11 | 2.77 | 1.61 | 3.06 | 2.33 |
| Adam's Peak | 10.89 | 4.14 | 16.22 | 9.99 | 9.94 | 9.63 | 9.21 | 9.62 | 9.58 |

(MAE; the GRU-without-graph gives the same picture: Horton pre-trained + 90 d = 2.02.)

- **Zero-shot fails** in both directions (worse than the historical average, p < 0.001). The parks are too
  different: day visits vs night pilgrimage, ~1,000 vs up to 12,000 people a day, and a summit queue.
- **Pre-training helps:** fine-tuned beats trained-from-scratch in 7 of 8 settings (p_Holm < 0.05), e.g.
  Horton 90 d ST-GNN 2.33 vs 3.06.
- **But not enough:** with 30–90 days of counts, a historical average from the same days is as good or better.

**Reading:** "deploy to a new park without changes" (NFR3) holds for the *pipeline*, not for the *trained
weights*. A new park should start with the historical average and switch to the network once it has about a
season of counts; pre-training shortens that wait. **Next:** a learning curve (k = 30 … 365 days) to find where the
network overtakes the historical average.

---

## RQ3 – Value of the forecast for crowd control (`src.control.evaluate_forecast_value`, run `results/adams_peak/20261016_112228_forecast_value`)

Adam's Peak, 132 nights of the 2025 season, 50 % of advised pilgrims follow the advice. The advice is computed
before the night from each forecast; the night then happens as it really did.

| Advice from | Forecast error (MAE, climbers/night) | Waiting on the final steps (person-h) | Cut vs no advice | Share of the perfect-knowledge benefit | Pilgrims moved |
|---|---|---|---|---|---|
| No advice | – | 45,841 | – | 0 % | 0 % |
| Calendar average | 805 | 45,841 | 0 % | 0 % | 0 % |
| Forecast 30 days ahead (P50) | 649 | 42,233 | 8 % | 23 % | 2.0 % |
| Forecast 1 day ahead (P50) | 646 | 43,082 | 6 % | 18 % | 2.0 % |
| **Forecast 1 day ahead (P90)** | 1,246 | **27,508** | **40 %** | **117 %** | 6.4 % |
| Perfect knowledge | 0 | 30,121 | 34 % | 100 % | 4.0 % |

Season total difference with a paired bootstrap 95 % interval over nights: P90 advice vs no advice −18,333
person-h [−40,361, −2,489]; P90 vs P50 advice −15,574 [−34,178, −2,107]; perfect vs no advice −15,720
[−36,854, −2,303]. Queues form on only ~10 nights a season, so per-night tests have little power (Wilcoxon p ≈ 0.03–0.1).

**Reading:** a smaller forecast error does not by itself give better control. The median forecast is too low on
exactly the rare peak nights, so the advice does not trigger; the P90 forecast errs on the safe side and beats
even "perfect knowledge of the total" (which still misjudges where in the night people start), at the cost of
moving 6 % of pilgrims instead of 4 %. This is why officers plan on the busy case (decisions.md, 16 Oct 2026),
and it is a result about **decision-focused** forecast evaluation, not only accuracy.

---

> **Note (19 Oct 2026):** RQ3 and RQ4 were run with the *earlier* advice model (climb times on an empty
> mountain, starts from 00:00, sunrise fixed at 06:00). The advice now uses crowd-dependent climb times,
> starts from 18:00 the evening before and the real sunrise of each date (`assumptions_adams_peak.md`, N1–N7).
> Re-run `src.control.evaluate_advisory`, `--sweep` and `src.control.evaluate_forecast_value` to update these
> numbers (planned after PP1).

## RQ4 – Sensitivity (`src.control.evaluate_advisory --sweep`, run `results/adams_peak/20261016_112652_advisory_sweep`)

Final-steps flow (people per minute; assumed 25) × share of pilgrims who follow the advice (assumed 50 %).

Cut in waiting on the final steps from **start times alone (B)**, vs no control:

| Flow (people/min) | 25 % follow | 50 % follow | 75 % follow | 100 % follow | No control: person-h |
|---|---|---|---|---|---|
| 15 | 19 % | 46 % | 56 % | 61 % | 220,086 |
| 20 | 14 % | 31 % | 40 % | 44 % | 99,541 |
| 25 | 6 % | 22 % | 25 % | 24 % | 45,649 |
| 30 | −1 % | 2 % | 6 % | 5 % | 19,410 |
| 35 | −8 % | −2 % | 3 % | 1 % | 8,302 |

- **Halfway checks (C, D)** remove all waiting on the final steps at every flow (in the simulator the hold is
  obeyed perfectly; real compliance at the rest halts is an open question). Total waiting with **both (D, 50 %)**
  is 48 % (flow 15) to 0 % (flow 35) lower than no control.
- **Start times (B)** work when the final steps really are a bottleneck; above ~30 people/min queues are short and
  advice changes little (small negatives are noise of a few hundred person-hours). Returns diminish beyond ~75 %
  compliance.
- The **flow is the number that matters most** (waiting changes 26-fold between 15 and 35 people/min): measuring
  it on one Poya night is the most valuable field work.

---

## RQ1 update – 3 seeds and an LSTM-cell variant (P0-4, 20 Oct 2026)

Temporal protocol (every segment counted), 3 seeds, runs `results/adams_peak/20261020_002150_benchmark_p04`
and `results/20261020_020459_benchmark_p04` (tagged runs: the app's model is unchanged).

| Park | LSTM (no graph) | ST-GNN (GRU) | ST-GNN (LSTM cell) |
|---|---|---|---|
| Adam's Peak | 3.83 | **3.80** | 3.87 |
| Horton Plains | **1.42** | 1.42 | 1.43 |

Paired tests (Holm): ST-GNN (GRU) vs LSTM – no significant difference at either park (p = 0.09 / 0.12);
the LSTM-cell variant is **worse** than the GRU ST-GNN at Adam's Peak (p = 0.007) and worse than the LSTM at
Horton Plains (p = 0.005), so it is dropped. **Reading:** the earlier single-seed "LSTM beats ST-GNN at Adam's
Peak" was seed noise. With every segment counted the graph adds nothing measurable; its value is on segments
*without* counts (spatial CV, Horton Plains significant). **Next:** spatial CV at Adam's Peak with 3 seeds.

## RQ6 – On-device inference (objective O6, NFR1; `src.edge.export`, 20 Oct 2026)

Trained day-ahead ST-GNN exported to ONNX (opset 17); one forecast = 24 hours × every segment; latency on ONE
laptop CPU thread (ONNX Runtime), median of 200 runs. Runs `results/20261020_001929_edge`,
`results/adams_peak/20261020_002009_edge`.

| | Horton Plains | Adam's Peak |
|---|---|---|
| Parameters | 13,665 | 13,665 |
| ONNX file (fp32) | 103 KB | 111 KB |
| Latency, ONNX fp32 | **1.9 ms** | **2.2 ms** |
| Latency, PyTorch | 3.5 ms | 4.0 ms |
| ONNX fp32 vs PyTorch, largest difference | 0.0001 people | 0.0012 people |
| int8 (dynamic) MAE change | −0.3 % | **+24.6 %** |
| int8 file | 101 KB | 109 KB |

NFR1 (< 2 s) is met with a margin of about 1,000× on a laptop core (a phone core is a few times slower).
**int8 quantisation is not used:** the model is already tiny, int8 saves 2 KB and at Adam's Peak, where crowds
span a much wider range, it raises the error by a quarter.

**On the phone:** the same model runs in plain Dart (`lib/features/component_4/domain/edge_forecaster.dart`) from a
daily "edge pack" (`src/edge/pack.py`, `GET /edge/pack`, ~175 KB): the phone builds the inputs and runs the
forecast itself, also with no connection. Parity with PyTorch: largest difference **0.00007 people** over 24 h ×
48 segments; about 140 ms per forecast in the Dart test runner (unoptimised). Tests:
`test/component_4/edge_forecaster_test.dart`, `tests/test_edge.py`.

## Limitations (say these before an examiner does)
1. The target is synthetic: all RQs test the method, not the real parks. Field counts (Horton: World's End on
   2–3 days; Adam's Peak: flow on the final steps on one Poya night) would calibrate and validate the simulator.
2. One seed at Adam's Peak and in RQ2; three for Horton RQ1 temporal.
3. RQ3/RQ4 control results use the same simulator that generated the data.
4. Usability (SUS) and expert review with DWC / Sri Pada officers are not done yet.
