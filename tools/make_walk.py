#!/usr/bin/env python3
"""Walk cycles for Archie and Holly, built in code from the supplied art only
(tools/art/*_source.png). No image generator is involved: these are real
family members, so every pixel comes from Nathan's source pictures.

    python3 tools/make_walk.py              # both characters
    python3 tools/make_walk.py --debug DIR  # also save the cut-out parts

How it works, per source picture (one front 3/4 view and one back 3/4 view
per character; the other two facings are mirror images):

1. The source is cut out and scaled to WORK_H (640 px) for the figure.
2. It is split into parts with hand-placed outlines (SOURCES below):
   body (head, torso, hoodie or dress), near leg, far leg, near arm and far
   arm. Which leg is near is judged by the feet: the lower foot is nearer.
3. Each frame of an 8-frame cycle poses the parts:
   - legs: the foot travels along the walking direction on screen (planted
     feet move back at exactly the ground speed; swinging feet lift and come
     forward), the leg shears from the hip to the ankle, the shoe stays rigid,
     and the knee pushes forward while the foot is off the ground;
   - the far leg (and far arm) is darker and drawn behind;
   - arms swing opposite to the legs on their side;
   - the body bobs (lowest at each heel strike) and leans a little forward.
4. Frames are drawn at work size then downscaled (premultiplied Lanczos plus
   a light unsharp mask, as make_sprites.py) to a 160 px figure.

Output (assets/characters/):
  <name>_<facing>.png       standing frame (idle), same canvas as the walk
  <name>_<facing>_walk.png  8 frames side by side
  <name>_walk.json          frame size, ground anchor per facing, each
                            frame's foot positions and which foot touches
                            down, and the distance one cycle covers (tiles)
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_sprites import ART, defringe  # noqa: E402

OUT = os.path.join(HERE, "..", "assets", "characters")
WORK_H = 640          # figure height while posing
FIGURE_H = 160        # figure height in the game (standing)
K = WORK_H / FIGURE_H  # work px per game px
FRAMES = 8
STANCE = 0.56         # fraction of the cycle a foot is planted
TILE_PX = math.hypot(56, 28)  # screen length of one tile step along x or y
FAR_SHADE = (0.80, 0.77, 0.76)   # far leg in shadow (warm, so skin does not go grey)
FAR_ARM_SHADE = 0.86

# Hand-placed part outlines, in work pixels of the cropped figure (640 high).
# fwd: the walking direction on screen for this view (x right, y down).
SOURCES = {
    "archie_se": dict(
        file="archie_se_source.png", white_bg=False, fwd=(2, 1),
        hem=[(0, 402), (50, 394), (100, 391), (150, 386), (179, 386)],
        pivot=396, foot_h=56,
        far_leg=[(100, 380), (179, 380), (179, 603), (128, 607), (112, 597), (103, 584), (100, 575)],
        near_arm=[(4, 236), (44, 222), (60, 262), (57, 330), (54, 395), (51, 409), (56, 424), (56, 440), (46, 449),
                  (37, 453), (24, 448), (16, 438), (14, 412), (4, 402)],
        near_shoulder=(32, 245), near_hand=(36, 450),
        far_arm=[(146, 246), (172, 240), (179, 300), (179, 410), (170, 418), (151, 418), (149, 372), (149, 330)],
        far_shoulder=(160, 255), far_hand=(164, 395)),
    "archie_ne": dict(
        file="archie_ne_source.png", white_bg=True, fwd=(2, -1),
        clear_white=[(72, 440), (94, 440), (94, 557), (72, 557)],   # backdrop showing between the legs
        hem=[(0, 384), (30, 386), (100, 393), (140, 396), (196, 398)],
        pivot=394, foot_h=44,
        far_leg=[(0, 380), (76, 380), (80, 460), (84, 552), (88, 600), (90, 618), (0, 618)],
        near_arm=[(108, 228), (150, 212), (178, 238), (182, 420), (176, 462), (142, 462), (138, 426), (128, 414), (118, 330), (110, 280)],
        near_shoulder=(150, 240), near_hand=(156, 440),
        far_arm=[(0, 226), (26, 222), (27, 300), (34, 412), (8, 412), (0, 350)],
        far_shoulder=(14, 240), far_hand=(22, 395)),
    "holly_sw": dict(
        file="holly_sw_source.png", white_bg=False, fwd=(-2, 1), arm_key="skin",
        hem=[(0, 440), (40, 452), (57, 460), (78, 468), (95, 462), (105, 455), (140, 458), (201, 440)],
        pivot=410, foot_h=80,
        far_leg=[(0, 440), (103, 440), (103, 550), (95, 556), (80, 573), (66, 588), (58, 600), (50, 612), (0, 612)],
        near_arm=[(116, 214), (150, 202), (168, 250), (168, 330), (160, 380), (158, 428), (118, 428), (121, 370), (128, 300), (121, 262)],
        near_shoulder=(146, 222), near_hand=(138, 405),
        far_arm=[(12, 208), (46, 202), (50, 250), (44, 296), (18, 300), (12, 262)],
        far_shoulder=(30, 215), far_hand=(28, 330)),
    "holly_ne": dict(
        file="holly_ne_source.png", white_bg=True, fwd=(2, -1), arm_key="skin",
        hem=[(0, 445), (50, 465), (95, 472), (115, 478), (160, 480), (219, 460)],
        pivot=412, foot_h=74,
        far_leg=[(0, 440), (108, 440), (110, 530), (120, 545), (118, 560), (113, 580), (108, 600), (106, 622), (0, 622)],
        near_arm=[(132, 214), (176, 198), (204, 240), (208, 330), (212, 400), (209, 455), (170, 455), (166, 380), (153, 310), (138, 262)],
        near_shoulder=(170, 225), near_hand=(190, 430),
        far_arm=[(38, 188), (72, 178), (78, 250), (72, 334), (46, 334), (40, 262)],
        far_shoulder=(56, 195), far_hand=(60, 320)),
}

# Facings built from each source; the other two are mirror images.
CHARS = {
    "archie": dict(sources={"se": "archie_se", "ne": "archie_ne"}, mirror={"sw": "se", "nw": "ne"},
                   stride=22, lift=7, bob=2.2, lean=2.5, arm=9),
    "holly": dict(sources={"sw": "holly_sw", "ne": "holly_ne"}, mirror={"se": "sw", "nw": "ne"},
                  stride=18, lift=6, bob=2.0, lean=2.0, arm=8),
}


# ----------------------------------------------------------------- helpers
def poly_mask(shape, pts, feather=0.0):
    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=255)
    if feather:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(m, np.float32) / 255.0


def hem_mask(shape, pts):
    """1 above the hem line (the body), 0 below (the legs)."""
    xs, ys = zip(*pts)
    yh = np.interp(np.arange(shape[1]), xs, ys)
    return (np.arange(shape[0])[:, None] < yh[None, :]).astype(np.float32)


def premul(img):
    a = np.asarray(img.convert("RGBA"), np.float32) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a


def unpremul_image(arr):
    a = arr[..., 3:4]
    rgb = np.where(a > 1e-4, arr[..., :3] / np.maximum(a, 1e-4), 0)
    out = np.concatenate([rgb, a], axis=2)
    return Image.fromarray(np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), "RGBA")


def sample(src, sx, sy):
    """Bilinear sample of a premultiplied HxWx4 array at float coords
    (outside = transparent)."""
    h, w = src.shape[:2]
    pad = np.zeros((h + 2, w + 2, 4), np.float32)
    pad[1:-1, 1:-1] = src
    x = np.clip(sx + 1, 0, w + 0.999)
    y = np.clip(sy + 1, 0, h + 0.999)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, w + 1)
    y1 = np.minimum(y0 + 1, h + 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    out = (pad[y0, x0] * (1 - fx) * (1 - fy) + pad[y0, x1] * fx * (1 - fy)
           + pad[y1, x0] * (1 - fx) * fy + pad[y1, x1] * fx * fy)
    outside = (sx < -1) | (sx > w) | (sy < -1) | (sy > h)
    out[outside] = 0
    return out


def over(dst, src):
    return src + dst * (1 - src[..., 3:4])


def diffuse_fill(arr, hole, iters=160, firm=True):
    """Fill hole pixels (premultiplied RGBA) by repeated neighbour averaging,
    at half resolution for speed, so a part can be lifted off cleanly."""
    h, w = hole.shape
    out = arr.copy()
    small = np.asarray(Image.fromarray((hole * 255).astype(np.uint8)).resize((w // 2, h // 2), Image.BILINEAR),
                       np.float32) / 255 > 0.02
    lo = np.stack([np.asarray(Image.fromarray(arr[..., c]).resize((w // 2, h // 2), Image.BILINEAR))
                   for c in range(4)], axis=2)
    known = ~small
    val = np.where(known[..., None], lo, 0)
    wgt = known.astype(np.float32)
    v, wt = val.copy(), wgt.copy()
    for _ in range(iters):
        acc = np.zeros_like(v)
        cnt = np.zeros_like(wt)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            acc += np.roll(np.roll(v * wt[..., None], dy, 0), dx, 1)
            cnt += np.roll(np.roll(wt, dy, 0), dx, 1)
        grow = (~known) & (cnt > 0)
        v[grow] = acc[grow] / cnt[grow][:, None]
        wt = np.where(grow, 1.0, wt)
    up = np.stack([np.asarray(Image.fromarray(v[..., c].astype(np.float32)).resize((w, h), Image.BILINEAR))
                   for c in range(4)], axis=2)
    if firm:
        # a crisp silhouette where the fill meets the background
        a = up[..., 3:4]
        na = np.clip((a - 0.35) / 0.3, 0, 1)
        na = na * na * (3 - 2 * na)
        up = np.where(a > 1e-4, up / np.maximum(a, 1e-4), 0) * na
        up[..., 3:4] = na
    m = hole[..., None]
    return out * (1 - m) + up * m


def texture_fill(filled, src, hole, cx):
    """Give a filled-in gap real texture (the dress pattern, the hoodie) by
    copying the pixels just beside it, on the side towards the middle of the
    figure; the outline (alpha) comes from the diffused fill."""
    out = filled.copy()
    h, w = hole.shape
    hm = hole > 0.5
    a_src = src[..., 3]
    for y in range(h):
        row = hm[y]
        if not row.any():
            continue
        xs = np.nonzero(row)[0]
        runs = np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1)
        for run in runs:
            x0, x1 = run[0], run[-1] + 1
            n = x1 - x0
            sx = run - n if (x0 + x1) / 2 > cx else run + n
            ok = (sx >= 0) & (sx < w)
            run, sx = run[ok], sx[ok]
            good = (a_src[y, sx] > 0.9) & ~hm[y, sx]
            run, sx = run[good], sx[good]
            if len(run) == 0:
                continue
            col = src[y, sx, :3] / np.maximum(a_src[y, sx, None], 1e-3)
            out[y, run, :3] = col * filled[y, run, 3:4]
    m = hole[..., None]
    return filled * (1 - m) + out * m


def extend_up(layer, rows=48, reach=24):
    """Continue a leg's top edge upwards (hidden under the body) so no gap
    opens at the hip when the leg swings. Only columns whose leg starts at
    the hem (not ones holding just a toe) are extended."""
    a = layer[..., 3]
    out = layer.copy()
    h, w = a.shape
    tops = [np.nonzero(a[:, x] > 0.6)[0] for x in range(w)]
    first = min((c[0] for c in tops if len(c)), default=0)
    for x in range(w):
        col = tops[x]
        if len(col) == 0 or col[0] > first + reach:
            continue
        top = col[0]
        src = layer[min(top + 2, h - 1), x]
        lo = max(0, top - rows)
        out[lo:top, x] = np.where(out[lo:top, x, 3:4] < src[3], src, out[lo:top, x])
    return out


def skin_key(src, region):
    """Narrow an arm outline down to the bare arm: skin-coloured pixels
    inside it, holes closed, grown a little to take in the line art."""
    a = src[..., 3]
    rgb = np.where(a[..., None] > 1e-3, src[..., :3] / np.maximum(a[..., None], 1e-3), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    skin = (r - b > 0.12) & (r > 0.45) & ((r + g + b) / 3 > 0.42) & (region > 0.5) & (a > 0.5)
    img = Image.fromarray((skin * 255).astype(np.uint8))
    img = img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))   # close small holes
    img = img.filter(ImageFilter.MaxFilter(5))                                     # take in the outline
    m = np.asarray(img, np.float32) / 255 * (region > 0.5)
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)),
                      np.float32) / 255


# ------------------------------------------------------------------ parts
class Parts:
    def __init__(self, key):
        cfg = SOURCES[key]
        self.cfg = cfg
        im = defringe(Image.open(os.path.join(ART, cfg["file"])), white_bg=cfg["white_bg"])
        im = im.crop(im.split()[3].getbbox())
        w = round(im.width * WORK_H / im.height)
        im = im.convert("RGBa").resize((w, WORK_H), Image.LANCZOS, reducing_gap=3.0).convert("RGBA")
        src = premul(im)
        self.h, self.w = WORK_H, w
        shape = (self.h, self.w)
        f = np.array(cfg["fwd"], np.float32)
        self.fwd = f / np.linalg.norm(f)

        if "clear_white" in cfg:
            zone = poly_mask(shape, cfg["clear_white"]) > 0.5
            rgb = np.where(src[..., 3:4] > 1e-3, src[..., :3] / np.maximum(src[..., 3:4], 1e-3), 0)
            white = zone & (rgb.min(2) > 0.80)
            soft = zone & (rgb.min(2) > 0.62) & ~white
            src[white] = 0
            src[soft] *= 0.35
        hem = hem_mask(shape, cfg["hem"])
        near_arm = poly_mask(shape, cfg["near_arm"], 0.8)
        far_arm = poly_mask(shape, cfg["far_arm"], 0.8)
        if cfg.get("arm_key") == "skin":
            near_arm = skin_key(src, near_arm)
            far_arm = skin_key(src, far_arm)
        arms = np.maximum(near_arm, far_arm)
        self.near_arm = src * near_arm[..., None]
        self.far_arm = src * far_arm[..., None]
        self.far_arm[..., :3] *= FAR_ARM_SHADE

        def grow(m, n=7):
            img = Image.fromarray(((m > 0.5) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(n))
            return np.asarray(img, np.float32) / 255
        inside = (src[..., 3] > 0.02).astype(np.float32)
        hole = grow(arms) * inside   # only where the figure was: no fill outside it
        # Body (head, torso) with the arms lifted off and the gap filled in.
        body_src = src * (hem * (1 - arms))[..., None]
        self.body = texture_fill(diffuse_fill(body_src, hole * hem), body_src, hole * hem, w / 2)
        # Legs, with any part a hand covered filled in from the leg around it.
        legs = (1 - hem)
        far = poly_mask(shape, cfg["far_leg"], 0.7)
        leg_hole = hole * legs
        self.near_leg = diffuse_fill(src * (legs * (1 - far) * (1 - arms))[..., None], leg_hole * (1 - far))
        self.far_leg = diffuse_fill(src * (legs * far * (1 - arms))[..., None], leg_hole * far)
        # Legs: rest geometry (sole, foot centre) from the layers themselves.
        self.legs = {}
        for name, layer in (("near", self.near_leg), ("far", self.far_leg)):
            a = layer[..., 3]
            rows = np.nonzero(a.max(1) > 0.5)[0]
            sole = float(rows[-1])
            band = a[int(sole - cfg["foot_h"]):int(sole) + 1]
            xs = np.nonzero(band.max(0) > 0.5)[0]
            self.legs[name] = dict(sole=sole, ankle=sole - cfg["foot_h"], foot_x=float((xs[0] + xs[-1]) / 2))
        self.near_leg = extend_up(self.near_leg)
        self.far_leg = extend_up(self.far_leg)
        self.far_leg[..., :3] *= np.array(FAR_SHADE, np.float32)
        self.ground = ((self.legs["near"]["foot_x"] + self.legs["far"]["foot_x"]) / 2,
                       (self.legs["near"]["sole"] + self.legs["far"]["sole"]) / 2)


def leg_motion(psi, a, lift):
    """Foot offset along the walking direction, its lift, and knee push, for
    a leg at cycle phase psi (0 = heel strike with the foot forward)."""
    psi %= 1.0
    if psi < STANCE:
        u = psi / STANCE
        return a * (1 - 2 * u), 0.0, 0.0
    u = (psi - STANCE) / (1 - STANCE)
    e = u * u * (3 - 2 * u)
    return -a + 2 * a * e, lift * math.sin(math.pi * u) ** 0.9, math.sin(math.pi * u)


def pose(parts, phi, ch, ox, oy, cw, chh):
    """Render one frame (work size) at cycle phase phi; None = standing."""
    cfg = parts.cfg
    ux, uy = parts.fwd
    yy, xx = np.mgrid[0:chh, 0:cw].astype(np.float32)
    canvas = np.zeros((chh, cw, 4), np.float32)
    walking = phi is not None
    feet = {}
    if walking:
        bob = ch["bob"] * K * math.cos(4 * math.pi * phi)     # +down: lowest at heel strikes (0, 0.5)
        lean = ch["lean"] * K
        legs_state = {"near": leg_motion(phi, ch["stride"] * K, ch["lift"] * K),
                      "far": leg_motion(phi + 0.5, ch["stride"] * K, ch["lift"] * K)}
    else:
        bob, lean = 0.0, 0.0
        legs_state = {"near": (0.0, 0.0, 0.0), "far": (0.0, 0.0, 0.0)}

    def leg_layer(name, layer):
        g = parts.legs[name]
        d, lift, knee = legs_state[name]
        fx, fy = d * ux, d * uy
        yp = cfg["pivot"]
        ya = g["ankle"]
        yp_o = yp + bob
        ya_o = ya + fy - lift
        Y = yy - oy
        X = xx - ox
        t = np.clip((Y - yp_o) / max(1.0, ya_o - yp_o), 0, None)
        upper = Y <= ya_o
        sy_up = np.where(Y < yp_o, Y - bob, yp + t * (ya - yp))
        kneex = knee * 0.22 * ch["stride"] * K * ux * np.sin(np.pi * np.clip(t, 0, 1))
        kneey = knee * 0.10 * ch["stride"] * K * np.sin(np.pi * np.clip(t, 0, 1))
        sx_up = X - (fx * np.clip(t, 0, 1) + kneex)
        sy_up = sy_up - kneey * 0
        sy_lo = Y - (fy - lift)
        sx_lo = X - fx
        sx = np.where(upper, sx_up, sx_lo)
        sy = np.where(upper, sy_up, sy_lo)
        feet[name] = dict(x=(g["foot_x"] + fx + ox), y=(g["sole"] + fy - lift + oy), lift=lift / K,
                          down=lift <= 1e-6)
        return sample(layer, sx, sy)

    canvas = over(canvas, leg_layer("far", parts.far_leg))
    canvas = over(canvas, leg_layer("near", parts.near_leg))

    # Body: bob, lean (more at the head), far arm warped in place.
    Y = yy - oy - bob
    X = xx - ox
    hfrac = np.clip((cfg["pivot"] - Y) / cfg["pivot"], 0, 1)
    X = X - lean * hfrac * ux
    near_d = legs_state["near"][0]
    far_d = legs_state["far"][0]
    arm_px = ch["arm"] * K
    a_max = ch["stride"] * K
    body = sample(parts.body, X, Y)
    # arms: their own layers, each swinging opposite the leg on its side;
    # the far one is darker and swings less (it is partly behind the body)
    arm_layers = []
    for side, d, amt in (("far", far_d, 0.7), ("near", near_d, 1.0)):
        sh, hd = cfg[side + "_shoulder"], cfg[side + "_hand"]
        sw = -d / a_max * arm_px * amt if walking else 0.0
        tt = np.clip((Y - sh[1]) / (hd[1] - sh[1]), 0, 1)
        arm_layers.append(sample(getattr(parts, side + "_arm"), X - tt * sw * ux, Y - tt * sw * uy * 0.6))
    canvas = over(canvas, body)
    for arm in arm_layers:
        canvas = over(canvas, arm)
    return canvas, feet


def downscale(arr, sharpen=60):
    img = unpremul_image(arr)
    w = round(img.width / K)
    h = round(img.height / K)
    small = img.convert("RGBa").resize((w, h), Image.LANCZOS, reducing_gap=3.0).convert("RGBA")
    if sharpen:
        rgb = small.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.0, percent=sharpen, threshold=1))
        small = Image.merge("RGBA", (*rgb.split(), small.split()[3]))
    return small


def build(name, debug=None):
    ch = CHARS[name]
    pad_x = int((ch["stride"] + 14) * K)
    pad_top, pad_bot = int(10 * K), int(16 * K)
    results = {}
    for facing, key in ch["sources"].items():
        parts = Parts(key)
        if debug:
            for lname in ("near_leg", "far_leg", "body", "near_arm"):
                unpremul_image(getattr(parts, lname)).save(os.path.join(debug, f"{key}_{lname}.png"))
        cw, chh = parts.w + 2 * pad_x, WORK_H + pad_top + pad_bot
        # keep the canvas a multiple of K so the downscale is exact
        cw += (-cw) % int(K)
        chh += (-chh) % int(K)
        ox, oy = (cw - parts.w) // 2, pad_top
        ox -= ox % int(K)
        frames, feet = [], []
        stand, rest = pose(parts, None, ch, ox, oy, cw, chh)
        for i in range(FRAMES):
            arr, ft = pose(parts, i / FRAMES, ch, ox, oy, cw, chh)
            frames.append(downscale(arr))
            feet.append({k: dict(x=round(float(v["x"]) / K, 2), y=round(float(v["y"]) / K, 2), lift=round(float(v["lift"]), 2),
                                 down=bool(v["down"])) for k, v in ft.items()})
        gx, gy = parts.ground
        rest = {k: dict(x=round(float(v["x"]) / K, 2), y=round(float(v["y"]) / K, 2), lift=0.0, down=True)
                for k, v in rest.items()}
        results[facing] = dict(stand=downscale(stand), frames=frames, feet=feet, rest=rest,
                               anchor=(float(gx + ox) / K, float(gy + oy) / K))
    # mirrored facings
    for facing, srcf in ch["mirror"].items():
        r = results[srcf]
        W = r["stand"].width
        results[facing] = dict(
            stand=r["stand"].transpose(Image.FLIP_LEFT_RIGHT),
            frames=[f.transpose(Image.FLIP_LEFT_RIGHT) for f in r["frames"]],
            feet=[{k: dict(v, x=round(W - v["x"], 2)) for k, v in ft.items()} for ft in r["feet"]],
            rest={k: dict(v, x=round(W - v["x"], 2)) for k, v in r["rest"].items()},
            anchor=(W - r["anchor"][0], r["anchor"][1]))
    # Crop everything to one shared box so all facings share a canvas size.
    boxes = [img.getbbox() for r in results.values() for img in [r["stand"], *r["frames"]]]
    W0 = max(r["stand"].width for r in results.values())
    l = min(b[0] for b in boxes) - 2
    t = min(b[1] for b in boxes) - 2
    rr = max(b[2] for b in boxes) + 2
    bb = max(b[3] for b in boxes) + 2
    meta = dict(frames=FRAMES, contacts={"near": 0, "far": FRAMES // 2}, stance=STANCE,
                cycle_tiles=round(2 * ch["stride"] / STANCE / TILE_PX, 4),
                size=[rr - l, bb - t], facings={})
    for facing, r in results.items():
        def crop(img):
            # results may differ in width (sources differ); centre on the same canvas first
            c = Image.new("RGBA", (W0, img.height), (0, 0, 0, 0))
            c.paste(img, (0, 0))
            return c.crop((l, t, rr, bb))
        stand = crop(r["stand"])
        sheet = Image.new("RGBA", ((rr - l) * FRAMES, bb - t), (0, 0, 0, 0))
        for i, f in enumerate(r["frames"]):
            sheet.paste(crop(f), (i * (rr - l), 0))
        stand.save(os.path.join(OUT, f"{name}_{facing}.png"))
        sheet.save(os.path.join(OUT, f"{name}_{facing}_walk.png"))
        meta["facings"][facing] = dict(
            anchor=[round(r["anchor"][0] - l, 2), round(r["anchor"][1] - t, 2)],
            rest={k: dict(v, x=round(v["x"] - l, 2), y=round(v["y"] - t, 2)) for k, v in r["rest"].items()},
            feet=[{k: dict(v, x=round(v["x"] - l, 2), y=round(v["y"] - t, 2)) for k, v in ft.items()}
                  for ft in r["feet"]])
    with open(os.path.join(OUT, f"{name}_walk.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"{name}: frame {rr - l}x{bb - t}, cycle {meta['cycle_tiles']} tiles")
    return meta


def main(argv):
    debug = None
    if "--debug" in argv:
        i = argv.index("--debug")
        debug = argv[i + 1]
        os.makedirs(debug, exist_ok=True)
        argv = argv[:i] + argv[i + 2:]
    for name in argv or list(CHARS):
        build(name, debug)


if __name__ == "__main__":
    main(sys.argv[1:])
