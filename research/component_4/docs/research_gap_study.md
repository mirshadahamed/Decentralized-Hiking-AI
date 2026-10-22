# Does the component answer the research gap? – Study and plan

21 Oct 2026. Sources:
- the proposal (section 1.3 research gap, 2.1 main objective, 2.2, 3.4–3.5);
- every result in `results/`, the code paths that produce them, and `evaluation_results.md`;
- the Horton Plains 3-seed spatial CV (run `20261021_013444_benchmark_p04s`, finished today);
- the first half of the frozen-core RQ5 run (Adam's Peak still running).

## 1. Verdict

**The work is relevant and goes a long way.** Every building block the gap names exists, works and is tested:
- the trail graph from open data;
- the ST-GNN;
- traffic pretraining;
- the Cifuentes cascade;
- offline inference;
- statistical benchmarking.

**But it does not yet answer the gap as written.** Four of the gap's own conditions are not met by the current
evidence. An examiner reading section 1.3 can find each one:

| | The gap says | What the code / results actually do |
|---|---|---|
| F1 | "… trail graph with **no historical sensor record**" | Evaluated with counts on every segment (temporal) or on 3 of 4 blocks (spatial CV). **The live service feeds the ST-GNN simulated counts for every segment**, which a real park does not have |
| F2 | "… whether that forecast can be **converted into a dynamic capacity recommendation to replace a static daily quota**" | The quota and slot tickets that cut overcrowding by 73 % / 99.6 % are computed with an **empty forecast** (`slots.daily_quota` passes zeros to Cifuentes). The ST-GNN only feeds the displayed safe number. **No experiment compares a forecast-driven capacity with a static quota** |
| F3 | "**micro-spatial bottleneck** forecast … **statistically defensible**" | Judged by MAE / RMSE over all segment-hours, mostly quiet ones. **Never judged as bottleneck detection**: is an over-capacity segment-hour flagged, and how early? |
| F4 | "pretrained on dense urban traffic and **domain-adapted** …" | Pretraining was tested where *days* are scarce, not where *sensors* are scarce, which is the gap's condition. Gains are small or negative (RQ5) |

There is also one validity issue under all of them:
- **F5**: training target, test target and live history all come from the same simulator, driven by the same
  weather and calendar inputs. The results show the method works *in the simulator's world*; field counts
  (December) and a robustness test are needed to show it is not just learning the simulator.

The good news: F1–F4 can be closed with **existing code and data in about 2–3 weeks**. Most of the machinery is
already there:
- the `sensed` mask;
- the entry-control replay;
- the pretrained weights;
- the field-validation tool.

---

## 2. The gap, split into testable claims

> "It is currently unknown whether **(C1)** a Spatio-Temporal Graph Neural Network, **(C2)** pretrained on dense
> urban traffic benchmarks and domain-adapted, using only open geographic, meteorological and calendar data,
> **(C3)** can produce a statistically defensible micro-spatial bottleneck forecast **(C4)** on a tiny, sparse,
> offline wilderness trail graph with no historical sensor record, and **(C5)** whether that forecast can be
> responsibly converted into a dynamic, segment-level carrying-capacity recommendation to replace a static daily
> quota."

| Claim | Evidence today | Status |
|---|---|---|
| **C1** Graph learning adds value on a trail | Horton Plains, segments without counts, 3 seeds: **ST-GNN 2.54 vs LSTM 2.59 vs GRU-no-graph 2.61 vs HA 4.20 (p_Holm < 10⁻¹²)**. A real but **small** gain (2 %), carried by one of 4 blocks. With counts everywhere: tie. Adam's Peak: worse at the summit queue | **Partly**: significant, but small and block-dependent |
| **C2** Traffic pretraining + domain adaptation helps | Fine-tuning helps Horton with 30–90 days of counts (−5 / −12 %); no help at Adam's Peak; zero-shot fails. Freezing the core (new): Horton 365 days 1.65 vs scratch 1.69 vs fine-tuned 1.71; full data equal. **Never tested with sparse sensors** | **Partly**: answered for scarce *time*, not scarce *sensors* |
| **C3** Defensible *bottleneck* forecast | **G3 done (RQ1b):** over-capacity F1 0.80 (Horton) / 0.85 (Adam's Peak) with counts everywhere, all models tied. On held-out segments F1 ≤ 0.56 and the ST-GNN is significantly *worse* than the LSTM / GRU (−0.01 to −0.06); every model misses peaks (recall ≤ 0.33 at Horton) | **Shown with counts; not without** (needs G8 peak-aware loss) |
| **C4** Tiny, sparse, offline, no sensor record | **G1 done (RQ10):** with gate counts only or none, interior MAE is 1.44 at Horton (all counted: 1.42) and 3.9 at Adam's Peak (all counted: 3.8). Bottleneck F1 is unchanged. But the graph and sensors add nothing, because the simulator has no unpredictable, persistent crowd behaviour for them to detect | **Feasible without sensors; graph's value not testable in the current simulator** |
| **C5** Forecast → dynamic capacity that beats a static quota | **G2 done (RQ9):** at equal visitors, the ST-GNN-driven Cifuentes quota cuts over-capacity person-hours by 27 % (Horton) and 24 % (Adam's Peak) vs a static quota. At Adam's Peak it is significantly better than static, weather-only and HA-forecast quotas (76 % of the oracle gain). At Horton it is not significant per day, and HA does as well | **Shown at Adam's Peak; partly at Horton** |
| Field validation (main objective) | Protocol and criteria fixed; counts in December | Pending (by design) |

What is **clearly answered and strong**:
- offline / edge feasibility (RQ6);
- the decision-focused finding that the busy-case forecast is what matters (RQ3);
- spread vs herd advice (RQ8);
- an honest, reproducible benchmark protocol;
- an end-to-end system at two very different parks.

These are good contributions. They are just not the exact question in section 1.3.

---

## 3. Plan: close the gap (priority order)

| ID | Closes | Work | Design | Done when | Effort |
|---|---|---|---|---|---|
| **G1** | **C4, F1** | **Sensor-sparse protocol ("gate-only" and "zero-sensor")** | Separate *input* mask from *loss* mask in `trainer.train`: the synthetic target exists for every segment, so training loss covers all segments. As input, the model sees only what a real park measures: **gate counts** at the access points (check-ins + walk-ins, which the app now records), or **nothing** (calendar + weather + segment descriptions). Compare HA-from-simulation prior, LSTM (same inputs), GRU-no-graph, ST-GNN; 3 seeds; paired tests per segment-day | A table "MAE on interior segments with only gate counts" for both parks; the graph's value measured in the gap's own condition | 4–5 days + overnight runs |
| **G2** | **C5, F2** | **Close the decision loop + RQ9 "does the forecast make the quota better?"** | Feed the day-ahead forecast into the daily quota and slot plan (Cifuentes FCcrowd from the forecast, as the proposal says). Replay 2025 with 5 capacity rules: (a) **static quota** (one number all year, DWC-style); (b) classic Cifuentes with weather; (c) + HA forecast; (d) + ST-GNN forecast; (e) + perfect forecast (oracle). Metrics: over-capacity person-hours, visitors admitted, days over; paired tests over days | "ST-GNN-driven capacity vs static quota" answered with numbers and its share of the oracle gain | 3–4 days |
| **G3** | **C3, F3** | **Bottleneck-event evaluation** | Over-capacity segment-hour (forecast ÷ capacity at once > 1) as an event. Precision, recall, F1 per model; lead time (hours of warning); hit rate on the 10 busiest days; for all protocols incl. G1 | Bottleneck table in RQ1; claim stated in event terms | 1–2 days |
| **G4** | **C2, F4** | **Transfer where sensors are scarce** | Repeat RQ5 in the G1 protocol: scratch vs fine-tuned vs frozen-core vs (optionally) PeMS04/08 sources. This is the setting the proposal's pretraining argument is about (Mallick et al.: unseen regions) | RQ5 answered for sparse sensors; one clear sentence for the thesis either way | 3 days + runs |
| **G5** | **F5** | **Sim-to-real robustness, before the field data** | Train on the default simulator; test on worlds that break its assumptions: demand ±30 %, arrivals ±1 h, route shares, viewpoint dwell, crowd slowdown, summit flow. Report how each model and each capacity rule degrades | A robustness table; which assumptions the conclusions depend on (targets the December counts) | 3–4 days |
| **G6** | F1 (deployment) | **Make the live service match G1** | Live ST-GNN input = real gate counts from the booking / check-in records (+ halfway counts at Adam's Peak), not simulated per-segment counts; the on-device pack carries the same | The app's forecast uses only data that exist; screens say which | 2 days after G1 |
| **G7** | Main objective | **Field validation (W1)** | December visits as planned; compare simulator *and* G1 model with A1–A3; recalibrate; re-run G1–G5 | Field-validated pilot trail | Dec – Jan |
| G8 | C1 | Model improvements, only where G1/G3 show errors | Capacity / queue-aware input for bottleneck segments; daily / weekly periodic inputs | Only if it improves G3 events | after G3 |

**Order:** G3 (quick, makes every later result interpretable) → G2 → G1 → G4 → G5 → G6, with G7 in December.
G2 and G3 can be done in the week after PP1; G1 and G4 by mid-November.

### Thesis statement after this plan (to adjust to the results)
> On a 48–57-segment trail graph observed only at its gates, an ST-GNN trained on a calibrated synthetic target
> forecasts segment-level bottlenecks [better / no better] than non-graph baselines (G1, G3). Converting its
> forecast into a Cifuentes capacity [reduces / does not reduce] overcrowding compared with a static quota and
> with weather-only capacity (G2). Pretraining on urban traffic helps [only / not] when … (G4). The method holds
> when the simulator's assumptions are wrong by … (G5) and agrees with field counts at … (G7).

---

## 4. What to say at PP1 (honest and strong)
- "Every block of the proposal is built, tested and running offline on a phone.
- The next phase tests the gap in its own words:
  - **only gate counts** (G1);
  - **does the forecast make the quota better than a static one** (G2);
  - **bottleneck detection**, not just error (G3);
  - **pretraining under sparse sensors** (G4).
- Field counts in December validate it."
- Present the 2 % graph gain, RQ5's mixed result and the simulator dependence as known limitations, with G1–G5
  as the corrective plan. This is exactly what the "risk mitigation" and "completion: corrective actions" rows of
  the mark sheet ask for.

## 5. After G1–G3 (21 Oct): why the app still misses the gap, and what to build

### What the new results say
| | Result | Consequence |
|---|---|---|
| G3 | Bottlenecks are caught well with counts (F1 0.80 / 0.85); on uncounted segments every model misses most peaks, and the ST-GNN smooths them away | Point forecasts under-call peaks. Officers need a **probability of over-capacity**, not a single number |
| G2 | A forecast-driven quota beats a static one by 24–27 % at equal visitors (significant at Adam's Peak). No daily quota stops crowding on most days | The decision that matters is **when people enter**, during the day, not the daily total |
| G1 | No counts at all ≈ counts everywhere; graph and gate counts add ≤ 3 % even for forecasts made during the day | In the simulator, crowds are fully explained by calendar + perfect weather + random noise. **Nothing exists for sensors or the graph to detect**, so the gap cannot be shown in this world |

**Root cause:** the simulator. Real trails have things a calendar cannot predict:
- a tour bus or school trip arriving at once;
- a viral post, or a festival nearby;
- a slow group or a closed section that backs walkers up behind it;
- the weather forecast being wrong.

Those are exactly what gate counts and graph propagation are for. Today the app forecasts the simulator's average day very well, and the graph has nothing to add.

### Plan: research core first, then the app shows it

| # | Work | Closes | Effort |
|---|---|---|---|
| **S1** | **Make the simulated world realistically unpredictable** (`src/sim`, tagged configs so old results stay reproducible): (a) persistent demand (AR(1) day effect, not independent noise); (b) event bursts: buses / school groups arriving together on random days; (c) day-to-day shift of the arrival peak; (d) incidents: slow-downs or closures on a segment that back walkers up; (e) **forecast weather instead of observed weather** as model input (Open-Meteo historical forecast archive) | F5; makes C1 / C4 testable | 4–5 days |
| **S2** | Re-run G1 (gate / zero), G3 and G2 on the S1 world, including **forecasts made during the day from gate counts** (08:00 / 10:00 / 12:00) | C1, C3, C4 | 2 days + runs |
| **S3** | **Probabilistic output**: quantile head (P50 / P90) or seed ensemble → probability of over-capacity per segment-hour; calibrated alert threshold, scored with G3 (recall at fixed precision) | C3 (G3's peak miss) | 3 days |
| **S4** | December field counts (G7) collected **through the app** (A4), compared with S1's simulator and the model | Main objective, F5 | Dec |

### App changes (each makes one claim visible in the product)

| # | Feature | Who | What it does | Claim |
|---|---|---|---|---|
| **A1** | **Live crowd map from gate counts** | Ranger, officer, visitor | Check-ins and walk-ins (already recorded) and a ranger's tap-counter at the gate update today's forecast on the phone, offline, every 15 min. The map says "updated 09:40 from 212 gate entries, 18 % busier than expected" | C4: no sensors inside the trail, only the gate |
| **A2** | **Dynamic capacity panel** | Officer | Per day: forecast-driven quota vs static quota, the limiting segment and the hours over capacity ("175 today, static 351: World's End 10–12 h"). Accept or override, and the slot plan follows (`booking._planned` passes the forecast to `daily_quota`) | C5, shown in the app |
| **A3** | **Gate hold advice during the day** | Gate officer | When the updated forecast (A1) puts a segment over capacity in the next 2 h: "Hold entries to the main loop for 30 min" or "send the next groups to Kirigalpotta / the reverse direction". This is the segment-level carrying capacity in real time | C5 with C3; uses RQ8 spread logic |
| **A4** | **Spot counts and forecast check** | Ranger | Count walkers on a segment (tap-counter, works offline, syncs later). Stored as the park's first sensor record; screen "forecast vs counted" (MAE, bottleneck hits) per week. Feeds Records ("counted" next to "estimated") and field validation | C4 (builds the record), F5 |
| **A5** | **Chance of crowding** | Everyone | Colours from the probability of over-capacity (S3), e.g. "70 % chance over capacity at 11:00", instead of a single number | C3 |
| **A6** | **Basis on every number** | Everyone | "No sensors: calendar + weather forecast" / "updated with gate counts" / "counted" | Honesty about F1 |

**Order:**
1. **A2 and A6** first. They need no new research and show C5 immediately; about 2 days.
2. **S1 → S2** next.
3. **A1 + A3**: the on-device update, built once S2 shows that gate counts help.
4. **S3 → A5.**
5. **A4** before December.

If S2 shows gate counts and the graph still add nothing in a realistic world, that is the thesis answer for C1 / C4, stated plainly. A1 then still gives officers today's real numbers, but not as the ST-GNN's contribution.

### Progress (21 Oct, branch `feature/component-4-research-gap`)
| # | Status | Where |
|---|---|---|
| A2 | **Done.** The ticket plan uses the forecast-driven quota by default (`control.default_quota_rule: forecast`); the day's forecast is saved by the refresh. Officer tab "Daily quota" shows forecast / weather-only / same-all-year / own number, the limiting section and its hours. Choosing a rule re-plans the tickets (freeze rule kept) | `booking.resolve_quota`, `set_quota`; `serve/capacity_panel.py`; `GET /admin/capacity/{day}`, `POST /admin/quota`; app `staff/capacity_screen.dart` |
| A6 | **Done.** Basis card on the quota panel; a basis line on the crowd map ("no counters inside the trail") | `capacity_screen.dart`, `bottleneck_screen.dart` |
| A3 | **Done (physics version).** Gate advice for the next 2 h from the gate counts and the coming slots: "hold new entries to X for N min, or send the next groups to Y" | `control/gate_advice.py`; `GET /gate/advice/{day}`; ranger Live tab |
| A4 | **Done.** Ranger "Count" tab (tap counter, works offline, sends once when the signal is back); officer "Forecast check" tab (error, bias, share within 30 %, over-capacity called / false alarms) | `serve/field_counts.py`; `POST /counts`, `GET /segments`, `GET /admin/forecast-check`; `count_screen.dart`, `services/count_store.dart` |
| A5 | **Done (live model).** The pack carries a calibration table P(really over \| forecast fullness) from the deployed model's validation year; the phone shows "% chance" per section | `edge/pack.crowd_calibration`, `eval/uncertainty.py`; `BottleneckDay.chanceOver` |
| S1 | **Done.** Realistic world: AR(1) demand, bus bursts, arrival-peak shift, route-share swings, incidents, forecast weather as input. Off by default; `build_dataset --world s1` → `dataset_s1.npz` | `sim/simulator.py` (`realism`, `day_events`), `data/build_dataset.py` |
| S2 | **Done (RQ11).** In the realistic world counts inside the trail help (−4 / −6 %), and with them the ST-GNN beats both non-graph models at both parks (significant). Gate counts alone add ≤ 1 % | `results/…_sparse_s1` |
| S3 | **Done (RQ12).** The calibrated chance halves the Brier score vs the base rate; the alert on it raises recall (Horton 0.50 → 0.60) and F1 at both parks | `…_sparse_s1/uncertainty/` |
| S4b | **Done (RQ11b).** With 7 / 9 counted sections only the ST-GNN improves the *uncounted* sections (Horton −1.7 %, Adam's Peak −4 %, ~80 % of the all-counted gain); significant vs LSTM and GRU at both parks | `results/…_sparse_s1` (spot) |
| A1 | **Done (server + app).** Today's forecast updated from the rangers' spot counts with the spot-trained ST-GNN (counts at ★ sections are model input; elsewhere a check). Ranger Live tab: "Rest of today · updated with N counts", sections now over capacity, what changed. Phone-offline version: next (the pack needs the spot model) | `live/intraday.py`; `GET /live/forecast/{day}`; `/segments` flags `model_input`; `TodayUpdateCard`, ★ in Count |

## 6. Scope note
Booking, the Adam's Peak advice, the 90-day planner, officer records and the second park go beyond the gap.
They show the system works end to end (design, completion, commercialisation marks). But they are not evidence for
C1–C5. In the thesis they belong in "system" and "extensions" chapters, while G1–G5 form the core results.
