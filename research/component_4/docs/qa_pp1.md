# PP1 – Likely questions and short answers

Answer in two or three sentences, then point to the evidence. If you do not know, say what you would do to find out.
Numbers: simulation, test year 2025, 3 seeds unless stated. Full explanations: `pp1_guide.md`.

## A. Problem and gap
**1. What exactly is the problem?**
Parks manage crowds with one fixed daily number (Horton Plains) or none (Adam's Peak), and nobody knows where on
the trail or when crowding happens. Damage and danger happen at bottlenecks, which a park total cannot see.
→ slide 2; slide 16 (quota screen).

**2. What is new here – ST-GNNs already exist?**
They are proven on 200–300-sensor city road networks with years of data. Nobody has tested one on a 48–57-node
trail graph with no sensor record, nor turned its output into a carrying capacity. I test that, claim by claim
(C1–C5), including the parts that do not work. → slide 3.

**3. How do you know the authorities need this?**
Visitor numbers are rising (national parks 1.8 → 1.9 M, +22 % foreign; Adam's Peak multi-hour queues on Poya).
DWC publishes only park totals. Direct interviews are not done yet; surveys are drafted and go out with the data
request the week of 26 Oct. Requirements are marked provisional until then.

**4. Why not just install people counters?**
They cost money, need power and maintenance, and still cover only a few points. The proposal's goal is open data
only. My RQ10 shows the model works from gate counts alone, and rangers' spot counts build a record cheaply.

## B. Data and the synthetic target
**5. Your target is simulated. Isn't the model just learning your simulator?**
That is the main threat (risk R1). Mitigations: (1) every assumption is in YAML and in `assumptions.md`; (2) a
realistic world (S1) adds what a calendar cannot predict – tour-bus bursts, busy spells, shifted peaks, incidents,
forecast weather; (3) December field counts are judged by criteria fixed on 20 Oct, before counting, with one day
held back. Until then, results are "the method works in a calibrated simulation".

**6. How is the simulator calibrated?**
Today it is an estimate, not yet calibrated: 450 visitors on an ordinary weekday (~240k a year, ~660 a day on
average), with known patterns (weekends ×1.9–2.1, Poya ×2.4, morning rain reduces visits); walking speed from Tobler's function × 0.75 for tourists; dwell times at viewpoints; group
sizes. Each value is in `assumptions.md` with what will calibrate it: DWC permit totals (requested) and field counts.

**7. What are the agreement criteria for the field counts?**
A1: MAE ÷ mean observed daily peak ≤ 0.25. A2: Spearman rank correlation ≥ 0.6. A3: hour of the highest count
within ±1 h of the highest prediction on at least half the place-days. → slide 17, `field_validation_protocol.md`.

**8. What if DWC refuses the data?**
Then I use published park totals and news figures to scale demand, and document the request and the refusal in the
decision log. The method does not depend on DWC data; it is a calibration improvement.

**9. Which weather data do you use, and what about CHIRPS?**
Open-Meteo (ERA5 archive + 16-day forecast) hourly. NASA POWER was checked: it agrees on wet days but is one
50 km cell for both parks, so it adds nothing as a feature. CHIRPS is next (daily rain, 5 km).

## C. Model
**10. Explain the ST-GNN in one minute.**
Each trail section is a node. Two graph-convolution layers let each section use its neighbours' recent state; a
GRU reads the last 24 hours; another graph layer spreads that memory; a decoder adds tomorrow's weather and calendar
and outputs people per section for each of the next 24 hours. 13,665 parameters. → slide 6.

**11. Why GCN + GRU and not DCRNN, STGCN or attention (ASTGCN)?**
Those were designed for hundreds of sensors and years of 5-minute data. With 48 nodes and no real counts a bigger
model overfits. GCN + GRU is the smallest model that still separates space and time, so I can remove the graph and
measure it; it also runs as a short loop on a phone. ASTGCN's periodic inputs are a planned improvement.

**12. Why GRU instead of LSTM?**
Fewer parameters, same job. I tested an ST-GNN with an LSTM cell: significantly worse (p = 0.007 at Adam's Peak),
so I dropped it.

**13. How do you handle sections with no counts?**
They are fed as zero with a "sensed = 0" flag, and in the first graph layer their outgoing edges are cut, so a
missing value is never averaged into a neighbour as "empty". Later layers use the full graph.

**14. What is the loss and why?**
Masked L1 (mean absolute error) over open hours and sections with a target. MAE is robust to the rare huge peaks
and is in people, so it is easy to read. Downside: it rewards under-forecasting peaks – RQ1b shows that – so a
peak-aware loss or a calibrated alert threshold is next.

**15. What does the graph actually add?**
Honestly, a little: on sections without counts at Horton, MAE 2.54 vs LSTM 2.59 (p < 10⁻¹²), about 2 %, mostly from
one block. With counts everywhere it ties. At the Adam's Peak summit it is worse, because a queue depends on the
steps' capacity, not on neighbours. In my default simulator crowds are fully explained by calendar + weather, so the
graph has little to find; the realistic world (S1) tests it properly (running).

**16. Is 2 % worth a graph model?**
It is not the main value. The contributions are: it works with no sensor record (RQ10), and its forecast makes a
better capacity than a static quota (RQ9). Whether the graph matters is a research answer either way, and I will
report it either way.

## D. Evaluation
**17. How do you prevent data leakage?**
Time split (train 2022–23, validate 2024, test 2025); scalers fitted on training years and sensed sections only;
spatial blocks are contiguous so a test section's neighbours are not in training; tests check all three
(`test_pipeline.py`).

**18. Why test over days and not hours?**
Hours within a day are strongly correlated; treating 8,760 hours as independent would make tiny differences look
significant. Paired t-test and Wilcoxon over 365 days, Holm-corrected for several baselines.

**19. What is spatial block cross-validation?**
The graph is cut into 4 contiguous blocks; one block at a time has no counts and no training loss, and the model must
forecast it from the rest. It is the realistic case: most sections of a real trail have no counter.

**20. Why ARIMA so bad?**
SARIMA is fitted per section on 60 days with a 24-hour season. It cannot use the calendar (Poya, holidays) or weather
forecasts, which drive trail crowds. That is exactly why it is a baseline.

**21. RMSE as well as MAE?**
Both are computed and saved for every run; slides show MAE because it is in people. RMSE tells the same story.

**22. Why only 3 seeds?**
CPU-only training; each run is ~10 min per model per seed and the protocols multiply that. Three seeds show the
spread and every significant result held across them. More seeds where the result is borderline.

## E. Capacity and control
**23. Explain Cifuentes.**
Physical capacity (space and time) × correction factors (social spacing, erosion, steepness, rain, wet ground,
trail condition, and my forecast-crowding factor) = real capacity; × management capacity 0.7 = effective capacity.
The most limiting section sets the trail's number. → `technical_design.md` §6.

**24. Where does the forecast enter Cifuentes?**
FCcrowd = share of open hours in which the forecast exceeds what the section holds at once (groups of 10, 50 m
apart). It lowers the real capacity on days the model expects crowding.

**25. Who chose 0.7, 50 m, groups of 10?**
Standard Cifuentes-style values from the literature; they are placeholders until DWC confirms them (plan W9).
Officers can also override the daily number in the app (audited).

**26. Does the forecast-driven quota really beat a static one?**
At equal visitors admitted: −27 % over-capacity time at Horton, −24 % at Adam's Peak (significant at Adam's Peak vs
static, weather-only and historical-average quotas). At Horton a historical-average forecast does as well and
per-day tests are not significant. → slide 10.

**27. Why do slot tickets work so much better (−99.6 %)?**
Crowding is about when people walk. A daily total cannot spread arrivals; tickets per 30-min slot can, and the LP
checks every section every half hour.

**28. Isn't turning people away unfair at a pilgrimage site?**
Yes, so Adam's Peak gets no tickets: recommended start times and halfway holds only. Nobody is refused.

## F. Transfer, edge, integration
**29. Did pretraining on traffic help?**
Only at Horton with 30–90 days of counts (−5 % / −12 %). Not at Adam's Peak; zero-shot is 4–5× worse than a
historical average; with a full year it slightly hurts (negative transfer). Freezing the core helps only Horton at
365 days. Clear, mostly negative answer to that part of the gap. → slide 13.

**30. Then why keep pretraining?**
It is in the proposal and it is a genuine research question; a negative answer is a result. Next I test it where
*sensors*, not days, are scarce (the gap's condition), add PeMS04/08 and one adversarial method.

**31. Does it really run on a phone?**
Yes: the same forward pass in plain Dart from a 175 KB daily pack, equal to PyTorch within 0.0001 people, ~150 ms
in the test runner; ONNX 2 ms on a laptop core. Next: timing on two Android phones.

**32. Why not quantise to int8?**
Tested: saves 2 KB but raises error 25 % at Adam's Peak. Not worth it for a 100 KB model.

**33. How does Module 3 use your output?**
`GET /module3/feed` with a JSON Schema (`c4-module3-feed-1`) and contract tests; the same feed is inside the offline
pack. Module 3's owner signs off the schema in November.

## G. Engineering, requirements, process
**34. What standards / best practices did you follow?**
Reproducible runs (seed, config, git hash per folder), no-leakage tests, 101 Python + 34 Flutter tests, ruff lint,
GitHub Actions CI, JSON Schema contract, role checks on the server, scrypt password hashes, audit log, model and
data card with licences. → slide 7.

**35. How are requirements traced?**
`docs/requirements.md`: every FR / NFR → code → test → result. FR6–FR13 were added during the build.

**36. Are you on schedule?**
Ahead: the Gantt gives Component 4 months 3–8 and we are in month 2. Field validation and team integration are
planned for December – February as in the Gantt.

**37. What did AI tools do?**
As declared in the proposal (Appendix 3): drafting help and explanations. In development I used an AI coding
assistant; every result is produced by code in the repository, re-run from saved configs, tested, and I can explain
each part. Responsibility stays with me.

**38. What is your biggest weakness?**
No real counts yet, and the graph's added value is small in the current simulator. Both have dated actions:
realistic world (running), field counts (December).

## H. Commercialisation
**39. Who pays?**
DWC / Sri Pada Trust per site (licence), plus a small booking fee per ticket; tour operators for planning. No
sensors to buy; a new site is one config file. Next: letters of interest and a cost per park.
