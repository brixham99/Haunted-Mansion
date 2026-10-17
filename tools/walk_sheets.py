#!/usr/bin/env python3
"""Contact sheets and an animated GIF of the walk cycles, for review.

    python3 tools/walk_sheets.py [OUTDIR]     (default /workspace)

hm_walk_archie.png / hm_walk_holly.png: every frame of every facing (plus
the standing frame) on a mid-grey floor, each on its own small floor tile
with the contact shadow the game draws, feet marked when touching down.
hm_walk.gif: Archie and Holly walking round a square on a grey floor.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CH = os.path.join(HERE, "..", "assets", "characters")
FACINGS = ("se", "sw", "nw", "ne")
GREY = (128, 128, 128)


def load(name):
    meta = json.load(open(os.path.join(CH, f"{name}_walk.json")))
    fw, fh = meta["size"]
    out = {}
    for f in FACINGS:
        sheet = Image.open(os.path.join(CH, f"{name}_{f}_walk.png")).convert("RGBA")
        out[f] = dict(stand=Image.open(os.path.join(CH, f"{name}_{f}.png")).convert("RGBA"),
                      frames=[sheet.crop((i * fw, 0, (i + 1) * fw, fh)) for i in range(meta["frames"])])
    return meta, out


def contact_shadows(canvas, meta, facing, frame, x0, y0):
    """The same shadows as the game: one soft pool at the ground point and a
    small dark one under each foot, fading as the foot lifts."""
    fm = meta["facings"][facing]
    ax, ay = fm["anchor"]
    soft(canvas, x0 + ax, y0 + ay, 30, 12, 70)
    feet = fm["feet"][frame] if frame is not None else fm["rest"]
    for leg in ("far", "near"):
        f = feet[leg]
        lift = f["lift"]
        k = max(0.0, 1 - lift / 9)
        if k <= 0.05:
            continue
        soft(canvas, x0 + f["x"], y0 + f["y"] + lift - 1, 11 * (0.65 + 0.35 * k), 4.5 * (0.65 + 0.35 * k), 150 * k)


def soft(img, cx, cy, rw, rh, alpha):
    """Soft-edged ellipse, the same falloff as art.soft_shadow."""
    import numpy as np
    w, h = int(rw) * 2 + 2, int(rh) * 2 + 2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx + 0.5 - w / 2) / max(1, int(rw))) ** 2 + ((yy + 0.5 - h / 2) / max(1, int(rh))) ** 2)
    a = np.clip((1.0 - d) / 0.45, 0, 1)
    a = (a * a * (3 - 2 * a) * int(alpha)).astype(np.uint8)
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh.putalpha(Image.fromarray(a))
    img.alpha_composite(sh, (int(round(cx - w / 2)), int(round(cy - h / 2))))


def sheet(name, out):
    meta, imgs = load(name)
    fw, fh = meta["size"]
    n = meta["frames"] + 1
    lab = 70
    cw, chh = fw + 10, fh + 24
    S = Image.new("RGBA", (lab + n * cw, 30 + len(FACINGS) * chh), GREY + (255,))
    d = ImageDraw.Draw(S)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    d.text((8, 6), f"{name.title()} walk cycle: standing frame, then {meta['frames']} frames. "
                   f"Dots = foot touching the ground. One cycle = {meta['cycle_tiles']:.2f} tiles.",
           fill=(20, 20, 20), font=font)
    for r, f in enumerate(FACINGS):
        y0 = 30 + r * chh
        d.text((8, y0 + fh // 2), f.upper(), fill=(20, 20, 20), font=font)
        for c in range(n):
            x0 = lab + c * cw
            frame = None if c == 0 else c - 1
            contact_shadows(S, meta, f, frame, x0, y0)
            img = imgs[f]["stand"] if frame is None else imgs[f]["frames"][frame]
            S.alpha_composite(img, (x0, y0))
            d = ImageDraw.Draw(S)
            lbl = "stand" if frame is None else str(frame)
            d.text((x0 + 4, y0 + fh + 4), lbl, fill=(30, 30, 30), font=font)
            if frame is not None:
                for leg, col in (("near", (255, 230, 40)), ("far", (40, 200, 255))):
                    ft = meta["facings"][f]["feet"][frame][leg]
                    if ft["down"]:
                        d.ellipse((x0 + ft["x"] - 3, y0 + ft["y"] - 3, x0 + ft["x"] + 3, y0 + ft["y"] + 3),
                                  fill=col, outline=(0, 0, 0))
    S.convert("RGB").save(os.path.join(out, f"hm_walk_{name}.png"))


def gif(out):
    """Both characters walk a diamond on an isometric grey floor; the
    animation advances with distance walked, exactly as in the game."""
    W, H = 760, 520
    HW, HH = 56, 28
    ox, oy = W // 2, 130
    def P(x, y):
        return ox + (x - y) * HW, oy + (x + y) * HH
    floor = Image.new("RGBA", (W, H), (60, 60, 64, 255))
    d = ImageDraw.Draw(floor)
    for i in range(6):
        for j in range(6):
            col = (128, 128, 128) if (i + j) % 2 == 0 else (120, 120, 120)
            d.polygon([P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)], fill=col)
    chars = {n: load(n) for n in ("archie", "holly")}
    # square path: E along y=1, S along x=5, W along y=5, N along x=1
    legs = [((1.0, 1.0), (5.0, 1.0), "se"), ((5.0, 1.0), (5.0, 5.0), "sw"),
            ((5.0, 5.0), (1.0, 5.0), "nw"), ((1.0, 5.0), (1.0, 1.0), "ne")]
    per = 4.0
    speed = 3.0
    fps = 25
    total = 4 * per / speed
    frames = []
    for k in range(int(total * fps)):
        t = k / fps
        img = floor.copy()
        items = []
        for idx, (name, (meta, imgs)) in enumerate(chars.items()):
            dist = (t * speed + idx * 8.0) % (4 * per)
            seg = int(dist // per)
            (x0, y0), (x1, y1), facing = legs[seg]
            u = (dist - seg * per) / per
            x, y = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            ph = (0.2 + t * speed / meta["cycle_tiles"]) % 1.0   # by distance, as in the game
            fr = int(ph * meta["frames"]) % meta["frames"]
            # root motion, as in the game: draw where the frame was posed
            back = (ph * meta["frames"] - int(ph * meta["frames"])) * meta["cycle_tiles"] / meta["frames"]
            ux, uy = (x1 - x0) / per, (y1 - y0) / per
            x, y = x - back * ux, y - back * uy
            items.append((x + y, name, meta, imgs, facing, fr, x, y))
        for _, name, meta, imgs, facing, fr, x, y in sorted(items):
            sx, sy = P(x, y)
            ax, ay = meta["facings"][facing]["anchor"]
            x0, y0 = round(sx - ax), round(sy - ay)
            contact_shadows(img, meta, facing, fr, x0, y0)
            img.alpha_composite(imgs[facing]["frames"][fr], (x0, y0))
        frames.append(img.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT, dither=Image.NONE))
    frames[0].save(os.path.join(out, "hm_walk.gif"), save_all=True, append_images=frames[1:],
                   duration=int(1000 / fps), loop=0, optimize=False)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
    for n in ("archie", "holly"):
        sheet(n, out)
    gif(out)
    print("sheets and gif ->", out)
