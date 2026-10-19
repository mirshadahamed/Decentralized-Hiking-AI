# Assumptions – Adam's Peak (Sri Pada)

Everything below is an assumption made for the prototype (16 Oct 2026). Each one lists what would replace it.
Config: `configs/parks/adams_peak.yaml` (overrides `configs/default.yaml`). Horton Plains assumptions:
`assumptions.md`.

## Network
| # | Assumption | Value | Why | Replace with |
|---|---|---|---|---|
| A1 | Routes = the four named in OpenStreetMap | Nallathanniya, Palabaddala, Erathna, Dikelikanda ("… Sri Pada Foot-path") | Only these are mapped by name; Murraywatte, Mookuwatte, Malimboda are not found | GPS tracks of the minor routes |
| A2 | **Final link to the summit is approximate** | straight line from the highest mapped path node (~1,974 m) to the summit point (2,192 m DEM), tagged as steps | OSM paths stop ~355 m (vertical ~220 m) below the summit | a GPS track of the last flights of steps |
| A3 | Out-and-back: pilgrims return the way they came | every route up = down | Most pilgrims descend the same route (bus back from the same town) | exit survey |
| A4 | Halfway checkpoint = 50 % of the route length up, never on the last 2 segments | one per route | Stand-in for the existing rest halts (*ambalama*) | the real rest halts used by officers |
| A5 | Segment length ~500 m (Horton: 300 m) | 57 segments | longer routes; keeps the graph small | – |

## Walking
| # | Assumption | Value | Why | Replace with |
|---|---|---|---|---|
| W1 | Speed on steps | 9 m/min up, 18 m/min down (vertical) | typical stair-climbing rates for mixed-age pilgrims | timed climbs |
| W2 | Speed elsewhere | Tobler's hiking function, max grade 0.6 | steep paths | – |
| W3 | Result | Nallathanniya ~3.0 h up, ~2.1 h down; other routes 5–6 h up | matches common guide-book times | – |

## Demand
| # | Assumption | Value | Why | Replace with |
|---|---|---|---|---|
| D1 | Season = Unduvap Poya (Dec) to Vesak Poya (May) | `calendar.season` | the pilgrimage season | – |
| D2 | **Poya days after the `holidays` package's last year are estimated** | full moon in Sri Lanka time, 12 h earlier | the package has no 2027 LK data yet; check against the gazette 2022–2026: 47/62 exact, 62/62 within 1 day | the gazetted calendar when published |
| D3 | When the season's end Poya is not known | the window lasts 150 days (never > 200) | Unduvap → Vesak is ~150 days | – |
| D4 | Daily climbers | base 1,800 in season, ×4 on Poya days, ×0.08 off-season | ~530k a year (published estimates are 0.5–1 M) | Sri Pada Trust / police counts |
| D5 | Route shares | 78 % Nallathanniya, 12 % Palabaddala, 5 % Erathna, 5 % Dikelikanda | Hatton is by far the most used route | counts at each start |
| D6 | Start times | most start 00:00–03:00 to reach the summit by sunrise (~06:00) | the custom | – |
| D7 | Group size | 1 + Poisson(4) | families / village groups | – |

## Bottleneck
| # | Assumption | Value | Why | Replace with |
|---|---|---|---|---|
| B1 | **The final steps let ~25 people/min reach the summit terrace** | `bottleneck.flow_per_min: 25` | narrow steps and terrace; single file in places | timed counts on a Poya night |
| B2 | Time on the summit | 45 min ± 40 % | sunrise, worship, the bell | observation |
| B3 | Queue discipline | first come, first served on the steps | – | – |
| B4 | No queue below ~4,000 climbers a night; p90 wait 139 min at 12,000 | simulator result from B1–B2 | – | compare with reported waits |

## Crowd control (no tickets)
| # | Assumption | Value | Why | Replace with |
|---|---|---|---|---|
| C1 | Pilgrims are never refused; advice only | `booking_mode: advisory` | a pilgrimage, not a park visit | Sri Pada Trust policy |
| C2 | Recommended start = expected wait ≤ 20 min and summit before sunrise | `queue_limit_min: 20` | – | Trust / police choice |
| C3 | **Half the advised pilgrims follow the advice** | compliance 0.5 in the evaluation | no data; reported as a parameter | a pilot season |
| C4 | Advice is spread over windows in batches of 25 so it does not create a new peak | `Advisory.spread` | **Finding:** sending everyone to the same "quiet" time made the queue worse (+22 % person-hours waiting vs no advice, earlier run) | – |
| C5 | Halfway officers release at most their route's share of the summit flow per 10 min while the expected wait is over the limit | `release_rates` | the queue waits at a rest halt instead of on the steep steps | – |
| C6 | Live estimate from manual counts at the halfway points, shifted by the walking time to the summit | `Advisory.nowcast` | no sensors | – |

## Advice for each night (added 19 Oct 2026)
| # | Assumption | Value | Why | Replace with |
|---|---|---|---|---|
| N1 | A night is named after its sunrise date and starts at 18:00 the evening before | `night_start_h: 18` | Pilgrims start the day before and rest in community halls on the way | – |
| N2 | **Climb times depend on the night's crowd** | measured in the simulator at 0, 500, 1,500, 3,000, 5,000, 7,500, 10,000, 13,000 climbers; the nearest level is used | The crowd slowdown (W1/W2 + Greenshields-type density) makes the Nallathanniya climb ~3 h on a quiet night and ~6–7.6 h with the crowd on a busy one | timed climbs on a Poya night |
| N3 | Sunrise at the summit for each date | NOAA solar equations, summit 6.8096 N 80.4994 E, horizon dip for 2,243 m (≈ 5 min earlier) | Sunrise moves 05:48–06:18 over the season | – |
| N4 | **20 % of pilgrims start the evening before** | `evening_share: 0.20` | Reported practice; no counts | survey at the trailheads |
| N5 | Rest-hall capacity around each route's halfway point | Nallathanniya 2,000; Palabaddala 400; Erathna 200; Dikelikanda 200 | Placeholders (many halls and tea stalls on the Hatton side) | count on a field visit |
| N6 | A "good" start reaches the summit at most 2 h before sunrise; on busy nights where only earlier starts make sunrise, the latest of those are offered with an "arrive early" warning | `max_early_h: 2` | Waiting hours in the cold at the top is not a good recommendation | – |
| N7 | Evening plan: start from 18:00, at least 1 h rest at the halfway hall, leave the hall at the latest time that reaches the summit before sunrise with a short wait | – | – | – |

## Results these assumptions give (2025 season, simulation, run `20261016_130836_advisory`)
| Policy | Waiting on the final steps (person-h) | Waiting at halfway (person-h) | Poya nights: most people on the final steps |
|---|---|---|---|
| A. Nothing | 45,649 | 0 | 3,273 |
| B. Recommended start times | 35,471 | 0 | 3,017 |
| C. Halfway checks | 0 | 41,093 | 2,558 |
| D. Both | 0 | 33,050 | 2,410 |

Start times alone cut waiting by 22 % with 2.8 % of pilgrims moving their start. Halfway checks move the waiting
off the steep steps. Both together give the least waiting overall (−28 %). How these change when B1 and C3 are
wrong: `evaluation_results.md` (RQ4).
