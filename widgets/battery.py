import math

# 5-segment HUD-style meter, each segment worth 20%.
_SEGMENTS = 5


def get_context(battery_pct: int | None) -> dict:
    if battery_pct is None:
        return {"battery_pct": None, "battery_level": None, "battery_segments": None}

    level = "high" if battery_pct >= 50 else ("medium" if battery_pct >= 20 else "low")

    # ceil rather than floor, so even 1% shows a sliver instead of reading
    # as fully dead. Exactly 0% is special-cased to no segments at all.
    segments = min(_SEGMENTS, math.ceil(battery_pct / (100 / _SEGMENTS))) if battery_pct > 0 else 0

    return {"battery_pct": battery_pct, "battery_level": level, "battery_segments": segments}
