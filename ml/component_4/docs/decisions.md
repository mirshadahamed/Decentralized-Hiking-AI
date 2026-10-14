# Decision log (Component 4)

Continues the proposal's Appendix 2. Newest at the bottom.

| Date | Decision | Alternatives | Why | Supervisor |
|---|---|---|---|---|
| May 2026 | Build a forecasting tool | accept the static quota; build a counting tool | The gap is prediction, not measurement | — |
| May 2026 | Calibrated synthetic occupancy target + manual field counts | DWC historical data only; install counters | No segment-level data exists; counters are out of scope | — |
| Jun 2026 | Benchmark the ST-GNN against HA, ARIMA, LSTM with a paired t-test | assume the GNN is better | The claim has to be tested | — |
| Jun 2026 | Pretrain on traffic benchmarks, then domain-adapt | train from scratch only | 26 nodes, no sensor history | — |
| Jul 2026 | Use the Cifuentes cascade for capacity | invent a formula | Peer-reviewed method | — |
| Oct 2026 | **Graph nodes = ~300 m trail segments** (26 nodes); edges join touching segments | junctions as nodes | Occupancy is counted per stretch of trail (like a road sensor); OSM junctions alone give < 10 nodes | pending |
| Oct 2026 | **Forecast task: day-ahead.** At 00:00, use the previous 24 h + known calendar/weather for the next 24 h; predict hourly occupancy per segment for the whole day | rolling 1-h-ahead | The permit decision is made per day (FR2: next 24 h) | pending |
| Oct 2026 | **Score open hours only (06:00–18:00)** | all hours | Night-time zeros would make every model look accurate | pending |
| Oct 2026 | **Split: train 2022–23, validate 2024, test 2025** + spatial block CV (4 contiguous blocks; the held-out block has no history input and no training loss) | random split | Stops leakage across time and between neighbouring segments; spatial CV tests forecasting on segments without counts, which is the real deployment case | pending |
| Oct 2026 | **t-test pairs = forecast days** (365 per protocol), Holm-corrected over the baselines, with Wilcoxon and effect size (Cohen's d_z) | pairs = hours; pairs = folds | Hourly errors are autocorrelated (pairing them overstates significance); 4 folds give too little power | pending |
| Oct 2026 | **LSTM baseline = the same network without the graph** (plus a GRU-without-graph ablation) | an unrelated LSTM | The comparison then isolates what the graph adds | pending |
| Oct 2026 | **Forecast → Cifuentes link (v1):** PCC→RCC→ECC per segment, with trail-level social, erodibility and accessibility factors (as in Cifuentes). The forecast adds two daily factors: precipitation (rainy open hours ÷ open hours) and a new **crowding factor per segment** (open hours where forecast occupancy exceeds what the segment holds at social spacing ÷ open hours). Quota = min over segments of ECC | (a) per-segment slope/erosion factors: tried, gave 3–4 people per 300 m, which is not credible; (b) scale demand by peak ratio: unstable at viewpoints | The crowding factor has the same form as Cifuentes' own rain factor, so the forecast enters the RCC step exactly as the proposal says | **must confirm** |
| Oct 2026 | Train the networks on all hours; score open hours only | train on open hours only | When trained on open hours only, the model put people on the trail at 05:00 | — |
| Oct 2026 | Weather "forecast" = actual ERA5 weather (perfect forecast) for PP1 | archived forecasts | Time; flagged as an upper bound in assumptions.md | pending |
| Oct 2026 | Pretraining on METR-LA moved to after PP1; PP1 shows the from-scratch ST-GNN | pretrain before PP1 | 8 days to PP1, CPU-only machine; the from-scratch model is also the comparison point for transfer | pending |
