# Component 4 – Move into the team's folder structure

Written 18 Oct 2026. **Status 18 Oct, late: done on `feature/component-4-restructure`, not committed yet.**

| Check | Result |
|---|---|
| 1 Python tests | 56 passed, 4 skipped (same as before) |
| 2 Data unchanged | both `dataset.npz`, `bookings.sqlite`, `auth.sqlite`: identical SHA-256 |
| 3 Pipeline | `run_benchmark --quick` runs (found and fixed: a quick run overwrote `results/LATEST`) |
| 4 Live refresh | both parks; outlooks identical to before except the `generated_at` time |
| 5 API + gateway | 15 API responses byte-identical; real `serve_all` + gateway answer 200 |
| 6 Dashboard | in the test suite (passes) |
| 7 Slides rebuild | after `PP1_Component4.pptx` is closed in PowerPoint and moved |
| 8–9 Flutter | analyzer clean; 17 tests pass (16 Component 4 + `widget_test.dart`) |
| 10 Screens | 8 of 9 screenshots pixel-identical; the officer "Tonight" screen differs only in today's date |
| 11 App by hand | for you (RUN_APP.md) |
| 12 His files | identical to `origin/ai-hiking-assistant` |

Deviation from §4: the language setting stayed in `presentation/l10n/c4_i18n.dart` (it is UI text + the chosen
language; splitting it would make `services/` depend on `presentation/`).

## 1. Why, and what was decided

A team member asked why Component 4 lives in its own folders (`ml/component_4/`) instead of the project structure
he set up. His branch `ai-hiking-assistant` (fetched 18 Oct, last commit `54e7ef3`) uses:

| Part | His structure | Component 4 today | Decision |
|---|---|---|---|
| Python research | `research/` – shared `dataset/`, `notebooks/`, `models/`, `results/`, `requirements.txt` | `ml/component_4/` | Move as **one folder** to `research/component_4/` (your choice, 18 Oct) |
| Flutter feature | `lib/features/<feature>/` with layers `data / domain / models / presentation / services` | `lib/features/component_4/` with `data / screens / ui` | **Same folder, re-layered** to his layers (your choice, 18 Oct) |
| App shell | `lib/app/`, `lib/core/`, `lib/shared/` | uses `lib/app/app.dart` + `router.dart` | No change |

Rules for the move:
- **Nothing changes in behaviour.** Files move, imports and paths change. No model, number or screen changes.
- **His work is brought in, not rewritten.** His branch is merged into the new branch; his files are not touched.
- **New branch**, and the old branches stay as they are (they are the fallback until PP1).

## 2. Branches

```
origin/main  (has all Component 4 work, PR #7)
   └── feature/component-4-restructure   ← new branch
          ← merge origin/ai-hiking-assistant  (his research/, notebooks, RAG, .gitignore)
          ← move ml/component_4 → research/component_4
          ← re-layer lib/features/component_4
```

**Step 0 – before anything (you):** the latest work is still uncommitted on `feature/component-4-multi-park`
(slides, screenshot test, wait-chart fix, gateway home page). Commit it there first, so the new branch starts
from a clean, complete state:
```powershell
git add lib/features/component_4 ml/component_4/src/api/gateway.py ml/component_4/RUN_APP.md
git commit -m "Component 4: fix wait charts, gateway home page"
git add ml/component_4/src/report/slides.py ml/component_4/docs/slides test/component_4/screenshots_test.dart
git commit -m "Component 4: PP1 slides and app screenshots"
git push origin feature/component-4-multi-park
```
(and merge it into `main` with a pull request, like PR #7). Then I create the new branch from `main`.

`linux/` and `windows/flutter/generated_plugins.cmake` changed only because Flutter regenerated them; they can
be committed with the app or discarded (`git checkout -- linux windows`).

## 3. Python: `ml/component_4/` → `research/component_4/`

```
research/
  component_4/            ← everything that was ml/component_4 (src, configs, tests, dashboard, docs, README, RUN_APP)
    data/                 ← not in git (as before): OSM, DEM, weather, datasets, bookings/auth databases
    results/              ← run folders (as before)
    .venv/                ← Component 4's own Python 3.14 environment
    requirements.txt
  dataset/ notebooks/ models/ rag/ results/ requirements.txt   ← his, unchanged
```

Steps:
1. `git mv ml/component_4 research/component_4` (moves every tracked file; history follows the files).
2. Move the files git does not track (`data/`, `.venv/`, ignored result files, ~70 MB) with `Move-Item`, so
   datasets, trained models, bookings and staff accounts come along.
3. Paths in code: none to change – `src/config.py` and `dashboard/common.py` find the folder from their own
   location (`Path(__file__).parents[1]`). Only comments/messages mention `ml/component_4` (4 files).
4. `.gitignore`: our 5 rules become `research/component_4/data/*`, `research/component_4/results/**/*.pt`, … and
   are combined with his rules (his `/research/dataset/raw/` etc. are kept). His rules only cover
   `research/results/` and `research/models/` at the top level, so they do not hide our files.
5. Docs: `cd ml\component_4` → `cd research\component_4` in README, RUN_APP, the plan docs; `CLAUDE.md` and
   `.claude/agents/*` ("all work lives in ml/component_4") updated to the new path.
6. Python environment: we keep our own venv (he uses Python 3.9 at the repo root; we need 3.14 + PyTorch). The
   moved `.venv` is tested first (`python -m ...` calls work after a move); if anything fails it is rebuilt with
   `py -3.14 -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt` (~10 min).
7. Saved results that print an old path (3 forecast JSON files) are left as they are – they are records of past runs.

## 4. Flutter: re-layer `lib/features/component_4/`

| Layer (his) | Meaning | Component 4 files |
|---|---|---|
| `models/` | data classes parsed from the API | `models.dart` (unchanged content) |
| `data/` | talks to the server | `api_client.dart` |
| `services/` | device-side services | `ticket_store.dart` (tickets saved offline), language setting (part of `c4_i18n.dart`) |
| `domain/` | business rules without Flutter | nothing yet – all forecasting and decisions run on the server; kept with `.gitkeep` so the layout matches |
| `presentation/` | screens and widgets | `component4_home.dart`; `screens/visitor/*`, `screens/staff/*`, `screens/destinations_screen.dart` (was `park_picker.dart`); `widgets/c4_ui.dart`; `theme/c4_theme.dart`; `l10n/c4_i18n.dart` |

```
lib/features/component_4/
  models/models.dart
  data/api_client.dart
  services/ticket_store.dart, services/language_service.dart
  domain/.gitkeep
  presentation/
    component4_home.dart
    screens/destinations_screen.dart
    screens/visitor/  day, map, my_tickets, outlook, overview, start_times, ticket
    screens/staff/    login, ranger_home, officer_home, halfway, advisory_officer_home
    widgets/c4_ui.dart
    theme/c4_theme.dart
    l10n/c4_i18n.dart
```
Then: update the relative imports in every moved file, `lib/app/router.dart` (one import), and the two test files
(`test/component_4/c4_test.dart`, `screenshots_test.dart`). Class names stay the same, so no screen code changes.
`ParkPicker` was already renamed to `DestinationsScreen`; only the file name follows.

## 5. Checks after the move (all must pass before a pull request)

| # | Check | Command (from `research/component_4` unless noted) | Pass if |
|---|---|---|---|
| 1 | Python tests | `.venv\Scripts\python.exe -m pytest -q` | 56 passed, 4 skipped (same as before) |
| 2 | Data unchanged | compare SHA-256 of `data/processed/dataset.npz` (both parks) before/after | identical |
| 3 | Pipeline end to end | `python -m src.run_benchmark --quick --protocol temporal` | runs, writes `results/…_benchmark_quick` |
| 4 | Live refresh, both parks | `python -m src.live.refresh --today 2026-10-16` (and with `C4_PARK=adams_peak`) | same outlook as before |
| 5 | API + gateway | `python -m src.api.serve_all`; `GET /parks`, `/parks/adams_peak/advisory/2026-12-25`, `/parks/horton_plains/slots/2026-11-24` | 200, same JSON as before |
| 6 | Dashboard | covered by `tests/test_dashboard.py` (every page renders) | passes |
| 7 | Slides rebuild | `python -m src.report.slides` | deck builds |
| 8 | Flutter analyzer (repo root) | `flutter analyze` | no issues |
| 9 | Flutter tests (repo root) | `flutter test` | 16 Component 4 tests + his `widget_test.dart` pass |
| 10 | Screens pixel-identical | screenshot test **without** `--update-goldens` against the 9 saved screenshots | all 9 match → no screen changed |
| 11 | App by hand | `flutter run -d chrome --dart-define=C4_API=http://localhost:8000`: destinations, booking, start times, halfway HOLD, officer season | works as in RUN_APP.md |
| 12 | His work intact | his files (`research/dataset`, `research/rag`, notebooks) unchanged vs `origin/ai-hiking-assistant` | `git diff origin/ai-hiking-assistant -- research/dataset research/rag research/notebooks` is empty |

## 6. Risks

| Risk | Mitigation |
|---|---|
| PP1 is in 3–4 days and the demo breaks | Old branch untouched and runnable; new branch merged only after checks 1–12 pass |
| Merge conflict with his branch | Only `.gitignore` is changed on both sides → combine both sets of rules |
| Moved `.venv` does not start | Rebuild from `requirements.txt` (step 3.6) |
| Hidden absolute path | `git grep ml/component_4` after the move must only list old result files |
| He changes the structure again | Agree the layout with him on this plan before merging (send him section 3–4) |

## 7. Afterwards

- Pull request `feature/component-4-restructure` → `main`; ask him to review section 3–4.
- Later (not in this move): share the Horton Plains / Adam's Peak inputs with his `research/dataset/` release
  (same OSM PBF and Copernicus tiles) instead of downloading them twice – this changes inputs, so it needs a
  re-run of the results and is left until after PP1.
