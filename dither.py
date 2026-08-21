from io import BytesIO

from PIL import Image

# Saturation (0-255, HSV) below which a pixel is treated as "meant to be
# neutral" rather than genuinely colored — see _snap_neutrals below.
_NEUTRAL_SAT_THRESHOLD = 40


def _snap_neutrals(img: Image.Image) -> Image.Image:
    """Force near-gray pixels to pure black/white before quantizing.

    Chromium's font antialiasing doesn't hand back clean grayscale blends —
    edge pixels carry a faint RGB tint, just a few units of saturation and
    invisible against a white or black backdrop. Fed into a 6-color
    nearest-match quantizer, those few units are enough for Floyd-Steinberg
    to pick red or yellow over black or white, speckling every letter and
    border with a rainbow fringe. Only pixels below the saturation threshold
    get snapped; genuinely colored content still gets full dithering against
    the whole palette.
    """
    _, s, _ = img.convert("HSV").split()
    neutral_mask = s.point(lambda p: 255 if p < _NEUTRAL_SAT_THRESHOLD else 0)
    bw = img.convert("L").point(lambda p: 255 if p >= 128 else 0).convert("RGB")
    return Image.composite(bw, img, neutral_mask)


def apply(png_bytes: bytes, palette: list[tuple[int, int, int]]) -> bytes:
    """Quantize a full-color PNG down to a fixed device palette using
    Floyd-Steinberg error diffusion, then re-encode as PNG.

    Chromium hands back 24-bit RGB — anti-aliased text edges, smooth CSS
    gradients, none of which the panel can show. Dithering here rather than
    leaving it to the firmware means the PNG on the wire is already exactly
    what the panel will display, and thin anti-aliased strokes survive as a
    stipple instead of being thresholded away.
    """
    img = _snap_neutrals(Image.open(BytesIO(png_bytes)).convert("RGB"))

    # Pillow's quantize(palette=...) wants the target colors as another
    # image's palette rather than a plain list — this is the idiom for
    # quantizing to an exact fixed set of colors instead of letting Pillow
    # pick its own approximating palette.
    palette_img = Image.new("P", (1, 1))
    flat = [component for rgb in palette for component in rgb]
    flat += [0] * (768 - len(flat))  # putpalette always wants a full 256-entry table
    palette_img.putpalette(flat)

    dithered = img.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)

    out = BytesIO()
    dithered.convert("RGB").save(out, format="PNG")
    return out.getvalue()
