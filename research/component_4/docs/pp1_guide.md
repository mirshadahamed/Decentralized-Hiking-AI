# PP1 guide – Component 4 explained from the ground up

For Weerasekera J.V (IT23343948), to read before Progress Presentation 1.
Deck: `docs/slides/PP1_Component4.pptx` (22 main slides + backups; speaker notes on every slide; rebuild with
`.venv\Scripts\python.exe -m src.report.slides`). Questions: `docs/qa_pp1.md`.

---

## Part 1 – The story in five sentences
1. Sri Lankan parks control crowds with **one fixed daily number** (Horton Plains) or **nothing** (Adam's Peak), and
   nobody knows **where on the trail** or **when** the crowd will be.
2. I turned the trails into a **graph** (each ~300 m section is a node) and built an **ST-GNN** that forecasts how
   many people will be on every section, every hour, tomorrow – from open data only.
3. Because no section-level counts exist anywhere, the model learns from a **calibrated simulation** of hiker
   groups; December field counts will check it.
4. The forecast goes into the **Cifuentes carrying-capacity method**, so it becomes a **safe number per trail**
   that changes with weather and expected crowding, and drives **entry tickets, gate advice and hiker advice**.
5. I test every claim against simpler models with paired statistics, and I report the parts that did **not** work
   (small graph gain, pretraining mostly unhelpful) as findings, with a plan.

If you remember nothing else, remember those five.

---

## Part 2 – The problem (mark sheet: problem definition)

**Today (the "current implementation" the mark sheet asks about):**
- Horton Plains: DWC sets a daily permit cap. Same number on a rainy Tuesday and a dry Poya Sunday.
- Adam's Peak: no limit at all; on Poya nights thousands queue for hours on the steep final steps.
- DWC / SLTDA publish only **park totals**. No counts per trail section exist. No sensors on the trails.

**Why that matters:** damage and danger happen at **bottlenecks** (World's End viewpoint at 08–10, the summit steps
before sunrise), not in the park total. A total cannot see them.

**Show it in the product:** slide 16, first screen. For Sunday 1 Nov the officer sees the World's End loop
quota three ways: **with the crowd forecast 261**, weather only 347, same all year 287 – and *why*: "Baker's Falls is
expected over capacity 08–11 h". That one screen is the problem and the solution side by side.

---

## Part 3 – Concepts you must be able to explain

### 3.1 Graph
A graph = **nodes** + **edges**. Here a node is a trail section (~300 m at Horton, ~500 m at Adam's Peak), an edge
joins two sections you can walk between. Horton Plains: 48 nodes, 102 directed edges (3 trails). Adam's Peak: 57
nodes, 4 routes meeting at the summit. A road link between two trailheads is a weaker edge (weight 0.5).

Each node has **13 descriptions** (length, slope, wetness TWI, elevation, walking time both ways, viewpoint?,
access point?, dwell minutes, minutes from trailhead, passes per visit, visitor share). Sections are *described,
not named*, so the same model shape works at any park.

Each hour has **17 covariates**: hour / weekday / month (as sine–cosine so 23:00 is close to 00:00), open?, weekend,
holiday, **Poya**, long weekend, school holiday, rain, temperature, humidity, cloud, wind.

### 3.2 GCN (graph convolution) – "listen to your neighbours"
For each section, a GCN layer takes a weighted average of its own state and its neighbours' states, then applies a
learned linear map:  **H' = D̃^(−½) (A + I) D̃^(−½) · H · W**.
- A = adjacency (who is next to whom), I = "include yourself", D̃ = degree normalisation (so busy junctions do not
  dominate), W = learned weights.
- Intuition: if the section before World's End is filling up, World's End will fill next. Congestion **spreads
  along the trail**; a GCN lets the model use that.
- I use the **dense** form (`DenseGCNConv`): with ≤ 57 nodes a full matrix multiply is faster and exact.

### 3.3 GRU – "remember the last 24 hours"
A GRU is a recurrent network: it reads the 24 past hours one by one and keeps a memory vector, with gates that
decide what to keep and what to forget. It is a lighter LSTM (2 gates instead of 3); on my data it was as good or
better (the LSTM-cell ST-GNN was significantly worse, so I dropped it).

### 3.4 The ST-GNN, step by step (slide 6)
1. Input: last 24 h of counts (where they exist), a "sensed" flag, covariates, section descriptions.
2. **GCN ×2** mixes neighbouring sections every hour. Key trick: in the first layer, sections **without counts only
   receive** messages (their column of A is zeroed), so a missing count (fed as 0) is not read as "empty".
3. **GRU** runs over the 24 hours for each section.
4. **GCN** spreads the final memory to neighbours again.
5. **Decoder**: combines that memory with **tomorrow's** weather forecast and calendar, and outputs people per
   section for each of the next 24 hours.
- Size: hidden 32, **13,665 parameters** (~100 KB). Loss: masked L1 (= MAE) over open hours 06–18. Adam optimiser,
  lr 0.002, up to 20 epochs, early stopping on 2024.
- **Why this architecture and not DCRNN / STGCN / ASTGCN?** Those were built for 200–300-sensor road networks with
  years of 5-minute data. With 48 nodes, a few thousand windows and no real counts, a bigger model overfits. GCN +
  GRU is the smallest model that still has both parts (space and time), so I can remove the graph and see what it
  adds. It also exports to ONNX and to a short Dart loop for the phone.

### 3.5 Baselines (why each is there)
| Baseline | What it is | Why |
|---|---|---|
| Historical average (HA) | mean for that day type (weekday / weekend or holiday / Poya or long weekend) × hour × section, from training years | what a static rule "knows"; the floor to beat |
| SARIMA(1,0,1)(1,1,1)₂₄ | classic time-series model, one per section | the proposal's ARIMA baseline |
| LSTM | the same network with **no graph** and an LSTM cell | the strongest non-graph deep model |
| GRU-no-graph | the **identical** ST-GNN with every GCN replaced by a per-node linear layer | the clean ablation: only the graph is removed |

### 3.6 The training target: the simulator (slide 5, "Simulator" box)
No section counts exist in Sri Lanka, so I **simulate** them:
daily demand (weekday × holiday × Poya × month × morning rain × noise) → groups of 1 + Poisson(2.2) people →
arrival time at the gate (85 % early, mean 06:54) → trail choice (86 % World's End loop) → walk section by section at
Tobler's hiking speed × 0.75 (tourists) × rain slowdown × crowd slowdown → dwell at viewpoints (World's End 20 min).
Occupancy = average people on a section in an hour. Each day is simulated twice so crowding can slow walkers.
Every number is in `configs/default.yaml` and justified in `docs/assumptions.md`.

**Be ready for:** "your model just learns your simulator." Answer: yes, that is the main threat, so (1) every
assumption is listed and changeable, (2) the S1 realistic world adds what the calendar cannot predict (tour-bus
bursts, busy spells, shifted peaks, incidents, *forecast* not observed weather), (3) field counts in December are
compared with pre-registered criteria (A1–A3) fixed on 20 Oct, before any counting, and one day is held back.

### 3.7 Tobler's hiking function and TWI
- Tobler: speed = 6·e^(−3.5·|slope + 0.05|) km/h. Fastest (6 km/h) on a gentle 5 % downhill, slower uphill and steep
  downhill.
- TWI (topographic wetness index) = ln(upslope area / tan(slope)). High TWI = water collects = muddy, erodible.
  Used in the erodibility and wet-ground factors.

### 3.8 Cifuentes carrying capacity (slide 5, "Capacity & control" box; `src/capacity/cifuentes.py`)
Three steps per section, visits per day:
1. **PCC** (physical) = (section length ÷ 1 m per person) × (open minutes ÷ minutes a visit takes there).
2. **RCC** (real) = PCC × (1 − FCsoc)(1 − FCero)(1 − FCacc)(1 − FCpre)(1 − FCwet)(1 − FCcond) × **(1 − FCcrowd)**.
   - FCsoc: groups of 10 need 50 m gaps → most of the trail must stay empty.
   - FCero: wet-prone ground (TWI). FCacc: steep grades. FCpre: share of open hours with rain **forecast**.
   - FCwet: ground still wet from the last 3 days. FCcond: officer-reported condition (muddy, partly closed).
   - **FCcrowd (my addition): share of open hours where the ST-GNN forecasts more people than the section holds
     at once.** This is how the forecast enters the method (objective O5).
3. **ECC** (effective) = RCC × management capacity (0.7 = staff / infrastructure available).
- Trail quota = the **smallest** ECC on that trail (the limiting section). Park quota = sum of trails.
- **Why Cifuentes:** peer-reviewed, used in protected areas for 30 years; I did not invent a capacity formula.

### 3.9 Control (slides 11, 12, 16)
- **Slot tickets (Horton):** a ticket fixes trail + 30-min entry slot, so the simulator says where its holder will be
  each half hour. A **linear programme** (SciPy HiGHS) maximises tickets while every section stays under 90 % of
  capacity every half hour, inside the daily quota, keeping 20 % for walk-ins. Full slot → later slot, other
  trail, other day.
- **Gate advice:** from people already through the gate + coming slots, walk everyone forward; if a section goes
  over in the next 2 h → "hold entries to X for N min" or "send the next groups to Y".
- **Adam's Peak (no tickets):** recommended start times per route (wait ≤ 20 min, summit before sunrise, *spread* so
  the advice does not create a new peak) + halfway checkpoints where officers hold groups when the summit queue is
  too long.
- **Walk advice on the phone:** each phone draws one good option weighted by room left (spread, not herd).

### 3.10 Evaluation (slide 7)
- **Splits:** train 2022–23, validate 2024, test 2025. Scalers fitted on training years only → **no leakage**.
- **Temporal protocol:** every section counted; forecast at midnight for the next day.
- **Spatial block CV:** cut the graph into 4 contiguous blocks; hold one out (no counts, no training loss there),
  forecast it. Contiguous so neighbours of a test section are not in training (that would leak).
- **Sparse sensors (RQ10):** the model sees only the gate counts (or nothing) – the real deployment case.
- **Metrics:** MAE (people per section-hour; interpretable), RMSE (punishes big misses), **F1 of over-capacity
  section-hours** (did it flag the bottleneck?).
- **Statistics:** paired t-test and Wilcoxon over **days** (hours inside a day are correlated, so testing hours would
  fake significance), **Holm correction** for several comparisons, 3 seeds (42, 43, 44).
- **Decision-focused:** policies are replayed on the 2025 visitors and judged by over-capacity person-hours.

### 3.11 Transfer learning and domain adaptation (slide 13)
- **Pretraining:** train the same GCN + GRU core on city traffic (METR-LA 207 sensors, then PEMS-BAY 325), target =
  congestion.
- **Fine-tuning:** start from those weights, train everything on the trail.
- **Frozen core:** keep the traffic GCN + GRU fixed, train only the input and output layers (a simple domain
  adaptation).
- **Zero-shot:** use the traffic weights unchanged.
- Measured with 30, 90, 365 days and all data from the park.

### 3.12 Edge (slide 14)
Each evening the server publishes `edge_pack.json` (~175 KB: weights + scaled inputs). The phone runs the same maths
in plain Dart (no native library), matching PyTorch to 0.0001 people, in ~150 ms. ONNX on one laptop core: 2 ms.
int8 quantisation was tested and **rejected**: it saves 2 KB but raises error 25 % at Adam's Peak.

---

## Part 4 – Results, and how to say each one

| RQ | Question | What to say (one breath) | Numbers |
|---|---|---|---|
| RQ1 | Does the graph help? | "On sections without counts it lowers error, significantly but by about 2 %. With counts everywhere it ties. At Adam's Peak it is worse at the summit queue, because a queue depends on the steps' capacity, not on neighbours." | Horton unseen: ST-GNN 2.54, LSTM 2.59, GRU 2.61, HA 4.20, p < 10⁻¹² |
| RQ1b | Does it catch bottlenecks? | "Scored as events, every model ties with counts; on unseen sections the ST-GNN smooths peaks and flags slightly fewer. So the app shows a calibrated **chance** of crowding, and a peak-aware loss is next." | F1 0.80 / 0.85 with counts; 0.29 vs 0.32 unseen (Horton) |
| RQ10 | Does it work with no sensors? | "Yes: from gate counts only, interior error is almost as low as with a counter on every section. But in my default simulator nothing unpredictable happens, so the graph has nothing to add; I built a realistic world to test that properly – running now." | 1.45 gate-only vs 1.42 all counted; HA 1.63 |
| RQ9 | Does the forecast beat a static quota? | "At the same number of visitors, a forecast-driven quota cuts over-capacity time by 27 % at Horton and 24 % at Adam's Peak. Significant at Adam's Peak; at Horton a historical-average forecast does as well. No daily number fixes timing, so the forecast also drives tickets and gate advice." | −27 % / −24 %; 93 % / 76 % of a perfect forecast's gain |
| Control | Does it prevent overcrowding? | "Slot tickets remove 99.6 % of over-capacity time; the daily quota alone 73 %. At Adam's Peak, start times cut waiting 42 %, and halfway holds clear the final steps." | |
| RQ3 | Better forecast = better control? | "Only with the right rule: advice from the median forecast gets ~16 % of the possible benefit; from the busy case (P90), all of it – waiting −56 %." | backup slide |
| RQ5 | Does traffic pretraining help? | "Only at Horton with 30–90 days of counts (−5 / −12 %). Not at Adam's Peak. Zero-shot fails. Freezing the core helps only at 365 days. With ≤ 90 days a historical average still wins – so a new park starts on the average." | |
| RQ6 | Runs on a phone in < 2 s? | "Yes: 2 ms ONNX, ~150 ms in Dart, fully offline. Real Android timing is next." | |
| RQ7 | Field validation | "Criteria fixed before counting: A1 MAE ÷ daily peak ≤ 0.25, A2 Spearman ≥ 0.6, A3 peak hour ±1 h on half the place-days. Counts in December." | |
| RQ8 | Offline hiker advice | "Works if spread: up to −73 % with nobody turned away; identical advice on every phone backfires (+12 % worse)." | backup slide |

**The honest framing (use it, it earns marks on risk and completion):**
"Every block of the proposal is built and tested. The evidence is strong for C4 and C5 and partial for C1–C3;
I state that openly and the next phase tests each claim in the gap's own setting, then field counts validate it."

---

## Part 5 – Mark sheet → where you score

| Row (weight of total) | Slide(s) | What to make sure they hear |
|---|---|---|
| Problem definition (3 %) | 2, 16 | fixed number today; no section data; the quota screen showing 261 vs 287 vs 347 |
| Proof of concept (7 %) | 8–12, 15, 16 | forecast → capacity → tickets / advice, numbers from replays, live app |
| Key pillars (7.5 %) | 3, 6, 13 | graph learning, transfer learning, carrying capacity, edge AI, decision-focused evaluation |
| Technologies (17.5 %) | 6, 14, `technical_design.md` | GCN maths, masked first layer, GRU, why not DCRNN/ASTGCN, ONNX vs Dart, int8 rejected, LP |
| Design (8 %) | 5 | one YAML per park, layered code, versioned JSON contract for Module 3, offline pack |
| Completion (12 %) | 21 | ahead of the Gantt (Component 4 = months 3–8; we are in month 2) |
| Standards (8 %) | 7 | no leakage, spatial CV, paired tests + Holm, seeds, 101 + 34 tests, lint, CI, model card |
| Requirements (8 %) | 18 | FR1–FR5 / NFR1–NFR5 done, FR6–FR13 added, all traced (`requirements.md`); validation with DWC pending |
| Risk (4 %) | 19 | R1 synthetic target and R2 small graph gain, each with an action in progress |
| Communication (15 %) | all | ~15 min; speak to the notes; backup slides for questions |
| Commercialisation (10 %) | 20 | licence per site + booking fee; no sensors to buy; next: letters of interest |

---

## Part 6 – Talk track (main slides, ~15 min)

| # | Slide | Time | Say |
|---|---|---|---|
| 1 | Title | 0:20 | "I forecast where and when trails get crowded, and turn that into crowd control, at two very different sites." |
| 2 | Problem | 1:00 | Fixed number vs no limit; no section data; bottlenecks matter. |
| 3 | Gap, claim by claim | 1:00 | Five claims, what is shown, what is partial. Sets up honesty early. |
| 4 | Objectives | 0:45 | O1–O6 all have code and results; what is open. |
| 5 | System overview | 0:45 | Left to right; one YAML per park. |
| 6 | ST-GNN + technologies | 1:15 | GCN listens to neighbours, GRU remembers 24 h, decoder uses tomorrow's weather; masked first layer. |
| 7 | Evaluation + standards | 0:45 | No leakage, spatial CV, days not hours, Holm, F1 for bottlenecks, tests + CI. |
| 8 | RQ1 | 1:00 | Helps on unseen trail (2 %), ties with counts, smooths peaks. |
| 9 | RQ10 | 0:45 | Gate-only works; graph adds nothing in the simple world → realistic world running. |
| 10 | RQ9 | 1:00 | −27 % / −24 % vs static at equal visitors; timing matters. |
| 11 | Horton control | 0:45 | Slot tickets −99.6 %. |
| 12 | Adam's Peak | 0:45 | Advice and holds, nobody refused. |
| 13 | RQ5 | 0:45 | Pretraining: clear, mostly negative answer. |
| 14 | RQ6 | 0:30 | Runs on the phone offline. |
| 15 | Bottleneck map | 0:45 | The proposal's output on one screen. |
| 16 | Staff tools | 0:45 | Quota panel, gate advice, spot counts, forecast check. |
| 17 | RQ7 | 0:30 | Criteria fixed before counting. |
| 18 | Requirements | 0:30 | All traced; validation pending. |
| 19 | Risks | 0:30 | R1, R2 first. |
| 20 | Commercialisation | 0:30 | Who pays and why. |
| 21–22 | Progress, next steps | 0:45 | Ahead of plan; dated actions. |

**Live demo (if allowed, 2 min, after slide 16):** follow `RUN_APP.md`. Order: airplane mode on → Crowding tab
(bottleneck map, drag the hour) → staff login as officer → Daily quota (switch rule) → ranger Count tab. If anything
fails, go straight back to slide 16 – the screenshots are the backup.

---

## Part 7 – What changed on 21 Oct (so you are not surprised)
- New results: RQ1b (bottleneck F1), RQ9 (quota vs static), RQ10 (gate counts only), frozen-core pretraining.
- New app features: officer Daily-quota panel, gate advice, ranger spot counts (offline), forecast check, chance of
  crowding, basis line on every number.
- Realistic simulated world S1; its runs (S2) are still going – say "in progress", do not quote numbers.
- Clean-up: lint (`ruff`) with fixes, CI lint step, old plans moved to `docs/archive/`, empty app folders removed.
- New docs: `technical_design.md`, `requirements.md` (+ risk register), `model_card.md`, this guide, `qa_pp1.md`.
- Slides: gap slide, RQ9, RQ10, staff-tools slide; RQ1 and RQ5 updated; old slides kept as backups.

## Part 8 – Commands you may be asked to run
```powershell
cd research\component_4
.venv\Scripts\python.exe -m pytest -q                         # 101 tests (5 skip without data)
.venv\Scripts\python.exe -m ruff check src tests dashboard     # lint
.venv\Scripts\python.exe -m src.serve.predict --date 2025-05-12   # one forecast JSON
.venv\Scripts\python.exe -m uvicorn src.api.app:app --port 8000   # API + docs at /docs
.venv\Scripts\python.exe -m streamlit run dashboard/app.py       # research dashboard
cd ..\..; flutter test test/component_4                         # 34 app tests
```
