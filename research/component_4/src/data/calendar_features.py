"""Daily calendar: weekends, Sri Lankan public holidays, Poya days, long weekends, school holidays."""
import holidays
import numpy as np
import pandas as pd

# Approximate government-school vacation windows (month, day) -> (month, day).
# The real calendar shifted in 2022-2024 after COVID; refine from the Ministry of Education gazette.
SCHOOL_HOLIDAYS = [((4, 5), (4, 20)), ((8, 1), (8, 31)), ((12, 10), (12, 31))]


SYNODIC_DAYS = 29.530588853
REF_FULL_MOON_UTC = pd.Timestamp("2000-01-21 04:40")          # a known full moon
POYA_SHIFT_H = 12
POYA_BY_MONTH = ["Duruthu", "Navam", "Medin", "Bak", "Vesak", "Poson", "Esala", "Nikini", "Binara", "Vap", "Il",
                 "Unduvap"]


def lk_holidays(years) -> dict:
    """Sri Lankan holidays from the `holidays` package. Years it does not cover yet (the gazette is published
    late in the year before) get ESTIMATED Poya days: the date of the full moon in Sri Lanka time (can be a day
    off; replace with the gazette)."""
    lk = dict(holidays.country_holidays("LK", years=list(years)))
    for y in years:
        if any(d.year == y and "Poya" in n for d, n in lk.items()):
            continue
        start = pd.Timestamp(f"{y}-01-01")
        k = int(np.floor((start - REF_FULL_MOON_UTC).days / SYNODIC_DAYS))
        while True:
            # Sri Lanka time (+5.5 h), 12 h earlier: the gazetted Poya is usually the day the full moon begins
            fm = REF_FULL_MOON_UTC + pd.Timedelta(days=k * SYNODIC_DAYS) + pd.Timedelta(hours=5.5 - POYA_SHIFT_H)
            if fm.year > y:
                break
            if fm.year == y:
                lk[fm.date()] = f"{POYA_BY_MONTH[fm.month - 1]} Full Moon Poya Day (estimated)"
            k += 1
    return lk


def build_calendar(cfg) -> pd.DataFrame:
    days = pd.date_range(cfg["dates"]["start"], cfg["dates"]["end"], freq="D")
    lk = lk_holidays(range(days[0].year, days[-1].year + 1))
    df = pd.DataFrame(index=days)
    df["dow"] = days.dayofweek
    df["is_weekend"] = (df.dow >= 5).astype(int)
    names = [lk.get(d.date(), "") for d in days]
    df["holiday_name"] = names
    poya = [("Full Moon Poya Day" in n) and not n.startswith("Day Following") for n in names]
    df["is_poya"] = [int(p) for p in poya]
    df["is_holiday"] = [int(bool(n) and not p) for n, p in zip(names, poya)]

    off = (df.is_weekend | df.is_poya | df.is_holiday).astype(bool)
    run_id = (off != off.shift()).cumsum()
    run_len = off.groupby(run_id).transform("size")
    df["is_long_weekend"] = (off & (run_len >= 3)).astype(int)

    md = list(zip(days.month, days.day))
    df["is_school_holiday"] = [int(any(a <= x <= b for a, b in SCHOOL_HOLIDAYS)) for x in md]
    season = cfg.get("calendar", {}).get("season")
    if season:
        df["is_season"] = season_flag(days, season["from_poya"], season["to_poya"])
    return df


def season_flag(days: pd.DatetimeIndex, from_poya: str, to_poya: str) -> list:
    """1 from the `from_poya` Poya day (e.g. Unduvap, December) to the next `to_poya` Poya day (e.g. Vesak, May):
    the Sri Pada pilgrimage season."""
    lk = lk_holidays(range(days[0].year - 1, days[-1].year + 2))

    def is_(name, poya):                     # names can be joined, e.g. "International Workers' Day; Vesak ..."
        return any(part.strip().startswith(f"{poya} Full Moon Poya Day") for part in name.split(";"))
    starts = sorted(d for d, n in lk.items() if is_(n, from_poya))
    ends = sorted(d for d, n in lk.items() if is_(n, to_poya))
    # if the season's last Poya is not known yet, assume ~150 days (Unduvap -> Vesak); never more than 200 days
    windows = []
    for s in starts:
        e = next((e for e in ends if e > s), None)
        if e is None or (e - s).days > 200:
            e = s + pd.Timedelta(days=150).to_pytimedelta()
        windows.append((s, e))
    return [int(any(s <= d.date() <= e for s, e in windows)) for d in days]


if __name__ == "__main__":
    from src.config import load_config
    c = build_calendar(load_config())
    print(c.drop(columns="holiday_name").sum().to_string())
    print(c[c.is_poya == 1].loc["2025"].holiday_name.to_string())
