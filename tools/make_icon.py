"""Generate RoDraw's two black-and-white marks.

    rodraw.ico  -- the application icon: a brush whose tip is loaded with
                   black ink. Used for the exe, the installer, the tray and
                   the window icon.
    logo.ico    -- the house mark: a minimal portrait, built from the
                   reference photo and reduced to what still reads at 16 px
                   (short hair, full beard, heavy brows, glasses on the face).
                   Shown on the About tab.

Both share one technique. The tile is black and the figure is white, so any
black detail that reaches the figure's outline would merge into the
background and destroy the silhouette -- a black beard against a black tile
simply eats the head. Painting a thin white rim back over the outline keeps
the shape readable and reads as a lit edge.

Shapes are composed as masks rather than drawn strokes, so the beard can be an
exact intersection of head and crescent instead of a hand-placed outline that
drifts at small sizes.

Every size is rendered at 4x and downsampled, rather than scaling one large
drawing, so the taskbar versions keep clean edges.

    python tools/make_icon.py [--preview]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
SS = 4                      # supersampling factor

BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)


# -- mask algebra (masks are L-mode, 0 or 255) ---------------------------
def _and(a, b):
    return ImageChops.multiply(a, b)


def _or(a, b):
    return ImageChops.lighter(a, b)


def _not(a):
    return ImageChops.invert(a)


def _sub(a, b):
    return _and(a, _not(b))


def _compose(s: int, tile, lit) -> Image.Image:
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (s, s), BLACK), (0, 0), tile)
    img.paste(Image.new("RGBA", (s, s), WHITE), (0, 0), lit)
    return img


# ======================================================== the app icon

def draw_brush(size: int) -> Image.Image:
    """A white brush, tip dipped in black ink.

    Drawn upright and then rotated as one piece, so the boolean algebra stays
    on hard-edged masks and only the final result is resampled.
    """
    s = size * SS

    def mask():
        img = Image.new("L", (s, s), 0)
        return img, ImageDraw.Draw(img)

    def px(v: float) -> float:
        return v * s

    tile, td = mask()
    td.rounded_rectangle([0, 0, s - 1, s - 1], radius=px(0.21), fill=255)

    # --- brush, built vertically -----------------------------------------
    body, bd = mask()
    # handle
    bd.rounded_rectangle([px(0.448), px(0.085), px(0.552), px(0.545)],
                         radius=px(0.050), fill=255)
    # ferrule, a little wider than the handle
    bd.rounded_rectangle([px(0.421), px(0.478), px(0.579), px(0.612)],
                         radius=px(0.022), fill=255)
    # bristles: shoulders, then a taper to the point
    bd.polygon([(px(0.425), px(0.596)), (px(0.575), px(0.596)),
                (px(0.552), px(0.796)), (px(0.500), px(0.930)),
                (px(0.448), px(0.796))], fill=255)

    # --- the ink on the tip ----------------------------------------------
    ink_area, ind = mask()
    ind.rectangle([0, px(0.706), s, s], fill=255)
    ink = _and(body, ink_area)

    # --- keep the outline white so the ink does not merge with the tile ---
    rim = _sub(body, body.filter(ImageFilter.MinFilter(_odd(px(0.030)))))

    lit_brush = _or(_sub(body, ink), rim)
    # Tip to the lower left, handle to the upper right.
    lit_brush = lit_brush.rotate(-34, resample=Image.BICUBIC, center=(s / 2, s / 2))

    return _compose(s, tile, _and(lit_brush, tile)).resize((size, size), Image.LANCZOS)


def _odd(v: float) -> int:
    """MinFilter needs an odd kernel size of at least 3."""
    n = max(3, int(round(v)))
    return n if n % 2 else n + 1


# ===================================================== the company logo

def draw_portrait(size: int) -> Image.Image:
    """Minimal bearded portrait, glasses worn on the face."""
    s = size * SS

    def mask():
        img = Image.new("L", (s, s), 0)
        return img, ImageDraw.Draw(img)

    def px(v: float) -> float:
        return v * s

    tile, td = mask()
    td.rounded_rectangle([0, 0, s - 1, s - 1], radius=px(0.21), fill=255)

    # --- bust and neck ----------------------------------------------------
    bust, bd = mask()
    bd.rounded_rectangle([px(0.150), px(0.790), px(0.850), px(1.16)],
                         radius=px(0.20), fill=255)
    bd.rectangle([px(0.424), px(0.640), px(0.576), px(0.840)], fill=255)

    # --- head -------------------------------------------------------------
    head, hd = mask()
    hcx, hcy = px(0.500), px(0.430)
    hrx, hry = px(0.192), px(0.252)
    hd.ellipse([hcx - hrx, hcy - hry, hcx + hrx, hcy + hry], fill=255)

    # --- beard: head minus a raised inner face ----------------------------
    # The leftover crescent is exactly the jaw, chin and sideburns. The beard
    # starts below the glasses: run the sideburns any higher and the black
    # cheeks close in on the lenses until the face is a narrow strip.
    inner, idr = mask()
    idr.ellipse([hcx - px(0.130), hcy - px(0.236),
                 hcx + px(0.130), px(0.575)], fill=255)
    below, bl = mask()
    bl.rectangle([0, px(0.480), s, s], fill=255)      # sideburns start here
    beard = _and(_and(head, _not(inner)), below)

    # No hair mass on top: it is light in the photo, and a black cap plus a
    # black beard would leave the head almost entirely dark against the tile.

    # --- moustache --------------------------------------------------------
    moustache, md = mask()
    # Leaves only a slit above the chin beard -- a wider gap reads as a grin.
    md.rounded_rectangle([hcx - px(0.094), px(0.506), hcx + px(0.094), px(0.556)],
                         radius=px(0.019), fill=255)
    moustache = _and(moustache, head)

    # --- eyebrows ---------------------------------------------------------
    brows, ed = mask()
    for cx in (hcx - px(0.078), hcx + px(0.078)):
        ed.rounded_rectangle([cx - px(0.055), px(0.358), cx + px(0.055), px(0.385)],
                             radius=px(0.013), fill=255)

    # --- glasses, worn on the face ----------------------------------------
    # Solid frames with a white lens opening. An outline-only frame would be
    # well under a pixel wide by 32 px and vanish; this keeps the shape.
    gy = px(0.440)
    glasses, gd = mask()
    for cx in (hcx - px(0.078), hcx + px(0.078)):
        gd.ellipse([cx - px(0.070), gy - px(0.055), cx + px(0.070), gy + px(0.055)],
                   fill=255)
    gd.rectangle([hcx - px(0.026), gy - px(0.012), hcx + px(0.026), gy + px(0.012)],
                 fill=255)
    # temple arms, running back to the side of the head
    for sign in (-1, 1):
        x0 = hcx + sign * px(0.138)
        x1 = hcx + sign * px(0.196)
        gd.polygon([(x0, gy - px(0.030)), (x1, gy - px(0.052)),
                    (x1, gy - px(0.024)), (x0, gy - px(0.002))], fill=255)
    glasses = _and(glasses, head)

    # the lens openings, which stay white
    lenses, ld = mask()
    for cx in (hcx - px(0.078), hcx + px(0.078)):
        ld.ellipse([cx - px(0.046), gy - px(0.034), cx + px(0.046), gy + px(0.034)],
                   fill=255)

    # eyes behind the lenses
    pupils, pd = mask()
    for cx in (hcx - px(0.078), hcx + px(0.078)):
        pd.ellipse([cx - px(0.016), gy - px(0.014), cx + px(0.016), gy + px(0.014)],
                   fill=255)

    # --- compose ----------------------------------------------------------
    rim_inner, rd = mask()
    rd.ellipse([hcx - hrx + px(0.019), hcy - hry + px(0.021),
                hcx + hrx - px(0.019), hcy + hry - px(0.021)], fill=255)
    rim = _sub(head, rim_inner)

    lit = _and(_or(bust, head), tile)
    details = _or(_or(_or(beard, moustache), brows), glasses)
    lit = _sub(lit, details)
    lit = _or(lit, _and(lenses, tile))        # clear lenses, not sunglasses
    lit = _sub(lit, pupils)
    lit = _or(lit, _and(rim, tile))

    return _compose(s, tile, lit).resize((size, size), Image.LANCZOS)


# ================================================================ build

MARKS = {
    "rodraw": draw_brush,
    "logo": draw_portrait,
}


def build_ico(draw, out_path: Path) -> list[Image.Image]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw(n) for n in ICO_SIZES]
    frames[-1].save(out_path, format="ICO", sizes=[(n, n) for n in ICO_SIZES])
    frames[-1].save(out_path.with_suffix(".png"))
    print(f"wrote {out_path}  and  {out_path.with_suffix('.png').name}")
    return frames


def preview_sheet(path: Path) -> None:
    pad, cell, gap = 14, 256, 26
    width = pad * 2 + cell * 2 + gap
    sheet = Image.new("RGBA", (width, cell + pad * 2 + 92), (40, 44, 50, 255))
    for col, draw in enumerate((draw_brush, draw_portrait)):
        x = pad + col * (cell + gap)
        big = draw(256)
        sheet.paste(big, (x, pad), big)
        sx, y = x, pad + cell + 16
        for n in (16, 24, 32, 48, 64):
            frame = draw(n)
            sheet.paste(frame, (sx, y + (64 - n)), frame)
            sx += n + 13
    sheet.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true",
                        help="also write a sheet showing the small sizes")
    args = parser.parse_args()

    res = Path(__file__).resolve().parents[1] / "rodraw" / "resources"
    for name, draw in MARKS.items():
        build_ico(draw, res / f"{name}.ico")
    if args.preview:
        preview_sheet(res / "icon_preview.png")
