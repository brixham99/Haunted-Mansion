#!/usr/bin/env python3
"""Cut the painted art sheets (tools/art/sheets/*.jpg, white background)
into one PNG per sprite in assets/art/, which art.py loads in place of the
placeholders.

    python3 tools/cut_sheets.py [--sheet DIR] [--only a,b]   # --sheet: also writes a contact sheet; --only: just these sprites

- Background: near-white pixels flood-filled from the border (not a global
  white key), so white and pale things keep their whites: the ghost, lace,
  marble, the cot, the cream linen press, the tablecloth. Enclosed pockets
  count as background only when they are small-ish flat pure white (gaps
  between cot bars, holes in the cobweb, under a table).
- Items: connected blobs on the white, grouped into the sheet's items, read
  in rows top to bottom and left to right (SHEETS.md gives the order). A
  None in LAYOUT is an old version that a later sheet replaces: it is still
  found (so the rest of the sheet splits right) but not saved. furn1.jpg and
  the front-on pieces of furn2/3/4/7 were replaced by the corner views in
  furn1_iso.jpg and furn8_iso.jpg, and those in turn by exact-2:1 pieces built
  by tools/iso_box.py (fireplace, dresser, chest of drawers, bookcase,
  wardrobe, piano, clock, linen press, desk, toy box) and the corner views in
  organic_iso.jpg (armchair, chair, harp, rocking horse); the boiler and pumpkin by furn9_iso.jpg
  and pumpkin_iso.jpg (the pumpkin on the left of furn9_iso is not used).
- Edges: soft alpha from the distance to white, with the white unmixed from
  the edge colour (no white halo); specks are dropped.
- Facing: the manifest wants furniture fronts towards the viewer's lower
  right; items painted the other way are mirrored (MIRROR below). Wall items
  are flat front views and are left as they are.
- Pale grey painted ground shadows under furniture become translucent black
  (fix_ground_shadow), so they darken the floor instead of lighting it.
- Rugs are warped (perspective) so their four corners sit exactly on the
  footprint diamond, so they lie flat and fill their tiles.
- A light harmonise (HARMONISE) brings the painted colours a little closer to
  Archie and Holly.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SHEETS = os.path.join(HERE, "art", "sheets")
OUT = os.path.join(ROOT, "assets", "art")
sys.path.insert(0, ROOT)

LAYOUT = {
    "enemies.jpg": [["ghost", "goblin", "bat"], ["spider", "skeleton", "monster"]],
    # furn1.jpg (front-on) is no longer used: all six are in furn1_iso.jpg
    # furn1_iso.jpg: all six are now built by tools/iso_box.py (exact 2:1) from faces1/2.jpg
    "furn1_iso.jpg": [[None, None, None], [None, None, None]],
    "furn2.jpg": [[None, None, "wine_rack"], ["barrel", "coffin", None]],          # piano, desk, toy_box: iso_box.py
    "furn3.jpg": [["trunk", "suit_of_armour", None], ["bed", "coal_heap", "cauldron"]],   # linen_press: furn8_iso
    "furn4.jpg": [[None, None, "chest"], ["crate", None, "dining_table"]],                # chair, armchair, rocking_horse: furn8_iso
    "furn5.jpg": [["round_table", "kitchen_table", "sofa"], ["billiard_table", "range_cooker", "sink"]],
    "furn6.jpg": [[None, "water_tank", "tomb"], ["mangle", "washtub", "bath"]],           # boiler: furn9_iso
    "furn7.jpg": [["washstand", "cot", "potted_palm", "statue"], ["candelabra", None, "dummy", None]],  # harp: furn8_iso; pumpkin: pumpkin_iso
    # furn8_iso.jpg: piano and linen_press are built by iso_box.py; chair, armchair,
    # rocking_horse and harp come from organic_iso.jpg (true corner views)
    "furn8_iso.jpg": [[None, None, None], [None, None, None]],
    "organic_iso.jpg": [["armchair", "chair", "harp", "rocking_horse"]],
    # rear corner views, both facing the viewer's upper RIGHT (north): the
    # backrest is on the near (lower-left) edge of the seat, the seat runs
    # away to the upper right. See make_views() for the four facings.
    "chairs_back_iso.jpg": [["chair_ne", "armchair_ne"]],
    "furn9_iso.jpg": [[None, "boiler"]],          # the front-on pumpkin on the left is not used
    "pumpkin_iso.jpg": [["pumpkin"]],
    "wall.jpg": [["painting", "painting_lady", "painting_landscape", "mirror", "window", "cobweb"],
                 ["key", "sewing_machine"]],
    "links.jpg": [["front_door", "door_frame", "stairs_up", "stairs_down", "ladder_up", "trapdoor"],
                  ["rug", "rug_lifted"]],
}

# Painted with the front towards the viewer's lower LEFT: mirror to lower right.
# (Judged from the cut-outs: the side with the doors/drawers/face/seat.)
# Rule: if the narrow end panel shows on the RIGHT, the front faces lower left.
# Long pieces also have to lie along their footprint (bed, tables, bath, sofa).
# The iso sheets (furn1_iso, furn8_iso) are all painted front to lower left
# except the chair (seat already to the lower right) and the harp (symmetric).
# furn9_iso: the boiler's furnace door faces lower left (mirrored); pumpkin_iso:
# the face is already to the lower right (not mirrored).
# organic_iso.jpg is painted front to the lower right already (not mirrored).
# coffin, tomb, cot (1 wide x 2 deep) were painted with the long side on the
# right; mirrored so it lies along the footprint's long (lower-left) edge.
MIRROR = {"wine_rack", "trunk", "suit_of_armour", "bed",
          "chest", "dining_table", "sofa", "billiard_table", "range_cooker", "sink", "boiler", "bath",
          "washstand", "sewing_machine", "ladder_up", "goblin", "spider",
          "coffin", "tomb", "cot"}

BG_T = 20                  # "white": max channel distance from 255
HOLE_MAX, HOLE_FLAT = 40000, 0.6
# Sheets whose white has more JPEG noise: the gaps between the boiler's pipes
# and gauges (furn9_iso) are only ~53% within 5 of pure white.
HOLE_FLAT_SHEET = {"furn9_iso.jpg": 0.45, "organic_iso.jpg": 0.4, "chairs_back_iso.jpg": 0.4}
SPECK = 40
SOFT_LO, SOFT_HI = 8, 70
HARMONISE = dict(saturation=1.06, contrast=1.04, brightness=1.06)


def background(rgb, flat=HOLE_FLAT):
    d = (255.0 - rgb).max(axis=2)
    white = d < BG_T
    m = Image.fromarray(np.pad(np.where(white, 255, 0).astype(np.uint8), 1, constant_values=255)).copy()
    ImageDraw.floodfill(m, (0, 0), 128)
    arr = np.asarray(m)
    bg = arr[1:-1, 1:-1] == 128
    # enclosed white pockets: background if flat pure white (seen through a gap)
    rest = (arr[1:-1, 1:-1] == 255)
    lab = label(rest)
    for i in range(1, lab.max() + 1):
        comp = lab == i
        n = comp.sum()
        if 12 <= n <= HOLE_MAX and (d[comp] < 5).mean() >= flat:
            bg |= comp
    return bg, d


def label(mask):
    """Connected components (4-way) of a boolean mask, as an int array."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        if lab[y, x]:
            continue
        n += 1
        stack = [(y, x)]
        lab[y, x] = n
        while stack:
            cy, cx = stack.pop()
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
    return lab


def splits(profile, n, lo=0):
    """Cut a 1-D occupancy profile into n parts at the n-1 widest empty runs."""
    empty = profile <= 2          # (a stray JPEG speck does not join two items)
    runs, i = [], 0
    while i < len(empty):
        if empty[i]:
            j = i
            while j < len(empty) and empty[j]:
                j += 1
            if i > 0 and j < len(empty):
                runs.append((j - i, (i + j) // 2))
            i = j
        else:
            i += 1
    cuts = sorted(c for _, c in sorted(runs, reverse=True)[:n - 1])
    if len(cuts) != n - 1:
        raise ValueError(f"wanted {n} parts, found {len(cuts) + 1}")
    edges = [0] + cuts + [len(profile)]
    return [(edges[k] + lo, edges[k + 1] + lo) for k in range(n)]


def find_items(fg, rows):
    """Group the foreground into the sheet's items: connected blobs (grown a
    few px so a candle or a dangling spider stays with its item), the big
    ones are items (extra big ones merge into their nearest), small bits join
    the nearest item; then rows by height and left to right within a row."""
    n = sum(len(r) for r in rows)
    grown = np.asarray(Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))) > 0
    lab = label(grown)
    sizes = np.bincount(lab.ravel())
    ids = [i for i in range(1, len(sizes)) if sizes[i] >= 25]
    boxes = {}
    for i in ids:
        ys, xs = np.nonzero(lab == i)
        boxes[i] = [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, len(xs)]
    groups = {i: {i} for i in sorted(ids, key=lambda i: -boxes[i][4])[:n]}
    def gap(a, b):
        dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
        dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
        return dx * dx + dy * dy
    def gbox(g):
        bs = [boxes[i] for i in g]
        return [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
    for i in ids:
        if i in groups:
            continue
        best = min(groups, key=lambda k: gap(boxes[i], gbox(groups[k])))
        groups[best].add(i)
    items = []
    for k, g in groups.items():
        m = np.isin(lab, list(g)) & fg
        ys, xs = np.nonzero(m)
        items.append(((xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, m,
                      (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)))
    items.sort(key=lambda t: t[1])
    out = []
    at = 0
    for names in rows:
        row = sorted(items[at:at + len(names)], key=lambda t: t[0])
        at += len(names)
        for name, (_, _, m, box) in zip(names, row):
            out.append((name, box, m))
    return out


def cut_item(rgb, d, fg, box):
    x0, y0, x1, y1 = box
    f = fg[y0:y1, x0:x1].copy()
    # drop specks (keep anything sizeable: candles, a spider, a water drop)
    lab = label(f)
    sizes = np.bincount(lab.ravel())
    keep = np.zeros_like(f)
    for i in range(1, len(sizes)):
        if sizes[i] >= SPECK:
            keep |= lab == i
    f = keep
    sub = rgb[y0:y1, x0:x1]
    dd = d[y0:y1, x0:x1]
    fim = Image.fromarray((f * 255).astype(np.uint8))
    outer = np.asarray(fim.filter(ImageFilter.MaxFilter(3))) > 0
    inner = np.asarray(fim.filter(ImageFilter.MinFilter(3))) > 0
    band = outer & ~inner
    ramp = np.clip((dd - SOFT_LO) / (SOFT_HI - SOFT_LO), 0.0, 1.0)
    alpha = np.where(band, ramp, f.astype(np.float64))
    a = alpha[..., None]
    col = np.where(a > 0.02, (sub - (1.0 - a) * 255.0) / np.maximum(a, 0.02), 0.0)
    out = np.concatenate([np.clip(col, 0, 255), alpha[..., None] * 255.0], axis=2)
    img = Image.fromarray((out + 0.5).astype(np.uint8), "RGBA")
    return img.crop(img.split()[3].getbbox())


# Pieces painted standing on a pale grey drop shadow: the shadow is light
# grey on the white sheet, which would show as a pale patch on a dark floor.
# Only furniture (the ghost is pale grey all over), and only the lower band.
NO_SHADOW_FIX = {"ghost", "goblin", "bat", "spider", "skeleton", "monster", "key", "rug", "rug_lifted",
                 "painting", "painting_lady", "painting_landscape", "mirror", "window", "cobweb",
                 "front_door", "door_frame", "stairs_up", "stairs_down", "ladder_up", "trapdoor"}
SHADOW_BAND = 0.35
# Pale shadow seen through gaps (under a barrel stand, between iron legs) is
# enclosed, so it is not reached from the outside; enclosed pale-grey pockets
# in the bottom band count as shadow too, except on pieces whose own bodies
# are pale or grey metal/stone there (they would lose their highlights).
POCKETS_KEEP = {"washtub", "water_tank", "statue", "tomb", "suit_of_armour", "boiler", "cot", "round_table",
                "linen_press", "fireplace", "washstand", "bath", "coffin", "range_cooker", "pumpkin"}


def fix_ground_shadow(img, pockets=True):
    """Turn the painted pale-grey ground shadow (neutral light grey reached from
    the outside, in the bottom of the sprite) into translucent black with the
    same look over white, so it darkens the floor instead."""
    a = np.asarray(img).astype(np.float64)
    rgb, al = a[..., :3], a[..., 3] / 255.0
    h = a.shape[0]
    seen = 255.0 - al[..., None] * (255.0 - rgb)       # as painted over the white
    sat = seen.max(axis=2) - seen.min(axis=2)
    cand = (al > 0) & (sat < 14) & (seen.min(axis=2) > 115)
    cand[: int(h * (1 - SHADOW_BAND))] = False
    outside = np.asarray(Image.fromarray(((al < 0.5) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    lab = label(cand)
    ids = np.unique(lab[outside & cand])
    ids = ids[ids > 0]
    if pockets:
        sizes = np.bincount(lab.ravel())
        ids = np.union1d(ids, [i for i in range(1, len(sizes)) if sizes[i] >= 30])
    m = np.isin(lab, ids)
    if not m.any():
        return img
    out = a.copy()
    out[m, :3] = 0
    out[m, 3] = np.clip((255.0 - seen.mean(axis=2)[m]) * 1.3, 0, 255)
    return Image.fromarray((out + 0.5).astype(np.uint8), "RGBA")


# White seen between closely spaced bars (harp strings, a pierced chair
# back) is split into pockets too small to count as holes: key out pale,
# neutral pixels on these pieces (none of them has white of its own).
KEY_WHITE = {"harp": 228, "chair": 228, "chair_ne": 228}


def key_white(img, thr):
    a = np.asarray(img).astype(np.float64)
    rgb = a[..., :3]
    lo = rgb.min(axis=2)
    sat = rgb.max(axis=2) - lo
    k = np.clip((250.0 - lo) / (250.0 - thr), 0.0, 1.0)      # 1 below thr, 0 at pure white
    k = np.where(sat < 24, k, 1.0)
    a[..., 3] *= k
    return Image.fromarray((a + 0.5).astype(np.uint8), "RGBA")


def harmonise(img):
    a = img.split()[3]
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(HARMONISE["saturation"])
    rgb = ImageEnhance.Contrast(rgb).enhance(HARMONISE["contrast"])
    rgb = ImageEnhance.Brightness(rgb).enhance(HARMONISE["brightness"])
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def flatten_rug(img, name):
    """Warp a painted rug so its corners land on the footprint diamond."""
    from objects import footprint, canvas_size, T
    gx, gy = footprint(name, "E")
    W, H = canvas_size(gx, gy, T[name]["h"])
    S = 3                                  # warp at 3x the game size, the loader scales down
    a = np.asarray(img.split()[3]) > 128
    ys, xs = np.nonzero(a)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    # corners: extreme points along the diagonals and axes of the drawn shape
    left = pts[np.argmin(pts[:, 0] - 0.0 * pts[:, 1])]
    right = pts[np.argmax(pts[:, 0])]
    top = pts[np.argmin(pts[:, 1])]
    bottom = pts[np.argmax(pts[:, 1])]
    hw, hh = 56 * S, 28 * S
    top_h = H * S - (gx + gy) * hh         # flat: the diamond fills the bottom of the canvas
    # footprint diamond on the canvas (x along the north wall, y along the west wall)
    d_left = (0, top_h + gx * hh)
    d_top = (gy * hw, top_h)
    d_right = ((gx + gy) * hw, top_h + gy * hh)
    d_bottom = (gx * hw, top_h + (gx + gy) * hh)
    # PIL wants coefficients mapping output -> input
    src = [left, top, right, bottom]
    dst = [d_left, d_top, d_right, d_bottom]
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    coef = np.linalg.solve(np.array(A), np.array(B))
    return img.transform((W * S, H * S), Image.PERSPECTIVE, tuple(coef), Image.BICUBIC)


def main(argv):
    review = None
    if "--sheet" in argv:
        review = argv[argv.index("--sheet") + 1]
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    os.makedirs(OUT, exist_ok=True)
    made = {}
    for sheet, rows in LAYOUT.items():
        names = {n for r in rows for n in r if n}
        if not names or (only is not None and not only & names):
            continue
        rgb = np.asarray(Image.open(os.path.join(SHEETS, sheet)).convert("RGB")).astype(np.float64)
        bg, d = background(rgb, HOLE_FLAT_SHEET.get(sheet, HOLE_FLAT))
        fg = ~bg
        for name, box, mask in find_items(fg, rows):
            if name is None or (only is not None and name not in only):
                continue
            img = cut_item(rgb, d, mask, box)
            if name in KEY_WHITE:
                img = key_white(img, KEY_WHITE[name])
            if name in MIRROR:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            if name not in NO_SHADOW_FIX:
                img = fix_ground_shadow(img, pockets=name not in POCKETS_KEEP)
            img = harmonise(img)
            if name in ("rug", "rug_lifted"):
                img = flatten_rug(img, name)
            img.save(os.path.join(OUT, name + ".png"))
            made[name] = img
            print(f"{name:20s} {img.width}x{img.height}  ({sheet})")
    made.update(make_views())
    if review:
        contact(made, review)
    print(len(made), "sprites ->", OUT)


# Chairs and armchairs have four facings (art.FOUR_WAY): <name>_se is the
# front view (front to the lower right, = <name>.png), _sw its mirror, _ne
# the rear view (front to the upper right), _nw its mirror.
FOUR_WAY = ("chair", "armchair")


def make_views():
    out = {}
    for n in FOUR_WAY:
        front, back = os.path.join(OUT, n + ".png"), os.path.join(OUT, n + "_ne.png")
        if not (os.path.exists(front) and os.path.exists(back)):
            continue
        f, b = Image.open(front).convert("RGBA"), Image.open(back).convert("RGBA")
        views = {"se": f, "sw": f.transpose(Image.FLIP_LEFT_RIGHT), "ne": b, "nw": b.transpose(Image.FLIP_LEFT_RIGHT)}
        for k, im in views.items():
            if k != "ne":
                im.save(os.path.join(OUT, f"{n}_{k}.png"))
            out[f"{n}_{k}"] = im
    return out


def contact(made, path):
    from PIL import ImageFont
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    cell = 170
    names = list(made)
    cols = 11
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 18)), (110, 110, 110))
    dr = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        im = made[n].copy()
        im.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * (cell + 18)
        sheet.paste(im, (x + (cell - im.width) // 2, y + cell - im.height - 2), im)
        dr.text((x + 4, y + cell + 2), n + (" (m)" if n in MIRROR else ""), fill=(0, 0, 0), font=font)
    sheet.save(path)


if __name__ == "__main__":
    main(sys.argv[1:])
