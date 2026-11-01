"""N4: a busy park gets other parks with room (same kind first) and quieter days; a park that is down is unknown."""
from src.api.network import advice, park_row


def test_busy_park_gets_alternatives_same_kind_first():
    info = {"hp": {"name": "Horton Plains", "kind": "national_park"}, "ya": {"name": "Yala", "kind": "national_park"},
            "ap": {"name": "Adam's Peak", "kind": "pilgrimage"}, "pk": {"name": "Pekoe", "kind": "long_distance_trail"}}
    rows = [park_row("hp", info["hp"], {"total_expected": 1100, "total_safe_limit": 1000}),
            park_row("ya", info["ya"], {"total_expected": 500, "total_safe_limit": 900}),
            park_row("ap", info["ap"], {"total_expected": 100, "total_safe_limit": 1000}),
            park_row("pk", info["pk"], None)]
    days = [("2027-01-09", park_row("hp", info["hp"], {"total_expected": 700, "total_safe_limit": 1000})),
            ("2027-01-11", park_row("hp", info["hp"], {"total_expected": 1200, "total_safe_limit": 1000}))]
    out = advice("2027-01-10", rows, "hp", days)
    me = out["for_park"]
    assert me["level"] == "full" and me["load"] == 1.1
    assert [o["park"] for o in me["other_parks"]] == ["ya", "ap"]          # same kind before the quieter one
    assert [d["day"] for d in me["other_days"]] == ["2027-01-09"]
    assert "Quieter: 2027-01-09" in me["note"] and "Yala" in me["note"]
    assert next(r for r in out["parks"] if r["park"] == "pk")["level"] == "unknown"


def test_quiet_park_just_has_room():
    out = advice("2027-01-10", [park_row("hp", {"name": "Horton Plains"}, {"total_expected": 300, "total_safe_limit": 1000})], "hp")
    assert out["for_park"]["level"] == "room" and out["for_park"]["note"] == "Horton Plains has room on 2027-01-10."


def test_trip_puts_each_park_on_a_quiet_day():
    from src.api.network import plan_trip
    info = {"hp": {"name": "Horton Plains", "kind": "national_park"}, "kn": {"name": "Knuckles", "kind": "forest_reserve"}}
    load = {("hp", "d1"): 1.2, ("hp", "d2"): 0.5, ("hp", "d3"): 0.9,
            ("kn", "d1"): 0.3, ("kn", "d2"): 0.4, ("kn", "d3"): 1.1}
    rows = {k: park_row(k[0], info[k[0]], {"total_expected": v * 1000, "total_safe_limit": 1000}) for k, v in load.items()}
    t = plan_trip(["hp", "kn"], ["d1", "d2", "d3"], rows)
    assert [(v["park"], v["day"]) for v in t["visits"]] == [("kn", "d1"), ("hp", "d2")]
    assert t["note"] == "Every visit falls on a day with room."
    rows.pop(("kn", "d1"))                                                # unknown forecast: avoided if possible
    assert {v["park"]: v["day"] for v in plan_trip(["hp", "kn"], ["d1", "d2", "d3"], rows)["visits"]}["kn"] != "d1"
    import pytest
    with pytest.raises(ValueError):
        plan_trip(["hp", "kn"], ["d1"], rows)
