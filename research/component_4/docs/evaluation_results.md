# Component 4 – Research evaluation (results of 16 Oct 2026)

All results are from **simulation** (synthetic occupancy target; see `assumptions.md`, `assumptions_adams_peak.md`).
Test year 2025; day-ahead forecasts from midnight; errors are people per segment per hour (open hours).
Significance: paired tests over forecast days (or nights), Holm-corrected where several comparisons are made.

| RQ | Question | Short answer |
|---|---|---|
| RQ1 | Does the trail graph improve forecasts? | **On trail sections without counts, yes at Horton Plains** and on ordinary Adam's Peak trail; **not at the Adam's Peak summit queue**, where an LSTM is better. With counts everywhere: a tie with the LSTM at both parks (3 seeds) |
| RQ2 | Does a model trained on one park work on another? | **Not as it is** (worse than a historical average). Pre-training **does** help a new park learn from little data, but with ≤ 90 days of counts a historical average is as good |
| RQ3 | Do better forecasts give better crowd control? | **Only with the right decision rule.** Advice from the median forecast captures ~20 % of what perfect knowledge would; advice from the **P90 (busy case)** captures all of it |
| RQ4 | Do the Adam's Peak policies hold if the assumptions are wrong? | **Halfway checks: yes at every flow tested. Start times: useful when the final steps are a real bottleneck (≤ 25 people/min), little effect above** |
| RQ5 | Does pretraining on urban traffic (METR-LA, PEMS-BAY) help? | **Only at Horton Plains with 30–90 days of counts** (−5 to −12 % vs scratch); no help at Adam's Peak; zero-shot fails; a historical average still wins at ≤ 90 days |
| RQ8 | Can offline advice to hikers prevent overcrowding? | **Yes, if it is spread:** up to −73 % with nobody turned away (as much as the daily limit). Identical advice on every phone backfires at high compliance (+12 % worse). Limit + spread advice: −95 % |
| RQ6 | Can the forecast run on the phone within 2 s? | **Yes**: 2 ms (ONNX, laptop core), ~140 ms in plain Dart, offline |

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
*without* counts (spatial CV, Horton Plains significant).

**Adam's Peak spatial CV, 3 seeds** (run `results/adams_peak/20261020_110028_benchmark_p04s`, MAE on held-out
segments):

| Block held out | Historical avg | LSTM | GRU (no graph) | ST-GNN |
|---|---|---|---|---|
| 0 – summit and the final steps | 31.37 | **28.16** | 30.12 | 33.33 (seeds 26.8–42.4) |
| 1 | 11.80 | **2.53** | 2.69 | 3.04 |
| 2 | 12.68 | 1.37 | 1.38 | **1.30** |
| 3 | 13.16 | 0.87 | 0.90 | **0.84** |
| Mean | 17.25 | **8.23** | 8.77 | 9.63 |

The ST-GNN is significantly worse than the LSTM overall (+1.40, p_Holm < 0.001), and still far better than the
historical average. It is best on the two blocks of ordinary trail (2, 3). It loses on the block that holds the
summit queue, where one seed fails badly. **Reading:** propagating counts from neighbours helps on segments that
behave like their neighbours. It hurts at the summit: a queue there forms from the *capacity of the final steps*,
not from what nearby segments look like, and nothing else on the mountain behaves like it. So the graph's value
on unseen segments is confirmed at Horton Plains and on ordinary Adam's Peak trail, but not at the bottleneck
itself. **Next:** add the queue state as an input, or give the summit its own output head (B1 in the plan).

## RQ5 – Pretraining on urban traffic (objective O3, P0-1; `src.pretrain.traffic`, `src.eval.pretrain_transfer`, 20 Oct 2026)

The ST-GNN is pretrained on METR-LA and then PEMS-BAY. The target is congestion = 1 − speed / free-flow speed,
averaged per hour, on a road graph with Gaussian-kernel edge weights (run `20261020_050444_pretrain`). After
pretraining, the test congestion MAE is 8.1–8.3 % on METR-LA (the hour-of-day average gets 6.4 %) and 4.2–4.4 %
on PEMS-BAY (the average gets 4.8 %). The pretrained weights are then used at both parks:
- **zero-shot:** no training on the park; only the output is scaled, using 30 days of counts;
- **pretrained:** fine-tuned on the park;
- **scratch:** trained from random weights on the same data.

Same inputs and splits as RQ2, 3 seeds. Run `20261020_075237_pretrain_transfer`; MAE in people per segment per hour.

| Park | HA (2 y) | Zero-shot | Scratch, full | Pretrained, full | HA 30 d | Scratch 30 d | Pretrained 30 d | HA 90 d | Scratch 90 d | Pretrained 90 d | HA 365 d | Scratch 365 d | Pretrained 365 d |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Horton Plains | 1.60 | 7.04 | **1.42** | 1.43 | **2.06** | 3.11 | 2.96 | **1.61** | 2.72 | 2.40 | **1.61** | 1.69 | 1.71 |
| Adam's Peak | 10.89 | 36.62 | **4.23** | 4.59 | 9.99 | 9.89 | 10.47 | **9.21** | 9.59 | 9.61 | 10.63 | **6.25** | 6.69 |

Paired tests against the matching scratch model (Holm-corrected, over the 365 test days):

| Training data | Horton Plains | Adam's Peak |
|---|---|---|
| 30 days | pretraining **better** (−0.15, p < 0.001) | pretraining worse (+0.58, p < 0.001) |
| 90 days | pretraining **better** (−0.32, p < 0.001) | no difference (p = 0.45) |
| 365 days | pretraining slightly worse (+0.02, p < 0.001) | pretraining worse (+0.43, p < 0.001) |
| Full training data | pretraining slightly worse (+0.01, p = 0.005) | pretraining worse (+0.36, p < 0.001) |

- **Zero-shot traffic weights are useless on trails.** They are 4–5× worse than the historical average.
- **Pretraining helps only where the park is traffic-like and data are scarce.** Horton Plains is a daytime
  peak on a small network. There, fine-tuning beats training from scratch with 30 and 90 days of counts
  (−5 % and −12 %).
- **It does not help Adam's Peak.** The night pilgrimage with a summit queue has no counterpart in road traffic,
  and pretraining is worse or no different at every amount of data.
- **With a full year or more of data, pretraining costs a little everywhere.** This is negative transfer:
  the network starts from a road-traffic solution and does not fully leave it.
- **A historical average from the same few days still wins up to 90 days at both parks.** At Adam's Peak the
  network overtakes it at 365 days (6.25 vs 10.63). At Horton Plains it does not overtake it with 365 days of
  the target park alone (1.69 vs 1.61); it needs the full multi-year training set.

**Reading:** the proposal's research gap gets a clear, mostly negative answer. Dense urban traffic is a
useful starting point only for a new trail park with a few months of counts, and only if its crowds behave like
traffic peaks. Pretraining on the other park (RQ2) gives similar gains. In both cases, a new park should start
with the historical average.

## RQ8 – Offline walk advice vs entry limits (`src.control.evaluate_advice`, run `20261020_234527_advice`)

Horton Plains, 2025 test year (simulation), the same groups each day as the entry-control test.
- **The advice.** Every phone has tomorrow's ST-GNN forecast, from the benchmark's day-ahead predictions. For
  each trail, direction (the World's End loop either way) and start hour, it works out how full the sections will
  be when the hiker is on them.
- **When it applies.** A plan that meets a section at ≥ 80 % of what it holds is "crowded". Hikers with a crowded
  plan follow the advice with probability *c*.
- **Herd:** every phone gives the single best option.
- **Spread:** each phone draws one of the good options, weighted by room left (as the app does,
  `domain/walk_advice.dart`).

| Policy | Overcrowding removed | Days overcrowded | Turned away | Changed plan |
|---|---|---|---|---|
| No control (159,330 person-h over capacity) | – | 365 | 0 % | 0 % |
| Daily Cifuentes limit | 72.8 % | 356 | 43.6 % | 0 % |
| Slot tickets + moving | 99.6 % | 250 | 35.3 % | 0 % |
| Herd advice, 25 / 50 / 75 / 100 % follow | 34.9 / 40.7 / 22.5 / **−12.4** % | 364–365 | 0 % | 19–76 % |
| **Spread advice**, 25 / 50 / 75 / 100 % follow | 42.6 / 68.0 / **73.0** / 61.1 % | 364 / 335 / 276 / 310 | **0 %** | 19–76 % |
| Daily limit + spread advice (50 %) | **95.0 %** | 331 | 43.6 % | 20 % |

Wilcoxon over days: every policy differs from no control (p < 10⁻¹⁷). Spread beats herd at every compliance level
(p < 10⁻²⁶; e.g. −321 person-h per day at full compliance).

- **Advice works only if it is spread.** Identical advice moves the crowd together: at full compliance it is worse
  than no advice. This is the same herding found at Adam's Peak (naive start times made the queue 22 % worse).
- **Spread advice at 75 % compliance removes as much as the daily limit, without turning anyone away.** Above
  that it loses ground (61 % at 100 %): the phones do not know what other hikers chose, so the good options fill up.
- **Advice does not replace the limit:**
  - a limit plus spread advice removes 95 %;
  - only slot tickets (a booking that knows every choice) remove almost all overcrowding.
- **Answer to "can offline alternative-route suggestions solve overcrowding?":** they solve a large part of it,
  cheaply and with no signal, if each phone spreads its suggestion. The dynamic limit is still needed on the
  busiest days.
- **Limitations:**
  - it is simulation;
  - compliance is assumed;
  - the forecast is the ST-GNN's day-ahead forecast with observed weather (as in RQ1).

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
