# Component 4 – Requirements and traceability (21 Oct 2026)

Stakeholders (proposal section 5): DWC / SLTDA officials (permits, quotas), rangers and tour operators (act on the
numbers), hikers and pilgrims (benefit, get advice), and Module 3 (consumes the feed).

**Status of validation:** requirements FR1–FR5 / NFR1–NFR5 come from the proposal and are still **provisional**
until the stakeholder surveys and interviews return (plan W8). FR6–FR12 were added during the build; each traces
to a stated problem in section 1.1 of the proposal. Every row lists the code, the automated test and the result
that show it.

## Functional requirements

| ID | Requirement | Code | Test (automated) | Evidence / result | Status |
|---|---|---|---|---|---|
| FR1 | Build and maintain a trail graph from OSM with terrain and weather per node | `src/data/graph.py`, `terrain.py`, `weather.py`, `build_dataset.py` | `test_pipeline::test_graph_size_and_connectivity`, `test_out_and_back_trails_turn_at_the_peak` | 48 segments (Horton Plains), 57 (Adam's Peak) | Done |
| FR2 | Forecast occupancy per segment for the next 24 h with the ST-GNN | `src/models/stgnn.py`, `src/serve/predict.py`, `lib/.../domain/edge_forecaster.dart` | `test_pipeline::test_model_output_shape_and_seed`; Flutter `on-device ST-GNN matches PyTorch` | RQ1, RQ1b, RQ10 | Done |
| FR3 | Convert the forecast into a segment-level carrying capacity (Cifuentes PCC → RCC → ECC) | `src/capacity/cifuentes.py` | `test_live::test_wet_ground_lowers_the_daily_quota`, `test_capacity_panel::test_forecast_quota_never_above_classic` | RQ9: −27 % / −24 % over-capacity vs static | Done |
| FR4 | Output usable by the authority dashboard and Module 3 | `src/serve/module3.py`, `docs/schema/c4_module3_feed.schema.json`, `GET /module3/feed` | `test_module3` (6 contract tests, incl. a renamed field breaks the contract) | Feed also in the offline pack | Done; Module 3 sign-off open |
| FR5 | Log the synthetic-target limitation with every output | `src/serve/predict.py` (`disclaimer`), basis lines in the app | `test_module3::test_feed_means_what_it_says` | In every forecast JSON and screen | Done |
| FR6 | Sell entry tickets per trail and 30-min slot so no segment goes over capacity; offer alternatives when full | `src/control/slots.py`, `booking.py` | `test_control` (cannot overbook, plan never exceeds capacity, walk-in share kept, freeze rule) | −99.6 % over-capacity person-hours (2025 replay) | Done |
| FR7 | Let an officer choose the daily quota rule (forecast / weather / same all year / own number) and see why | `booking.resolve_quota`, `src/serve/capacity_panel.py`, `capacity_screen.dart` | `test_capacity_panel` (4 tests); Flutter `officer daily quota` | Slide "The problem in the product" | Done |
| FR8 | Advise the gate during the day when a section will go over capacity in the next 2 h | `src/control/gate_advice.py`, `GET /gate/advice/{day}` | `test_gate_advice` (2 tests); Flutter `gate advice` | Hold / redirect text | Done |
| FR9 | Let rangers record spot counts offline and compare them with the forecast | `src/serve/field_counts.py`, `count_screen.dart`, `count_store.dart` | `test_field_counts` (3 tests); Flutter `ranger counts walkers with no signal`, `officer forecast check` | The park's first sensor record; feeds RQ7 | Done |
| FR10 | Show the chance that a section goes over capacity, not only a number | `src/eval/uncertainty.py`, `src/edge/pack.py` (`crowd_calibration`) | `test_uncertainty::test_calibration_is_monotone_and_matches_rates` | Calibrated on the validation year | Done |
| FR11 | Give a 2–90-day outlook with a range and suggestions (quieter day / time / trail) | `src/planning/` | `test_planning` (4 tests incl. no information after the issue date) | Lead-time backtest | Done |
| FR12 | Adam's Peak: recommended start times and halfway holds without tickets | `src/control/advisory.py` | `test_adams_peak`, `test_api_adams_peak` | −22 % waiting (start times); final steps cleared (both) | Done |
| FR13 | Officer records: visitors per trail and day, past / today / future, CSV | `src/serve/records.py`, `records_screen.dart` | `test_records` (5 tests) | – | Done |

## Non-functional requirements

| ID | Requirement | How it is met | Test | Result | Status |
|---|---|---|---|---|---|
| NFR1 | On-device inference < 2 s | ONNX export; pure-Dart forward pass from a daily pack | `test_edge`; Flutter `fast enough for a phone` | 2 ms ONNX (laptop core), ~150 ms Dart | Done on laptop; **real phone open (W4)** |
| NFR2 | Degrade gracefully without a fresh weather forecast | Historical-average fallback, typical weather after 16 days | `test_live`; Flutter `offline-first` | Labelled `fallback_used` | Done |
| NFR3 | Other OSM parks without architectural change | One YAML per park, `C4_PARK` | `test_adams_peak::test_park_config_replaces_horton_values`, `test_horton_plains_is_unchanged_by_the_park_switch` | Adam's Peak added by config | Done |
| NFR4 | Actionable for a non-technical official: one number per segment + plain note | Safe number per trail, "why this limit", basis lines | Flutter `day screen shows the safe limit and why` | – | Done; check with officials (W8) |
| NFR5 | No personally identifiable data | Booking codes only; counts are numbers | `test_api::test_passwords_are_not_stored_in_plain_text` | – | Done |
| NFR6 | Security: staff roles enforced on the server; audit | Roles ranger < officer < admin; scrypt hashes; lockout | `test_api::test_roles_are_enforced`, `test_lockout_after_five_failures` | – | Done |
| NFR7 | Reproducibility: seeds logged, no leakage | Seeds in config; run folders with config + git hash; scalers on training years | `test_pipeline::test_scaler_uses_train_period_only`, `test_splits_do_not_overlap_in_targets`, `test_simulator_is_reproducible` | – | Done |
| NFR8 | Offline-first app | Stores the last responses and the edge pack | Flutter `offline-first: a screen seen once opens again with no connection` | – | Done |

## Risk register

| # | Risk | Likelihood / impact | Mitigation | Status (21 Oct) |
|---|---|---|---|---|
| R1 | No real segment counts: the target is synthetic | High / high | Assumptions listed; S1 realistic world; robustness (G5); pre-registered field criteria A1–A3; counting tool in the app | Field visits December |
| R2 | The graph adds little over an LSTM | Medium / high | Reported either way; test in the gap's own setting (gate-only, S1); periodic inputs, peak-aware loss | S2 running |
| R3 | DWC / SLTDA do not share visitation data | High / medium | Use published park totals; document the request and answer | Request to send week of 26 Oct |
| R4 | Stakeholders not reached before PP2 | Medium / high | Surveys drafted; interviews through the supervisor; SUS test with the app | W8 |
| R5 | Module 3 integration late | Medium / medium | Versioned schema, contract tests, feed in the offline pack | Contract done |
| R6 | Last part of the Adam's Peak trail missing in OSM | Medium / medium | Approximate link flagged; GPS track on the field visit | Open |
| R7 | Phone slower than expected | Low / medium | 13,665-parameter model; HA fallback | W4 |
| R8 | Traffic pretraining does not transfer | Happened at Adam's Peak | Reported as a finding (RQ5); frozen core and sparse-sensor test (G4) | Partly answered |
| R9 | CPU-only training time | Medium / low | Small graph, early stopping, overnight runs | Ongoing |
