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
| C4 | Advice is spread over windows in batches of 25 so it does not create a new peak | `Advisory.spread` | **Finding:** sending everyone to the same "quiet" time made the queue worse (46,765 vs 38,419 person-hours) | – |
| C5 | Halfway officers release at most their route's share of the summit flow per 10 min while the expected wait is over the limit | `release_rates` | the queue waits at a rest halt instead of on the steep steps | – |
| C6 | Live estimate from manual counts at the halfway points, shifted by the walking time to the summit | `Advisory.nowcast` | no sensors | – |

## Results these assumptions give (2025 season, simulation, run `*_advisory`)
| Policy | Waiting on the final steps (person-h) | Waiting at halfway (person-h) | Poya nights: most people on the final steps |
|---|---|---|---|
| A. Nothing | 38,419 | 0 | 3,333 |
| B. Recommended start times | 29,016 | 0 | 3,047 |
| C. Halfway checks | 0 | 34,185 | 2,543 |
| D. Both | 0 | 26,368 | 2,409 |

Start times alone cut waiting by 24 % with 2.8 % of pilgrims moving their start. Halfway checks move the waiting
off the steep steps. Both together give the least waiting overall.
