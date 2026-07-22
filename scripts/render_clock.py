#!/usr/bin/env python3
"""Minimal end-to-end check: render the clock widget to out.png."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render import render_screen
from widgets.clock import get_context


def main():
    ctx = get_context()
    png = render_screen("screen.html", ctx, width=800, height=480)
    out = Path(__file__).resolve().parent.parent / "out.png"
    out.write_bytes(png)
    print(f"wrote {out} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
