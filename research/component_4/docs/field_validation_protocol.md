# Field validation protocol (objective O2, RQ7)

Fixed on 20 Oct 2026, **before** any visit, so the agreement criteria cannot be tuned to the data afterwards.
Tool: `python -m src.eval.field_validation <sheets.csv>` (from `research/component_4`).

## 1. What is compared

| Quantity | From the field | From the model |
|---|---|---|
| People **present** on a place at a moment (snapshot headcount) | count everyone standing / walking within the place's marked area | the synthetic target (simulated history driven by that day's real weather) and the ST-GNN day-ahead forecast made the evening before, for that segment and hour |

## 2. Agreement criteria (pre-registered)

| # | Criterion | Pass if |
|---|---|---|
| A1 | Typical error relative to a busy moment: MAE ÷ mean observed daily peak | ≤ **0.25** |
| A2 | Ranking: Spearman correlation between counts and predictions | ≥ **0.6** |
| A3 | Timing: hour of the highest count vs. highest prediction, per place and day | within **±1 h** on at least half of the place-days |

Both the **simulated target** (is the training data realistic?) and the **forecast** (is the model useful?) are
reported. If the simulated target fails, recalibrate the simulator (`configs/*.yaml`, parameters marked (A)) with
these counts and re-run RQ1–RQ6; the counts used for calibration are then not reused to claim agreement – hold
back one visit day for the final check.

## 3. Horton Plains (2–3 visits, Dec 2026)

- **Days:** one weekday + one weekend / holiday day (+ one Poya day if possible), same counting plan.
- **Places (POI keys):** `entrance`, `mini_worlds_end`, `worlds_end`, `bakers_falls`; Kirigalpotta / Thotupola
  if a second counter is available.
- **When:** every 30 minutes from 06:00 to 13:00 at each place (one counter walks the loop and back, or one
  counter per viewpoint).
- **How:** count people inside the viewpoint railing / a 20 m stretch of path centred on the sign; write the
  time when the count starts.

## 4. Adam's Peak (Unduvap Poya night, 23 Dec 2026)

- **Final-steps flow (most important, assumption B1):** at the top of the last flight, count people stepping
  onto the summit terrace for 1 minute, every 15 minutes from 02:00 to 07:00 → people per minute.
- **Halfway counts:** at the Nallathanniya halfway rest halt, people passing in 10 minutes, every 30 minutes
  (same as the ranger screen) – also entered in the app as a test of the halfway-check flow.
- **Summit headcount:** `summit` snapshot every 30 minutes.
- **Climb times:** ask 10–20 groups at the top "what time did you start, and from where?" (no names).

## 5. Counting sheet (CSV)

```
date,time,place,count,counter,notes
2026-12-12,06:30,entrance,42,JV,mist
2026-12-12,07:00,worlds_end,18,JV,
2026-12-23,03:15,summit,640,JV,queue on the steps
```
`place` = a POI key above, or `seg:<segment number>`. One file per day and counter, saved in
`data/field/<park>/` (not committed: the raw sheets stay with the researcher).

## 6. Ethics and safety

- Counts only: no names, photos of faces or personal data (NFR5). Climb-time questions are anonymous and voluntary.
- Permission from the park warden (Horton Plains) and the Sri Pada trust / police (Adam's Peak) before counting.
- Two people on the Adam's Peak night; warm clothing; stop if the steps get dangerously crowded.
