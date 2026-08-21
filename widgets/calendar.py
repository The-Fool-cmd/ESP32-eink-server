import os
from datetime import datetime, timedelta

import caldav


def get_context(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    start = datetime.combine(now.date(), datetime.min.time())
    end = start + timedelta(days=1)

    # Defaults to loopback, on the assumption that the CalDAV server runs
    # on this same host; override with RADICALE_URL if it doesn't.
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

                    # Used only to pick the event to emphasize (below),
                    # never handed to the template: all-day events run to
                    # end-of-day, timed events to their dtend, and an event
                    # with no dtend counts as a point in time.
                    if all_day:
                        end_dt = datetime.combine(dtstart, datetime.min.time()) + timedelta(days=1)
                    elif dtend:
                        end_dt = dtend
                    else:
                        end_dt = sort_dt

                    raw_events.append(
                        {
                            "time": time_label,
                            "summary": str(component.get("summary", "(untitled)")),
                            "_sort": sort_dt,
                            "_end": end_dt,
                        }
                    )

        raw_events.sort(key=lambda e: e["_sort"])

        # Emphasize exactly one event: the first one, chronologically, that
        # hasn't ended yet — whatever is in progress, or next up. Once
        # everything today has ended, nothing is emphasized.
        current_idx = next((i for i, e in enumerate(raw_events) if e["_end"] > now), None)

        events = [
            {"time": e["time"], "summary": e["summary"], "current": i == current_idx}
            for i, e in enumerate(raw_events)
        ]
        return {"events": events, "calendar_error": None, "date_label": date_label}
    # Broad on purpose, same posture as the other widgets: a CalDAV or
    # parsing failure degrades to the "unavailable" widget state rather than
    # failing the whole render.
    except Exception as exc:
        return {"events": [], "calendar_error": str(exc), "date_label": date_label}
