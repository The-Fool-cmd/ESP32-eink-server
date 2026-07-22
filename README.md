# ESP32 E-Ink Server

Render server for a TRMNL 7.5" DIY e-ink kit (ESP32-C3/ESPHome). The device
wakes, does one `GET /image/<device_id>.png`, blits the PNG, and deep-sleeps.
Nothing here renders on a timer — every frame is built fresh per request.

Firmware/client side lives in a separate repo:
[ESP32-eink-client](https://github.com/The-Fool-cmd/ESP32-eink-client).

## Architecture

**Request flow:** Flask route (`server.py`) → widget modules build a context
dict each → Jinja renders `templates/screen.html` (which includes the widget
partials in `templates/widgets/`) → Playwright drives headless Chromium to
screenshot that HTML/CSS layout → PNG bytes go back in the response.

Rendering full HTML/CSS through a real browser (rather than drawing with
Pillow) means widgets are just normal web layout — flexbox, borders, fonts —
instead of manually positioned drawing calls.

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
"Calendar unavailable" message rather than failing the whole request.

**Devices:** `devices.py` maps a device id to its own template plus pixel
dimensions — one entry per physical panel. This is the extension point for
running more than one device at once: a second entry with its own `screen`
template and its own width/height (e.g. swapped for a rotated/portrait
mount) works today without touching `server.py` or the widget modules.
Widget partials (`templates/widgets/*.html`) are corner-positioned rather
than laid out relative to a specific canvas size, so they're reusable across
device templates; only the top-level per-device template (`screen.html`
today) needs to be authored with that device's dimensions and orientation in
mind.

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
nix develop --command python3 scripts/render_screen.py
```

renders one frame to `out.png` without touching the live service.

## Dependencies

| Package | Used for |
|---|---|
| Flask | HTTP server, one route per device |
| Jinja2 | HTML templating for widgets |
| Playwright (Chromium) | renders the HTML/CSS layout to a PNG screenshot |
| caldav | talks to Radicale for calendar events |
| Pillow | in the dependency set; not currently used by the code |

## Secrets

`secrets.env` (gitignored) holds `RADICALE_USERNAME` / `RADICALE_PASSWORD`,
loaded by systemd's `EnvironmentFile=`. Copy `secrets.env.example` to get
started — it must live at `/var/lib/esp32-eink-server/secrets.env`, not
wherever the repo happens to be checked out.
