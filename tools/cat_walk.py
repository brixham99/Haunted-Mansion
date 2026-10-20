#!/usr/bin/env python3
"""The black cat's walk cycle, animated from one painted frame per view.

    python3 tools/cat_walk.py [--strip OUT.png]   (cut_anims.py runs it too)

The generated walk sheets (cat_e/se/ne/s/n.jpg) barely change between
frames, so the walk was hardly visible. Here each view's best frame is
split into layers: the body, each visible leg and (where it hangs free)
the tail. Each leg is a rectangle of the frame below its hip line (LEGS);
the rest is the body. Every frame then:

  * moves each foot along the view's direction of travel (TRAVEL): on the
    ground for STANCE of the cycle, sliding back at exactly the speed the
    body moves over the floor (so nothing skates when the game advances a
    frame every cat.WALK_FRAME_D tiles), then lifted and swung forward.
    Diagonal pairs move together (PHASE 0 / 0.5): back-left with
    front-right, and so on. The leg layer is warped with the affine map
    that keeps the hip fixed and takes the foot to its new place (a shear
    along the leg: the painting is kept, nothing redrawn);
  * raises the body (and the hips) by BOB at the two passing moments,
    the stance legs stretching to keep their feet planted;
  * swings the tail a few degrees about its root.

Writes assets/art/cat_<view>_<n>.png (n = 1..FRAMES) on the canvas the
cut gave (same size and anchor: the feet line is untouched) and sets
"frames" in anims.json.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import cut_anims as CA  # noqa: E402
import cut_sheets as CS  # noqa: E402

FRAMES = 6
CYCLE_TILES = 0.5          # tiles walked per full cycle (cat.WALK_FRAME_D = CYCLE_TILES / FRAMES)
STANCE = 0.6               # share of the cycle a foot is on the ground
HW, HH = 56, 28            # half a floor tile on screen (game px)
# screen direction of travel and game px per tile walked, for each view
TRAVEL = {"cat_e": ((1, 0), HW * math.sqrt(2)), "cat_se": ((2, 1), math.hypot(HW, HH)),
          "cat_ne": ((2, -1), math.hypot(HW, HH)), "cat_s": ((0, 1), HH * math.sqrt(2)),
          "cat_n": ((0, -1), HH * math.sqrt(2))}
# legs: ([(x0, x1, y0, y1), ...], phase): the rectangles (canvas px of the cut
# base frame, index 1) that make up each leg; the first one's top is the hip line
LEGS = {
    "cat_e": [([(0, 84, 190, 999)], 0.0), ([(84, 150, 190, 999)], 0.5),
              ([(150, 207, 190, 999)], 0.0), ([(207, 999, 190, 999)], 0.5)],
    "cat_se": [([(0, 62, 228, 999)], 0.0), ([(62, 150, 242, 999)], 0.5),
               ([(150, 182, 252, 999)], 0.0), ([(182, 999, 252, 999)], 0.5)],
    "cat_ne": [([(122, 151, 352, 400), (110, 175, 400, 999)], 0.0), ([(151, 186, 352, 400)], 0.5),
               ([(190, 999, 266, 999)], 0.0)],
    "cat_s": [([(0, 87, 392, 505), (0, 96, 505, 999)], 0.0), ([(87, 999, 392, 505), (96, 999, 505, 999)], 0.5)],
    "cat_n": [([(100, 142, 398, 450), (100, 999, 450, 999)], 0.0), ([(142, 999, 346, 450)], 0.5)],
}
TAIL_KEEP = 14             # px of the tail's root left on the body (the swung tail goes behind it)
# the tail: (x0, x1, y0, y1, root x, root y) where it hangs free of the body
TAIL = {"cat_e": (0, 120, 0, 100, 66, 104), "cat_se": (0, 110, 0, 118, 55, 120),
        "cat_ne": (0, 80, 355, 999, 84, 384), "cat_s": (0, 999, 0, 150, 88, 150),
        "cat_n": (0, 76, 320, 999, 78, 384)}
OVERLAP = 8                # px of each leg's top also drawn above its hip line (behind the body): no seam
BOB = 1.2                  # game px the body rises at each passing moment
LIFT = 3.0                 # game px a swinging paw is lifted
TAIL_DEG = 7.0
PAD_X = 30                 # canvas px added left and right: a paw swung back stays on the canvas


def layers(img, view):
    a = np.asarray(img).copy()
    h, w = a.shape[:2]
    taken = np.zeros((h, w), bool)
    out = []
    yy, xx = np.mgrid[0:h, 0:w]
    xx = xx - PAD_X                    # LEGS and TAIL are in the cut frame's coordinates
    for rects, ph in LEGS[view]:
        m = np.zeros((h, w), bool)
        for x0, x1, y0, y1 in rects:
            m |= (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
        m &= (a[..., 3] > 0) & ~taken
        y0 = rects[0][2]
        taken |= m
        cols = np.nonzero(m[y0:y0 + 3].any(0))[0]
        if len(cols):
            m = m | ((yy >= y0 - OVERLAP) & (yy < y0) & (xx >= cols.min()) & (xx <= cols.max()) & (a[..., 3] > 0))
        ys, xs = np.nonzero(m & (a[..., 3] > 128))
        top = xs[ys <= ys.min() + 4]
        hip = (float(top.mean()) + PAD_X, float(y0))
        low = ys >= ys.max() - 6
        foot = (float(xs[low].mean()) + PAD_X, float(ys.max()))
        lay = a.copy()
        lay[..., 3] = np.where(m, a[..., 3], 0)
        out.append(("leg", Image.fromarray(lay), hip, foot, ph))
    tx0, tx1, ty0, ty1, rx, ry = TAIL[view]
    m = (xx >= tx0) & (xx < tx1) & (yy >= ty0) & (yy < ty1) & (a[..., 3] > 0) & ~taken
    # the swung tail is drawn behind the body, which keeps the root
    near_root = np.hypot(xx - rx, yy - ry) < TAIL_KEEP
    taken |= m & ~near_root
    lay = a.copy()
    lay[..., 3] = np.where(m, a[..., 3], 0)
    tail = ("tail", Image.fromarray(lay), (rx + PAD_X, ry))
    body = a.copy()
    body[..., 3] = np.where(taken, 0, a[..., 3])
    return Image.fromarray(body), [l for l in out], tail


def affine(img, M, t):
    """Draw img through x' = M x + t (PIL wants the inverse)."""
    Mi = np.linalg.inv(M)
    ti = -Mi @ t
    return img.transform(img.size, Image.AFFINE, (Mi[0, 0], Mi[0, 1], ti[0], Mi[1, 0], Mi[1, 1], ti[1]),
                         resample=Image.BICUBIC)


def foot_offset(phase, stride):
    """Along-travel offset (canvas px, + = ahead) and lift of a foot."""
    if phase < STANCE:
        return stride / 2 - stride * phase / STANCE, 0.0
    u = (phase - STANCE) / (1 - STANCE)
    return -stride / 2 + stride * (0.5 - 0.5 * math.cos(math.pi * u)), math.sin(math.pi * u)


def make(view, base, k):
    """FRAMES frames for one view; k = game px per canvas px."""
    wide = Image.new("RGBA", (base.width + 2 * PAD_X, base.height), (0, 0, 0, 0))
    wide.alpha_composite(base, (PAD_X, 0))
    base = wide
    body, legs, tail = layers(base, view)
    (dx, dy), ppt = TRAVEL[view]
    n = math.hypot(dx, dy)
    u = np.array([dx / n, dy / n])
    stride = STANCE * CYCLE_TILES * ppt / k        # canvas px a planted foot slides back relative to the body
    frames = []
    for i in range(FRAMES):
        phi = i / FRAMES
        bob = BOB / k * (0.5 - 0.5 * math.cos(4 * math.pi * phi))
        canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
        up = np.array([0.0, -bob])
        # tail (behind the body)
        _, timg, (rx, ry) = tail
        ang = math.radians(TAIL_DEG * math.sin(2 * math.pi * phi))
        R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
        root = np.array([rx, ry])
        canvas.alpha_composite(affine(timg, R, root - R @ root + up))
        warped = []
        for _, limg, hip, foot, ph in legs:
            s, lift = foot_offset((phi + ph) % 1.0, stride)
            hip_v, foot_v = np.array(hip), np.array(foot)
            v = foot_v - hip_v
            # the foot's new place relative to the (raised) hip
            delta = u * s + np.array([0.0, -lift * LIFT / k]) + np.array([0.0, bob])
            M = np.eye(2) + np.outer(delta, v) / (v @ v)
            t = hip_v - M @ hip_v + up
            warped.append((foot_v[1] - lift, affine(limg, M, t)))
        for _, w in sorted(warped, key=lambda p: p[0]):    # the nearer (lower) feet over the far ones
            canvas.alpha_composite(w)
        canvas.alpha_composite(affine(body, np.eye(2), up))
        frames.append(canvas)
    return frames


def main(argv=()):
    meta_path = os.path.join(CS.OUT, "anims.json")
    meta = json.load(open(meta_path))
    out = {}
    for view in LEGS:
        sheet, ref, size = CA.SETS[view]
        frames = CA.cut_frames(sheet)
        frames, _anchor = CA.align(view, frames)
        base = frames[1]
        old_pad = meta[view].get("walk_pad", 0)
        k = meta[view]["size"][1] / base.height
        ax, ay = meta[view]["anchor"]
        ax -= old_pad * k
        new = make(view, base, k)
        for i, f in enumerate(new):
            f.save(os.path.join(CS.OUT, f"{view}_{i + 1}.png"))
        for j in range(FRAMES, 8):
            p = os.path.join(CS.OUT, f"{view}_{j + 1}.png")
            if os.path.exists(p) and j >= FRAMES:
                os.remove(p)
        meta[view]["frames"] = FRAMES
        meta[view]["size"] = [max(1, round(new[0].width * k)), meta[view]["size"][1]]
        meta[view]["anchor"] = [round(ax + PAD_X * k, 1), ay]
        meta[view]["walk_pad"] = PAD_X
        meta[view]["walk"] = "tools/cat_walk.py"
        out[view] = new
        print(f"{view}: {FRAMES} walk frames")
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=1)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
