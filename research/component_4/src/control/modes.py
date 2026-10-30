"""Crowd control per trail (plan: docs/knuckles_and_next_steps_plan.md, section 3).

One park can mix mechanisms (Knuckles: ticketed nature trails, guided treks with permits, roadside viewpoints and
campsites). Each trail has a control mode; the API serves each mechanism only for the trails in that mode and the
app builds its screens from the modes in GET /status.

    area.trail_modes: {trail: mode}        per-trail override
    control.default_mode: mode             park default; older configs: booking_mode required -> gate_slots,
                                           advisory -> advisory_windows

Modes (what the visitor sees / the controller):
    gate_slots        a ticket for a slot; slot LP + closed-loop gate control (Horton Plains)
    advisory_windows  a recommended start window, never refused (Adam's Peak)
    vehicle_caps      a session ticket per vehicle; sighting rule (Yala)
    open_stages       stage advice, no ticket (Pekoe Trail)
    guided_permit     a permit for a day with a guide; daily cap from capacity and guides on duty; checked out and
                      back with an overdue alarm (Knuckles treks)
    open_viewpoint    open access; busy hours and parking advice (Knuckles roadside viewpoints)
    campsite          pitches per night (Knuckles camps)
"""
MODES = ("gate_slots", "advisory_windows", "vehicle_caps", "open_stages", "guided_permit", "open_viewpoint", "campsite")
TICKETED = ("gate_slots", "vehicle_caps")           # trails sold in slots (/slots, /bookings, start times)
_FROM_BOOKING = {"required": "gate_slots", "advisory": "advisory_windows"}


def default_mode(cfg) -> str:
    c = cfg["control"]
    mode = c.get("default_mode") or _FROM_BOOKING.get(c.get("booking_mode", "required"), "gate_slots")
    if mode not in MODES:
        raise ValueError(f"Unknown control.default_mode '{mode}' (one of {MODES})")
    return mode


def trail_modes(cfg) -> dict:
    """{trail: mode} for every trail of the park."""
    d = default_mode(cfg)
    over = cfg["area"].get("trail_modes") or {}
    out = {t: over.get(t, d) for t in cfg["area"]["trail_names"]}
    bad = {t: m for t, m in out.items() if m not in MODES}
    if bad:
        raise ValueError(f"Unknown control mode(s) {bad} (one of {MODES})")
    unknown = set(over) - set(out)
    if unknown:
        raise ValueError(f"area.trail_modes names trails not in area.trail_names: {sorted(unknown)}")
    return out


def trails_with(cfg, *modes) -> list:
    return [t for t, m in trail_modes(cfg).items() if m in modes]


def ticketed(cfg, trail: str) -> bool:
    return trail_modes(cfg).get(trail) in TICKETED


def park_modes(cfg) -> list:
    """The modes present in the park, in MODES order (the app shows one card / tab per mode)."""
    present = set(trail_modes(cfg).values())
    return [m for m in MODES if m in present]
