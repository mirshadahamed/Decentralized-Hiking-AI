# How to run the Component 4 app (Horton Plains visit planner)

Two programs run at the same time:
1. **The park server** (Python): forecasts, bookings, staff logins. Terminal 1.
2. **The Flutter app**: what visitors, rangers and officers use. Terminal 2.

Paths on this laptop:
- Project: `D:\Documents\SLIIT\Research\Decentralized-Hiking-AI`
- Flutter SDK: `C:\Users\Jhonny\dev\flutter` (separate folders is normal)

---

## Every time (3 steps)

### 1. Start the park server – Terminal 1
```powershell
cd D:\Documents\SLIIT\Research\Decentralized-Hiking-AI\ml\component_4
.venv\Scripts\python.exe -m src.live.refresh
.venv\Scripts\python.exe -m uvicorn src.api.app:app --port 8000
```
- `refresh` takes about 1 minute. Run it **once a day**: it fetches the weather and makes the forecasts and
  ticket plans. The app treats the day of the last refresh as "today".
- Leave this terminal open. Check in a browser: http://localhost:8000/health shows `{"ok":true}`.
  All API calls are listed at http://localhost:8000/docs.

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

**Visitor**
1. **Plan your visit** → the 90-day calendar (green = quiet … red = very busy).
2. Tap a day (e.g. **24 Nov 2026**, Il Poya) → expected crowd, suggestions for a quieter visit, trails.
3. Pick trail, group size and a time (`07:00 · 20 left`) → **Book** → QR ticket with an 8-letter code.
4. **My tickets** shows it again (works offline).

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
4. Python environment: `ml\component_4\.venv` with `pip install -r requirements.txt`.
5. Staff accounts (password is asked, at least 10 characters):
   ```powershell
   cd ml\component_4
   .venv\Scripts\python.exe -m src.api.users add --username ranger1 --role ranger
   .venv\Scripts\python.exe -m src.api.users add --username officer1 --role officer
   .venv\Scripts\python.exe -m src.api.users list
   ```

---

## If something goes wrong

| You see | Do this |
|---|---|
| `flutter : The term 'flutter' is not recognized` | Close **all** VS Code windows and open again. Quick fix for one terminal: `$env:Path += ";C:\Users\Jhonny\dev\flutter\bin"` |
| `Building with plugins requires symlink support` | Turn on Developer Mode (setup step 2) |
| App says **Cannot reach the park server** | Terminal 1 is not running, or stopped. Check http://localhost:8000/health |
| **No live data yet** | Run the `refresh` line in step 1 |
| **Bookings open from tomorrow up to 90 days ahead** | Pick a day 1–90 days after the last refresh date |
| Check-in **Too early / Too late** | Set the ranger **demo time** within 15 min of the ticket's slot |
| **Wrong username or password, or account locked** | 5 wrong tries lock the account for 15 min. Forgot the password? Make a new account (setup step 5) |
| `address already in use` / port 8000 busy | Use another port: `--port 8001` in Terminal 1 and `C4_API=http://localhost:8001` in Terminal 2 |
| Chrome shows an old version | Press `R` in Terminal 2, or stop (`q`) and run step 2 again |

## Notes
- Visitor history after 2025 is **simulated** with real weather until DWC ticket data are connected; screens say
  "estimated". Bookings are stored only on this computer (`ml/component_4/data/bookings.sqlite`).
- The demo time button only works because `api.allow_time_override: true` in `configs/default.yaml`.
  Set it to `false` for real use.
- Android phone/emulator: needs Android Studio. Emulator: `C4_API=http://10.0.2.2:8000`. Real phone: start the
  server with `--host 0.0.0.0` and use the PC's IP address.
