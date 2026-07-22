from datetime import datetime


def get_context(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    return {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%A, %B %-d"),
    }
