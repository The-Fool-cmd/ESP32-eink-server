import os
from datetime import datetime, timedelta

import caldav


def get_context(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    start = datetime.combine(now.date(), datetime.min.time())
    end = start + timedelta(days=1)

    # Loopback, not the LAN hostname: this server and Radicale run on the same host.
    url = os.environ.get("RADICALE_URL", "http://127.0.0.1:5232")
    username = os.environ.get("RADICALE_USERNAME")
    password = os.environ.get("RADICALE_PASSWORD")

    date_label = now.strftime("%A %d/%m")

    if not username or not password:
        return {
            "events": [],
            "calendar_error": "Radicale credentials not configured",
            "date_label": date_label,
        }

    try:
        client = caldav.DAVClient(url=url, username=username, password=password, timeout=10)
        principal = client.principal()

        raw_events = []
        for cal in principal.calendars():
            for event in cal.search(start=start, end=end, event=True, expand=True):
                for component in event.icalendar_instance.walk("VEVENT"):
                    dtstart = component["dtstart"].dt
                    dtend = component["dtend"].dt if component.get("dtend") else None
                    all_day = not isinstance(dtstart, datetime)
                    sort_dt = datetime.combine(dtstart, datetime.min.time()) if all_day else dtstart

                    if all_day:
                        time_label = "All day"
                    elif dtend:
                        time_label = f"{dtstart.strftime('%H:%M')}–{dtend.strftime('%H:%M')}"
                    else:
                        time_label = dtstart.strftime("%H:%M")

                    raw_events.append(
                        {
                            "time": time_label,
                            "summary": str(component.get("summary", "(untitled)")),
                            "_sort": sort_dt,
                        }
                    )

        raw_events.sort(key=lambda e: e["_sort"])
        events = [{"time": e["time"], "summary": e["summary"]} for e in raw_events]
        return {"events": events, "calendar_error": None, "date_label": date_label}
    except Exception as exc:
        return {"events": [], "calendar_error": str(exc), "date_label": date_label}
