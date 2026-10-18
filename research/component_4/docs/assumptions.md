# Assumptions (Component 4)

Every number the pipeline uses that is **not** measured. Values live in `configs/default.yaml`.
Status: **A** = from a cited/open source, **E** = engineering estimate (to calibrate with field counts / DWC data).

## Trail graph
| Item | Value | Status | Reason |
|---|---|---|---|
| Area | OSM paths/tracks/footways/steps in bbox 80.775–80.825 E, 6.770–6.815 N | A | OpenStreetMap |
| Main loop | Visitor Center → Mini World's End → World's End → Baker's Falls → Visitor Center (shortest path through the POIs) | A | OSM; matches the park's standard circuit |
| Loop length | 8.3 km walked, 7.5 km unique (shared ~670 m start/end stretch, 80 m Baker's Falls spur) | A | OSM; commonly quoted as ~9 km |
| Other trails | Kirigalpotta (Visitor Center → peak, 5.2 km, out and back) and Thotupola Kanda (trailhead → peak, 1.3 km, out and back) | A | OSM "Kirigalpotta Trail", "Thotupola Trail (2km)" |
| Graph nodes | 48 segments of ~300 m (loop 27, Kirigalpotta 17, Thotupola 4) | E | Above the proposal's 25–40 because two trails were added; 300 m kept for consistency |
| Edges | segments that share an end point (weight 1) + one road link Visitor Center ↔ Thotupola trailhead (weight 0.5) | E | Thotupola is only reachable by a 4.2 km drive on the Pattipola road |

## Terrain (Copernicus GLO-30 DEM)
| Item | Value | Status | Reason |
|---|---|---|---|
| Elevation profile | sampled every 30 m, smoothed over 150 m | E | 30 m DEM noise |
| Grade cap | ±25 % | E | Next to the World's End escarpment the DEM cells mix in the ~870 m cliff; raw values gave 40 % grades the trail does not have |
| TWI | ln(a / tan β), D8 flow accumulation | A | Standard definition |
| Wet ground | TWI ≥ 8 | E | Upper tail of the park's TWI distribution |

## Weather and calendar
| Item | Value | Status | Reason |
|---|---|---|---|
| Weather | Open-Meteo archive (ERA5-based), hourly, one grid point for the whole park | A | Park is ~5 km across; ERA5 grid is ~25 km, so all segments share weather |
| Future weather | the model is given the **actual** weather of the forecast day (a perfect forecast) | E | Upper bound. Later: replace with archived forecasts or add forecast noise |
| Holidays & Poya | `holidays` package, country LK | A | Matches the gazetted Poya list for 2025 |
| School holidays | 5–20 Apr, 1–31 Aug, 10–31 Dec | E | Approximate; post-COVID calendars shifted |
| Long weekend | ≥ 3 consecutive weekend/holiday/Poya days | E | |

## Simulator (synthetic occupancy target)
| Item | Value | Status | Reason |
|---|---|---|---|
| Base demand | 450 visitors on an ordinary weekday | E | Gives ~240k visitors/yr and ~660/day on average; **calibrate against DWC permit totals** |
| Day of week | Mon–Sun ×1.0, 0.9, 0.9, 0.95, 1.1, 1.9, 2.1 | E | Domestic weekend tourism |
| Public holiday / Poya | ×1.9 / ×2.4 (the larger of day-of-week, holiday and Poya is used) | E | Poya long-weekend crowding reported for hill-country sites (proposal ref [10]) |
| Long weekend / school holiday | ×1.3 / ×1.25 | E | |
| Month | Jan–Dec ×1.1, 1.1, 1.0, 1.4, 0.9, 0.8, 0.85, 1.0, 0.8, 0.8, 0.85, 1.2 | E | April New Year and Dec–Feb peak season; monsoon months lower |
| Morning rain | demand × exp(−0.06 × rain mm 05:00–10:00), floor 0.35 | E | People cancel when it rains in the morning |
| Day-to-day noise | lognormal, σ = 0.15 | E | |
| Group size | 1 + Poisson(2.2) (mean 3.2) | E | Families and small groups |
| Arrival time | 85 % Normal(06:54, 45 min), 15 % Uniform(08:30–12:30); gate 06:00, last entry 13:00 | E | Visitors come early to see World's End before the mist |
| Trail choice | 86 % World's End loop, 9 % Thotupola, 5 % Kirigalpotta | E | World's End is the main attraction; Kirigalpotta is long and strenuous. **Check against DWC data and the hiker survey** |
| Thotupola start | walk starts 12 min after the gate (drive + parking) | E | 4.2 km road |
| Kirigalpotta last start | 09:30 | E | ~10 km return; must finish before closing. Check DWC rules |
| Direction (loop) | 85 % standard (Mini World's End first), 15 % reverse | E | |
| Walking speed | Tobler: v = 6·exp(−3.5·\|grade + 0.05\|) km/h × 0.75 leisure factor × lognormal(σ = 0.12) per group | A + E | Tobler (1993); 0.75 because tourists stop for photos. Gives a median loop of **3.4 h** (commonly quoted 3–4 h) |
| Rain slowdown | ×0.85 if ≥ 0.5 mm/h, ×0.70 if ≥ 3 mm/h | E | Slippery, muddy trail |
| Crowd slowdown | speed × 1 / (1 + (ρ / 0.4)²), floor 0.4; ρ = persons per metre | E | Greenshields-type density–speed effect. Two passes per day so crowding feeds back |
| Dwell (median, log-σ 0.4) | Mini World's End 8 min, World's End 20 min, Baker's Falls 12 min, Kirigalpotta peak 20 min, Thotupola peak 15 min | E | Viewing and photo stops |
| Observation noise | Poisson(true × lognormal(σ = 0.10)) | E | Error of a manual headcount |

**Known limitation (FR5):** the forecast models learn from this simulator, so part of what they learn is the
simulator's own rules. Mitigation: every assumption above is listed, the data has noise, and field
counts (after PP1) will be used to calibrate and to check the synthetic target.

## Cifuentes capacity
| Item | Value | Status | Reason |
|---|---|---|---|
| Space per person | 1 m of trail | A | Cifuentes (1992) convention for trails. Viewpoints (World's End, Baker's Falls) are treated as trail length, not platform area, which makes them look stricter than they are. Measure the platform areas on a field visit |
| Group size / gap | 10 people, 50 m between groups | A/E | Common values in Cifuentes applications |
| Open hours | 12 (06:00–18:00) | E | |
| Erodibility | 1.5 × fraction of segment with TWI ≥ 8 | E | Wet peaty ground erodes under trampling |
| Accessibility | 1.0 × fraction with grade 10–20 % + 1.5 × fraction > 20 % | A | Standard Cifuentes slope classes |
| Precipitation | share of open hours with forecast rain ≥ 0.5 mm | E | Daily, from the forecast (the dynamic part) |
| Management capacity | 0.7 | E | Placeholder until DWC staffing data is available |
| Per trail | social, erodibility and accessibility factors are computed for each trail separately; park quota = sum of trail quotas | E | Each visitor hikes one trail |

## Entry control and booking
| Item | Value | Status | Reason |
|---|---|---|---|
| Entry slots | 30 min, 06:00–12:30 starts; Kirigalpotta none from 09:30 | E | Gate hours; Kirigalpotta length |
| Segment capacity at once | Cifuentes social spacing (groups of 10, 50 m apart) × management capacity 0.7 × (1 − rain share) × capacity standard | A + E | Same parameters as the capacity cascade |
| Viewpoints | at least 50 people at once (before × 0.7) | E | They are platforms, not 1-m trail. **Measure platform areas on a field visit** |
| Access points | Visitor Center and Thotupola trailhead not limited | E | Facilities, not trail |
| Safety margin | plan to 90 % of capacity | E | The linear model ignores crowd slowdown; every plan is checked in the full simulator |
| Response table | 300 simulated walkers per trail × slot × dry/wet; people per segment per half hour per ticket | E | Measured with the simulator (tiny cohorts, no crowd effect) |
| Walk-in share | 20 % of every slot not bookable | E | Visitors without internet or a booking must still be able to come |
| Gate window | 15 min before to 15 min after the slot start | E | Practical tolerance at the gate |
| Booking horizon | tomorrow to 90 days ahead; days beyond the forecast use typical rain for that week | E | Same horizon as the planning model |
| Evaluation behaviour | visitors accept a slot up to 2 h later; 30 % accept another trail; the rest are offered another day | E | **Check with the hiker survey** |
| Capacity standard | ×1 (strict Cifuentes) by default; trade-off shown for ×1 … ×4 | E | DWC's choice, not the model's |

## 90-day planning model
| Item | Value | Status | Reason |
|---|---|---|---|
| Inputs | calendar of the target day, typical weather for that time of year (±15 days, 2022–23), mean visitors of the 28 days before the issue date, lead time | E | What is actually known weeks ahead; no actual weather, no hourly counts |
| Daily model | gradient-boosted quantile regression, trained on (issue, target) pairs inside 2022–23 at 12 lead times (2–90 days) | E | |
| Range | P10/P90 = P50 × 10th/90th percentile of actual ÷ P50 on the 2024 validation year (conformal) | A | The model's own quantiles were too narrow (60 % coverage) |
| Split per trail | trail shares by day type (weekday / weekend-holiday / Poya-long weekend) from 2022–23 | E | |
| Hourly profile | people per segment-hour per visitor, by demand tercile × wet/dry morning, mixed by the chance of a wet morning | E | Captures the crowd slowdown on busy days |
| Rain for capacity | rain share of open hours = chance of a wet morning × 0.5 | E | Rough; replace with an hourly rain climatology |
| Crowd level | 1–5 = quintiles of daily visitors in 2022–23 | E | |
| Suggestions | other date (±7 days, ≥ 20 % fewer on the loop); later start (meet ≤ half the World's End peak; walking time to World's End from Tobler); reverse direction (≥ 20 % fewer); other trail only if crowd level ≥ 3, loop over quota and the trail has room under its own quota | E | Thresholds are design choices; check acceptance in the hiker survey |
