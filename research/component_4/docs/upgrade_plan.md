# Component 4 – Upgrade plan: from forecasting crowds to preventing them

Written 16 Oct 2026. Builds on `roadmap.md` (what exists) and answers the panel's question:
**"How, and with what logic, does the system prevent overcrowding?"**

**Status (branch `feature/component-4-entry-control`):** layers 3–5 built: slot planner (`src/control/slots.py`),
live nowcast and traffic lights, slot **booking** with alternatives and gate check (`src/control/booking.py`),
policy evaluation (`src/control/evaluate.py`), dashboard pages *Entry control* and *Book a slot*.
Result on 2025 (simulation, run `20261015_155035_entry_control`):

| Policy | Person-hours over capacity | Admitted | Moved slot / trail | Another day |
|---|---|---|---|---|
| A. No limit | 160,656 | 100 % | – | – |
| B. Daily quota | 43,395 (−73 %) | 56 % | – | 44 % |
| C. Slot tickets | 273 (−99.8 %) | 43 % | – | 57 % |
| D. Slot tickets + moving | 616 (−99.6 %) | 64 % | 36 % / 13 % | 36 % |

At a 2× capacity standard: 83 % admitted, 99.4 % of overcrowding prevented. Not yet built: exit scans,
ranger-count corrections, platform-area capacities (need a field visit).

---

## 1. The honest answer today, and the gap

What the component does now:
1. **Predicts** how many people will be on each 300 m segment, per hour (day-ahead ST-GNN, 90-day planning model).
2. **Limits** with a daily quota per trail (Cifuentes PCC → RCC → ECC, with forecast crowding and rain).
3. **Suggests** a quieter day, a later start, or another trail.

What it does **not** do yet: decide *who may enter, when, and on which trail*. A daily quota alone does not prevent
crowding. 1,000 people spread over the day are fine; 1,000 people who all start at 06:30 jam World's End at
08:00, the main bottleneck in every simulation. Suggestions alone do not prevent it either: people can ignore them.

**Overcrowding is prevented only at the point where access is granted: the ticket counter / booking.**
So the upgrade is an **admission controller**: a rule, driven by the forecast and the capacity numbers, that
decides how many tickets to issue for each **trail** and each **entry time slot**.

---

## 2. The overcrowding-prevention logic (the answer for the panel)

Five layers, each acting earlier than the next:

| Layer | When | What it does | Lever |
|---|---|---|---|
| **1. Predict** | 90 days → 1 day before | Forecast demand and occupancy per segment and hour (already built) | information |
| **2. Limit** | Day before | Capacity per segment = how many people it can hold *at the same time* (Cifuentes social spacing × management capacity × weather) | the hard ceiling |
| **3. Spread** (new) | Day before | **Timed-entry slot quotas**: split the daily quota into 30-min entry slots per trail, so that the predicted occupancy of *every* segment stays under its ceiling in *every* hour | tickets per slot |
| **4. Steer** | Booking / at the gate | When a slot or trail is full: offer the next free slot, another trail with room, or another day (suggestions, already built) | choices |
| **5. Check** (new) | During the day | Live **nowcast** from the tickets already scanned: who entered, when, which trail → expected position now. Traffic-light status per segment; rangers act on red | correction |

In one sentence for the viva:
> *"We do not count people on the trail. We control how many enter and when. Every ticket has an entry time and a
> trail, so we know where those people will be over the next hours. The system only issues a ticket if that keeps
> every segment, especially World's End, under its safe capacity in every hour. If not, it offers a later slot,
> another trail or another day."*

### 2.1 Layer 3 in detail: slot quotas as a linear programme

A group that enters trail *r* in slot *k* adds a predictable amount of occupancy to segment *s* in hour *h*
(the walking-time profile). Call that the **response** `K[r, k, s, h]` (people on *s* in *h* per person admitted).
It is measured with the simulator we already have: send a small test cohort into each slot of each trail and
record where it is every hour.

Decision: `x[r, k]` = tickets for trail *r*, slot *k*.

```
maximise    Σ x[r,k]                                   (admit as many people as possible)
subject to  Σ_r Σ_k K[r,k,s,h] · x[r,k]  ≤  C[s,h]      for every segment s and hour h   (never over capacity)
            Σ_k x[r,k]  ≤  quota_r                      (Cifuentes daily quota per trail)
            x[r,k] ≤ demand[r,k] + shifted demand        (do not issue tickets nobody wants)
            x ≥ 0
```

- `C[s,h]` = the segment's capacity at one time (social spacing × management capacity × rain factor for that
  hour); viewpoints use their platform area once measured.
- Solved with `scipy.optimize.linprog` in well under a second (≈ 3 trails × 14 slots = 42 variables).
- The answer is a table the ticket counter can use directly: *"World's End loop, 06:30–07:00: 85 tickets"*.
- Demand that does not fit in its preferred slot is offered the nearest slot with room, then the other trails,
  then another day. That is the existing suggestions logic, now with real numbers behind it.

Why linear works: occupancy is (almost) the sum of the people who entered. The crowd slowdown makes it slightly
non-linear on busy days. So every plan is **re-checked in the full simulator** (closed loop), and `C` is
reduced by a safety margin if the simulator still shows an overflow.

### 2.2 Layer 5 in detail: live nowcast without sensors

- Inputs available at the gate: ticket scan time, trail, group size (and exit scan, if added).
- Nowcast of segment *s* now = Σ over groups still out of `K[r, k, s, now]` × size (same response as above).
- If exit scans exist, the nowcast is corrected: groups that left are removed; slow groups (no exit yet) stay.
  This also gives real walking times to recalibrate the simulator.
- Optional corrections: ranger headcounts at World's End (a phone form), Module 1 positions synced when online.
- **Traffic light per segment** (shown to rangers and on the dashboard):
  green < 80 % of capacity · amber 80–100 % (offer alternatives at the gate) · red > 100 %
  (pause entries to that trail for the next slot; send a ranger to manage the viewing platform).
- Works offline at the gate: the response table is computed the evening before; only arithmetic on the day.

### 2.3 How we prove it works (research evidence)

Re-run the 2025 test year in the simulator under four policies and compare:

| Policy | Description |
|---|---|
| A. Status quo | no limit (or one fixed park number) |
| B. Daily quota | Cifuentes quota per trail, no time slots |
| C. Slot quotas | layer 3 (LP), no diversion |
| D. Full control | slot quotas + diversion (suggestions accepted by 10 / 20 / 30 % of visitors) + live nowcast |

Metrics per policy: **person-hours over capacity** at each segment (main target), peak at World's End, number of
days with any red hour, visitors admitted (the cost), visitors shifted to another slot / trail / day.
Expected story: B barely helps (the morning peak remains); C removes most of the overflow with only a few
visitors moved to later slots; D lets almost everyone in. This is a clean, quantitative answer to
"does it prevent overcrowding?" and a strong thesis chapter.

---

## 3. Other upgrades, by value

### A. Close the gaps against the proposal (must do)
| # | Upgrade | Proposal ref | Effort |
|---|---|---|---|
| A1 | **Pretraining on METR-LA / PEMS-BAY + fine-tuning** (scratch vs pretrained, esp. in spatial CV) | Obj 3, gap statement | 3–4 days + Colab GPU |
| A2 | **Field counts**: 3–4 visits incl. a Poya weekend; calibrate the simulator; report agreement (MAD) | Obj 2, §3.5 | visits Dec–Jan |
| A3 | **On-device model**: ONNX / int8, latency < 2 s on a phone or Raspberry Pi; offline cache | Obj 6, NFR1 | 2 days |
| A4 | DWC daily ticket totals → retrain the planning model on real numbers | §3.2 | depends on DWC |

### B. Make the forecasts more trustworthy
| # | Upgrade | Why |
|---|---|---|
| B1 | **Uncertainty for the ST-GNN** (quantile outputs or conformal bands, like the planning model) | Capacity decisions should use a cautious value (e.g. P80), not the average |
| B2 | **Real weather forecasts**: Open-Meteo forecast API (16 days) and its archived forecasts for honest backtests | Today the model sees the *actual* weather, which is an upper bound |
| B3 | **Sensitivity analysis** of simulator and Cifuentes parameters (tornado chart: which assumption moves the quota most?) | Examiners attack assumptions; this shows which ones matter |
| B4 | Simulator calibration by search (fit parameters to field counts and DWC totals instead of setting them by hand) | Defensible synthetic target |

### C. Connect with the other modules (integration marks)
| # | Upgrade | With |
|---|---|---|
| C1 | **Damage-aware capacity**: Module 2's trail-damage score per segment feeds the erodibility factor, so a damaged segment's capacity drops automatically | Module 2 |
| C2 | **JSON v2** with slot quotas, traffic lights and options; Module 3 turns them into advice for each hiker | Module 3 |
| C3 | Optional: Module 1 synced positions correct the nowcast | Module 1 |
| C4 | Safety coupling: heavy rain / fog warnings lower capacity on exposed segments (World's End escarpment) | Module 3 |

### D. Show it generalises (research value)
| # | Upgrade | Why |
|---|---|---|
| D1 | **Second park** (e.g. Knuckles or a Sri Pada route) built with the same pipeline from OSM | NFR3; tests the "small sparse graph" claim on a different network |
| D2 | **Transfer without retraining**: apply the Horton Plains model to the second park (the segment features were made transferable on 15 Oct) | Directly answers the research gap |

### E. Usability for officials (NFR4)
| # | Upgrade |
|---|---|
| E1 | A **ranger / ticket-counter view**: today's slot table, live traffic lights, "next free slot" lookup; works offline, large buttons |
| E2 | "Why this quota?" panel: factor-by-factor breakdown in plain words |
| E3 | Sinhala / Tamil labels for the ranger view |

---

## 4. Order of work

### Before PP1 (~5 days): answer the panel's question with something that runs
| Day | Work |
|---|---|
| 1 | Response table `K` from the simulator; LP slot planner (`src/control/slots.py`); unit tests (never over capacity, never more tickets than demand) |
| 2 | Policy comparison A–D on the 2025 test year (`src/control/evaluate.py`); one results table + one chart |
| 3 | Dashboard page **"Entry control"**: slot table for a chosen day, before/after occupancy at World's End, traffic lights from a simulated morning of ticket scans |
| 4–5 | Supervisor meeting (scope, capacity parameters), slides, rehearsal |

### After PP1
| Window | Work |
|---|---|
| Dec–Jan | A2 field counts (+ viewpoint platform areas for `C`), A4 DWC data, B4 calibration, C1 with Module 2 |
| Jan | A1 pretraining / fine-tuning; B1 uncertainty; B2 real weather forecasts |
| Feb | A3 on-device; E1 ranger view; live nowcast with exit scans (layer 5) |
| Mar | D1/D2 second park; B3 sensitivity analysis; final policy evaluation with calibrated simulator |
| Mar–Apr | Thesis chapters; integration testing with the team (C2–C4) |

---

## 5. Risks and limits to state openly

| Risk | Answer |
|---|---|
| Visitors arrive outside their slot | Gate enforces the slot window (±15 min); live nowcast uses actual scan times, not booked times |
| Capacity numbers are placeholders | The logic does not depend on them; they are inputs to confirm with DWC; sensitivity analysis shows the effect |
| Linear model ignores crowd slowdown | Every plan is checked in the full simulator; safety margin on `C` |
| Turning people away hurts revenue / access | Policy D shows how many are only *moved* (slot / trail / day) rather than refused; DWC chooses the margin |
| Pushing people to Kirigalpotta / Thotupola harms sensitive habitat | Those trails have their own capacity in the same LP; they cannot be overfilled either |
| Booking system does not exist yet | v1 works at the counter (paper or tablet) using the slot table; online booking is a later B2G product |
| Still synthetic | All results are "in simulation" until field counts and DWC data arrive; said on every screen (FR5) |
