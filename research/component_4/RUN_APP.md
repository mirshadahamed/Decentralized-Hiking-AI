# How to run the Component 4 app (Horton Plains, Adam's Peak, Yala)

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
2. Tap a day (e.g. **24 Nov 2026**, Il Poya) → expected crowd, the **safe limit for this day** per trail
   (expected / limit; it changes with rain, wet ground, crowding and trail condition – tap **Why this limit?**),
   suggestions for a quieter visit, trails.
3. Pick trail, group size and a time (`07:00 · 20 left`) → **Book** → QR ticket with an 8-letter code.
4. **My tickets** shows it again (works offline). **Map**: the three trails.

**Adam's Peak pilgrim** (no tickets)
1. **Start times** → calendar of the season (e.g. **Wed 23 Dec 2026**, Unduvap Poya: the season opens).
2. Tap a night → pick a route → sunrise at the summit for that date, best start for sunrise and how long the
   climb takes with that night's crowd (busy nights move the start into **the evening before**, with an
   "arrive early" warning), the **evening plan** (start the evening before, rest at the halfway hall, leave at the
   given time), expected wait near the top per start time, and when the summit is busiest.
   Compare **Tue 10 Nov** (quiet: best 02:30) with **Fri 25 Dec** (busy: best 23:30 the evening before).
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
4. **Live**: traffic lights estimated from who went through the gate. The card on top says what to do at the gate
   for the next 2 hours: *keep the gate open*, or *hold new entries to a trail for N min / send the next groups to
   another trail*. To see it act, check in or sell many groups for one trail between 06:00 and 08:00.
5. **Count**: pick a section (★ = the count also updates today's forecast), tap **+1** for every walker you see, **Save count**. Works in airplane mode: the count
   waits on the phone ("1 waiting to be sent") and is sent with **Send now** when the signal is back.
   Back on **Live**, the card *Rest of today · updated with N counts* shows the sections now expected over capacity.
6. **Crowding**: on each section the **% chance** that it is really over capacity at that hour.

**Yala visitor** (Plan your visit → filter **Safari** → *Yala National Park (Block 1)*)
1. Overview: three safari circuits from the Palatupana and Katagamuwa entrances, the quiet days, the annual closure.
2. Calendar → a day → expected visitors, the safe limit per circuit, suggestions → book a jeep slot (06:00 morning or
   14:00–15:30 afternoon) exactly as at Horton Plains.

**Yala ranger: wildlife sightings** (choose Yala → **Staff** → log in with a **Yala** ranger account, setup step 5)
1. Press **Now** → demo time, e.g. 10 Nov 2026 07:10. Sell a few walk-ins on *Patanangala and Buthawa* first
   (Walk-ins tab) so jeeps are on the tracks.
2. **Sightings** tab (only at Yala) → pick a section (e.g. *Heenwewa Tank*), species **leopard** → **Report at 07:10**.
3. The card shows the rule (*at most 10 jeeps stopped, 10 min each*), the jeeps estimated near it from the gate, and
   – when it is crowded – which circuits avoid it. **Animal gone** ends it.

**Park officer** (log out, log in as `officer1`)
1. **Daily quota**: pick a day → per trail the quota *with the crowd forecast* (what the tickets use), *weather
   only* and *the same all year*, why the forecast lowers it (which section, which hours), and the sections
   expected over capacity. Tap another rule or **My number** to change the day's tickets (bookings are kept).
2. **Forecast check**: rangers' counts next to the forecast of the same section and hour (mean error, share
   within 30 %, over-capacity called / false alarms).
3. **This week**: next 7 days with bookings; **Refresh now** re-runs the daily refresh.
4. **Trail condition**: trail, days, Good / Muddy / Partly closed / Closed, note → the safe limit and tickets
   for those days change at once; bookings now over the limit are listed. Visitors see the condition on the day screen.
5. **Close trail**: date, trail, time window, reason → affected bookings are listed (never cancelled).
6. **Alerts**: slots with more bookings than is safe after the weather got worse, a trail condition or a closure.

---

## Use it on your phone

The app is built for phones: phone-sized screens, offline tickets and an offline forecast. The phone and the
laptop must be on the **same Wi-Fi**. The laptop's Wi-Fi address here is `192.168.1.6`; check yours with
`ipconfig`, line "IPv4 Address" under the Wi-Fi adapter.

**Terminal 1 (both options):** start the servers so the phone can reach them:
```powershell
.venv\Scripts\python.exe -m src.api.serve_all --host 0.0.0.0
```
The laptop's Wi-Fi must be a **Private** network (Settings → Network & internet → Wi-Fi → the network →
Network profile type: **Private**). It was *Public* on 20 Oct, and then Windows blocks the phone. If Windows asks
to allow Python through the firewall, tick **Private networks** → Allow. On the phone's browser,
http://192.168.1.6:8000/parks should list both parks. If it doesn't load, the firewall is blocking port 8000.

### Option A – in the phone's browser (works now, nothing to install)
Terminal 2:
```powershell
cd D:\Documents\SLIIT\Research\Decentralized-Hiking-AI
flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8080 --dart-define=C4_API=http://192.168.1.6:8000
```
- On the phone, open **http://192.168.1.6:8080** in Chrome. Then use ⋮ → **Add to Home screen** for an app icon.
- Everything works, including the forecast made on the phone. Exception: **QR scanning** at the ranger gate
  needs HTTPS in a browser, so type the ticket code instead.

### Option B – install the Android app (APK)
One-time: install **Android Studio** (it brings the Android SDK), open it once and let it finish the SDK setup.
Then run `flutter doctor` until "Android toolchain" has a ✓, and accept licences with
`flutter doctor --android-licenses`.

**Phone connected by USB** (Settings → About phone → tap *Build number* 7 times → Developer options → **USB
debugging** on):
```powershell
flutter devices                                            # the phone must be listed
flutter run -d <phone id> --dart-define=C4_API=http://192.168.1.6:8000
```

**Or build an APK file** and copy it to the phone (allow "install unknown apps" for Files / Drive):
```powershell
flutter build apk --debug --dart-define=C4_API=http://192.168.1.6:8000
# -> build\app\outputs\flutter-apk\app-debug.apk
```
- Use the **debug** build: it allows plain `http://` to the laptop. A release build needs the server on HTTPS.
- The server address is fixed into the build. If the laptop's IP changes, build again.
- The Android emulator uses `C4_API=http://10.0.2.2:8000` instead.

**Demo with no signal (offline-first app + forecast made on the phone):**
1. Run the Horton Plains `refresh` **on the demo day**. The pack is for the day after the refresh, and the app's
   "tomorrow" is that day.
2. While connected, open the app once: **Plan your visit → Horton Plains**. Opening a park stores its screens and
   tomorrow's forecast pack on the phone. Open **Crowding** and tomorrow in **Plan & book** too, so their extra
   data is stored.
3. Turn on **airplane mode**, with Wi-Fi off too. You can now even close and reopen the app.
4. Everything opened before still works. A dark bar at the bottom says **Offline · showing the copy saved on …**:
   - destinations;
   - Horton Plains overview and calendar;
   - tomorrow's day screen, with the **Forecast made on this phone** card;
   - **Crowding**: bottleneck map, safe numbers, your walk.
5. What needs the server says so clearly: booking a ticket, and screens never opened while online.
6. The number of ms on the cards is the time on *this* phone: the real-phone NFR1 measurement (plan item B4).

**Crowding tab (the proposal's core output), also offline:**
- **Days:** the chips at the top pick **Today**, **Tomorrow** or one of the next 5 days.
  - Today and tomorrow: "ST-GNN on this phone · … ms".
  - Later days: "Planning outlook · saved on this phone" (calendar + typical or forecast weather).
  - The whole week is in the daily pack, so it works offline.
- **Where:**
  - hikers: **Crowding** in the bottom bar;
  - officers: **Bottlenecks**, the first tab (Adam's Peak: the third);
  - rangers: **Tomorrow**;
  - the on-device card: **Every section on the map**.
- **Map:** every trail section is coloured by tomorrow's ST-GNN forecast ÷ what it holds at once: green quiet,
  yellow filling up, orange busy, red over capacity. Drag the **hour slider**; tap a section for its hourly bars and
  PCC / RCC / ECC.
- **Safe numbers:** the park's safe number for tomorrow (vs the fixed Cifuentes number); per trail the safe number
  and the section that sets it, with the fullest sections first.
- **Your walk:** what most visitors will do and what they will meet, the plan suggested for *this* phone, and other
  good options (start time, the loop the other way round, another trail). Each phone draws a different good option,
  so the advice does not move the whole crowd to one place (RQ8).

**Officer records (keep the daily counts):** log in as an officer → **Records** tab (both parks).
- **Dates:** presets (Past 30 days + next week, Past 30 days, Today + 6 days, Next 90 days, Past year) or
  **Custom…** for any range.
- **Trails:** the trail dropdown filters to one trail.
- **Per day:**
  - visitors: past = DWC total or the estimate, labelled; future = the forecast with its range;
  - the system's own counts: booked, at the gate, halfway;
  - the safe limit. Red days were above the safe limit.
- **Keep the records:** the copy button puts the table on the clipboard as CSV (paste into Excel). Or download:
  http://localhost:8101/admin/records?start=2026-10-01&end=2026-10-31&format=csv (needs an officer token; easiest
  from http://localhost:8101/docs → Authorize).

**Module 3 and the authority dashboard:**
- The feed for Module 3: http://localhost:8000/parks/horton_plains/module3/feed. Contract:
  `docs/schema/c4_module3_feed.schema.json`; sample: `docs/schema/sample_module3_feed.json`.
- Authority view on the laptop: `.venv\Scripts\python.exe -m streamlit run dashboard/app.py` → **Bottlenecks
  (authority)**.
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
   Yala has its own accounts too: the same lines with `$env:C4_PARK = "yala"`.
6. Adam's Peak data (once, ~10 min): `$env:C4_PARK = "adams_peak"; .venv\Scripts\python.exe -m src.data.build_dataset`
7. Yala data (once, ~10 min): `$env:C4_PARK = "yala"; .venv\Scripts\python.exe -m src.data.build_dataset`, then
   `.venv\Scripts\python.exe -m src.run_benchmark` (model, a few hours) and `.venv\Scripts\python.exe -m src.live.refresh`.

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
| Terminal 1 shows `error while attempting to bind on address ('127.0.0.1', 8101)` | An **old** `serve_all` is still running (and serving old code). Stop it: close its terminal, or `Get-CimInstance Win32_Process -Filter "Name='python.exe'" \| Where-Object CommandLine -match 'src.api' \| ForEach-Object { Stop-Process -Id $_.ProcessId }`, then start again |
| Yala staff login fails | Yala has its own accounts: make one with `$env:C4_PARK = "yala"` (setup step 5) |
| `address already in use` / port 8000 busy | Use another port: `--port 8001` in Terminal 1 and `C4_API=http://localhost:8001` in Terminal 2 |
| Chrome shows an old version | Press `R` in Terminal 2, or stop (`q`) and run step 2 again |

## Notes
- Visitor history after 2025 is **simulated** with real weather until DWC ticket data are connected; screens say
  "estimated". Bookings are stored only on this computer (`research/component_4/data/bookings.sqlite`).
- The demo time button only works because `api.allow_time_override: true` in `configs/default.yaml`.
  Set it to `false` for real use.
- Phone or emulator: see **Use it on your phone** above.
