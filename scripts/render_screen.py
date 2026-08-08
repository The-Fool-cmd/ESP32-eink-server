#!/usr/bin/env python3
"""Minimal end-to-end check: render a device's widgets to out.png.

Usage: render_screen.py [device_id]   (defaults to fool-nightstand)
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devices import DEVICES
from render import render_screen
from widgets import battery, calendar, uptime


def main():
    device_id = sys.argv[1] if len(sys.argv) > 1 else "fool-nightstand"
    device = DEVICES[device_id]

    ctx = battery.get_context(87)
    ctx.update(calendar.get_context())
    ctx.update(uptime.get_context())
    ctx.update(updated_at=datetime.now().strftime("%a %H:%M"))
    ctx.update(width=device["width"], height=device["height"])

    png = render_screen(
        device["screen"], ctx, width=device["width"], height=device["height"], palette=device.get("palette")
    )
    out = Path(__file__).resolve().parent.parent / "out.png"
    out.write_bytes(png)
    print(f"wrote {out} ({len(png)} bytes) for {device_id} ({device['screen']})")


if __name__ == "__main__":
    main()
