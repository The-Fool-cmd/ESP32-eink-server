"""Device registry: one entry per physical panel.

The device id is whatever the client asks for (`GET /image/<device_id>.png`);
each entry names the top-level template to render, the panel's pixel
dimensions, and the palette to dither down to.
"""

# Dither target palettes (see dither.py). A 1-bit panel is exact by
# definition. The SPECTRA6 values are the pure-saturated RGB triples the
# ESP32-eink-client firmware uses for its own native colors, so what this
# server quantizes to is byte-for-byte what the firmware expects.
_MONO = [(0, 0, 0), (255, 255, 255)]
_SPECTRA6 = [
    (0, 0, 0),  # black
    (255, 255, 255),  # white
    (255, 0, 0),  # red
    (255, 255, 0),  # yellow
    (0, 255, 0),  # green
    (0, 0, 255),  # blue
]

DEVICES = {
    # 7.5" mono panel, landscape: calendar + battery.
    "fool-nightstand": {
        "screen": "screen.html",
        "width": 800,
        "height": 480,
        "palette": _MONO,
    },
    # 7.3" SPECTRA6 panel, landscape: service status + battery.
    "fool-workdesk": {
        "screen": "screen_status.html",
        "width": 800,
        "height": 480,
        "palette": _SPECTRA6,
    },
    # Same 7.3" SPECTRA6 panel, portrait-mounted: weather + battery.
    "fool-entrance": {
        "screen": "screen_weather.html",
        "width": 480,
        "height": 800,
        "palette": _SPECTRA6,
    },
}
