#!/usr/bin/env python3
import atexit

from flask import Flask, Response

from render import Renderer
from widgets.clock import get_context

PANEL_WIDTH = 800
PANEL_HEIGHT = 480

app = Flask(__name__)
renderer = Renderer()
atexit.register(renderer.close)


@app.route("/image.png")
def image():
    ctx = get_context()
    png = renderer.render("screen.html", ctx, PANEL_WIDTH, PANEL_HEIGHT)
    return Response(png, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
