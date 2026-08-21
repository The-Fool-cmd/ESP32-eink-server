import json
import os
import urllib.request
from urllib.error import URLError

# Cap matches the fixed 4x2 tile grid in templates/widgets/uptime.html —
# more monitors than this in Kuma is fine, only the first 8 get shown.
MAX_SERVICES = 8

_TIMEOUT = 10

# Uptime Kuma's heartbeat "status" ints, per its own source
# (server/model/monitor.js): 0=DOWN, 1=UP, 2=PENDING, 3=MAINTENANCE.
_STATUS_LABELS = {
    0: "down",
    1: "up",
    2: "pending",
    3: "maintenance",
}

# Status is never color-alone: every tile also carries one of these as a
# plain-text bracket label alongside its color.
_STATUS_TEXT = {
    "up": "ONLINE",
    "down": "OFFLINE",
    "pending": "PENDING",
    "maintenance": "MAINT",
    "unknown": "UNKNOWN",
}


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def get_context(url: str | None = None, slug: str | None = None) -> dict:
    url = url or os.environ.get("UPTIME_KUMA_URL")
    slug = slug or os.environ.get("UPTIME_KUMA_STATUS_SLUG")

    if not url or not slug:
        return {"services": [], "uptime_error": "Uptime Kuma not configured"}

    base = url.rstrip("/")
    try:
        page = _fetch_json(f"{base}/api/status-page/{slug}")
        heartbeat = _fetch_json(f"{base}/api/status-page/heartbeat/{slug}")

        monitors = []
        for group in page.get("publicGroupList", []):
            monitors.extend(group.get("monitorList", []))

        heartbeat_list = heartbeat.get("heartbeatList", {})
        uptime_list = heartbeat.get("uptimeList", {})

        services = []
        for monitor in monitors[:MAX_SERVICES]:
            monitor_id = monitor.get("id")
            beats = heartbeat_list.get(str(monitor_id)) or []
            last_status = beats[-1].get("status") if beats else None
            uptime_pct = uptime_list.get(f"{monitor_id}_24")
            status = _STATUS_LABELS.get(last_status, "unknown")

            services.append(
                {
                    "name": monitor.get("name", "unknown"),
                    "status": status,
                    "status_label": _STATUS_TEXT[status],
                    "uptime_pct": round(uptime_pct * 100, 1) if uptime_pct is not None else None,
                }
            )

        return {"services": services, "uptime_error": None}
    # Broad on purpose, same posture as widgets/calendar.py: a bad response
    # shape (KeyError/TypeError/ValueError from malformed JSON) degrades to
    # the "unavailable" widget state rather than failing the whole render.
    except (URLError, OSError, ValueError, KeyError, TypeError) as exc:
        return {"services": [], "uptime_error": str(exc)}
