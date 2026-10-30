# Component 4: privacy review

*Plan §6.3.14. For the ethics section of the report and the field trial (December 2026). Reviewed 30 Oct 2026
against the code on `feature/component-4-knuckles`.*

## 1. Summary

Component 4 counts **groups**, not people. It keeps **no names, phone numbers, ID numbers, e-mail addresses or
locations of visitors**. A visitor is known only by a random code that they hold.

The only personal data is about **staff**: usernames, password hashes and an audit log of their actions.

## 2. What is stored, where, and why

All data sits on the park's server, one folder per park (`data/` or `data/<park>/`, not in git).

| Data | Table / file | Holds | Why |
|---|---|---|---|
| Slot tickets | `bookings` | Random 8-character code, day, trail, slot, group size, check-in time | Gate check, no-shows |
| Start times (no ticket) | `start_advice` | Random code, day, trail, slot, group size, arrival time | Let on-time groups in first (RQ13b) |
| Guided-trek permits | `permits` | Random 7-character code, day, trek, group size, out / due / back times | Daily cap; overdue alarm (safety) |
| Campsite pitches | `campsite_bookings` | Random code, night, site, pitches, people | Pitches per night |
| Gate queue and log (R7) | `gate_queue`, `gate_log` | Code, queue-join and let-in times, kind (ticket / start time) | Measured gate waiting time |
| Walk-ins | `walkins` | Day, trail, slot, group size, the ranger's username | Places left |
| Spot counts | `spot_counts`, `checkpoint_counts` | Section, time, number counted, the ranger's username | Forecast check and correction |
| Sightings (Yala) | `sightings` | Place, species, time, the ranger's username | Jeep rule |
| Trail conditions, incidents | `trail_conditions` | Trail, level, a short note, the officer's username | Lower limits at once |
| Staff accounts | `auth.sqlite`: `users`, `sessions` | Username, role, salted scrypt hash, failed logins, session tokens (expire) | Log-in |
| Audit log | `auth.sqlite`: `audit` | Time, username, action, detail (e.g. a code checked in) | Accountability of staff actions |
| Backups | `data/backups/<park>/<day>/` | Copies of the two databases above, last 14 days | Recovery |

**On the phone (visitor):**
- the visitor's own ticket codes (`ticket_store`), to show them offline;
- the language;
- the forecast pack for offline use.

**On the phone (ranger):** spot counts waiting for a signal (`count_store`).

## 3. Design choices that protect privacy

- **Random codes.** Codes are drawn with Python's `secrets` from an alphabet without look-alike characters. They
  carry no information about the holder and cannot be guessed in sequence.
- **Group size only.** Group size is the only number about a group. The app never asks for a name, phone number or
  nationality.
- **No visitor accounts and no tracking.** There is no GPS, no device ID and no analytics SDK. The Overdue check
  (Knuckles) uses only the ranger's out / back scan of the permit code.
- **QR count sharing (N5)** carries only section ids, times and counts, e.g. "12 walkers at section 5 at 08:10".
  It holds no personal data, so a lost phone or a photographed QR reveals nothing about anyone.
- **Staff passwords:**
  - salted scrypt hashes (n = 2^14), at least 10 characters;
  - the account locks after repeated failures;
  - session tokens expire.
- **Reports and exports are aggregates:**
  - the day report, trends and `recalibrate --export` give totals per trail, hour or section;
  - field-validation data holds counts only.
- **Public endpoints show forecasts only.** Everything with a code or a username needs a staff log-in. One
  exception: a visitor may look up their own code.

## 4. Risks and what to do

| Risk | Mitigation now | Before a real deployment |
|---|---|---|
| Someone who holds a code can see that booking | The code is the only key, like a paper ticket | Rate-limit code lookups at the gateway |
| The audit log links staff usernames to actions | Needed for accountability | Tell staff in writing; keep for 1 year |
| Codes and times are kept indefinitely | Codes alone identify nobody | Delete codes and times older than 13 months; keep only daily totals |
| A server or backup disk is lost | No visitor identities on it; staff passwords are hashed | Encrypt the backup folder; keep the server in the park office |
| A photo of a ticket QR | Valid for one day and one slot | — |
| The free-text note on an incident could name a person | 200 characters, staff only | Tell officers not to write names in notes |

## 5. Field trial (December)

- **Spot counts:** rangers count groups at places. Nobody is photographed or asked anything.
- **Survey of app use and following advice (plan §7):**
  - anonymous and on paper or a form;
  - no names and no contact details;
  - verbal consent;
  - under-18s are not asked.
- **Data shared with SLIIT for the thesis:**
  - daily or hourly totals and counts only;
  - never the databases themselves.
