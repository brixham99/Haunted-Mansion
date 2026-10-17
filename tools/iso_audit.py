#!/usr/bin/env python3
"""Measure how isometric each floor-standing sprite in assets/art/ is.

    python3 tools/iso_audit.py [OUTDIR]   (default /workspace/iso_audit)

For each furniture / flat / link sprite (drawn facing E: front = lower-right
face, side = lower-left face) it estimates the angle of the receding
horizontal edges two ways:
  * silhouette: robust line fits to the bottom outline either side of the
    lowest point (the footprint V) and to the top outline (the lid / cornice);
  * Canny + probabilistic Hough on colour+alpha edges, length-weighted
    histogram of segment angles, peak for "rising to the right" (front face
    edges) and "falling to the right" (side face edges), plus the share of
    edge length that is near-horizontal (front-on tell-tale).
True 2:1 isometric is atan(0.5) = 26.57 deg. Writes audit.csv and an overlay
image per sprite (ideal footprint diamond + 26.57 deg guide lines).
"""
import csv
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, HERE)
import objects as O  # noqa: E402

ISO = math.degrees(math.atan(0.5))
OUT = sys.argv[1] if len(sys.argv) > 1 else "/workspace/iso_audit"


def load(name):
    img = cv2.imread(os.path.join(HERE, "assets", "art", name + ".png"), cv2.IMREAD_UNCHANGED)
    a = img[:, :, 3]
    ys, xs = np.where(a > 8)
    img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    w, d = O.T[name]["size"]
    tw = (w + d) * O.TILE_W // 2 * 3          # measure at 3x game size
    k = tw / img.shape[1]
    return cv2.resize(img, (tw, max(1, round(img.shape[0] * k))), interpolation=cv2.INTER_AREA)


def robust_angle(xs, ys):
    """Angle (deg, + = rising to the right on screen) of a RANSAC-ish line fit."""
    if len(xs) < 8:
        return None
    pts = np.stack([xs, ys], 1).astype(np.float32)
    best, bestn = None, 0
    rng = np.random.default_rng(1)
    tol = max(2.0, 0.01 * (xs.max() - xs.min()))
    for _ in range(300):
        i, j = rng.choice(len(pts), 2, replace=False)
        p, q = pts[i], pts[j]
        if abs(q[0] - p[0]) < 0.15 * (xs.max() - xs.min()):
            continue
        m = (q[1] - p[1]) / (q[0] - p[0])
        r = np.abs(pts[:, 1] - (p[1] + m * (pts[:, 0] - p[0]))) / math.sqrt(1 + m * m)
        n = (r < tol).sum()
        if n > bestn:
            best, bestn = r < tol, n
    if best is None or bestn < 0.3 * len(pts):
        return None
    m, _ = np.polyfit(pts[best, 0], pts[best, 1], 1)
    return -math.degrees(math.atan(m))


def silhouette(img, name):
    a = img[:, :, 3] > 128
    H, W = a.shape
    cols = np.where(a.any(0))[0]
    bot = np.array([H - 1 - np.argmax(a[::-1, c]) for c in cols])
    top = np.array([np.argmax(a[:, c]) for c in cols])
    w, d = O.T[name]["size"]
    vx = d / (w + d) * W                       # expected lowest vertex
    # side (left of vertex) should fall to the right (-26.6), front rises (+26.6)
    margin = 0.08 * W
    L = (cols > margin) & (cols < vx - margin)
    R = (cols > vx + margin) & (cols < W - margin)
    res = {"bot_side": robust_angle(cols[L], bot[L]), "bot_front": robust_angle(cols[R], bot[R])}
    tx = cols[np.argmin(top)]
    L = (cols > margin) & (cols < tx - margin)
    R = (cols > tx + margin) & (cols < W - margin)
    res["top_left"] = robust_angle(cols[L], top[L])      # rising to the right (back-left edge)
    res["top_right"] = robust_angle(cols[R], top[R])     # falling to the right (back-right edge)
    return res


def hough(img):
    a = img[:, :, 3].astype(np.float32) / 255
    bgr = (img[:, :, :3].astype(np.float32) * a[:, :, None]).astype(np.uint8)
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    e = cv2.Canny(g, 40, 110) | cv2.Canny(img[:, :, 3], 50, 150)
    L = cv2.HoughLinesP(e, 1, np.pi / 360, 30, minLineLength=max(20, img.shape[1] // 12), maxLineGap=4)
    rise, fall, horiz, total = [], [], 0.0, 0.0
    segs = []
    if L is not None:
        for x1, y1, x2, y2 in L.reshape(-1, 4).tolist():
            dx, dy = x2 - x1, y2 - y1
            ln = math.hypot(dx, dy)
            ang = -math.degrees(math.atan2(dy, dx))
            if ang > 90:
                ang -= 180
            if ang < -90:
                ang += 180
            if abs(ang) > 60:          # verticals carry no depth information
                continue
            total += ln
            segs.append((x1, y1, x2, y2, ang))
            if abs(ang) < 6:
                horiz += ln
            elif ang > 0:
                rise.append((ang, ln))
            else:
                fall.append((-ang, ln))

    def peak(v):
        if not v:
            return None, 0.0
        ang = np.array([p[0] for p in v])
        wt = np.array([p[1] for p in v])
        h, edges = np.histogram(ang, bins=np.arange(6, 61, 2), weights=wt)
        i = int(np.argmax(h))
        sel = (ang >= edges[max(0, i - 1)]) & (ang < edges[min(len(edges) - 1, i + 2)])
        return float(np.average(ang[sel], weights=wt[sel])), float(wt.sum())

    pr, lr = peak(rise)
    pf, lf = peak(fall)
    return {"h_front": pr, "h_side": pf, "len_rise": lr, "len_fall": lf,
            "horiz_share": horiz / total if total else 0.0, "segs": segs, "edges": e}


def overlay(img, name, hres, path):
    a = img[:, :, 3:4].astype(np.float32) / 255
    base = (img[:, :, :3] * a + 40 * (1 - a)).astype(np.uint8)
    H, W = base.shape[:2]
    w, d = O.T[name]["size"]
    u = W / (w + d)
    vx = d * u
    pts = np.array([(0, H - 1 - w * u / 2), (vx, H - 1), (W - 1, H - 1 - d * u / 2), (W - 1 - vx, H - 1 - (w + d) * u / 2)], np.int32)
    out = base.copy()
    for x1, y1, x2, y2, ang in hres["segs"]:
        c = (0, 200, 255) if abs(abs(ang) - ISO) <= 4 else ((255, 80, 255) if abs(ang) < 6 else (0, 0, 255))
        cv2.line(out, (x1, y1), (x2, y2), c, 2)
    cv2.polylines(out, [pts], True, (0, 255, 0), 2)
    for y0 in range(0, H + W, 60):            # faint true-iso guides
        cv2.line(out, (0, y0), (W, y0 - W // 2), (90, 140, 90), 1)
    cv2.imwrite(path, np.concatenate([base, out], 1))


def fmt(v):
    return "" if v is None else f"{v:.1f}"


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for name, t in O.T.items():
        if t["kind"] not in ("furniture", "flat", "link"):
            continue
        if not os.path.exists(os.path.join(HERE, "assets", "art", name + ".png")):
            continue
        img = load(name)
        s = silhouette(img, name)
        h = hough(img)
        overlay(img, name, h, os.path.join(OUT, name + ".png"))
        rows.append(dict(name=name, size="%dx%d" % t["size"], h_px=t["h"],
                         sil_side=fmt(s["bot_side"] and -s["bot_side"]), sil_front=fmt(s["bot_front"]),
                         top_left=fmt(s["top_left"]), top_right=fmt(s["top_right"] and -s["top_right"]),
                         hough_front=fmt(h["h_front"]), hough_side=fmt(h["h_side"]),
                         len_front=round(h["len_rise"]), len_side=round(h["len_fall"]),
                         horiz_share=f"{h['horiz_share']:.2f}"))
    with open(os.path.join(OUT, "audit.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, rows[0].keys())
        wr.writeheader()
        wr.writerows(rows)
    keys = list(rows[0].keys())
    print(" ".join(f"{k:>11}" for k in keys))
    for r in rows:
        print(" ".join(f"{str(r[k]):>11}" for k in keys))


if __name__ == "__main__":
    main()
