# Pekoe Trail – assumptions (A)

The Pekoe Trail has **no visitor counts at all**: no gate, no tickets, open access at every stage. That is the
research gap's "no historical sensor record" case. Every number below is an assumption, to be replaced with
the trail organisation's figures, guesthouse / booking listings and a field count at one or two hotspot stages.
Config: `configs/parks/pekoe_trail.yaml`.

| What | Value | Basis / how to check |
|---|---|---|
| Route | 22 stages, OSM superroute 19413306 (stage relations 19413301 … 19415325), ~323 km | OSM route relations (tags `ref` PT01–PT22, `distance`); compare with the official GPX files |
| Sections | ~2 km each (~160 nodes) | Graph size kept close to the other parks' order of magnitude; phone pack size |
| Walkers on the whole trail | 120 on an ordinary weekday in season | **(A)** No data. Calibrate with the trail organisation's registrations or guesthouse occupancy |
| Weekday / holiday / Poya | weekend ×1.5–1.6, holiday ×1.5, Poya ×1.3 | **(A)** Domestic visitors come at weekends and on holidays |
| Season (month factors) | Dec–Apr ×1.3–1.5; May–Jun ×0.6–0.7 | **(A)** Foreign tourist season and the south-west monsoon |
| Share of walkers per stage | Ella / Haputale stages 13–16: 7–12 %; Horton Plains stages 10–11: 5–6 %; others 3 % | **(A)** Day visitors add to the long-distance walkers near Ella, Lipton's Seat and Horton Plains |
| Start times | 80 % around 07:00 (sd 45 min); the rest 08:30–10:30; none after 11:00 | **(A)** Stages take 4–8 h; afternoon rain |
| Group size | 1 + Poisson(1.5) | **(A)** Pairs and small groups |
| Stops | Lipton's Seat 30 min, Little Adam's Peak 25, Nine Arch Bridge 20, Ella Rock 25 | **(A)** |
| Capacity at once | groups of 6, 100 m apart, 2 m per person; hotspots at least 40 people | **(A)** Estate roads are wider than forest paths |
| Bursts (realistic world S1) | a tour group or school trip of 15–45 on one stage, 07:00–09:30 | **(A)** |
| Weather | one point (Nuwara Eliya) for now; per-stage weather planned | Stages span ~600–2,100 m and two monsoon sides |

**Not modelled yet:** multi-day walkers carried from stage k to k+1 the next day (P2), and day visitors at hotspots who
do not walk a stage (e.g. Nine Arch Bridge from the road).
