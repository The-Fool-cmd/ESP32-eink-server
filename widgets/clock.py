"""Minimal reference widget: the smallest thing that satisfies the
get_context() -> dict contract. Not included in any screen."""
from datetime import datetime


def get_context(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    return {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%A, %B %-d"),
    }
