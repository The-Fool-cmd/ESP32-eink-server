# ESP32 E-Ink Server

A render server for battery-powered e-ink dashboards. A device wakes from
deep sleep, makes one `GET /image/<device_id>.png`, blits the PNG to its
panel, and goes back to sleep. Nothing renders on a timer — every frame is
built fresh for the request that asked for it.

Screens are plain HTML and CSS, screenshotted by headless Chromium and
dithered down to whatever colors the panel can physically show. Adding a
widget means writing a Python function and a Jinja partial; adding a whole
new dashboard means one more template and one more dict entry.

The firmware side lives in a separate repo:
[ESP32-eink-client](https://github.com/The-Fool-cmd/ESP32-eink-client).

## How it works

```
GET /image/<device_id>.png
        │
        ├─ devices.py      look up the device: template, size, palette
        ├─ widgets/*.py    each get_context() returns a dict; all merged into one
        ├─ templates/      Jinja renders the device's screen (which includes widget partials)
        ├─ render.py       Playwright screenshots that HTML at the device's exact viewport
        └─ dither.py       Floyd-Steinberg quantize down to the panel palette → PNG bytes
```

Rendering through a real browser rather than drawing with Pillow means
widgets are ordinary web layout — flexbox, borders, `clip-path` — instead of
manually positioned draw calls. Pillow only handles the final step of turning
Chromium's 24-bit output into something the panel can display.

### Dithering

The firmware blits the PNG it is sent, so the PNG has to already be exactly
what the panel will show. Each device declares a `palette` in `devices.py`,
and `dither.py` quantizes the screenshot to it with Floyd-Steinberg error
diffusion rather than a flat per-pixel threshold: anti-aliased text keeps its
apparent stroke weight as a stipple instead of being rounded away, and flat
CSS colors read as believable shading even on a six-color panel.

One wrinkle: Chromium's antialiasing isn't clean grayscale. Edge pixels carry
a faint RGB tint that a six-color nearest-match will happily call "red",
speckling every letter with a rainbow fringe. `dither.py` snaps
low-saturation pixels to pure black or white *before* quantizing, so only
genuinely colored content goes through full multi-color dithering.

## Adding a widget

A widget is one Python module plus one Jinja partial. The module owns the
data, the partial owns the markup, and each device's screen template owns how
it looks there.

**1. Write `widgets/<name>.py`** exposing `get_context(...) -> dict`:

```python
from datetime import datetime


def get_context(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    return {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%A, %B %-d"),
    }
```

Conventions worth following:

- **Namespace your keys.** `server.py` merges every widget's dict into one
  context, so two widgets returning `date_label` will silently clobber each
  other. Prefix anything generic (`weather_date_label`, `battery_pct`).
- **Degrade, don't raise.** A widget that talks to the network catches its
  own failures and returns an error key (`calendar_error`, `weather_error`)
  that the partial renders as an "offline" state. One unreachable service
  should not cost the device its whole screen.
- **Read config from the environment**, with a sensible default or a clear
  "not configured" context when it's missing. See `widgets/uptime.py`.
- **Accept injectable arguments** (`now`, `url`, …) defaulting to the real
  source, so the widget can be rendered deterministically.

`widgets/clock.py` is the smallest complete example of the contract.

**2. Write `templates/widgets/<name>.html`** — markup and class names only,
no styling:

```html
<div class="widget-clock">
  <div class="clock-time">{{ time }}</div>
  <div class="clock-date">{{ date }}</div>
</div>
```

Branch on every state the module can return, including its error and empty
states — `templates/widgets/calendar.html` covers all three.

If the widget renders a variable-length list, mark each repeated element
`data-trim-overflow`. After the page loads, `render.py` runs a small JS pass
that removes any flagged element whose box runs past the canvas edge, so a
partial can emit as many items as exist and only whole, uncut ones survive.
See `templates/widgets/calendar.html`.

**3. Merge it into the context** in `server.py`:

```python
ctx.update(clock.get_context())
```

Add the same line to `scripts/render_screen.py` so the preview script stays
in sync.

**4. Include it** in whichever screens should show it, and style it in each
of those screens' `<style>` blocks:

```html
{% include "widgets/clock.html" %}
```

Styling lives in the screen, not the partial, on purpose: the same battery
partial renders as white-on-black inside one device's header bar and as
colored segments on another's dark canvas, without either device needing its
own copy of the markup.

## Adding a dashboard

A dashboard is a top-level template plus one entry in `devices.py`. No
changes to `server.py` or to any widget module.

**1. Add the device** to `DEVICES` in `devices.py`:

```python
"kitchen-panel": {
    "screen": "screen_kitchen.html",
    "width": 480,
    "height": 800,
    "palette": _SPECTRA6,   # or _MONO, or your own list of RGB triples
},
```

The key is the device id the firmware requests. `width`/`height` are the
panel's pixels in the orientation it is mounted — a portrait-mounted panel is
just a swapped width and height, not a code change. `palette` is optional;
omit it to serve an undithered full-color PNG.

**2. Write `templates/screen_<name>.html`.** It owns the whole canvas: the
`<style>` block, the layout, and which widget partials it includes.

```html
<html>
<head><style>
  html, body {
    margin: 0; padding: 0;
    width: {{ width }}px;
    height: {{ height }}px;
  }
  /* … styling for the partials you include below … */
</style></head>
<body>
  {% include "widgets/battery.html" %}
  {% include "widgets/clock.html" %}
  {% if updated_at %}
  <div class="updated-at">Updated {{ updated_at }}</div>
  {% endif %}
</body>
</html>
```

Use `{{ width }}` and `{{ height }}` rather than hardcoded pixels — both are
passed in from the device entry, and hardcoding them means the template
silently breaks the day it is reused on another panel.

**3. Preview it** without touching the running service:

```
nix develop --command python3 scripts/render_screen.py kitchen-panel
```

That writes `out.png`. Open it, and zoom in before trusting a color — see the
rules below.

### Rules for a color panel

If the device has a palette, the template has to cooperate with the
quantizer:

- **Copy fill colors verbatim from the palette in `devices.py`.** An exact
  palette match quantizes with zero error and stays a flat fill. A
  near-miss — a "close enough" hex picked independently — gets
  Floyd-Steinberg'd against the real palette and speckles with stray flecks.
  It looks fine at a glance and obvious at 400%.
- **No gradients or gray tones** on a palette without gray. Mid-gray sits
  about equally near several primaries, so it dithers into confetti rather
  than a clean stipple. Get de-emphasis from font size or weight instead.
- **No webfonts.** Every render is an on-demand screenshot, so an external
  font fetch puts network latency and a new failure mode on the request path.
  Same for emoji and icon fonts: the weather icons are pure CSS shapes.
- **Watch ink coverage.** Large solid black fills cost refresh time on a
  reflective panel. The dark-canvas screens here keep their text-dense
  surfaces light and only darken the surrounding frame.

### Shared visual language

The screens in this repo share one HUD/terminal look, which is worth matching
if you add another: monospace for technical readouts (dates, times, status,
percentages) and body sans-serif for free text; chamfered rather than rounded
card corners via `clip-path`; two opposing corner brackets framing the canvas;
and yellow as the decorative accent, kept off anything that carries a status
so it is never confused with a status color.

Two rules do real work beyond taste:

- **Status is never color alone.** Every status-bearing element also carries
  a plain-text bracket label — `[ ONLINE ]`, `[ OFFLINE ]`, `[ HIGH ]` —
  because a six-color panel can't rely on hue for colorblind readers.
- **Emphasis is spent on one thing.** The calendar inverts exactly one
  event, the one in progress or next up. Everything else stays plain. A
  screen that emphasizes everything emphasizes nothing, and this is a glance
  surface.

The one deliberate exception is an offline service tile, where the text
itself goes red: an alert is not plain identity, and alert text in the alarm
color is a standard, legible convention.

## Example dashboards

The three devices in `devices.py` are the author's own, kept in the repo as
working examples of the patterns above rather than as anything you'd deploy
unchanged.

| Device | Screen | Panel | Shows |
|---|---|---|---|
| `fool-nightstand` | `screen.html` | 800x480 mono | Calendar + battery |
| `fool-workdesk` | `screen_status.html` | 800x480 SPECTRA6 | Service status + battery |
| `fool-entrance` | `screen_weather.html` | 480x800 SPECTRA6, portrait | Weather + battery |

Between them they cover the cases you're likely to hit: a one-bit panel that
has no lever but light and dark, a six-color panel on a dark canvas with
white tiles, and the same six-color panel rotated to portrait with a
different tile treatment. The battery partial is shared by all three and
styled differently in each.

The widgets they use:

- **`calendar`** — reads a CalDAV server (Radicale, by default over
  loopback). Flags exactly one event as `current`.
- **`uptime`** — reads [Uptime Kuma](https://github.com/louislam/uptime-kuma)'s
  unauthenticated status-page JSON API, so there are no credentials to
  manage. Capped at `MAX_SERVICES` (8) to match a fixed 4x2 tile grid.
- **`weather`** — reads [Open-Meteo](https://open-meteo.com), which is free
  and needs no API key. One request covers current conditions, an hourly
  strip, and the day's UV, wind and sun times.
- **`battery`** — renders a percentage passed by the device in the query
  string (`?battery=87`) as five discrete segments.
- **`clock`** — minimal reference widget, not wired into any screen.

## Local dev

`nix develop` opens a shell pinned to the same nixpkgs as the deployed
service, so the Python, Playwright and Chromium versions match exactly.

```
nix develop --command python3 scripts/render_screen.py [device_id]
```

renders one frame to `out.png` without touching the running service.
`device_id` defaults to `fool-nightstand`.

To run the server itself:

```
nix develop --command python3 server.py    # listens on :8000
```

Then fetch a frame the way a device would:

```
curl -o out.png 'http://localhost:8000/image/fool-nightstand.png?battery=87'
```

## Deployment

Runs as a systemd unit on the same host as the calendar and status services
it reads. It is deliberately not containerized: this is a plain Python
project living at a mutable path that gets edited and restarted in place.
Nix's only job is supplying the interpreter and a patched Playwright/Chromium.

```ini
[Service]
WorkingDirectory=/var/lib/esp32-eink-server
EnvironmentFile=/var/lib/esp32-eink-server/secrets.env
ExecStart=/path/to/nix/python3 /var/lib/esp32-eink-server/server.py
```

To deploy a change: `git pull` in the working directory, then
`systemctl restart esp32-eink-server`.

## Configuration

All configuration is environment variables, loaded from `secrets.env` (which
is gitignored). Copy `secrets.env.example` to `secrets.env` and fill it in;
it must sit next to `server.py`, at the path the unit's `EnvironmentFile=`
points at.

| Variable | Used by | Notes |
|---|---|---|
| `RADICALE_URL` | calendar | Defaults to `http://127.0.0.1:5232` |
| `RADICALE_USERNAME` / `RADICALE_PASSWORD` | calendar | Unset renders "[ CALENDAR OFFLINE ]" |
| `UPTIME_KUMA_URL` | uptime | Base URL of the Kuma instance |
| `UPTIME_KUMA_STATUS_SLUG` | uptime | Status page slug, not a URL |
| `WEATHER_LAT` / `WEATHER_LON` | weather | Decimal degrees |
| `WEATHER_LOCATION_NAME` | weather | Optional header label; falls back to lat/lon |

Every one of these is optional in the sense that missing config degrades to
that widget's "offline" state rather than failing the render.

## Dependencies

| Package | Used for |
|---|---|
| Flask | HTTP server, one route serving every device |
| Jinja2 | HTML templating for screens and widgets |
| Playwright (Chromium) | renders the HTML/CSS layout to a PNG screenshot |
| Pillow | quantizes and dithers that screenshot to each panel's palette |
| caldav | reads calendar events |

`widgets/uptime.py` and `widgets/weather.py` use stdlib `urllib.request`
rather than pulling in `requests`.
