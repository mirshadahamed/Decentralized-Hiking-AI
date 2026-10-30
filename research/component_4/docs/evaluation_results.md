# Component 4 – Research evaluation (results of 16 Oct 2026)

All results are from **simulation** (synthetic occupancy target; see `assumptions.md`, `assumptions_adams_peak.md`).
Test year 2025; day-ahead forecasts from midnight; errors are people per segment per hour (open hours).
Significance: paired tests over forecast days (or nights), Holm-corrected where several comparisons are made.

| RQ | Question | Short answer |
|---|---|---|
| RQ1 | Does the trail graph improve forecasts? | **On trail sections without counts, yes at Horton Plains** and on ordinary Adam's Peak trail; **not at the Adam's Peak summit queue**, where an LSTM is better. With counts everywhere: a tie with the LSTM at both parks (3 seeds) |
| RQ2 | Does a model trained on one park work on another? | **Not as it is** (worse than a historical average). Pre-training **does** help a new park learn from little data, but with ≤ 90 days of counts a historical average is as good |
| RQ3 | Do better forecasts give better crowd control? | **Only with the right decision rule.** Advice from the median forecast captures ~16–18 % of what perfect knowledge would; advice from the **P90 (busy case)** captures all of it (115 %, −56 % waiting) |
| RQ4 | Do the Adam's Peak policies hold if the assumptions are wrong? | **Halfway checks: yes at every flow tested. Start times: −42 % at the assumed flow, useful up to 30 people/min, slightly harmful at 35** |
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

## RQ3 – Value of the forecast for crowd control (`src.control.evaluate_forecast_value`, run `results/adams_peak/20261021_214725_forecast_value`)

Re-run 21 Oct 2026 with the current advice model (crowd-dependent climb times, evening starts, real sunrise;
`assumptions_adams_peak.md` N1–N7). Adam's Peak, 132 nights of the 2025 season, 50 % of advised pilgrims follow
the advice. The advice is computed before the night from each forecast; the night then happens as it really did.

| Advice from | Forecast error (MAE, climbers/night) | Waiting on the final steps (person-h) | Cut vs no advice | Share of the perfect-knowledge benefit | Pilgrims moved |
|---|---|---|---|---|---|
| No advice | – | 45,841 | – | 0 % | 0 % |
| Calendar average | 805 | 45,841 | 0 % | 0 % | 0 % |
| Forecast 30 days ahead (P50) | 649 | 41,852 | 9 % | 18 % | 0.5 % |
| Forecast 1 day ahead (P50) | 646 | 42,173 | 8 % | 16 % | 0.5 % |
| **Forecast 1 day ahead (P90)** | 1,246 | **20,182** | **56 %** | **115 %** | 3.8 % |
| Perfect knowledge | 0 | 23,586 | 49 % | 100 % | 2.2 % |

Paired bootstrap 95 % intervals over nights are in `tests.json` (P90 vs median advice and perfect vs no advice
both exclude 0). Queues form on only a few nights a season, so per-night tests have little power.

**Reading (unchanged by the re-run, stronger):** a smaller forecast error does not by itself give better control.
The median forecast is too low on exactly the rare peak nights, so the advice does not trigger; the P90 forecast
errs on the safe side and beats even "perfect knowledge of the total" (which still misjudges where in the night
people start). This is why officers plan on the busy case (decisions.md, 16 Oct 2026): a result about
**decision-focused** forecast evaluation, not only accuracy.

---

## RQ4 – Sensitivity (`src.control.evaluate_advisory --sweep`, run `results/adams_peak/20261021_214443_advisory_sweep`)

Re-run 21 Oct 2026 with the current advice model. Final-steps flow (people per minute; assumed 25) × share of
pilgrims who follow the advice (assumed 50 %). Main run (`20261021_213251_advisory`, flow 25, 50 %): start times
alone cut waiting on the final steps by **42 %** (was 22 % with the old model), moving 2.3 % of pilgrims' starts;
halfway checks remove all waiting on the final steps; both together cut total waiting by 44 %.

Cut in waiting on the final steps from **start times alone (B)**, vs no control:

| Flow (people/min) | 25 % follow | 50 % follow | 75 % follow | 100 % follow | No control: person-h |
|---|---|---|---|---|---|
| 15 | 52 % | 77 % | 77 % | 73 % | 221,038 |
| 20 | 40 % | 62 % | 66 % | 66 % | 100,125 |
| 25 | 25 % | 42 % | 45 % | 45 % | 45,912 |
| 30 | 11 % | 24 % | 31 % | 33 % | 19,614 |
| 35 | −14 % | −14 % | −14 % | −14 % | 8,483 |

- **Halfway checks (C, D)** remove all waiting on the final steps at every flow (the hold is obeyed perfectly in the
  simulator; real compliance at the rest halts is an open question). Total waiting with **both (D, 50 %)** is 78 %
  (flow 15) to 31 % (flow 30) lower than no control, and no lower at flow 35.
- **Start times (B)** work when the final steps are a real bottleneck (≤ 30 people/min). At 35 people/min queues are
  short and the advice makes them slightly worse (−14 %, a few hundred person-hours): there the app should not advise.
- The **flow is the number that matters most** (waiting changes 26-fold between 15 and 35 people/min): measuring it
  on one Poya night is the most valuable field work.

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

**Horton Plains spatial CV, 3 seeds** (run `results/20261021_013444_benchmark_p04s`, held-out segments):
- **Mean MAE:** ST-GNN **2.54** · LSTM 2.59 · GRU without graph 2.61 · historical average 4.20.
- **Significance (Holm):** ST-GNN vs LSTM −0.05 and vs GRU without graph −0.07, both p < 10⁻¹².
- **Per block** (ST-GNN vs LSTM): 3.78 vs 3.72, 3.97 vs 3.98, 0.91 vs 0.80, **1.51 vs 1.88**. So the
  significant gain is small (2 %) and comes from one block.

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

## RQ1b – Bottleneck events, not just error (G3; `src.eval.bottlenecks`, run `20261021_094226_bottlenecks`)

**Event:** a segment-hour during open hours (test year 2025) where people on the segment exceed `capacity_at_once`
(Cifuentes spacing). Same trained models as RQ1, 3 seeds (Adam's Peak temporal GRU-no-graph: 1 seed). Bootstrap
over days, 2,000 resamples. Full table: `metrics.csv`; tests: `tests.json`.

F1 of over-capacity segment-hours (precision / recall in brackets):

| Park, protocol | Historical avg | LSTM | GRU (no graph) | ST-GNN |
|---|---|---|---|---|
| Horton, all segments counted | 0.75 | 0.80 | 0.80 | **0.80** (0.88 / 0.74) |
| Horton, held-out segments | 0.03 | 0.32 | **0.35** | 0.29 (0.33 / 0.26) |
| Adam's Peak, all counted | 0.49 | 0.85 | 0.85 | **0.85** (0.86 / 0.84) |
| Adam's Peak, held-out | 0.03 | **0.56** | 0.55 | 0.54 (0.43 / 0.70) |

ST-GNN − other F1, 95 % interval:
- **All segments counted:** a tie at both parks. Every interval contains 0 or is within ±0.01.
- **Held-out segments:** the ST-GNN is **worse**:
  - Horton: −0.03 vs LSTM [−0.04, −0.03]; −0.06 vs GRU without graph [−0.07, −0.05].
  - Adam's Peak: −0.03 vs LSTM [−0.03, −0.02]; −0.01 vs GRU without graph [−0.02, −0.01].
- **Busy events (≥ 0.8 capacity):** the same pattern.

**Reading:**
- The ST-GNN's lower MAE on held-out Horton segments (RQ1) **does not carry over to bottleneck detection**. It
  smooths peaks from neighbours: lower average error, but fewer over-capacity hours flagged (recall 0.26).
- Every model under-forecasts peaks on segments without counts (recall ≤ 0.33 at Horton). MAE training rewards
  that, so claim C3 needs a peak-aware loss or a calibrated alert threshold (G8).
- Day level is not informative here: in the simulator, some segment is over capacity on 363 of 365 Horton days.
- "Warning hours" (~8 h) is simply the hour of the event, because the forecast is issued at midnight.

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

**Domain adaptation by freezing the pretrained core** (run `20261021_064549_pretrain_transfer`, variant
`frozen`). The graph and recurrent layers keep the traffic weights; only the input and output layers adapt.

MAE by amount of target-park data:

| Park | Days | Scratch | Fine-tuned | Frozen core |
|---|---|---|---|---|
| Horton Plains | 30 | 3.11 | **2.96** | 3.07 |
| | 90 | 2.72 | **2.40** | 2.43 |
| | 365 | 1.69 | 1.71 | **1.65** |
| | full | **1.42** | 1.43 | 1.42 |
| Adam's Peak | 30 | **9.89** | 10.47 | 12.15 |
| | 90 | **9.59** | 9.62 | 10.03 |
| | 365 | **6.25** | 6.69 | 6.95 |
| | full | **4.23** | 4.59 | 4.88 |

Freezing helps only Horton Plains at 365 days, by 2 %. At Adam's Peak it is the worst variant at every amount of
data. This confirms the reading above: the traffic core fits trails whose crowds look like traffic peaks, and not
the summit queue.

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

## RQ10 – No sensor record: gate counts only, or nothing (G1; `src.eval.sparse_sensors`)

**Runs:** `results/20261021_100713_sparse` (Horton Plains) and `results/adams_peak/20261021_133744_sparse`.

**Setup:**
- The synthetic target trains every segment.
- As input, the model sees either the gate segments' counts (`gate`) or no counts at all (`zero`).
- Scored on the interior segments, test year 2025, 3 seeds.

| Interior MAE | Horton, gate | Horton, zero | Adam's Peak, gate | Adam's Peak, zero |
|---|---|---|---|---|
| Historical average (simulation) | 1.63 | 1.63 | 11.28 | 11.28 |
| LSTM | 1.44 | 1.44 | **3.87** | 3.90 |
| GRU (no graph) | **1.43** | 1.44 | 3.97 | 3.94 |
| ST-GNN | 1.45 | 1.45 | 4.00 | 3.96 |

Over-capacity F1 (G3 events): 0.80–0.81 at Horton and 0.85–0.86 at Adam's Peak, the same for every model and both settings.

**Paired tests (Holm), ST-GNN vs each model:**
- vs the historical average: better at both parks, p < 10⁻¹¹.
- vs the LSTM and GRU at Horton: slightly worse, by 0.01–0.02 (p ≤ 0.02).
- vs the LSTM at Adam's Peak: slightly worse, by 0.07–0.12 (p ≤ 0.04).
- vs the GRU at Adam's Peak: no difference.

**Forecasts made during the day** (same models, issued at 08:00 / 10:00 / 12:00 for the rest of the day): gate counts
improve the interior MAE by at most 3 % over no counts.

**Reading:**
- Without any counts, a model trained on the calibrated simulation forecasts almost as well as with every segment
  counted (Horton 1.44 vs 1.42). That supports deployment at a park with **no sensor record**.
- The **graph and the sensors add nothing**, because in the simulator a day's crowd is fully set by calendar +
  weather + independent noise:
  - day-to-day noise is lognormal with sd 0.15 and does not carry over between days;
  - the arrival-time pattern is the same every day;
  - the weather covariates are the *observed* weather, i.e. a perfect weather forecast.
- So nothing exists that counts or neighbours could reveal. This is finding F5 made concrete: the simulator cannot
  show the value of what the gap asks about. See `research_gap_study.md`, section 5.

### RQ10 on the realistic world S1 (S2; run `results/20261021_172706_sparse_s1`, Horton Plains, 3 seeds)
S1 adds what a calendar cannot predict: persistent busy spells, tour-bus bursts, shifted arrival peaks, route-share
swings, incidents, and a **forecast** (not observed) weather input. Interior-segment MAE, test year 2025:

| Input | Historical avg | LSTM | GRU (no graph) | ST-GNN | ST-GNN vs LSTM (Holm) |
|---|---|---|---|---|---|
| Every segment counted | 2.35 | 2.21 | 2.20 | **2.19** | −0.019, p = 0.002 (better) |
| Gate counts only | 2.35 | 2.29 | 2.29 | 2.29 | +0.002, p = 1.0 (tie) |
| No counts | 2.35 | 2.28 | 2.30 | 2.30 | +0.018, p = 0.12 (tie) |

Forecasts issued during the day (10:00) with gate counts: 1.09 vs 1.07 with every segment counted.

**Reading:**
- In a world with unpredictable crowds, **counts inside the trail matter**: every segment counted beats the
  historical average by 7 %; gate counts only by 3 % (ST-GNN vs HA, p_Holm = 0.08 – not significant).
- **The graph now helps when counts exist**: the ST-GNN is significantly better than both the LSTM and the same
  network without the graph (−0.013, p_Holm = 0.007). Small (≤ 1 %), but it is the first setting where the graph's
  value is significant with counts everywhere – the default simulator had nothing for it to find.
- **With gate counts only, the graph adds nothing**: information that never reaches the gates cannot be propagated.
  So C1 holds only where some sections are counted; C4 (no sensor record) is feasible but leaves most of the
  attainable gain unused. Spot counts by rangers (A4) are the cheap way to recover it – the next experiment
  (a few counted sections + gates).

## RQ11 – The same question in a realistic world (S1 + S2; `src.eval.sparse_sensors --world s1`)

**Runs:** `results/20261021_172706_sparse_s1` (Horton Plains) and `results/adams_peak/20261021_220619_sparse_s1`.

**The S1 world:** the simulator gets things a calendar cannot predict:
- busier or quieter spells that last for days;
- bus bursts;
- a morning peak that comes earlier or later;
- swings in the trail split;
- incidents that slow a section;
- models given a **weather forecast with errors** instead of the observed weather.

Scored on the interior segments, 3 seeds.

| Interior MAE | Horton: none | Horton: gates | Horton: all counted | Adam's Peak: none | Adam's Peak: gates | Adam's Peak: all counted |
|---|---|---|---|---|---|---|
| Historical average | 2.35 | 2.35 | 2.35 | 12.76 | 12.76 | 12.76 |
| LSTM | 2.28 | 2.29 | 2.21 | **7.12** | **7.14** | 6.84 |
| GRU (no graph) | 2.30 | 2.29 | 2.20 | 7.21 | 7.14 | 6.78 |
| ST-GNN | 2.30 | 2.29 | **2.19** | 7.21 | 7.19 | **6.73** |

Forecasts made during the day: rest-of-day MAE at 08:00, Adam's Peak, ST-GNN:

| Counts the model sees | MAE |
|---|---|
| None | 4.90 |
| Gates only | 4.87 |
| Every segment | 4.24 |

**Paired tests (Holm), ST-GNN vs the other models:**
- **Every segment counted:** better than the LSTM at both parks (−0.02, p = 0.002 Horton; −0.11, p = 0.003 Adam's Peak). Better than the GRU without graph at both (p = 0.007 / 0.018).
- **Gates only or no counts:** no significant difference, or slightly worse.

**Over-capacity F1:**

| Park | Range across models and settings | Best |
|---|---|---|
| Horton | 0.61–0.64 | The historical average ties the models |
| Adam's Peak | 0.74–0.76 | The ST-GNN is highest in every setting |

**Reading:**
1. **The world now has something to learn, and counts on the trail help:** −4 % (Horton) and −6 % (Adam's Peak)
   MAE vs no counts, and −13 % during the day at Adam's Peak.
2. **With those counts the graph adds a small, significant gain at both parks.** This is the first result where the
   ST-GNN beats both non-graph models on held-out time at Adam's Peak. Claim C1 holds *when segments are counted*.
3. **Gate counts do not carry into the trail** (≤ 1 % at any hour). An entry count says how many came, not where
   the day's deviations are: incidents, route swings, slow sections. So a gate-only phone update (A1 as planned) is
   **not worth building**. What helps is counting *inside* the trail, which the rangers' spot counts (A4) provide.

### RQ11b – A few counted sections: does the graph carry them to the rest? (S4b)

**Runs:** `results/20261022_042402_sparse_s1` (Horton) and `results/adams_peak/20261022_054232_sparse_s1`.

**Setup:**
- Counted sections ("spot"):
  - Horton: the 2 gates and 5 viewpoints (7 of 48);
  - Adam's Peak: the 4 gates, the summit and the halfway checkpoints (9 of 57).

  These are places where a ranger can stand and count (A4).
- Scored on the **uncounted** interior sections: 41 at Horton, 48 at Adam's Peak.
- Compared with the RQ11 models on the same sections.

MAE on uncounted sections, mean of 3 seeds (day-ahead / issued at 08:00):

| Counts the model sees | Horton: LSTM | Horton: GRU (no graph) | Horton: ST-GNN | Adam's Peak: LSTM | Adam's Peak: GRU (no graph) | Adam's Peak: ST-GNN |
|---|---|---|---|---|---|---|
| None | 1.76 / 1.50 | 1.78 / 1.51 | 1.78 / 1.52 | 5.45 / 3.29 | 5.52 / 3.30 | 5.50 / 3.31 |
| Gates only | 1.77 / 1.51 | 1.78 / 1.51 | 1.78 / 1.51 | 5.47 / 3.28 | 5.45 / 3.28 | 5.48 / 3.29 |
| **Gates + spots** | 1.77 / 1.51 | 1.79 / 1.52 | **1.75 / 1.49** | 5.51 / 3.31 | 5.46 / 3.26 | **5.28 / 3.13** |
| Every section | 1.71 / 1.46 | 1.72 / 1.46 | 1.70 / 1.45 | 5.32 / 3.03 | 5.26 / 2.96 | 5.23 / 2.97 |

Paired tests (Holm), ST-GNN vs the other models in the spot setting, interior sections:
- **Horton:** −0.02 vs LSTM (p = 0.002); −0.03 vs GRU without graph (p < 0.001).
- **Adam's Peak:** −0.25 vs LSTM (p < 10⁻⁵); −0.20 vs GRU without graph (p < 10⁻⁴).

**Reading:** this is the research gap's own condition: a sparse, offline trail graph with a handful of counts.
- **Only the graph model uses a few counts to improve the sections nobody counts.** The LSTM and the GRU without
  graph do not improve on uncounted sections when spots are counted, because they have no way to pass a count to a
  neighbour.
- **The ST-GNN does improve:**
  - Horton: −1.7 %, recovering about a third of the gain from counting every section;
  - Adam's Peak: −4 %, recovering **about 80 %** of that gain with 9 of 57 sections counted.
- **Claims C1 and C4 are supported here** (simulation; field check in December). It also makes the A4 spot counts
  a model input, not only a check.

## RQ12 – A calibrated chance of over-capacity (S3; `src.eval.uncertainty`)

Same S1 runs, seed 42, in folder `uncertainty/`.

**Brier score:** 0.007 at both parks, against 0.014 (Horton) and 0.022 (Adam's Peak) for the base rate. So the
chance is informative.

**Alert on the chance, threshold chosen on the validation year (0.25–0.40), vs the "forecast > capacity" rule:**

| Park | Recall: point rule → chance | F1 change |
|---|---|---|
| Horton | 0.49–0.54 → 0.58–0.65 | +0.01 to +0.03 for every model and setting |
| Adam's Peak | Up for gate / zero, e.g. GRU 0.66 → 0.81 | +0.00 to +0.02 |

**Reading:** part of the peaks that point forecasts miss (G3) are caught when the alert uses the calibrated chance.
This is what the app now shows per section (A5).

## RQ9 – Does the forecast make the daily quota better than a static one? (G2; `src.control.evaluate_quota`)

**Runs:** `results/20261021_100715_quota` (Horton Plains) and `results/adams_peak/20261021_102216_quota`.

**Setup:**
- Test year 2025 (simulation).
- The same groups arrive every day for every rule. Each trail has a daily quota, filled first come, first served at the gate.
- A quota trades visitors for crowding, so every rule is swept over quota multipliers. Each is then re-run at the
  multiplier that admits **as many visitors as the static quota**, and the rules are compared at that level.

| Rule (equal visitors admitted) | Horton: over-capacity person-h | vs static | Adam's Peak: over-capacity person-h | vs static |
|---|---|---|---|---|
| Static (one number per trail, all year) | 60,444 | – | 93,140 | – |
| Classic Cifuentes with the day's rain | 46,157 | −24 % | 77,227 | −17 % |
| + historical-average forecast (FCcrowd) | 43,855 | −27 % | 74,204 | −20 % |
| **+ ST-GNN forecast (FCcrowd)** | **44,023** | **−27 %** | **70,840** | **−24 %** |
| + perfect forecast (oracle) | 42,859 | −29 % | 63,721 | −32 % |

Visitors admitted at the matched level: Horton 58 %, Adam's Peak 28 % of those who came.

Share of the oracle's gain over the static quota: ST-GNN 93 % (Horton), 76 % (Adam's Peak).

Paired Wilcoxon over days, ST-GNN rule vs:
- **Adam's Peak:** static p < 10⁻⁷, weather-only p < 10⁻⁴, historical-average forecast p = 0.013. Significant on every comparison.
- **Horton Plains:** static p = 0.89, weather-only p = 0.28, historical-average forecast p = 0.51. Not significant: the
  total cut is large, but it comes from a minority of busy days, while most days change little either way.

**Reading:**
- A forecast-driven Cifuentes quota beats a static quota at equal visitor numbers at both parks: a cut of 24–27 % in over-capacity time.
- The ST-GNN's own contribution beyond weather and the historical average is clear only at Adam's Peak, where demand
  swings most (Poya days, season). At Horton Plains a historical-average forecast does as well.
- No daily quota removes over-capacity on most days, because crowding is about *when* people walk, not how many come
  in a day. That is why slot tickets and walk advice (RQ8) cut far more. The forecast's natural place is
  therefore in the slot plan's capacity and the walk advice, not only in the daily number.

**Code:** `slots.EntryControl.daily_quota(..., forecast=)` accepts the day-ahead forecast. The live ticket plan uses
the forecast-driven quota by default (`control.default_quota_rule: forecast`); officers can switch the rule per day
(`booking.resolve_quota`, `POST /admin/quota`).

## RQ13 – Closed-loop control at the gate (MPC) vs day-ahead plans (`src.control.evaluate_mpc`, 27 Oct 2026)

**Runs:** `results/20261027_215804_mpc` (default world) and `results/20261027_220425_mpc_s1` (realistic world S1).
Horton Plains, 2025, the same groups for every policy.

**The controller** (`src/control/mpc.py`) re-plans entry caps every 30 min:
- **Input:** only the gate counts so far.
- **Forecast:** the day's expected visitors, corrected by arrivals so far vs expected.
- **Constraint:** every section under 90 % of capacity over the next 3 h.
- **Groups over the cap:** wait up to 2 h, then are offered another trail; the share that accepts is the compliance.

Realistic world (S1):

| Policy | Over-capacity cut | Admitted | Turned away | Sent to another trail | Waited at the gate (mean wait) |
|---|---|---|---|---|---|
| B: same daily quota all year | 62.7 % | 57.1 % | 42.9 % | – | – |
| D: day-ahead slot tickets + moving (needs advance booking) | **99.6 %** | **63.0 %** | 37.0 % | 13.3 % | 35.8 % moved to a later slot in advance |
| MPC, 50 % accept another trail | 99.3 % | 59.0 % | 41.0 % | 3.1 % | 40.9 % (92 min) |
| MPC, 75 % accept | 99.3 % | 59.2 % | 40.8 % | 3.4 % | 41.1 % (92 min) |
| MPC without feedback | 99.3 % | 58.9 % | 41.1 % | 3.1 % | 40.6 % (92 min) |

The default world shows the same pattern: B cut 61 % / admitted 58 %; D 99.6 % / 64.8 %; MPC 99.3 % / 61.5 %.

Paired Wilcoxon tests over days, MPC (50 %) vs:
- **B:** −191 over-capacity person-hours per day and +12 people admitted per day (p < 10⁻⁴ for both).
- **D:** +1.4 person-hours per day and −26 admitted per day (p < 10⁻¹⁷); D is better on both.
- **Without feedback:** no difference (p ≥ 0.3).

**Reading:**
1. **With only gate counts and no booking, the controller removes 99 % of over-capacity time.** A fixed daily
   quota removes 61–63 %, while admitting fewer people. This answers "can a forecast-driven, segment-level capacity
   replace a static quota" for open-access sites, which have no booking system (Adam's Peak, Pekoe Trail, walk-ins).
2. **Advance booking is still better** (+4 points admitted, half the remaining overcrowding). It knows every
   group's wish in advance and moves them before they travel. The gate controller learns only when people arrive.
3. **The cost is waiting:** 4 in 10 visitors wait at the gate, about 1.5 h on average. The next step is to move
   that wait *before* the trip: tell visitors by phone the start time the controller would give them (N3).
4. **Feedback and redirect acceptance hardly matter in this setup.** Waiting people get priority over forecast
   arrivals, so the corrected forecast changes little. On busy days the other trails are full too, so only about
   3 % can be redirected.

### RQ13b – Start times sent before the trip (N3), on top of gate control

**Run:** `results/20261027_233052_mpc_s1`.

**Setup:**
- The evening before, groups with the app get the earliest start, at or after the time they wanted, that still has
  room in the controller's day plan (up to 3 h later). 80 % of them follow it.
- Everyone then goes through the same gate controller.
- Realistic world (S1), 2025.

| Policy | Over-capacity cut | Admitted | Moved by advice | Waited at the gate (mean) |
|---|---|---|---|---|
| D: advance booking | 99.6 % | 63.0 % | – | – |
| MPC only | 99.3 % | 59.0 % | – | 40.9 % (92 min) |
| MPC + start times, 30 % with the app | 99.3 % | 59.9 % | 10.3 % | 42.0 % (95 min) |
| MPC + start times, 60 % with the app | 99.2 % | 61.6 % | 19.1 % | 43.6 % (92 min) |
| MPC + start times, 90 % with the app | 99.3 % | 61.9 % | 22.0 % | 42.2 % (88 min) |

Paired tests (60 % with the app):
- vs MPC only: +17 admitted per day (p < 10⁻²⁹), with slightly more gate waiting (+27 person-hours per day).
- vs advance booking: −9 admitted per day, **not significant** (p = 0.49).

**Reading:**
- **With start times on the phone, an open-access site gets as many visitors in as with advance booking**, with no
  booking system, and still with 99 % less over-capacity time.
- **But the gate wait does not shrink.** The advice plan is made from the forecast; on the day, the realistic world
  differs (bursts, busy spells), so the gate still holds people.
**Priority at the gate for groups on their advised time** (N3p, run `results/20261028_000127_mpc_s1`):

| Policy | Over-capacity cut | Admitted | Gate wait (person-hours/year) | Wait if on advised time | Wait otherwise |
|---|---|---|---|---|---|
| MPC + start times, 60 % with the app | 99.2 % | 61.6 % | 158,343 | – | – |
| MPC + start times + priority, 60 % with the app | 99.3 % | 59.5 % | **85,061** | **0.5 min** | 72 min |
| MPC + start times + priority, 90 % with the app | 99.4 % | 59.7 % | **78,380** | 0.5 min | 70 min |

Priority vs no priority (60 % with the app), per day:
- **Gate waiting:** −201 person-hours (p < 10⁻⁵⁸), i.e. it **halves**.
- **Admitted:** −13.5 people (p < 10⁻²³).

**Reading:** there is a clear trade-off, and the park chooses.
- **Start times without priority** admit the most (as many as advance booking).
- **With priority**, waiting halves and people who follow the advice walk straight in. That is a strong reason to
  use the app. But a few more people are turned away, because the later slots fill up.

**Next:** re-send start times during the morning from the live gate counts, so the advice follows the day.

### RQ13c – Stress tests: what the controllers did not plan for (`evaluate_mpc --world s1 --stress`, 29 Oct 2026)
Realistic world, 2025, run `20261029_232929_mpc_stress_s1`. Over-capacity cut vs no control / people admitted / gate
wait (person-hours):

| scenario | B static quota | D booking | MPC (gate control) | N3p (start times + priority) |
|---|---|---|---|---|
| none | 62.7 % / 57.1 % / 0 | 99.6 % / 63.0 % / 0 | 99.3 % / 59.0 % / 148k | 99.3 % / 59.5 % / 85k |
| surge: 50 % more people every day | 76.6 % / 44.3 % / 0 | 99.8 % / 52.0 % / 0 | 99.6 % / 47.8 % / 197k | 99.6 % / 48.3 % / 125k |
| visitor forecast 30 % too low | = none | = none | 99.3 % / 58.9 % / 148k | 99.3 % / 59.6 % / 97k |
| visitor forecast 30 % too high | = none | = none | 99.3 % / 59.0 % / 148k | 99.3 % / 59.5 % / 77k |
| rain not planned for (day planned dry) | = none | 90.3 % / 70.5 % / 0 | 89.0 % / 67.0 % / 158k | 89.0 % / 67.4 % / 92k |

- **Surges and wrong visitor forecasts:** gate control still cuts over-capacity by 99 % or more; the gate counts
  correct the forecast (feedback). A wrong forecast only changes how long people wait for start times (a too-low
  forecast gives out too many early start times: 97k vs 85k person-hours).
- **Rain the plan did not expect is the weak spot:** every controller lets ~10 % of the overcrowding through
  (18–21k person-hours), because capacity drops and nobody told the plan. Remedy in the live system: the rain
  forecast is refreshed every evening, and a ranger can lower the limits during the day (`POST /incident`, E1).
- B and D do not use the visitor forecast, so the forecast scenarios leave them unchanged.

## RQ14 – Knuckles: one area, several mechanisms (`C4_PARK=knuckles`, `src.control.evaluate_knuckles`, 30 Oct 2026)
Simulated 2025, run `results/knuckles/20261030_010706_knuckles`. Assumptions: `assumptions_knuckles.md` (most
trails are drawn approximately; OSM is thin in the range).

**Guided-trek permits** (5 treks, 21 guides at 4 entries; a mean of 28 group requests a day):

| Policy | Groups served / day | People over a trek's daily cap / day | Days with a trek over its cap | Guides idle / day |
|---|---|---|---|---|
| none (a guide is free → go) | 16.6 | 6.5 | 91 | 4.4 |
| first come first served within the cap | 15.5 | 0.0 | 0 | 5.5 |
| LP plan made the evening before | 14.1 | 0.3 | 26 | 6.9 |

- The cap removes all over-capacity days at the cost of about one group a day.
- The evening-before LP allocation is **worse** than first come first served: it plans on expected requests, and the
  real day differs. **Design change:** the live system gives permits first come first served within the cap while a
  guide is free (`permits.request`). The LP stays only as the suggested guide roster per trek.

**Overdue alarm** (20,000 simulated groups, 1 % in trouble):

| Rule | False alarms / 1,000 groups that are fine | Troubled groups caught | Alarm, minutes after due back |
|---|---|---|---|
| fixed: walking time + 2 h | 136 | 72 % | 76 |
| model: expected time for group size and rain + 2.3 × spread (≥ 45 min, sooner in rain) | 34 | 58 % | 124 |

- The model rule cuts false alarms by 4×. Rangers stop trusting an alarm that is wrong 1 time in 7.
- The cost is a later alarm for groups in real trouble. The margin (`overdue_z`) is the knob for the Forest Department to choose.

**Open-viewpoint advice** (weekends; visitors who would arrive in the busy hours come in a quiet hour instead):
- Pitawala Pathana's peak drops from 28 to 20 / 19 / 22 people at once when 30 / 60 / 90 % follow the advice.
- Sera Ella's peak drops from 19 to 15 / 13 / 14.
- The car parks never overflow with the assumed weekend demand.
- **Check against weekend counts in December:** the real Pitawala crowds may be much larger than assumed.

### RQ14b – Pekoe stage advice: which advice spreads the peaks? (`src.control.evaluate_stages`, 30 Oct 2026)
Pekoe Trail, 2025 weekends, viewpoint sections hold 30 people at once (`control.hotspot_at_once`, A). Run
`results/pekoe_trail/20261030_011618_stage_advice`. Person-hours over capacity at the viewpoints per weekend day
(none: 1.80):

| Advice to walkers on a busy stage | 30 % follow | 60 % follow | 90 % follow |
|---|---|---|---|
| start early (everyone the same advice) | 2.79 | 3.59 | 6.35 |
| a quieter neighbouring stage | 1.09 | 1.46 | 3.39 |
| **spread: each walker a different start, 06:00–11:00** | 1.25 | **0.86** | **0.46** |

- The same advice to everyone **moves the crowd** instead of spreading it. "Start early" makes it worse the more
  people follow it, and so does sending everyone to the neighbouring stage once most follow.
- Personal, spread start times cut the overcrowding by 53–74 %. This is the same lesson as RQ8 (spread, not herd).
- **Design change:** `/stages/{day}` now gives busy stages a `spread_window`, and the app shows each visitor their own
  suggested start.

## RQ1 on the Pekoe Trail – a long, sparse trail (`C4_PARK=pekoe_trail`, `src.run_benchmark`, 28 Oct 2026)
323 km, 22 stages, ~163 walkers a day (simulated, `docs/assumptions_pekoe_trail.md`); seed 42, no ARIMA.

| sections | model | temporal MAE | temporal RMSE | spatial MAE (4 folds) |
|---|---|---|---|---|
| 161 × 2 km (`20261027_231345_benchmark`) | HA | 0.415 | 1.01 | 0.53 |
| | LSTM / GRU / ST-GNN | 0.348 | 1.25 | 0.35 |
| 54 × 6 km (`20261028_214959_benchmark_6km`) | HA | 0.993 | 2.12 | 1.32 |
| | LSTM | 0.846 | 2.21 | **0.98** |
| | GRU (no graph) | 0.843 | 2.17 | 1.39 |
| | ST-GNN | 0.844 | 2.18 | 1.28 |

- **2 km sections are too fine:** most sections are empty most hours, every network learned "empty" (flat validation
  loss) and lost to HA on RMSE and at the busy places.
- **6 km sections:** the networks learn and beat HA by ~15 % on MAE over time (p_holm < 0.001); ST-GNN = LSTM = GRU
  (n.s.). On held-out sections the ST-GNN beats the no-graph GRU (−0.11, p < 0.001) but not the LSTM; fold 2
  (the busy Haputale–Ella stages) is where every network struggles (MAE 1.8–3.4 vs ~0.7 on other folds).
- **Meaning:** on a trail with few walkers the graph adds little; the bottleneck problem is at the few busy stages.
  Pekoe forecasts should be read per stage, and its control is advisory stage advice (P4), not section quotas.

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

## O1 – Rain from a second source (`src.data.rain_check`, 21 Oct 2026)

Daily rain 2022–2025 at each park's weather point: Open-Meteo / ERA5 (what the model uses) vs NASA POWER
(PRECTOTCORR). Runs `results/20261021_013055_rain_check`, `results/adams_peak/20261021_013106_rain_check`.

| | Horton Plains | Adam's Peak |
|---|---|---|
| Daily correlation (Pearson / Spearman) | 0.65 / 0.72 | 0.52 / 0.61 |
| Mean rain, Open-Meteo vs NASA POWER (mm/day) | 6.1 vs 6.4 | 10.9 vs 6.4 |
| Wet-day agreement (≥ 1 mm) | 80 % | 77 % |
| Monthly correlation | 0.77 | 0.51 |

- **The two sources agree on which days are wet** (77–80 %), which is what the demand and FCpre factors use.
- **They disagree on amounts.** This is worst at Adam's Peak: Open-Meteo has 70 % more rain on the wet
  south-western slope.
- **NASA POWER cannot tell the two parks apart.** It gives *identical* series for both: they fall in the same
  ~50 km grid cell. It is too coarse to be a useful extra feature for a single trail.
- **Decision:** keep Open-Meteo (finer grid, hourly) as the feature and NASA POWER as a published cross-check.
  Add **CHIRPS** (~5 km, daily) as the second source the proposal names (W5).

## Limitations (say these before an examiner does)
1. The target is synthetic: all RQs test the method, not the real parks. Field counts (Horton: World's End on
   2–3 days; Adam's Peak: flow on the final steps on one Poya night) would calibrate and validate the simulator.
2. One seed at Adam's Peak and in RQ2; three for Horton RQ1 temporal.
3. RQ3/RQ4 control results use the same simulator that generated the data.
4. Usability (SUS) and expert review with DWC / Sri Pada officers are not done yet.
