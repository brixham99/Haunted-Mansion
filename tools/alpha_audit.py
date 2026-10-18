#!/usr/bin/env python3
"""Alpha audit of the room art in assets/art: find white sheet background
left showing through where the sprite should be transparent.

    python3 tools/alpha_audit.py [--dir DIR] [--contact OUT_PREFIX] [--only a,b] [--all]

Two checks per sprite (cut-out PNG):
  pockets  opaque, near-white, low-saturation regions (connected areas of
           at least POCKET_MIN px) that sit inside the sprite: the gaps
           between bedposts, chair rails, under tables, in a cobweb. For the
           pieces cut from a sheet by cut_sheets.py the source is checked too:
           enclosed near-white regions of the sheet (the background colour)
           that the cutter kept as foreground.
  halo     the rim (pixels within 1 px of transparency) that is clearly
           lighter than the paint just inside it: a pale outline on a dark
           floor.
Genuinely white paint (bedsheets, pillows, candles, the ghost, porcelain,
bones, lace) also shows up as "pockets"; the report is for a person to judge
against the contact sheets (each sprite over a dark and a magenta floor).
Exit status 0 always; --all lists clean sprites too.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ART = os.path.join(ROOT, "assets", "art")
sys.path.insert(0, HERE)

POCKET_MIN = 30
WHITE_LO, WHITE_SAT = 222, 20          # "near white": every channel >= 222, spread < 20
DARK, MAGENTA = (28, 24, 34), (255, 0, 255)

# not drawn in the rooms (or not cut-outs): skipped
SKIP_PREFIX = ("bat_", "skeleton_walk_")


def box_sum(x, r):
    c = np.pad(x, ((r + 1, r), (r + 1, r))).cumsum(0).cumsum(1)
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def label(mask):
    from cut_sheets import label as L
    return L(mask)


def pale_mask(a):
    rgb, al = a[..., :3].astype(np.float64), a[..., 3]
    lo, hi = rgb.min(axis=2), rgb.max(axis=2)
    return (al > 200) & (lo >= WHITE_LO) & (hi - lo < WHITE_SAT)


def pockets(a):
    """Connected near-white opaque areas: [(size, cx, cy, enclosed)]."""
    m = pale_mask(a)
    if m.sum() < POCKET_MIN:
        return []
    small = 1
    if m.size > 600_000:                  # big sprites: work at half size (enough to find pockets)
        small = 2
        m = m[::2, ::2]
    lab = label(m)
    sizes = np.bincount(lab.ravel())
    clear = a[::small, ::small, 3] < 40
    near_clear = box_sum(clear.astype(np.float64), 2) > 0
    out = []
    for i in range(1, len(sizes)):
        n = sizes[i] * small * small
        if n < POCKET_MIN:
            continue
        ys, xs = np.nonzero(lab == i)
        enclosed = not near_clear[ys, xs].any()
        out.append((int(n), int(xs.mean() * small), int(ys.mean() * small), enclosed))
    return sorted(out, reverse=True)


def halo(a):
    """Fraction of rim pixels clearly lighter than the paint inside."""
    rgb = a[..., :3].astype(np.float64)
    al = a[..., 3] / 255.0
    lum = rgb @ np.array([0.3, 0.59, 0.11])
    clear = (al < 0.5).astype(np.float64)
    rim = (al > 0.15) & (box_sum(clear, 1) > 0)
    inner = ((al >= 0.9) & ~rim).astype(np.float64)
    ws = box_sum(inner, 2)
    ls = box_sum(lum * inner, 2)
    ok = rim & (ws > 0)
    if not ok.any():
        return 0.0, 0
    paint = ls[ok] / ws[ok]
    bad = (lum[ok] > paint + 40) & (lum[ok] > 150)
    return float(bad.mean()), int(bad.sum())


def audit(path):
    a = np.asarray(Image.open(path).convert("RGBA"))
    p = pockets(a)
    enc = [q for q in p if q[3]]
    h, hn = halo(a)
    return {"size": a.shape[1::-1], "pockets": p, "enclosed_px": sum(q[0] for q in enc),
            "pale_px": sum(q[0] for q in p), "halo": h, "halo_px": hn}


def source_pockets():
    """For the sheet-cut pieces: enclosed near-white regions of the source
    sheet (background colour) that the cutter kept, per item:
    {name: [(size, flat fraction)]}."""
    import cut_sheets as CS
    out = {}
    for sheet, rows in CS.LAYOUT.items():
        if not any(n for r in rows for n in r):
            continue
        rgb = np.asarray(Image.open(os.path.join(CS.SHEETS, sheet)).convert("RGB")).astype(np.float64)
        bg, d = CS.background(rgb, CS.HOLE_FLAT_SHEET.get(sheet, CS.HOLE_FLAT))
        white = d < CS.BG_T
        kept = white & ~bg
        lab = label(kept)
        sizes = np.bincount(lab.ravel())
        for name, box, mask in CS.find_items(~bg, rows):
            if not name:
                continue
            x0, y0, x1, y1 = box
            sub = lab[y0:y1, x0:x1]
            ids = [i for i in np.unique(sub) if i and sizes[i] >= 12]
            out[name] = sorted(((int(sizes[i]), round(float((d[lab == i] < 5).mean()), 2)) for i in ids), reverse=True)
    return out


def contact(paths, prefix, per_page=24, cols=6, cell=200, title=""):
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    pages = []
    for p0 in range(0, len(paths), per_page):
        chunk = paths[p0:p0 + per_page]
        rows = (len(chunk) + cols - 1) // cols
        W, H = cols * (2 * cell + 8), rows * (cell + 20) + (24 if title else 0)
        sheet = Image.new("RGB", (W, H), (70, 70, 70))
        dr = ImageDraw.Draw(sheet)
        if title:
            dr.text((6, 4), f"{title}  (page {p0 // per_page + 1})", fill=(255, 255, 255), font=font)
        for i, path in enumerate(chunk):
            im = Image.open(path).convert("RGBA")
            im.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
            x = (i % cols) * (2 * cell + 8)
            y = (i // cols) * (cell + 20) + (24 if title else 0)
            for k, col in enumerate((DARK, MAGENTA)):
                bgc = Image.new("RGBA", (cell, cell), col + (255,))
                bgc.alpha_composite(im, ((cell - im.width) // 2, (cell - im.height) // 2))
                sheet.paste(bgc.convert("RGB"), (x + k * cell, y))
            dr.text((x + 4, y + cell + 2), os.path.splitext(os.path.basename(path))[0], fill=(255, 255, 255), font=font)
        out = f"{prefix}{'' if len(paths) <= per_page else '_' + str(p0 // per_page + 1)}.png"
        sheet.save(out)
        pages.append(out)
    return pages


def main(argv):
    d = argv[argv.index("--dir") + 1] if "--dir" in argv else ART
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    names = sorted(f[:-4] for f in os.listdir(d) if f.endswith(".png") and not f.startswith(SKIP_PREFIX))
    if only:
        names = [n for n in names if n in only]
    src = source_pockets() if "--source" in argv else {}
    print(f"{'sprite':22s} {'size':>10s} {'enclosed':>9s} {'pale':>7s} {'halo':>6s}  biggest pockets (px @x,y; e=enclosed)  source pockets kept")
    for n in names:
        r = audit(os.path.join(d, n + ".png"))
        flag = r["enclosed_px"] >= POCKET_MIN or r["halo"] > 0.02
        if not flag and "--all" not in argv and not src.get(n):
            continue
        ps = " ".join(f"{s}@{x},{y}{'e' if e else ''}" for s, x, y, e in r["pockets"][:4])
        sp = " ".join(f"{s}({f})" for s, f in src.get(n, [])[:4])
        print(f"{n:22s} {r['size'][0]:4d}x{r['size'][1]:<5d} {r['enclosed_px']:9d} {r['pale_px']:7d} {r['halo']:6.3f}  {ps:40s} {sp}")
    if "--contact" in argv:
        pre = argv[argv.index("--contact") + 1]
        print("\n".join(contact([os.path.join(d, n + ".png") for n in names], pre, title=d)))


if __name__ == "__main__":
    main(sys.argv[1:])
