# ESP32 E-Ink Server

Render server for a TRMNL 7.5" DIY e-ink kit (ESP32-C3/ESPHome). The device
wakes, does one `GET /image/<device_id>.png`, blits the PNG, and deep-sleeps.
Nothing here renders on a timer — every frame is built fresh per request.

Firmware/client side lives in a separate repo:
[ESP32-eink-client](https://github.com/The-Fool-cmd/ESP32-eink-client).

## Architecture

**Request flow:** Flask route (`server.py`) → widget modules build a context
dict each → Jinja renders the device's top-level template (which includes the
widget partials in `templates/widgets/`) → Playwright drives headless
Chromium to screenshot that HTML/CSS layout → `dither.py` quantizes the
full-color screenshot down to the device's exact panel palette → PNG bytes go
back in the response.

Rendering full HTML/CSS through a real browser (rather than drawing with
Pillow) means widgets are just normal web layout — flexbox, borders, fonts —
instead of manually positioned drawing calls. Pillow's job is the last step
only: converting Chromium's 24-bit output into what the physical panel can
actually show.

**Dithering (`dither.py`):** the device firmware blits the PNG it's sent
rather than doing anything sophisticated with color itself, so the PNG we
send needs to already be exactly what the panel will display. Each device in
`devices.py` declares a `palette` (exact list of RGB colors its panel
supports); after the Chromium screenshot, `dither.py` quantizes the image
down to that palette with Floyd-Steinberg error diffusion rather than a flat
per-pixel threshold, so anti-aliased text edges become a dot-pattern stipple
that keeps their apparent stroke weight instead of getting rounded away, and
flat CSS colors read as believable shading even on a 6-color panel. One
wrinkle: Chromium's antialiasing isn't clean grayscale — edge pixels carry a
faint genuine RGB tint, which a 6-color nearest-match will happily call "red"
or "yellow" instead of black/white, speckling every letter with a faint
rainbow fringe. `dither.py` snaps low-saturation pixels to pure black/white
*before* quantizing to route around this — only genuinely colored content
(widget accent fills) goes through full 6-way dithering. `fool-nightstand`'s
palette is just `[black, white]`, so this is mostly moot there.

`fool-workdesk`'s SPECTRA6 palette is the pure-saturated RGB triples
(`(255,0,0)` red, etc.) that match the `ESP32-eink-client` firmware's own
native `Color(r,g,b,w)` constants byte-for-byte (see that repo's
`test.yaml`), not a "measured, close-enough" approximation of the physical
ink — an earlier version of this file used muted/measured-looking values,
which is worth knowing if this regresses, but matching the firmware's own
representation exactly is the more defensible default until proven
otherwise. **Live status as of 2026-08-08: the panel renders this design's
geometry correctly (chamfered corners, corner brackets) but not color** —
confirmed the server sends genuine multi-color RGB (not palette-indexed)
PNGs matching this exact palette, so the remaining bug is believed to be in
`ESP32-eink-client` (refresh-mode selection or its PNG color-mapping path),
not here. Any changes to this palette should stay in sync with the CSS
custom properties in `templates/screen_status.html` (`--c-red` etc.) — see
that file's comment for why an inexact match speckles solid fills.

**Widgets:** each `widgets/*.py` exposes `get_context(...) -> dict`; `server.py`
merges all of them into one context and hands it to the template. Adding a
widget is one Python module plus one template partial.

**Per-device canvas, variable content:** canvas size isn't hardcoded — each
device in `devices.py` declares its own width/height, which flow into both
the Playwright viewport and the template itself (`{{ width }}`/`{{ height }}`
in `screen.html`), so different panels, orientations, or a portrait/
vertically-mounted display are just a different `devices.py` entry, not a
code change. On top of that, content like the calendar event list varies in
length regardless of canvas size. `render.py` handles this by running a small
JS pass after the page loads that drops any element flagged
`data-trim-overflow` whose box would run past the canvas edge — so a template
can list as many items as exist, at whatever size that canvas is, and only
whole, uncut boxes ever get shown.

**Calendar:** talks to a local Radicale CalDAV instance over loopback (same
host, so no LAN hop). Missing credentials or a Radicale failure degrades to a
"[ CALENDAR OFFLINE ]" message rather than failing the whole request. Exactly
one event (whichever hasn't ended yet, in chronological order — the thing
happening now, or coming up next) is flagged `current` and rendered in
inverse video; the rest stay plain. See "Visual theme" below for why only one
thing is ever emphasized.

**Weather (`fool-entrance`):** talks to two free, keyless
[Open-Meteo](https://open-meteo.com) APIs — the main forecast API
(`WEATHER_LAT`/`WEATHER_LON`) and its separate Air Quality API, fetched
independently so a failure in one only takes out its own tile, not the whole
screen (see below). The forecast call (`forecast_days=2`, `timezone=auto`)
gets current conditions, hourly temperature/rain-chance/humidity, and daily
UV/wind/sunrise-sunset in one request; `forecast_days=2` rather than `1`
because the hourly forecast strip needs "now" plus the next 6 hours, which
can roll past midnight into tomorrow depending what time the device happens
to render at. Same degrade-gracefully posture as calendar/uptime: missing
lat/lon or a request failure renders "[ WEATHER OFFLINE ]" instead of
failing the request. Shows current conditions (temperature, condition text,
a pure-CSS/no-webfont weather icon) plus the near-term hourly strip — since
every render happens on demand at wake-up, "current conditions as of now"
is exactly the right freshness, not a stale live reading. The Air Quality
tile is the one place a partial failure is visible on-screen rather than
degrading the whole request: `widgets/weather.py`'s `_fetch_air_quality`
catches its own errors and returns `aqi_error`, which the template renders
as a red-bordered "LINK DOWN" tile instead of failing to render at all.
`WEATHER_LOCATION_NAME` (optional) sets the header's location label; unset,
it prints the lat/lon instead.

**Service status (`fool-workdesk`):** talks to Uptime Kuma's unauthenticated
status-page JSON API (`/api/status-page/<slug>` +
`/api/status-page/heartbeat/<slug>`), not its admin API — no credentials to
manage. Same degrade-gracefully posture as calendar: missing config or a
request failure renders "Status unavailable" instead of failing the request.
Capped at 8 monitors (`widgets/uptime.py`'s `MAX_SERVICES`) to match the
fixed 4x2 tile grid in `templates/screen_status.html`; add more monitors in
Kuma freely; only the first 8 the status page returns get shown.

**Devices:** `devices.py` maps a device id to its own template plus pixel
dimensions — one entry per physical panel. This is the extension point for
running more than one device at once: a second entry with its own `screen`
template and its own width/height (e.g. swapped for a rotated/portrait
mount, or a different panel technology entirely) works today without
touching `server.py` or the widget modules. Widget partials
(`templates/widgets/*.html`) are corner-positioned rather than laid out
relative to a specific canvas size, so they're reusable across device
templates; only the top-level per-device template needs to be authored with
that device's dimensions, orientation, and color capability in mind.

Three devices today:
- `fool-nightstand` → `screen.html` — 800x480, plain black/white e-ink,
  calendar + battery.
- `fool-workdesk` → `screen_status.html` — 800x480, SPECTRA6 6-color e-ink
  (black/white/red/yellow/green/blue), service status + battery. Its
  `<style>` block uses flat, saturated colors rather than the grayscale
  hatch-pattern trick `screen.html` uses for "battery low" — the panel
  dithers whatever RGB it's sent to its nearest of the 6 primaries, so exact
  hex values don't matter, just staying flat/saturated (no gradients, which
  would speckle).
- `fool-entrance` → `screen_weather.html` — 480x800, the same SPECTRA6 panel
  as `fool-workdesk` but portrait-mounted, weather + battery. Unlike
  `fool-workdesk`'s white tiles-on-black, its stat tiles stay black with a
  colored corner-tick accent (a full colored border reads much lower
  contrast than white on this panel's black canvas) — color plus a
  plain-text bracket label either way, never color-alone, same rule as the
  uptime status tiles. UV and Air Quality both use that accent for their
  actual risk/status level; Air Quality's failure state (red border,
  "LINK DOWN") is the one place on this device a partial failure shows on
  its own tile rather than degrading the whole screen — see
  `widgets/weather.py`'s `_uv_category`/`_aqi_category`/`_fetch_air_quality`.

The battery widget partial itself (`templates/widgets/battery.html`) is
shared across all three — it only emits a `level-{high,medium,low}` class,
the color/pattern decision lives in each device's own template.

**Visual theme:** both devices share one HUD/terminal design language —
monospace headers and technical readouts (dates, times, status, the
battery/uptime %), chamfered (not rounded) card corners via `clip-path`, and
two opposing corner brackets framing the canvas. Status is never
color-alone: every service tile carries a plain-text bracket label
(`[ ONLINE ]`, `[ OFFLINE ]`, …) alongside its color — a 6-color panel can't
rely on hue alone for colorblind readers. Emphasis is deliberately spent on
one thing at a time rather than decorating everything equally: the
calendar's current/next event inverts to white-on-black; a `status-down`
service tile is the one place text is allowed to wear its status color
(red), a considered exception to keeping color on marks and text in plain
ink everywhere else. The battery meter is 5 discrete segments, not a smooth
fill — more legible at this size once dithered, and reads as an HUD/LED
meter rather than a phone-style icon. Colors used as *fills* (battery
segments, tile accents) are copy-pasted from `devices.py`'s palette
verbatim, not just "close" — a fill that's off by even a few RGB values from
the real palette entry stops being an exact match for `dither.py`'s
quantizer and speckles with stray colors instead of staying flat (caught by
rendering and zooming in, not obvious at a glance — see git history if this
regresses).

The two devices diverge on light vs. dark: `fool-nightstand` (mono — it's
physically incapable of any hue, so this is the only lever it has) stays
white-canvas with black chrome and a full-bleed black title bar; the user
considers this "already dark mode" in feel via that bar plus the
current-event inverse-video treatment, so it's deliberately left alone.
`fool-workdesk` (SPECTRA6) is genuinely dark-canvas: black background and
chrome, but the service tiles themselves stay white "panels" rather than
going all-black too — keeps ink coverage down on a reflective panel (a full
black canvas costs real refresh time/ghosting risk) and the status colors
read better against black than they ever did against white (yellow
especially — the one contrast WARN the dataviz palette validator flagged
earlier effectively disappears against a dark surface). Its two purely
decorative accents (the corner brackets, and a yellow rule under the title
in place of a same-color-as-canvas title bar) use the user's stated
preferred accent color, yellow — kept off every tile so it's never
confused with `status-pending`'s yellow, which is a status color, not
decoration.

## Deployment

Runs as the systemd unit `esp32-eink-server`, declared in
`/etc/nixos/hosts/foolaiserver/host_config.nix` (section 5f) on this same
host. Deliberately *not* a podman container: this is a plain Python project
living at a mutable path (`/var/lib/esp32-eink-server`) that gets edited and
`systemctl restart`ed directly — never rebuilt through Nix. Nix's only job is
supplying the Python interpreter and a NixOS-patched Playwright/Chromium.

To deploy a change: edit (or `git pull`) here, then
`sudo systemctl restart esp32-eink-server`.

## Local dev

`nix develop` opens a shell pinned to the same nixpkgs (`nixos-26.05`) as the
deployed service, so Python/Playwright/Chromium versions match exactly.

```
nix develop --command python3 scripts/render_screen.py [device_id]
```

renders one frame to `out.png` without touching the live service.
`device_id` defaults to `fool-nightstand`; pass `fool-workdesk` or
`fool-entrance` to preview the SPECTRA6 templates instead.

## Dependencies

| Package | Used for |
|---|---|
| Flask | HTTP server, one route per device |
| Jinja2 | HTML templating for widgets |
| Playwright (Chromium) | renders the HTML/CSS layout to a PNG screenshot |
| caldav | talks to Radicale for calendar events |
| Pillow | quantizes/dithers the Chromium screenshot down to each device's panel palette (`dither.py`) |

`widgets/uptime.py` and `widgets/weather.py` both talk to their APIs over plain
`urllib.request` (stdlib) rather than adding a `requests` dependency — no new
package needed. Open-Meteo needs no API key, so `widgets/weather.py` has no
new dependency to manage on the auth side either.

## Secrets

`secrets.env` (gitignored) holds `RADICALE_USERNAME` / `RADICALE_PASSWORD`,
`UPTIME_KUMA_URL` / `UPTIME_KUMA_STATUS_SLUG`, and `WEATHER_LAT` /
`WEATHER_LON`, loaded by systemd's `EnvironmentFile=`. Copy
`secrets.env.example` to get started — it must live at
`/var/lib/esp32-eink-server/secrets.env`, not wherever the repo happens to be
checked out.
