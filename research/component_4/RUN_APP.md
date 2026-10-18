# How to run the Component 4 app (Horton Plains + Adam's Peak)

Two programs run at the same time:
1. **The park servers** (Python): forecasts, bookings, staff logins; one per park behind one address. Terminal 1.
2. **The Flutter app**: what visitors, pilgrims, rangers and officers use. Terminal 2.

Paths on this laptop:
- Project: `D:\Documents\SLIIT\Research\Decentralized-Hiking-AI`
- Flutter SDK: `C:\Users\Jhonny\dev\flutter` (separate folders is normal)

---

## Every time (3 steps)

### 1. Start the park servers – Terminal 1
```powershell
cd D:\Documents\SLIIT\Research\Decentralized-Hiking-AI\research\component_4
.venv\Scripts\python.exe -m src.live.refresh                                   # Horton Plains
$env:C4_PARK = "adams_peak"; .venv\Scripts\python.exe -m src.live.refresh; Remove-Item Env:C4_PARK   # Adam's Peak
.venv\Scripts\python.exe -m src.api.serve_all
```
- Each `refresh` takes about 1–2 minutes. Run them **once a day**: they fetch the weather and make the forecasts,
  ticket plans (Horton Plains) and start-time advice (Adam's Peak). The app treats the day of the last refresh as "today".
- `serve_all` starts one server per park and a gateway on port 8000; wait until it prints `Uvicorn running`
  (about 30 s). Check in a browser: http://localhost:8000/parks lists both parks.
- Only one park, the old way: `.venv\Scripts\python.exe -m uvicorn src.api.app:app --port 8000` (Horton Plains);
  the app then skips the park picker.

### 2. Start the app – Terminal 2 (click **+** in the terminal panel for a new one)
```powershell
cd D:\Documents\SLIIT\Research\Decentralized-Hiking-AI
flutter run -d chrome --dart-define=C4_API=http://localhost:8000
```
- Chrome opens with the app (first build takes a few minutes).
- Windows window instead of Chrome: replace `-d chrome` with `-d windows`.
- In this terminal: `r` = reload after a code change, `R` = restart, `q` = quit.

### 3. Stop
- Terminal 2: press `q`.
- Terminal 1: press `Ctrl + C`.

---

## Demo walk-through

**Trip planner**: **Plan your visit** → **Where to?** lists every destination with its type, region, trails and
the crowd for the next 7 days (quietest day marked). Filter by type (National park / Pilgrimage). Tap one →
**Overview**: summary, the week ahead, the 3 quietest days in the next 2 weeks, best time, getting there, good to
know, trails → **Plan your visit / Plan your climb**. The ← button returns to all destinations. The 文A button
switches English / සිංහල / தமிழ்.

**Horton Plains visitor**
1. The 90-day calendar (green = quiet … red = very busy).
2. Tap a day (e.g. **24 Nov 2026**, Il Poya) → expected crowd, suggestions for a quieter visit, trails.
3. Pick trail, group size and a time (`07:00 · 20 left`) → **Book** → QR ticket with an 8-letter code.
4. **My tickets** shows it again (works offline). **Map**: the three trails.

**Adam's Peak pilgrim** (no tickets)
1. **Start times** → calendar of the season (e.g. **Wed 23 Dec 2026**, Unduvap Poya: the season opens).
2. Tap a night → pick a route → best start for sunrise, good start times, expected wait near the top per start
   time (green bars = recommended), and when the summit is busiest.
3. **Map**: the four routes, start points, halfway checkpoints and the summit (dashed = approximate last part).

**Adam's Peak halfway officer** (choose Adam's Peak → **Staff** → log in with an Adam's Peak account)
1. **Now** → demo time, e.g. 23 Dec 2026 02:00.
2. Pick **My checkpoint**, enter the people who passed in the last 10 minutes (e.g. **+100** five times = 500)
   → **Record** (the demo time moves on 10 minutes each time).
3. Record 500 two or three times: the final steps take ~250 people per 10 min, so the card turns red: **HOLD**,
   with how many to let through per 10 minutes at each checkpoint.

**Adam's Peak officer** (log in with an Adam's Peak **officer** account)
1. **Tonight**: HOLD / NORMAL for the whole mountain, each halfway checkpoint (counted, last count, let pass or
   release per 10 min, tonight's forecast plan, a warning when a holding checkpoint has not reported), the latest
   counts. Updates every minute (pull down in demo time). **Record a count** opens the halfway screen.
2. **Season**: every night of the next 90 days: *Checks needed* (likely), *Stand by* (only if it is as busy as the
   high case, 1 night in 10 busier) or *Normal*. Try **25 Dec 2026**: Stand by, holds 04:15–07:45 at the summit.
3. Tap a night → **Night plan**: expected wait at the summit through the night (likely and if busier), when each
   checkpoint should hold, release per 10 minutes, and the start times given to pilgrims.
4. ⟳ **Refresh forecasts** reruns the daily refresh.

**Ranger** (top right **Staff** → log in as `ranger1`)
1. Press the **Now** button at the top → set a demo date/time, e.g. 24 Nov 2026 07:00.
   A ticket is valid from 15 min before to 15 min after its slot.
2. **Check in**: type the code (or scan the QR in Chrome) → green tick. A second try says "checked_in".
3. **Walk-ins**: sell places to visitors without a booking.
4. **Live**: traffic lights estimated from who went through the gate.

**Park officer** (log out, log in as `officer1`)
1. **This week**: next 7 days with bookings; **Refresh now** re-runs the daily refresh.
2. **Close trail**: date, trail, time window, reason → affected bookings are listed (never cancelled).
3. **Alerts**: slots with more bookings than is safe after the weather got worse or a closure.

---

## One-time setup (already done on this laptop – only for a new computer)
1. Install Flutter (stable) and add its `bin` folder to the user PATH; restart VS Code.
2. Turn on Windows **Developer Mode**: Win + R → `ms-settings:developers` → On.
3. Project packages: in the project folder run `flutter pub get`.
4. Python environment: `research\component_4\.venv` with `pip install -r requirements.txt`.
5. Staff accounts (password is asked, at least 10 characters):
   ```powershell
   cd research\component_4
   .venv\Scripts\python.exe -m src.api.users add --username ranger1 --role ranger
   .venv\Scripts\python.exe -m src.api.users add --username officer1 --role officer
   .venv\Scripts\python.exe -m src.api.users list
   ```
   Adam's Peak has its **own** accounts:
   ```powershell
   $env:C4_PARK = "adams_peak"
   .venv\Scripts\python.exe -m src.api.users add --username ranger1 --role ranger
   Remove-Item Env:C4_PARK
   ```
6. Adam's Peak data (once, ~10 min): `$env:C4_PARK = "adams_peak"; .venv\Scripts\python.exe -m src.data.build_dataset`

---

## If something goes wrong

| You see | Do this |
|---|---|
| `flutter : The term 'flutter' is not recognized` | Close **all** VS Code windows and open again (a new terminal tab is not enough). Quick fix for one terminal: `$env:Path += ";C:\Users\Jhonny\dev\flutter\bin"` |
| Terminal 1 shows `GET / 404` or `torch.jit.script is not supported` | Harmless: the first is a browser opening the bare address (older version), the second a PyTorch warning on Python 3.14 |
| `.venv\Scripts\python.exe` is not recognized / path `ml\component_4` not found | Component 4 moved to `research\component_4` (18 Oct 2026). Close old terminals and editor tabs, then `cd D:\Documents\SLIIT\Research\Decentralized-Hiking-AI\research\component_4` |
| `Building with plugins requires symlink support` | Turn on Developer Mode (setup step 2) |
| App says **Cannot reach the park server** | Terminal 1 is not running, or stopped. Check http://localhost:8000/health |
| **The adams_peak service is not running** | `serve_all` is still starting (wait 30 s), or that park's server crashed: see Terminal 1 |
| Adam's Peak staff login fails with a Horton account | Accounts are per park: make one with `C4_PARK=adams_peak` (setup step 5) |
| Sinhala / Tamil text shows boxes | The browser is still downloading the font; wait a moment. The translations are drafts for native review |
| **No live data yet** | Run the `refresh` line in step 1 |
| **Bookings open from tomorrow up to 90 days ahead** | Pick a day 1–90 days after the last refresh date |
| Check-in **Too early / Too late** | Set the ranger **demo time** within 15 min of the ticket's slot |
| **Wrong username or password, or account locked** | 5 wrong tries lock the account for 15 min. Forgot the password? Make a new account (setup step 5) |
| `address already in use` / port 8000 busy | Use another port: `--port 8001` in Terminal 1 and `C4_API=http://localhost:8001` in Terminal 2 |
| Chrome shows an old version | Press `R` in Terminal 2, or stop (`q`) and run step 2 again |

## Notes
- Visitor history after 2025 is **simulated** with real weather until DWC ticket data are connected; screens say
  "estimated". Bookings are stored only on this computer (`research/component_4/data/bookings.sqlite`).
- The demo time button only works because `api.allow_time_override: true` in `configs/default.yaml`.
  Set it to `false` for real use.
- Android phone/emulator: needs Android Studio. Emulator: `C4_API=http://10.0.2.2:8000`. Real phone: start the
  server with `--host 0.0.0.0` and use the PC's IP address.
