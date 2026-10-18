#!/usr/bin/env python3
"""Exact 2:1 isometric furniture built from flat orthographic face images.

    python3 tools/iso_box.py --build [NAME ...]   # writes assets/art/<name>.png (all of BUILDS by default)
    python3 tools/iso_box.py --build --out DIR    # write somewhere else (for review)

Every receding edge of a built sprite runs at exactly 1 px down per 2 px
across (atan 0.5 = 26.57 deg), matching the floor tiles, and the front faces
the viewer's lower RIGHT (objects.py convention); the game mirrors it for the
other wall.

Coordinates are those of art.Painter for an object drawn FACING EAST: x =
depth in tiles (0 = back wall, gx = front of the footprint), y = width in
tiles (0 = screen-right end, gy = screen-left end), z = px above the floor.
One tile edge is TE = 62.6 px long in the same units as z, so a face image
keeps its proportions when its width in tiles * TE and its height in px are
in the image's ratio.

Faces of a box:
  front  plane x = x1, the lower-RIGHT face; image left = screen left (y1), image top = z1.
  side   plane y = y1, the lower-LEFT face;  image left = back (x0), image top = z1.
  top    plane z = z1, plan view with the front at the bottom: image top-left = (x0, y1).

Face images come from the flat elevation sheets tools/art/sheets/faces1.jpg
and faces2.jpg (white background, cut with cut_sheets.py). A front elevation
is split into horizontal bands by its silhouette (cornice, body, plinth,
clock hood/trunk/base...): each band becomes its own box, as wide as the band
and as deep as the matching rows of the side elevation (or, with no side, as
deep as the body plus the band's overhang), so cornices and plinths really
stand proud. Missing sides and tops are synthesised: a side from the front's
outer stile (stretched, so its mouldings line up) with wood grain from a side
panel; a top from wood grain tinted to the front's top edge. Recesses (the
fireplace's firebox, the desk's kneehole) are real: a back panel set in by
the recess depth plus the visible inner wall and floor, seen through the hole
in the front.

The sprite canvas is exactly the footprint wide (art.py loads these without
cropping, see art.ISO_BOX_ART), so a piece shallower than its footprint
still sits against the wall at the right size. Painted at 2x game size.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from objects import TILE_W, TILE_H, T  # noqa: E402

HW, HH = TILE_W / 2, TILE_H / 2
TE = math.hypot(HW, HH)            # px per tile edge
SCALE, SS = 2, 3                   # 2x game size, 3x supersampled
WOOD = {"top": 1.0, "side": 0.92, "front": 0.85}     # light shading only: the art is already lit
MARBLE = {"top": 1.0, "side": 0.96, "front": 0.93}   # keeps the marble pale
SHEETS = os.path.join(HERE, "art", "sheets")
FACE_LAYOUT = {
    "faces1.jpg": [["fp_front", "fp_side", "fp_top"], ["dr_base", "dr_rack", "dr_side"],
                   ["cd_front", "cd_side", "cd_top"]],
    "faces2.jpg": [["bc_front", "bc_side", "wd_front", "wd_side"], ["pn_front", "pn_keys", "pn_side", "gc_front"],
                   ["lp_front", "dk_front", "dk_top", "tb_front"]],
}
_FACES = {}


# ---------------------------------------------------------------- face images
def faces():
    """All face images, cut from the sheets (white removed, edges unmixed)."""
    if not _FACES:
        import cut_sheets as C
        for sheet, rows in FACE_LAYOUT.items():
            rgb = np.asarray(Image.open(os.path.join(SHEETS, sheet)).convert("RGB")).astype(np.float64)
            bg, d = C.background(rgb)
            for name, box, mask in C.find_items(~bg, rows):
                _FACES[name] = prep(C.cut_item(rgb, d, mask, box))
    return _FACES


def prep(img, pale_bottom=0.06, trim=2):
    """Hard alpha (the supersampled render anti-aliases the edges again) and
    no pale painted floor shadow in the bottom rows."""
    a = np.asarray(img).astype(np.float32).copy()
    rgb = a[..., :3]
    sat = rgb.max(2) - rgb.min(2)
    lum = rgb.mean(2)
    h = a.shape[0]
    if pale_bottom:
        band = np.zeros(h, bool)
        band[int(h * (1 - pale_bottom)):] = True
        a[band[:, None] & (sat < 22) & (lum > 150), 3] = 0
    a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)
    img = crop(Image.fromarray(a.astype(np.uint8), "RGBA"))
    # the painted outline / rim light on the outermost pixels would show as a
    # pale seam on the corner where two faces meet: trim it off
    t = trim
    return crop(img.crop((t, t, img.width - t, img.height - t)))


def crop(img):
    bb = img.split()[3].getbbox()
    return img.crop(bb) if bb else img


def drop_pale(img, box, lum=120, sat=26):
    """Make pale neutral pixels inside box transparent (shadow seen through a gap)."""
    a = np.asarray(img).copy()
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1].astype(np.int32)
    m = (sub[..., :3].mean(2) > lum) & ((sub[..., :3].max(2) - sub[..., :3].min(2)) < sat)
    a[y0:y1, x0:x1, 3][m] = 0
    return Image.fromarray(a, "RGBA")


def lum_grain(img, size, rotate=False):
    """Luminance of a wood texture, normalised to mean 1 (0.8..1.2)."""
    g = img.convert("RGBA")
    if rotate:
        g = g.rotate(90, expand=True)
    a = np.asarray(g).astype(np.float32)
    al = a[..., 3] > 0
    # crop to the opaque middle (no edge mouldings)
    ys, xs = np.nonzero(al)
    h, w = al.shape
    g = g.crop((int(w * .15), int(h * .1), int(w * .85), int(h * .9)))
    l = np.asarray(g.convert("L").resize(size, Image.BICUBIC)).astype(np.float32)
    return np.clip(l / max(1.0, l.mean()), 0.8, 1.2)


def tinted(grain, colour, border=0.0):
    out = grain[..., None] * np.array(colour, np.float32)[None, None, :]
    if border:
        h, w = grain.shape
        b = max(1, int(min(h, w) * border))
        out[:b] *= 0.82; out[-b:] *= 0.78; out[:, :b] *= 0.82; out[:, -b:] *= 0.78
    a = np.full(grain.shape + (1,), 255, np.float32)
    return Image.fromarray(np.concatenate([out.clip(0, 255), a], 2).astype(np.uint8), "RGBA")


def mean_colour(img, box=None):
    a = np.asarray(img.crop(box) if box else img).astype(np.float32)
    m = a[..., 3] > 0
    return np.median(a[..., :3][m], axis=0) if m.any() else np.array([90, 60, 40], np.float32)


def fill_sides(img, inset=3):
    """Per row, replicate an opaque pixel just inside the outline out to the
    image edges, so a face fills its parallelogram (no see-through gap and no
    pale rim light on the corner where two faces meet)."""
    a = np.asarray(img).copy()
    op = a[..., 3] > 0
    for r in range(a.shape[0]):
        xs = np.nonzero(op[r])[0]
        if len(xs):
            i = min(len(xs) - 1, inset)
            a[r, :xs[i]] = a[r, xs[i]]
            a[r, xs[-1 - i] + 1:] = a[r, xs[-1 - i]]
    return Image.fromarray(a, "RGBA")


def synth_side(front_band, size, grain):
    """A side panel for a band: the front's outer stile stretched to the depth
    (its mouldings line up with the front) times wood grain."""
    w, h = front_band.size
    k0 = max(2, int(w * 0.03))                   # just inside the rim light
    k = max(3, int(w * 0.05))
    strip = np.asarray(fill_sides(front_band).crop((k0, 0, k0 + k, h)).resize(size, Image.BICUBIC)).astype(np.float32)
    g = lum_grain(grain, size)
    strip[..., :3] *= g[..., None]
    strip[..., 3] = 255
    return Image.fromarray(strip.clip(0, 255).astype(np.uint8), "RGBA")


def bands(img, tol=None, min_h=None):
    """Split a front elevation into horizontal bands of similar silhouette:
    [(r0, r1, c0, c1)], top to bottom."""
    a = np.asarray(img)[..., 3] > 0
    h, w = a.shape
    tol = tol or max(2, int(w * 0.02))
    min_h = min_h or max(3, int(h * 0.03))
    ext = []
    for r in range(h):
        xs = np.nonzero(a[r])[0]
        ext.append((xs[0], xs[-1] + 1) if len(xs) else None)
    out = []
    r = 0
    while r < h:
        if ext[r] is None:
            r += 1
            continue
        L, R = ext[r]
        r1 = r + 1
        while r1 < h and ext[r1] is not None and abs(ext[r1][0] - L) <= tol and abs(ext[r1][1] - R) <= tol:
            r1 += 1
        out.append([r, r1, L, R])
        r = r1
    # thin bands join the neighbour closest in width
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i, b in enumerate(out):
            if b[1] - b[0] < min_h:
                cand = [j for j in (i - 1, i + 1) if 0 <= j < len(out)]
                j = min(cand, key=lambda j: abs((out[j][3] - out[j][2]) - (b[3] - b[2])))
                o = out[j]
                o[0], o[1] = min(o[0], b[0]), max(o[1], b[1])
                rows = [e for e in ext[o[0]:o[1]] if e]
                o[2] = int(np.median([e[0] for e in rows]))
                o[3] = int(np.median([e[1] for e in rows]))
                del out[i]
                changed = True
                break
    return [tuple(b) for b in out]


# ---------------------------------------------------------------- renderer
class Scene:
    """3-D quads and decals for one sprite; render() lays them out on the
    exact canvas for the footprint (gx deep, gy wide)."""

    def __init__(self, name):
        w, d = T[name]["size"]
        self.name, self.gx, self.gy = name, d, w
        self.ops = []

    # every face is a parallelogram given by three 3-D corners: image (0,0), (w,0), (0,h)
    def quad(self, tex, A, B, C, shade=1.0):
        self.ops.append(("quad", tex, A, B, C, shade))

    def box(self, x0, y0, z0, x1, y1, z1, front=None, side=None, top=None, shade=WOOD):
        if side is not None:
            self.quad(side, (x0, y1, z1), (x1, y1, z1), (x0, y1, z0), shade["side"])
        if front is not None:
            self.quad(front, (x1, y1, z1), (x1, y0, z1), (x1, y1, z0), shade["front"])
        if top is not None:
            self.quad(top, (x0, y1, z1), (x0, y0, z1), (x1, y1, z1), shade["top"])

    def decal(self, img, x, y, z, height):
        self.ops.append(("decal", img, x, y, z, height))

    def render(self):
        k = SCALE * SS
        top = 0.0
        for op in self.ops:
            if op[0] == "quad":
                top = max(top, *(p[2] for p in op[2:5]))
            else:
                top = max(top, op[4] + op[5])
        h = int(math.ceil(top + 2))
        W = int(round((self.gx + self.gy) * HW * k))
        H = int(round(((self.gx + self.gy) * HH + h) * k))
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        def P(x, y, z):
            return np.array([(self.gy + x - y) * HW * k, (h + (x + y) * HH - z) * k])

        for op in self.ops:
            if op[0] == "quad":
                _, tex, A, B, C, shade = op
                draw_quad(img, tex, P(*A), P(*B), P(*C), shade)
            else:
                _, dimg, x, y, z, ht = op
                s = ht * k / dimg.height
                im = dimg.resize((max(1, round(dimg.width * s)), max(1, round(dimg.height * s))), Image.LANCZOS)
                px, py = P(x, y, z)
                img.alpha_composite(im, (int(round(px - im.width / 2)), int(round(py - im.height))))
        return img.resize((W // SS, H // SS), Image.LANCZOS)


def draw_quad(img, tex, A, B, C, shade, pad=4):
    tex = tex.convert("RGBA")
    w, h = tex.size
    a = np.asarray(tex).astype(np.float32)
    if shade != 1.0:
        a[..., :3] *= shade
    a = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")    # no transparent fringe at the face edge
    tex = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA")
    M = np.column_stack([(B - A) / w, (C - A) / h])
    if abs(np.linalg.det(M)) < 1e-9:
        return
    Mi = np.linalg.inv(M)
    off = -Mi @ A + pad
    layer = tex.transform(img.size, Image.AFFINE, (Mi[0, 0], Mi[0, 1], off[0], Mi[1, 0], Mi[1, 1], off[1]),
                          Image.BICUBIC)
    D = B + C - A
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon([tuple(A), tuple(B), tuple(D), tuple(C)], fill=255)
    la = np.asarray(layer).copy()
    la[..., 3] = (la[..., 3].astype(np.uint16) * np.asarray(mask) // 255).astype(np.uint8)
    img.alpha_composite(Image.fromarray(la, "RGBA"))


# ---------------------------------------------------------------- parts
def part(sc, front, y_left, width, z0, height, x0=0.0, depth=None, side=None, max_depth=None,
         top=None, grain=None, shade=WOOD, split=True, base_depth=None, holes=(), crest=0):
    """One elevation as a stack of boxes. front: image; the bbox maps to
    y_left .. y_left - width (tiles), z0 .. z0 + height (px). Depth from the
    side image's matching rows (side), or base_depth + overhang. holes: list
    of (u0, v0, u1, v1, depth, back_tex, wall_tex, floor_tex) in front-image
    px: a recess drawn behind the front."""
    fw, fh = front.size
    su = width * TE / fw            # px per image px across (world)
    sz = height / fh                # px per image px up
    max_depth = max_depth if max_depth is not None else sc.gx - x0
    bl = bands(front) if split else [(0, fh, 0, fw)]
    if crest:          # top rows (a clock's pediment and finial) stand flat on the front, no box
        bl = [(max(crest, b[0]), b[1], b[2], b[3]) for b in bl if b[1] > crest]
    body = max(bl, key=lambda b: b[1] - b[0])
    if grain is None:
        grain = side if side is not None else front

    def zrow(r):
        return z0 + (fh - r) * sz

    def yc(c):
        return y_left - c * su / TE

    def band_depth(b):
        if side is not None:
            sw, sh = side.size
            s0, s1 = int(b[0] / fh * sh), max(int(b[0] / fh * sh) + 1, int(b[1] / fh * sh))
            sa = np.asarray(side)[s0:s1, :, 3] > 0
            cols = np.nonzero(sa.any(0))[0]
            dpx = (cols[-1] + 1 - cols[0]) if len(cols) else sw
            d = dpx * (fh * su / sh) / TE          # side drawn at the front's unstretched scale
            if depth is not None:
                d *= depth / (sw * (fh * su / sh) / TE)
        else:
            d = (base_depth or 0.5) + ((b[3] - b[2]) - (body[3] - body[2])) / 2 * su / TE
        return float(np.clip(d, 0.04, max_depth))

    # recesses first: they are seen only through the holes in the front
    fb = front.copy()
    for (u0, v0, u1, v1, rd, back_tex, wall_tex, floor_tex) in holes:
        bd = band_depth(body)
        xf = x0 + bd
        xb = xf - rd
        ya, yb, za, zb = yc(u0), yc(u1), zrow(v1), zrow(v0)
        sc.box(xb - 0.01, yb, za, xb, ya, zb, front=back_tex, shade=shade)          # back panel
        if wall_tex is not None:                                                     # inner wall, screen-right
            sc.quad(wall_tex, (xb, yb, zb), (xf, yb, zb), (xb, yb, za), shade["side"] * 0.8)
        if floor_tex is not None:
            sc.quad(floor_tex, (xb, ya, za), (xb, yb, za), (xf, ya, za), shade["top"] * 0.85)
    for i, b in reversed(list(enumerate(bl))):      # bottom up: each box hides the ledge under the next
        r0, r1, c0, c1 = b
        band = fill_sides(fb.crop((c0, r0, c1, r1)))
        # holes punched back in (fill_sides only fills the outer margins)
        d = band_depth(b)
        yl, yr = yc(c0), yc(c1)
        za, zb = zrow(r1), zrow(r0)
        if side is not None:
            sw, sh = side.size
            s0, s1 = int(r0 / fh * sh), max(int(r0 / fh * sh) + 1, int(r1 / fh * sh))
            sb = side.crop((0, s0, sw, s1))
            bb = sb.split()[3].getbbox()
            sb = fill_sides(sb.crop((bb[0], 0, bb[2], sb.height))) if bb else sb
        else:
            sb = synth_side(band, (max(4, int(d * TE * 2)), max(2, int((zb - za) * 2))), grain)
        if i == 0 and top is not None:
            tp = top
        else:
            col = mean_colour(band)
            tp = tinted(lum_grain(grain, (max(4, int(abs(yl - yr) * TE * 2)), max(4, int(d * TE * 2))), rotate=True),
                        col, border=0.04)
        sc.box(x0, yr, za, x0 + d, yl, zb, front=band, side=sb, top=tp, shade=shade)
    if crest:
        cr = fb.crop((0, 0, fw, crest))
        bb = cr.split()[3].getbbox()
        if bb:
            cr = cr.crop((bb[0], 0, bb[2], crest))
            d = band_depth(bl[0]) - 0.03
            sc.quad(cr, (x0 + d, yc(bb[0]), zrow(0)), (x0 + d, yc(bb[2]), zrow(0)), (x0 + d, yc(bb[0]), zrow(crest)),
                    shade["front"])
    return bl


def punch(img, mask_fn):
    a = np.asarray(img).copy()
    a[..., 3][mask_fn(a)] = 0
    return Image.fromarray(a, "RGBA")


# ---------------------------------------------------------------- the pieces
def furn1_iso_item(name):
    """An old corner-view sprite straight from its sheet (for small extras)."""
    import cut_sheets as C
    rows = [["grandfather_clock", "wardrobe", "bookcase"], ["chest_of_drawers", "kitchen_dresser", "fireplace"]]
    rgb = np.asarray(Image.open(os.path.join(SHEETS, "furn1_iso.jpg")).convert("RGB")).astype(np.float64)
    bg, d = C.background(rgb)
    for n, box, mask in C.find_items(~bg, rows):
        if n == name:
            return C.cut_item(rgb, d, mask, box)


def build_fireplace():
    F = faces()
    sc = Scene("fireplace")
    front, side, top = F["fp_front"], F["fp_side"], F["fp_top"]
    fw, fh = front.size
    # firebox opening: the non-marble region inside the arch (dark soot, grate, green flames)
    u0, v0, u1, v1 = 72, 50, 282, 208
    a = np.asarray(front).astype(np.int32)
    rgb = a[..., :3]
    marble = (rgb.mean(2) > 105) & ((rgb.max(2) - rgb.min(2)) < 40)
    # the arch is the marble joined to the edge of the box; pale islands inside
    # (bright flames, highlights on the grate) belong to the opening
    import cut_sheets as C
    m = marble[v0:v1, u0:u1]
    lab = C.label(m)
    edge = np.unique(np.concatenate([lab[0], lab[:, 0], lab[:, -1]]))
    arch = np.isin(lab, edge[edge > 0])
    hole = np.zeros(marble.shape, bool)
    hole[v0:v1, u0:u1] = ~arch
    soot = tinted(lum_grain(side, (40, 40)), (46, 45, 42))
    bk = np.asarray(front).copy()
    bk[~hole] = (28, 30, 30, 255)
    back = Image.fromarray(bk, "RGBA").crop((u0, v0, u1, v1))
    holed = punch(front, lambda arr: hole)
    hearth = top.resize((top.width, top.height))
    H = 112                                   # 1.3x the face's own proportions: a mantel at hip height
    sc.box(0, 0, 0, 1.0, 2.0, 6, front=top.crop((0, 0, top.width, 16)), side=top.crop((0, 0, top.width // 2, 16)),
           top=hearth, shade=MARBLE)           # hearth slab
    part(sc, holed, 2.0, 2.0, 6, H, side=side, top=top, shade=MARBLE, max_depth=0.62,
         holes=[(u0, v0, u1, v1, 0.24, back, soot, soot)])
    candles = furn1_iso_item("fireplace")
    if candles is not None:
        c = candles.crop((48, 6, 98, 64)).transpose(Image.FLIP_LEFT_RIGHT)
        sc.decal(crop(c), 0.25, 0.55, 6 + H, 30)
    return sc


def build_kitchen_dresser():
    F = faces()
    sc = Scene("kitchen_dresser")
    base, rack, side = F["dr_base"], F["dr_rack"], F["dr_side"]
    hb = 2.0 * TE * base.height / base.width                # 79 px
    rw = 2.0 * rack.width / base.width                      # 1.6 tiles
    hr = rw * TE * rack.height / rack.width * 1.1
    part(sc, base, 2.0, 2.0, 0, hb, side=side, depth=0.78, grain=side)
    part(sc, rack, 1.0 + rw / 2, rw, hb, hr, side=side, depth=0.34, grain=side, split=False)   # set back on the worktop
    return sc


def build_chest_of_drawers():
    F = faces()
    sc = Scene("chest_of_drawers")
    f = F["cd_front"]
    part(sc, f, 2.0, 2.0, 0, 2.0 * TE * f.height / f.width, side=F["cd_side"], top=F["cd_top"], grain=F["cd_side"])
    return sc


def build_bookcase():
    F = faces()
    sc = Scene("bookcase")
    f = F["bc_front"]
    part(sc, f, 2.0, 2.0, 0, 2.0 * TE * f.height / f.width, side=F["bc_side"], grain=F["bc_side"])
    return sc


def build_wardrobe():
    F = faces()
    sc = Scene("wardrobe")
    f = F["wd_front"]
    part(sc, f, 2.0, 2.0, 0, 2.0 * TE * f.height / f.width, side=F["wd_side"], grain=F["wd_side"])
    return sc


def build_linen_press():
    F = faces()
    sc = Scene("linen_press")
    f = F["lp_front"]
    part(sc, f, 2.0, 2.0, 0, 2.0 * TE * f.height / f.width, base_depth=0.62, grain=F["bc_side"])
    return sc


def build_grandfather_clock():
    F = faces()
    sc = Scene("grandfather_clock")
    f = F["gc_front"]
    part(sc, f, 1.0, 1.0, 0, 1.0 * TE * f.height / f.width, base_depth=0.42, grain=F["wd_side"], crest=23)
    return sc


def build_toy_box():
    F = faces()
    sc = Scene("toy_box")
    f = F["tb_front"]
    part(sc, f, 1.0, 1.0, 0, 1.0 * TE * f.height / f.width * 1.25, base_depth=0.6, grain=F["cd_side"])
    return sc


def build_desk():
    F = faces()
    sc = Scene("desk")
    f = drop_pale(F["dk_front"], (60, 40, 170, 139))
    fw, fh = f.size
    # the kneehole: where the front is see-through between the pedestals
    al = np.asarray(f)[..., 3] > 0
    gap = [c for c in range(fw // 4, 3 * fw // 4) if not al[int(fh * .45):int(fh * .9), c].any()]
    u0, u1 = (gap[0], gap[-1] + 1) if gap else (75, 152)
    rows = [r for r in range(fh) if not al[r, u0 + 2:u1 - 2].any()]
    v0 = rows[0] if rows else 43
    wood = mean_colour(f, (0, 30, u0, fh - 10))
    dark = tinted(lum_grain(F["cd_side"], (60, 60)), wood * 0.45)
    inner = tinted(lum_grain(F["cd_side"], (60, 60)), wood * 0.6)
    part(sc, f, 2.0, 2.0, 0, 2.0 * TE * fh / fw, base_depth=0.82, top=F["dk_top"], grain=F["cd_side"],
         holes=[(u0, v0, u1, fh, 0.62, dark, inner, None)])
    return sc


def build_piano():
    F = faces()
    sc = Scene("piano")
    f, keys, side = F["pn_front"], F["pn_keys"], F["pn_side"]
    fw, fh = f.size
    H = 2.0 * TE * fh / fw
    sz = H / fh
    su = 2.0 * TE / fw / TE        # tiles per image px across
    case_d = 0.5
    # the case: one flat front (the keys painted on it get covered by the key bed)
    part(sc, f, 2.0, 2.0, 0, H, side=side, depth=case_d, grain=side, split=False)
    kr0, kr1 = 84, 100             # rows of the keys + key slip on the front
    cheek = 13                     # cheek block / leg columns at each end
    zk0, zk1 = (fh - kr1) * sz, (fh - kr0) * sz
    xk = case_d + 0.36
    black = tinted(lum_grain(side, (60, 60)), mean_colour(side) * 1.0)
    # legs under the cheeks, then the key bed, then the cheeks
    for c0, c1 in ((0, cheek), (fw - cheek, fw)):
        y1, y0 = 2.0 - c0 * su, 2.0 - c1 * su
        leg = fill_sides(f.crop((c0, kr1, c1, fh)))
        sc.box(case_d, y0, 0, xk - 0.04, y1, zk0, front=leg, side=black, top=black)
    slip = f.crop((cheek, kr0 + 4, fw - cheek, kr1))
    sc.box(case_d, 2.0 - (fw - cheek) * su, zk0, xk, 2.0 - cheek * su, zk1 - 1.5, front=slip, side=black, top=keys)
    for c0, c1 in ((0, cheek), (fw - cheek, fw)):
        y1, y0 = 2.0 - c0 * su, 2.0 - c1 * su
        ch = fill_sides(f.crop((c0, kr0 - 6, c1, kr1)))
        sc.box(case_d, y0, zk0, xk, y1, zk1 + 2, front=ch, side=black, top=black)
    return sc


LADDER_TOP = 254          # px: the rails' tops, up through the hatch


def build_ladder_up():
    """The loft ladder, built rather than cut: two leaning rails and round
    rungs in worn oak, feet on the floor out from the wall, tops resting on
    the back edge of a framed hatch in the ceiling at the wall's top. All
    edges exact 2:1: the rails lean in the x-z plane only (verticals stay in
    their planes), and the hatch frame is four boards on the ceiling line."""
    from objects import WALL_H
    F = faces()
    sc = Scene("ladder_up")
    oak = np.array([104, 74, 47], np.float32)
    g = F["cd_side"]

    def wood(w, h, k=1.0, rotate=False):
        return tinted(lum_grain(g, (max(4, int(w)), max(4, int(h))), rotate=rotate), oak * k)

    hz = WALL_H
    dark = Image.new("RGBA", (8, 8), (10, 7, 6, 255))
    # the hatch: a dark opening into the loft, framed by boards on the ceiling line
    hx0, hx1, hy0, hy1, bw, bt = 0.0, 0.66, 0.12, 0.88, 0.07, 9
    sc.quad(dark, (hx0, hy1, hz), (hx0, hy0, hz), (hx1, hy1, hz))
    # the shaft's far walls, seen up through the opening (dim boards)
    sc.quad(wood(60, 30, 0.35), (hx0 + 0.01, hy1, hz + 26), (hx0 + 0.01, hy0, hz + 26), (hx0 + 0.01, hy1, hz), 1.0)
    sc.quad(wood(60, 30, 0.28), (hx0, hy0 + 0.01, hz + 26), (hx1, hy0 + 0.01, hz + 26), (hx0, hy0 + 0.01, hz), 1.0)
    boards = {"back": (hx0 - 0.02, hy0 - bw, hx0 + 0.03, hy1 + bw), "right": (hx0, hy0 - bw, hx1 + bw, hy0),
              "left": (hx0, hy1, hx1 + bw, hy1 + bw), "front": (hx1, hy0 - bw, hx1 + bw, hy1 + bw)}

    def board(k):
        x0, y0, x1, y1 = boards[k]
        L, D = (y1 - y0) * TE * 2, (x1 - x0) * TE * 2
        sc.box(x0, y0, hz, x1, y1, hz + bt, front=wood(L, bt * 2, 0.8), side=wood(D, bt * 2, 0.7),
               top=wood(L, D, 1.0, rotate=True))

    board("back")
    board("right")
    # the ladder: rails from the feet (xf, floor) to the tops (xt, LADDER_TOP)
    xf, xt, zt = 0.64, 0.05, LADDER_TOP
    yR, yL, rw, th = 0.22, 0.78, 0.065, 7.0          # rails' inner faces (tiles), rail width (tiles), depth (px)
    dxp, dz = (xt - xf) * TE, zt
    n = math.hypot(dxp, dz)
    ox, oz = dz / n * th / TE, -dxp / n * th          # outward offset of the rails' front face (tiles, px)

    def along(t):          # point on the back line of the ladder, t = 0 foot .. 1 top
        return xf + (xt - xf) * t, zt * t

    # rungs: round, every ~25 px, set into the rails' thickness
    nr = int(zt // 25)
    for i in range(1, nr + 1):
        t = (i * 25 - 6) / zt
        if t > 0.94:
            break
        x, z = along(t)
        xm = x + ox * 0.5
        sc.box(xm - 0.035, yR, z - 2.5, xm + 0.035, yL, z + 2.5, front=wood(70, 10, 0.95), side=wood(10, 10, 0.8),
               top=wood(70, 10, 1.15, rotate=True))
    Lpx = n * 2
    for y0, y1 in ((yR - rw, yR), (yL, yL + rw)):
        # side face (plane y = y1, the lower-left face), then the front (leaning) face
        sc.quad(wood(th * 2, Lpx, 0.82), (xt, y1, zt), (xt + ox, y1, zt + oz), (xf, y1, 0), 1.0)
        sc.quad(wood(rw * TE * 2, Lpx, 1.0), (xt + ox, y1, zt + oz), (xt + ox, y0, zt + oz), (xf + ox, y1, oz), 1.0)
        # the rail's top end, cut level
        sc.quad(wood(rw * TE * 2, th * 2, 1.1), (xt, y1, zt), (xt, y0, zt), (xt + ox, y1, zt), 1.0)
    board("left")
    board("front")
    return sc


def recolour(img, target, keep_brass=True):
    """A painted face repainted in another colour: its own light and shade
    (luminance, normalised) times target; brass handles keep their colour."""
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    rgb = a[..., :3]
    lum = rgb @ np.array([0.3, 0.59, 0.11], np.float32)
    m = a[..., 3] > 0
    k = lum / max(1.0, float(np.median(lum[m])))
    out = np.clip(k[..., None] * np.array(target, np.float32), 0, 255)
    if keep_brass:
        brass = (rgb[..., 0] - rgb[..., 2] > 38) & (rgb[..., 0] > 90)
        out[brass] = rgb[brass]
    a[..., :3] = out
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def butcher_block(w, h, seed=3, end_grain=False):
    """Scrubbed pine/beech butcher-block: glued strips of slightly different
    tone with fine grain, pale scrubbed wear in the middle. w x h px, strips
    across the width (or end-grain blocks for the front edge)."""
    rng = np.random.default_rng(seed)
    base = np.array([198, 166, 120], np.float32)
    img = np.zeros((h, w, 3), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if end_grain:
        bw = max(6, w // 26)
        for i in range(0, w, bw):
            t = rng.uniform(0.82, 1.08)
            img[:, i:i + bw] = base * t
            img[:, i:i + 1] *= 0.72
        img *= (0.92 + 0.08 * np.sin(yy * 1.7 + xx * 0.3))[..., None]
    else:
        sw = max(5, h // 9)
        y = 0
        while y < h:
            t = rng.uniform(0.84, 1.08)
            hh = int(sw * rng.uniform(0.8, 1.2))
            img[y:y + hh] = base * t
            img[y:y + 1] *= 0.74                      # glue line
            y += hh
        grain = 0.94 + 0.06 * np.sin(xx * 0.09 + 3 * np.sin(yy * 0.31) + rng.uniform(0, 6))
        img *= grain[..., None]
        wear = np.exp(-(((xx - w / 2) / (w * 0.35)) ** 2 + ((yy - h / 2) / (h * 0.4)) ** 2))
        img = img * (1 + 0.1 * wear[..., None])        # scrubbed pale in the middle
        img *= (1 - 0.05 * rng.random((h, w)))[..., None]
    a = np.full((h, w, 1), 255, np.float32)
    return Image.fromarray(np.concatenate([np.clip(img, 0, 255), a], 2).astype(np.uint8), "RGBA")


def _pan(w=90, h=60):
    """A copper saucepan from the side: body with a rolled rim, a long handle."""
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bx0, bx1, by0, by1 = 4 * S, 52 * S, 18 * S, 56 * S
    d.rectangle([bx0, by0, bx1, by1], fill=(168, 88, 46, 255))
    for i in range(bx1 - bx0):
        t = i / (bx1 - bx0)
        c = int(150 + 80 * math.sin(math.pi * (0.15 + 0.7 * t)) ** 3)
        d.line([(bx0 + i, by0), (bx0 + i, by1)], fill=(c, int(c * 0.52), int(c * 0.28), 255))
    d.ellipse([bx0, by1 - 6 * S, bx1, by1 + 2 * S], fill=(120, 60, 30, 255))
    d.rectangle([bx0 - S, by0 - 3 * S, bx1 + S, by0 + 2 * S], fill=(214, 140, 84, 255))
    d.polygon([(bx1, by0 + 6 * S), (w * S - 2 * S, by0 - 2 * S), (w * S - S, by0 + 2 * S), (bx1, by0 + 12 * S)],
              fill=(70, 62, 58, 255))
    return crop(im.resize((w, h), Image.LANCZOS))


def _bowl(w=70, h=42):
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    W, H = w * S, h * S
    d.chord([0, -H * 0.9, W, H], 0, 180, fill=(222, 206, 172, 255))
    for i in range(W):
        t = i / W
        c = 0.72 + 0.32 * math.sin(math.pi * t) ** 0.6
        y0 = H * 0.05 + 0 * t
        d.line([(i, y0 + 2), (i, H * 0.05 + (H * 0.95 - 2) * math.sqrt(max(0, 1 - (2 * t - 1) ** 2)))],
               fill=(int(226 * c), int(208 * c), int(170 * c), 255))
    d.rectangle([W * 0.06, H * 0.36, W * 0.94, H * 0.44], fill=(150, 170, 196, 255))      # a blue band
    d.ellipse([W * 0.02, -H * 0.06, W * 0.98, H * 0.16], fill=(236, 226, 200, 255))
    d.ellipse([W * 0.1, -H * 0.02, W * 0.9, H * 0.12], fill=(170, 130, 80, 255))           # batter
    return crop(im.resize((w, h), Image.LANCZOS))


def _loaf(w=64, h=34):
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    W, H = w * S, h * S
    d.rounded_rectangle([0, H * 0.15, W, H], radius=H * 0.45, fill=(176, 112, 56, 255))
    d.rounded_rectangle([W * 0.05, H * 0.12, W * 0.95, H * 0.62], radius=H * 0.35, fill=(204, 146, 80, 255))
    for k in range(4):
        x = W * (0.22 + k * 0.18)
        d.line([(x, H * 0.2), (x + W * 0.08, H * 0.55)], fill=(232, 196, 140, 255), width=S * 2)
    return crop(im.resize((w, h), Image.LANCZOS))


def build_kitchen_island():
    """A big square Victorian kitchen island (3 x 3 tiles): the dresser's
    panelled cupboard base (drawers over doors on a plinth, brass handles)
    repainted deep green and widened, freestanding in the middle
    of its footprint under a scrubbed butcher-block top; a bread board with a
    loaf, a mixing bowl, a copper pan and a cake spread out on top."""
    F = faces()
    sc = Scene("kitchen_island")
    green = (66, 96, 72)
    base = recolour(F["dr_base"], green)
    hb = 1.8 * TE * base.height / base.width            # ~71 px: worktop height, as before
    x0, depth = 0.32, 2.36
    side = recolour(F["dr_side"], green)
    part(sc, base, 2.82, 2.64, 0, hb, x0=x0, side=side, depth=depth, grain=side, max_depth=depth, split=False)
    # the butcher-block top, overhanging the base a little all round
    tx0, tx1, ty0, ty1, z0, z1 = 0.2, 2.8, 0.06, 2.94, hb, hb + 9
    L, D = (ty1 - ty0) * TE * 2, (tx1 - tx0) * TE * 2
    sc.box(tx0, ty0, z0, tx1, ty1, z1, front=butcher_block(int(L) // 2, 16, end_grain=True),
           side=butcher_block(int(D) // 2, 16, seed=5, end_grain=True), top=butcher_block(int(L) // 2, int(D) // 2))
    board = recolour(butcher_block(90, 60, seed=9), (150, 110, 70), keep_brass=False)
    sc.quad(board, (0.7, 2.6, z1 + 1.5), (0.7, 2.0, z1 + 1.5), (1.3, 2.6, z1 + 1.5), 1.0)
    sc.decal(_loaf(), 1.0, 2.3, z1 + 2, 15)
    sc.decal(_bowl(), 2.0, 2.2, z1, 18)
    sc.decal(_pan(), 1.0, 0.8, z1, 17)
    sc.decal(_bowl(), 2.1, 0.9, z1, 14)
    return sc


BUILDS = {"fireplace": build_fireplace, "kitchen_dresser": build_kitchen_dresser,
          "chest_of_drawers": build_chest_of_drawers, "bookcase": build_bookcase, "wardrobe": build_wardrobe,
          "piano": build_piano, "grandfather_clock": build_grandfather_clock, "linen_press": build_linen_press,
          "desk": build_desk, "toy_box": build_toy_box, "ladder_up": build_ladder_up,
          "kitchen_island": build_kitchen_island}


def main(argv):
    out = os.path.join(ROOT, "assets", "art")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
        argv = [a for i, a in enumerate(argv) if a != "--out" and (i == 0 or argv[i - 1] != "--out")]
    names = [a for a in argv if not a.startswith("--")] or list(BUILDS)
    os.makedirs(out, exist_ok=True)
    for n in names:
        img = BUILDS[n]().render()
        p = os.path.join(out, n + ".png")
        img.save(p)
        print(f"{n:18s} {img.width}x{img.height} -> {p}")


if __name__ == "__main__":
    if "--build" in sys.argv:
        main([a for a in sys.argv[1:] if a != "--build"])
    else:
        print(__doc__)
