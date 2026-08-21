#!/usr/bin/env python3
import atexit
from datetime import datetime

from flask import Flask, Response, abort, request

from devices import DEVICES
from render import Renderer
from widgets import battery, calendar, uptime, weather

app = Flask(__name__)
renderer = Renderer()
atexit.register(renderer.close)


@app.route("/image/<device_id>.png")
def image(device_id):
    device = DEVICES.get(device_id)
    if device is None:
        abort(404)

    ctx = battery.get_context(request.args.get("battery", type=int))
    ctx.update(calendar.get_context())
    ctx.update(uptime.get_context())
    ctx.update(weather.get_context())
    ctx.update(updated_at=datetime.now().strftime("%a %H:%M"))
    ctx.update(width=device["width"], height=device["height"])

    png = renderer.render(device["screen"], ctx, device["width"], device["height"], device.get("palette"))
    return Response(png, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
