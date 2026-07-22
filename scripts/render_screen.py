#!/usr/bin/env python3
"""Minimal end-to-end check: render the calendar + battery widgets to out.png."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render import render_screen
from widgets import battery, calendar


def main():
    width, height = 800, 480
    ctx = battery.get_context(87)
    ctx.update(calendar.get_context())
    ctx.update(width=width, height=height)
    png = render_screen("screen.html", ctx, width=width, height=height)
    out = Path(__file__).resolve().parent.parent / "out.png"
    out.write_bytes(png)
    print(f"wrote {out} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
