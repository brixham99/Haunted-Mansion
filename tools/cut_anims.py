#!/usr/bin/env python3
"""Cut the enemy animation sheets into aligned frames.

    python3 tools/cut_anims.py [--strips DIR]   # DIR: also write frame strips for review

Sheets (tools/art/sheets/, white background, four frames left to right):
  bat_flap.jpg       wings up, wings outstretched, wings down, wings folded
  skeleton_walk.jpg  stride, legs together, other stride, jolt
  vampire.jpg        hovering: cape flared, settled, flared, settled
  mummy_se/ne.jpg    the mummy's shamble, front and back 3/4 (arms out)
  cat_se/ne/e/s/n.jpg the black cat's walk in five views (mirrored: eight)
  cat_poses.jpg      sit, hiss, curled up asleep, welcome stretch (front 3/4)
  cat_poses_back.jpg sit, tail flick, bristling, bristling (from behind)

Background and soft edges use the same cutter as cut_sheets.py (border
flood fill, enclosed flat-white pockets such as the gaps between the bat's
wing fingers and between the skeleton's bones/legs/coat tatters count as
background, soft alpha with the white unmixed), then cut_sheets.defringe(): the rim
takes the colour of the paint just inside it, so JPEG ringing leaves no
pale dotted outline on the dark floors, and one-pixel specks are dropped.

Alignment, on one canvas per set (every frame the same size; anims.json
records the anchor point in in-game pixels):
  bat:      the body centre (the red eyes, a little lower) fixed in all frames
  skeleton: the boot soles on one ground line; the upper body (hat, skull,
            chest) centred horizontally
  vampire:  the head and shoulders centred horizontally and the top of the
            head on one line (the cape and the dangling feet move); the
            anchor is under the body, where its feet hang (median height)

Writes assets/art/<set>_<n>.png (n = 1..4) and assets/art/anims.json with
the canvas size each set is drawn at in the game, chosen so that the sprite
matches the old single image: the bat's outstretched frame as wide as the
old bat (108 px), the skeleton's legs-together frame as tall as the old
skeleton (165 px), now 20% taller (SKELETON_H 198 px).
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cut_sheets as CS  # noqa: E402

OUT = CS.OUT
# The skeleton is drawn 20% taller than the old single sprite (165 px), so it
# stands clearly over Archie and Holly (159 px); game.SKEL_FRAME_D scales too.
SKELETON_H = 198
MUMMY_H = 188             # a little shorter than the skeleton, hunched
VAMPIRE_H = 196            # about the skeleton's height: he looms over Archie and Holly
SETS = {
    # name: (sheet, reference frame index, ("w" | "h", in-game px of the reference frame))
    "bat": ("bat_flap.jpg", 1, ("w", 108)),
    "skeleton_walk": ("skeleton_walk.jpg", 1, ("h", SKELETON_H)),
    "vampire": ("vampire.jpg", 1, ("h", VAMPIRE_H)),
    # the Lumber Room mummy: front 3/4 (walking to the lower right) and back 3/4
    # (to the upper right); the game mirrors them for the other two directions
    "mummy_se": ("mummy_se.jpg", 1, ("h", MUMMY_H)),
    "mummy_ne": ("mummy_ne.jpg", 1, ("h", MUMMY_H)),
    # the black cat: five walking views (mirrored in the game for eight
    # directions) and its poses: sit, hiss, curled up asleep, welcome stretch
    "cat_se": ("cat_se.jpg", 1, ("h", 74)),
    "cat_ne": ("cat_ne.jpg", 1, ("h", 76)),
    "cat_e": ("cat_e.jpg", 1, ("w", 92)),
    "cat_s": ("cat_s.jpg", 1, ("h", 76)),
    "cat_n": ("cat_n.jpg", 1, ("h", 74)),
    "cat_poses": ("cat_poses.jpg", 0, ("h", 70)),
    # seen from behind, facing the upper right: sit, sit (tail flicked), bristling, bristling
    "cat_poses_back": ("cat_poses_back.jpg", 0, ("h", 68)),
}
HOLE_FLAT = 0.2            # the gaps between bones, coat and arm, wing fingers: small pockets of noisy JPEG white
PAD = 6


def cut_frames(sheet):
    rgb = np.asarray(Image.open(os.path.join(CS.SHEETS, sheet)).convert("RGB")).astype(np.float64)
    bg, d = CS.background(rgb, HOLE_FLAT)
    fg = ~bg
    names = [f"f{i}" for i in range(4)]
    frames = []
    for _name, box, mask in CS.find_items(fg, [names]):
        img = CS.defringe(CS.cut_item(rgb, d, mask, box))
        frames.append(CS.harmonise(img))
    return frames


def clean_tips(img, below=0.45):
    """The cape tatters' points and the boot tips end in a pale pixel or two
    (the sheet's white caught in the JPEG): in the lower part of the frame,
    pale grey pixels within 2 px of the outline take the colour of the dark
    paint next to them (dropped if there is none). Shine inside the boots,
    away from the edge, stays."""
    a = np.asarray(img).astype(np.float64).copy()
    h, w = a.shape[:2]
    rgb, al = a[..., :3], a[..., 3]
    L = rgb.mean(2)
    sat = rgb.max(2) - rgb.min(2)
    clear = np.asarray(Image.fromarray(((al < 40) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    pale = (al > 0) & (L > 100) & (sat < 60) & clear
    pale[: int(h * below)] = False
    ys, xs = np.nonzero(pale)
    for y, x in zip(ys, xs):
        y0, y1, x0, x1 = max(0, y - 3), min(h, y + 4), max(0, x - 3), min(w, x + 4)
        nb = (al[y0:y1, x0:x1] > 200) & (L[y0:y1, x0:x1] < 90)
        if nb.any():
            rgb[y, x] = np.median(rgb[y0:y1, x0:x1][nb], axis=0)
        else:
            al[y, x] = 0
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA")


def clear_pockets(img, min_px=30):
    """Sheet white caught in small enclosed gaps (between the mummy's arms
    and a dangling bandage): near-white, unsaturated blobs of at least
    min_px become transparent (feathered by a pixel). The bandages are a
    warm beige, well away from that white."""
    import cv2
    a = np.asarray(img).astype(np.float64).copy()
    rgb, al = a[..., :3], a[..., 3]
    white = (rgb.min(2) > 226) & (rgb.max(2) - rgb.min(2) < 16) & (al > 0)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(white.astype(np.uint8), connectivity=4)
    kill = np.zeros_like(white)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_px:
            kill |= lab == i
    if kill.any():
        grow = cv2.dilate(kill.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        al[grow & ~kill] *= 0.5
        al[kill] = 0
        a = CS.defringe(Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA"))
        return a
    return img


def eye_centre(img):
    a = np.asarray(img).astype(np.float64)
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    red = (al > 200) & (r > 150) & (r > 2.2 * g) & (r > 2.2 * b)
    ys, xs = np.nonzero(red)
    if len(xs) < 3:
        raise ValueError("no red eyes found")
    return xs.mean(), ys.mean()


def upper_centre_and_feet(img):
    al = np.asarray(img)[..., 3] > 128
    ys, xs = np.nonzero(al)
    top, bot = ys.min(), ys.max()
    upper = al[top:top + int((bot - top) * 0.45)]
    uy, ux = np.nonzero(upper)
    return ux.mean(), bot


def align(name, frames):
    """Anchors -> one canvas; returns the frames on it and the anchor point
    on that canvas (the bat's body centre, the skeleton's feet)."""
    if name == "bat":
        anchors = []
        for f in frames:
            ex, ey = eye_centre(f)
            anchors.append((ex, ey + 18))          # the body centre, a little below the eyes
    elif name == "vampire":
        tops = []
        for f in frames:
            al = np.asarray(f)[..., 3] > 128
            ys, xs = np.nonzero(al)
            top, bot = ys.min(), ys.max()
            head = al[top:top + int((bot - top) * 0.22)]       # head, collar and shoulders
            hy, hx = np.nonzero(head)
            tops.append((hx.mean(), top, bot - top))
        body = float(np.median([t[2] for t in tops]))
        anchors = [(x, top + body) for x, top, _ in tops]
    else:
        anchors = [upper_centre_and_feet(f) for f in frames]
    left = max(ax for ax, _ in anchors)
    right = max(f.width - ax for f, (ax, _) in zip(frames, anchors))
    up = max(ay for _, ay in anchors)
    down = max(f.height - ay for f, (_, ay) in zip(frames, anchors))
    W, H = int(np.ceil(left + right)) + 2 * PAD, int(np.ceil(up + down)) + 2 * PAD
    if name == "skeleton_walk" or name.startswith(("mummy", "cat")):
        H = int(np.ceil(up)) + 2 * PAD          # feet (the anchor) on the bottom edge, less the pad
    out = []
    anchor = (PAD + left, H - PAD if name == "skeleton_walk" or name.startswith(("mummy", "cat")) else PAD + up)
    for f, (ax, ay) in zip(frames, anchors):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        c.alpha_composite(f, (int(round(PAD + left - ax)), int(round(PAD + up - ay))))
        out.append(c)
    return out, anchor


def main(argv):
    strips = argv[argv.index("--strips") + 1] if "--strips" in argv else None
    meta = {}
    for name, (sheet, ref, (dim, px)) in SETS.items():
        frames = cut_frames(sheet)
        if name == "vampire":
            frames = [clean_tips(f) for f in frames]
        if name.startswith("mummy"):
            frames = [clear_pockets(f) for f in frames]
        frames, anchor = align(name, frames)
        bb = frames[ref].split()[3].getbbox()
        ref_px = (bb[2] - bb[0]) if dim == "w" else (bb[3] - bb[1])
        k = px / ref_px
        W, H = frames[0].size
        size = [max(1, round(W * k)), max(1, round(H * k))]
        for i, f in enumerate(frames):
            f.save(os.path.join(OUT, f"{name}_{i + 1}.png"))
        meta[name] = {"frames": len(frames), "size": size, "sheet": sheet,
                      # in-game px from the top-left: the bat's body centre, the skeleton's feet,
                      # the vampire's hanging feet
                      "anchor": [round(anchor[0] * k, 1), round(anchor[1] * k, 1)]}
        print(f"{name}: {len(frames)} frames, canvas {W}x{H} -> in game {size[0]}x{size[1]}")
        if strips:
            strip(name, frames, size, anchor, os.path.join(strips, f"{name}_strip.png"))
    with open(os.path.join(OUT, "anims.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    import cat_walk                      # the cat's walk: six frames per view from one painted frame
    cat_walk.main()


LABELS = {"bat": ("1 wings up", "2 outstretched", "3 wings down", "4 folded"),
          "skeleton_walk": ("1 stride", "2 legs together", "3 other stride", "4 jolt"),
          "vampire": ("1 cape flared", "2 settled", "3 flared", "4 settled"),
          "cat_poses": ("1 sit", "2 hiss", "3 curled up", "4 welcome stretch"),
          "cat_poses_back": ("1 sit", "2 tail flick", "3 bristling", "4 bristling")}


def strip(name, frames, size, anchor, path):
    """Review strip: each frame at twice its in-game size, on a dark and a
    light floor, with a guide through the anchor (the bat's body centre,
    the skeleton's ground line) and the frame names."""
    k = 2 * size[0] / frames[0].width
    ax, ay = anchor[0] * k, anchor[1] * k
    cells = []
    for i, f in enumerate(frames):
        g = f.resize((size[0] * 2, size[1] * 2), Image.LANCZOS)
        cell = Image.new("RGB", (g.width + 20, g.height * 2 + 52), (40, 34, 44))
        dr = ImageDraw.Draw(cell)
        dr.rectangle([0, g.height + 15, cell.width, g.height * 2 + 30], fill=(200, 196, 186))
        for y0 in (5, g.height + 20):
            dr.line([(0, y0 + ay), (cell.width, y0 + ay)], fill=(0, 170, 230), width=1)
            dr.line([(10 + ax, y0), (10 + ax, y0 + g.height)], fill=(0, 170, 230), width=1)
        cell.paste(g, (10, 5), g)
        cell.paste(g, (10, g.height + 20), g)
        dr.text((10, g.height * 2 + 36), LABELS.get(name, ("",) * 4)[i], fill=(230, 225, 215))
        cells.append(cell)
    W = sum(c.width for c in cells)
    out = Image.new("RGB", (W, cells[0].height), (40, 34, 44))
    x = 0
    for c in cells:
        out.paste(c, (x, 0))
        x += c.width
    out.save(path)


if __name__ == "__main__":
    main(sys.argv[1:])
