import os
from datetime import datetime, timedelta

import caldav


def get_context(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    start = datetime.combine(now.date(), datetime.min.time())
    end = start + timedelta(days=1)

    # Loopback, not the LAN hostname: Radicale's container publishes its port
    # with no bind-address restriction, so it's reachable on every host
    # interface including 127.0.0.1 — and this server runs natively on the
    # same host as Radicale, not in its own container/network namespace.
    url = os.environ.get("RADICALE_URL", "http://127.0.0.1:5232")
    username = os.environ.get("RADICALE_USERNAME")
    password = os.environ.get("RADICALE_PASSWORD")

    if not username or not password:
        return {"events": [], "calendar_error": "Radicale credentials not configured"}

    try:
        client = caldav.DAVClient(url=url, username=username, password=password)
        principal = client.principal()

        raw_events = []
        for cal in principal.calendars():
            for event in cal.search(start=start, end=end, event=True, expand=True):
                for component in event.icalendar_instance.walk("VEVENT"):
                    dtstart = component["dtstart"].dt
                    all_day = not isinstance(dtstart, datetime)
                    sort_dt = datetime.combine(dtstart, datetime.min.time()) if all_day else dtstart
                    raw_events.append(
                        {
                            "time": "All day" if all_day else dtstart.strftime("%H:%M"),
                            "summary": str(component.get("summary", "(untitled)")),
                            "_sort": sort_dt,
                        }
                    )

        raw_events.sort(key=lambda e: e["_sort"])
        events = [{"time": e["time"], "summary": e["summary"]} for e in raw_events]
        return {"events": events, "calendar_error": None}
    except Exception as exc:
        return {"events": [], "calendar_error": str(exc)}
