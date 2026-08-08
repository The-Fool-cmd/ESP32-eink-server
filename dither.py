from io import BytesIO

from PIL import Image

# Saturation (0-255, HSV) below which a pixel is treated as "meant to be
# neutral" rather than genuinely colored — see _snap_neutrals below.
_NEUTRAL_SAT_THRESHOLD = 40


def _snap_neutrals(img: Image.Image) -> Image.Image:
    """Force near-gray pixels to pure black/white before quantizing.

    Chromium's font antialiasing doesn't hand back clean grayscale blends —
    edge pixels carry a faint, genuine RGB tint (subpixel-style
    antialiasing), just a few units of saturation, invisible against a
    white/black backdrop. Fed straight into a 6-color nearest-match
    quantizer, those few units are enough for Floyd-Steinberg to decide
    "nearest palette entry" is red or yellow rather than black or white,
    speckling every letter and border with a faint rainbow fringe instead
    of the clean black/white stipple a 2-color quantize would produce. Only
    pixels below the saturation threshold get snapped — genuinely colored
    content (the widget accent fills) is untouched and still gets full
    Floyd-Steinberg dithering against all 6 colors.
    """
    _, s, _ = img.convert("HSV").split()
    neutral_mask = s.point(lambda p: 255 if p < _NEUTRAL_SAT_THRESHOLD else 0)
    bw = img.convert("L").point(lambda p: 255 if p >= 128 else 0).convert("RGB")
    return Image.composite(bw, img, neutral_mask)


def apply(png_bytes: bytes, palette: list[tuple[int, int, int]]) -> bytes:
    """Quantize a full-color PNG down to a fixed device palette using
    Floyd-Steinberg error diffusion, then re-encode as PNG.

    Chromium hands back full 24-bit RGB — anti-aliased text edges, smooth
    CSS gradients, none of which the panel can actually show. Without this,
    the device firmware would have to nearest-color-threshold every pixel
    itself with no error diffusion, which is what actually hurts text
    legibility (thin anti-aliased strokes either disappear or turn blocky)
    and makes flat CSS colors the only option. Doing it here means the PNG
    we send is already exactly what the panel will show, dithered the same
    way regardless of whatever the firmware's own PNG decoder does.
    """
    img = _snap_neutrals(Image.open(BytesIO(png_bytes)).convert("RGB"))

    # Pillow's quantize(palette=...) wants the target colors as another
    # image's palette, not a plain list — this is the standard idiom for
    # "quantize to this exact fixed set of colors" rather than letting
    # Pillow pick its own approximating palette.
    palette_img = Image.new("P", (1, 1))
    flat = [component for rgb in palette for component in rgb]
    flat += [0] * (768 - len(flat))  # putpalette always wants a full 256-entry table
    palette_img.putpalette(flat)

    dithered = img.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)

    out = BytesIO()
    dithered.convert("RGB").save(out, format="PNG")
    return out.getvalue()
