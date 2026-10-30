"""Crowd control per trail: defaults from the old booking_mode, per-trail overrides, ticketed trails only."""
import pytest

from src.config import load_config
from src.control import modes


def test_existing_parks_keep_their_mechanism():
    assert set(modes.trail_modes(load_config(park="horton_plains")).values()) == {"gate_slots"}
    assert set(modes.trail_modes(load_config(park="adams_peak")).values()) == {"advisory_windows"}
    pekoe = load_config(park="pekoe_trail")
    assert modes.park_modes(pekoe) == ["open_stages"] and not modes.ticketed(pekoe, "s10")


def test_per_trail_override_and_errors():
    cfg = load_config(park="horton_plains")
    cfg["area"]["trail_modes"] = {"thotupola": "open_viewpoint"}
    assert modes.trail_modes(cfg)["thotupola"] == "open_viewpoint" and modes.ticketed(cfg, "main")
    assert modes.park_modes(cfg) == ["gate_slots", "open_viewpoint"]
    assert modes.trails_with(cfg, "open_viewpoint") == ["thotupola"]
    cfg["area"]["trail_modes"] = {"thotupola": "teleport"}
    with pytest.raises(ValueError, match="Unknown control mode"):
        modes.trail_modes(cfg)
    cfg["area"]["trail_modes"] = {"nowhere": "gate_slots"}
    with pytest.raises(ValueError, match="not in area.trail_names"):
        modes.trail_modes(cfg)
