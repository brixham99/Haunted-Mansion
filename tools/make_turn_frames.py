#!/usr/bin/env python3
"""In-between turn views for Archie and Holly (shown only mid-turn, never
for walking). Cuts the supplied pictures out of their backgrounds and scales
them to match the 160 px in-game figures exactly.

    python3 tools/make_turn_frames.py                 # every source found, both characters
    python3 tools/make_turn_frames.py holly           # one character
    python3 tools/make_turn_frames.py archie --src pic.jpg --view s   # one picture from anywhere
    python3 tools/make_turn_frames.py --sheet /workspace/turn_check.png   # also a review sheet

Sources (tools/art/), one per view, full body, standing still:
    <name>_turn_s_source.png   facing the camera (front, straight on)
    <name>_turn_w_source.png   facing screen left (left-hand profile)
    <name>_turn_e_source.png   facing screen right (right-hand profile)
    <name>_turn_n_source.png   facing away from the camera (back view)
(.jpg/.jpeg/.webp also accepted.) A transparent background is used as it is;
otherwise the background colour is taken from the picture's border, removed
by flood fill from the edges (plus enclosed pockets of the same colour, such
as gaps between the arms and body) with a soft edge, and edge pixels mixed
with the backdrop colour are unmixed so there is no pale halo.

Scaling: the figure (pixels at least 16% opaque, as measured on the game
sprites) is scaled to exactly the height of the standing sprites (160 px),
with the same premultiplied Lanczos + light unsharp mask as make_walk.py,
and placed on the standing-frame canvas with its feet on the same ground
line as the two diagonal facings either side of it. The ground point (the
middle of the feet, from the bottom rows of the figure) becomes the view's
anchor in assets/characters/<name>_turn.json.

Output: assets/characters/<name>_<view>.png (+ <name>_turn.json). The game
uses each one automatically (game.player_pose, art.TURN_BETWEEN):
    se <-> sw : s (front)      sw <-> nw : w (screen left)
    nw <-> ne : n (back)       ne <-> se : e (screen right)
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_sprites import defringe  # noqa: E402

ART = os.path.join(HERE, "art")
CHAR_DIR = os.path.join(HERE, "..", "assets", "characters")
VIEWS = ("s", "w", "e", "n")
# The two diagonal sprites each view sits between (screen orientation).
NEIGHBOURS = {"s": ("se", "sw"), "w": ("sw", "nw"), "n": ("nw", "ne"), "e": ("ne", "se")}
SOLID = 40            # alpha counted as "figure" when measuring (same as the sprite audit)
TOL_HARD, TOL_SOFT = 18.0, 60.0   # colour distance from the background: gone / kept
POCKETS = True                    # also clear enclosed backdrop-coloured gaps (--no-pockets turns off)
TOL_RIM = 120.0                   # ... and kept, for the antialiased rim beside the cut


def find_source(name, view):
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = os.path.join(ART, f"{name}_turn_{view}_source.{ext}")
        if os.path.exists(p):
            return p
    return None


def cut_background(img):
    """RGBA with the background removed (soft edge), unless already transparent."""
    img = img.convert("RGBA")
    a = np.asarray(img).astype(np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    if (border[:, 3] < 250).mean() > 0.5:          # transparent already: keep it
        return defringe(img, white_bg=False), None
    bg = np.median(border[:, :3], axis=0)
    dist = np.sqrt(((a[..., :3] - bg) ** 2).sum(axis=2))
    # flood fill from the border through background-coloured pixels
    near = (dist < TOL_SOFT).astype(np.uint8) * 255
    mask_img = Image.fromarray(near, "L")
    h, w = near.shape
    seeds = [(x, 0) for x in range(0, w, 6)] + [(x, h - 1) for x in range(0, w, 6)] + \
            [(0, y) for y in range(0, h, 6)] + [(w - 1, y) for y in range(0, h, 6)]
    for sx, sy in seeds:
        if mask_img.getpixel((sx, sy)) == 255:
            ImageDraw.floodfill(mask_img, (sx, sy), 128)
    outside = np.asarray(mask_img) == 128
    # enclosed pockets that are almost exactly the background colour
    # (only sizeable ones: an opening of about 4 px of the final figure keeps
    # small white details such as dress patterns and highlights)
    pocket = (dist < TOL_HARD * 0.7) & ~outside if POCKETS else np.zeros_like(outside)
    if pocket.any():
        n = max(3, int(round(h / 40)) | 1)
        pm = Image.fromarray((pocket * 255).astype(np.uint8), "L")
        pm = pm.filter(ImageFilter.MinFilter(n)).filter(ImageFilter.MaxFilter(n))
        pocket = (np.asarray(pm) > 0) & pocket
    region = outside | pocket
    alpha = np.clip((dist - TOL_HARD) / (TOL_SOFT - TOL_HARD), 0, 1)
    alpha = np.where(region, alpha, 1.0)
    # the antialiased rim just inside the cut is still part backdrop: a wider
    # soft range there (about 2 px of the final 160 px figure), so no pale rim
    r = max(1, int(round(h / 160)))
    band = np.asarray(Image.fromarray((region * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(2 * r + 1))) > 0
    rim = np.clip((dist - TOL_HARD) / (TOL_RIM - TOL_HARD), 0, 1)
    alpha = np.where(band & ~region, np.minimum(alpha, rim), alpha)
    alpha = np.where(dist < TOL_HARD, np.where(region, 0.0, 1.0), alpha)
    out = a.copy()
    # unmix soft edge pixels from the actual backdrop colour: C = a*F + (1-a)*bg  ->  F
    part = (alpha > 0.02) & (alpha < 0.98)
    am = np.maximum(alpha, 0.02)[..., None]
    fixed = np.clip((a[..., :3] - (1 - alpha[..., None]) * bg) / am, 0, 255)
    out[..., :3] = np.where(part[..., None], fixed, a[..., :3])
    out[..., 3] = alpha * 255
    return defringe(Image.fromarray((out + 0.5).astype(np.uint8), "RGBA"), white_bg=False), tuple(int(v) for v in bg)


def solid_box(img):
    return img.split()[3].point(lambda v: 255 if v > SOLID else 0).getbbox()


def foot_x(img, rows=6):
    """x of the middle of the feet: opaque pixels in the bottom rows."""
    a = np.asarray(img.split()[3])
    ys = np.nonzero((a > 128).any(axis=1))[0]
    band = a[max(0, ys[-1] - rows + 1):ys[-1] + 1] > 128
    xs = np.nonzero(band.any(axis=0))[0]
    return (xs.min() + xs.max() + 1) / 2.0


def downscale(img, height, sharpen=60):
    w = max(1, round(img.width * height / img.height))
    small = img.convert("RGBa").resize((w, height), Image.LANCZOS, reducing_gap=3.0).convert("RGBA")
    if sharpen:
        rgb = small.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.0, percent=sharpen, threshold=1))
        small = Image.merge("RGBA", (*rgb.split(), small.split()[3]))
    return small


def build_view(name, view, src_path, out_dir):
    with open(os.path.join(CHAR_DIR, f"{name}_walk.json")) as f:
        meta = json.load(f)
    fw, fh = meta["size"]
    # Target: the neighbouring standing sprites' figure height, ground line and anchor
    boxes, anchors = [], []
    for k in NEIGHBOURS[view]:
        boxes.append(solid_box(Image.open(os.path.join(CHAR_DIR, f"{name}_{k}.png"))))
        anchors.append(meta["facings"][k]["anchor"])
    fig_h = round(sum(b[3] - b[1] for b in boxes) / len(boxes))
    bottom = round(sum(b[3] for b in boxes) / len(boxes))
    anchor = [round(sum(a[0] for a in anchors) / 2, 2), round(sum(a[1] for a in anchors) / 2, 2)]

    cut, bg = cut_background(Image.open(src_path))
    box = solid_box(cut)
    if box is None:
        raise SystemExit(f"{src_path}: nothing left after removing the background")
    fig = cut.crop(box)
    # scale so the solid figure is exactly fig_h tall (pad 2 source px so soft edges survive)
    k = fig_h / fig.height
    pad = int(round(3 / k))
    padded = Image.new("RGBA", (fig.width + 2 * pad, fig.height + 2 * pad), (0, 0, 0, 0))
    padded.paste(fig, (pad, pad))
    small = downscale(padded, max(1, round(padded.height * k)))
    sb = solid_box(small)
    # nudge to the exact height if rounding left it a pixel out
    if sb[3] - sb[1] != fig_h:
        small = downscale(padded, max(1, round(padded.height * k * fig_h / (sb[3] - sb[1]))))
        sb = solid_box(small)
    fx = foot_x(small)
    canvas = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    ox = round(anchor[0] - fx)
    oy = bottom - sb[3]
    canvas.alpha_composite(small, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy)))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{name}_{view}.png")
    canvas.save(out)
    got = solid_box(canvas)
    print(f"{name}_{view}: {os.path.basename(src_path)} {Image.open(src_path).size} "
          f"bg {bg or 'transparent'} -> figure {got[3] - got[1]} px tall (target {fig_h}), "
          f"feet at y {got[3]} (target {bottom}), anchor {anchor}{'' if got[2] - got[0] < fw - 4 else '  WARNING: wider than the canvas'}")
    return out, anchor


def write_json(name, out_dir, done):
    path = os.path.join(out_dir, f"{name}_turn.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = {"views": {}}
    data["note"] = ("In-between views shown only mid-turn (tools/make_turn_frames.py): s front, w screen left, "
                    "e screen right, n away; anchor = ground point on the standing-frame canvas.")
    for view, anchor in done.items():
        data["views"][view] = {"anchor": anchor}
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def review(out_dir, path):
    """Standing diagonals and in-between views in turn order, on a grey floor."""
    rows = []
    for name in ("archie", "holly"):
        order = ["se", "s", "sw", "w", "nw", "n", "ne", "e", "se"]
        cells = []
        for k in order:
            p = os.path.join(out_dir if len(k) == 1 else CHAR_DIR, f"{name}_{k}.png")
            cells.append(Image.open(p) if os.path.exists(p) else None)
        w, h = max(c.width for c in cells if c), max(c.height for c in cells if c)
        row = Image.new("RGBA", (w * len(cells), h), (60, 52, 56, 255))
        for i, c in enumerate(cells):
            if c:
                row.alpha_composite(c, (i * w, 0))
        rows.append(row)
    sheet = Image.new("RGBA", (max(r.width for r in rows), sum(r.height for r in rows)), (60, 52, 56, 255))
    y = 0
    for r in rows:
        sheet.alpha_composite(r, (0, y))
        y += r.height
    ImageDraw.Draw(sheet).line([(0, 167), (sheet.width, 167)], fill=(120, 110, 110, 255))
    sheet.save(path)
    print("review sheet:", path)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("names", nargs="*", default=["archie", "holly"])
    ap.add_argument("--src", help="one source picture (with --view and a single name)")
    ap.add_argument("--view", choices=VIEWS)
    ap.add_argument("--out", default=CHAR_DIR, help="output folder (default assets/characters)")
    ap.add_argument("--sheet", help="also save a review sheet here")
    ap.add_argument("--no-pockets", action="store_true",
                    help="keep enclosed backdrop-coloured areas (for very pale clothes)")
    args = ap.parse_args(argv)
    global POCKETS
    POCKETS = not args.no_pockets
    for name in args.names:
        done = {}
        if args.src:
            if not args.view or len(args.names) != 1:
                ap.error("--src needs --view and exactly one name")
            done[args.view] = build_view(name, args.view, args.src, args.out)[1]
        else:
            for view in VIEWS:
                src = find_source(name, view)
                if src:
                    done[view] = build_view(name, view, src, args.out)[1]
        if done:
            write_json(name, args.out, done)
        else:
            print(f"{name}: no tools/art/{name}_turn_<s|w|e|n>_source.* pictures yet; the game squashes the turn instead")
    if args.sheet:
        review(args.out, args.sheet)


if __name__ == "__main__":
    main(sys.argv[1:])
