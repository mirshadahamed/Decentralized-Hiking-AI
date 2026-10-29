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
