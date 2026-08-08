# Per-device dither target palettes (see dither.py). Pure black/white is
# exact — there's no calibration question for a 1-bit panel. The SPECTRA6
# values are the exact pure-saturated RGB triples the ESP32-eink-client
# firmware's own native Color(r,g,b,w) constants use (see that repo's
# test.yaml forced-write test) — not a "measured, close-enough" approximation
# of the physical ink like an earlier version of this file used. Matching the
# firmware's own values byte-for-byte, rather than something merely close,
# rules out any mismatch between what we quantize to here and whatever
# color-matching the firmware does on the other end. If color still doesn't
# reproduce on the panel with these exact values, the bug is downstream of
# this palette (refresh mode, or the PNG decode/color-mapping path) — see
# the "Dithering" section in README.md for the live debugging thread.
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
    "fool-nightstand": {
        "screen": "screen.html",
        "width": 800,
        "height": 480,
        "palette": _MONO,
    },
    "fool-workdesk": {
        "screen": "screen_status.html",
        "width": 800,
        "height": 480,
        "palette": _SPECTRA6,
    },
}
