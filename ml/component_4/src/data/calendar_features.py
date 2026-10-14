"""Daily calendar: weekends, Sri Lankan public holidays, Poya days, long weekends, school holidays."""
import holidays
import pandas as pd

# Approximate government-school vacation windows (month, day) -> (month, day).
# The real calendar shifted in 2022-2024 after COVID; refine from the Ministry of Education gazette.
SCHOOL_HOLIDAYS = [((4, 5), (4, 20)), ((8, 1), (8, 31)), ((12, 10), (12, 31))]


def build_calendar(cfg) -> pd.DataFrame:
    days = pd.date_range(cfg["dates"]["start"], cfg["dates"]["end"], freq="D")
    lk = holidays.country_holidays("LK", years=range(days[0].year, days[-1].year + 1))
    df = pd.DataFrame(index=days)
    df["dow"] = days.dayofweek
    df["is_weekend"] = (df.dow >= 5).astype(int)
    names = [lk.get(d.date(), "") for d in days]
    df["holiday_name"] = names
    poya = [n.endswith("Full Moon Poya Day") and not n.startswith("Day Following") for n in names]
    df["is_poya"] = [int(p) for p in poya]
    df["is_holiday"] = [int(bool(n) and not p) for n, p in zip(names, poya)]

    off = (df.is_weekend | df.is_poya | df.is_holiday).astype(bool)
    run_id = (off != off.shift()).cumsum()
    run_len = off.groupby(run_id).transform("size")
    df["is_long_weekend"] = (off & (run_len >= 3)).astype(int)

    md = list(zip(days.month, days.day))
    df["is_school_holiday"] = [int(any(a <= x <= b for a, b in SCHOOL_HOLIDAYS)) for x in md]
    return df


if __name__ == "__main__":
    from src.config import load_config
    c = build_calendar(load_config())
    print(c.drop(columns="holiday_name").sum().to_string())
    print(c[c.is_poya == 1].loc["2025"].holiday_name.to_string())
