#!/usr/bin/env python3
"""Render the WHOLE Haunted Mansion as one exploded isometric picture
(a doll's-house cutaway), for reference only - the game does not use it.

It uses the real data and the real drawing code:
  * rooms, sizes, furniture, wall hangings, doors and floor links come from
    mansion.py (Mansion());
  * each room is drawn by the game's own Game.build_background (floor,
    thresholds, walls, doorways, hangings) and Game.blit_footprint /
    draw_floor_shadow (furniture sprites from assets/art), depth-sorted with
    game.depth_sort, at full game scale; the whole picture is then scaled.

Layout: every room has a `map` cell on its floor's grid (N/S/E/W doors join
grid neighbours), so the plan is the real one. Columns and rows are sized to
the largest room in them (over all floors, so the floors line up), rooms sit
centred in their cell with a small gap, and short floor strips join each
pair of doorways. The floor grids are independent in the data, so each floor
is shifted by whole cells to put its main stair over the one below:
first floor +1 column (Staircase Hall -> Landing), basement +1/+1 (Kitchen
-> Cellar Passage), loft +1/+1 (Upper Corridor -> Loft Landing). Walls are
cut down to CUT_H so the interiors show; floors are raised ('exploded')
just enough not to overlap. Stairs, ladders and trapdoors are joined by
dotted lines.

    python3 tools/house_render.py [--out /workspace/hm_house_iso.png]
        [--small /workspace/hm_house_iso_small.png] [--width 5000]
        [--floors-dir /workspace]     # also one PNG per floor
"""
import argparse
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import game as G  # noqa: E402
import mansion as M  # noqa: E402
import art  # noqa: E402
import grand  # noqa: E402
import roundroom  # noqa: E402

HW, HH = G.HW, G.HH
CUT_H = 150            # walls cut down to this (px above the floor; full walls are 230)
GAP = 2                # tiles between neighbouring rooms
FLOOR_GAP = 150        # px of clear space between floors
FLOOR_SHIFT = {"ground": (0, 0), "first": (1, 0), "basement": (1, 1), "loft": (1, 1)}
FLOOR_ORDER = ("basement", "ground", "first", "loft")      # bottom to top
LINK_WORD = {"stairs_up": "stairs", "stairs_down": "stairs", "ladder_up": "ladder", "trapdoor": "trapdoor"}
BG_TOP, BG_BOT = (22, 16, 34), (5, 4, 10)


# ----------------------------------------------------------------- layout
def plan(house):
    """World tile origin (X0, Y0) of every room, from the real map grid."""
    cols, rows = {}, {}
    for r in house.rooms.values():
        sx, sy = FLOOR_SHIFT[r.floor]
        c, w = r.map[0] + sx, r.map[1] + sy
        cols[c] = max(cols.get(c, 0), r.w)
        rows[w] = max(rows.get(w, 0), r.d)
    cx, x = {}, 0
    for c in sorted(cols):
        cx[c] = x
        x += cols[c] + GAP
    ry, y = {}, 0
    for w in sorted(rows):
        ry[w] = y
        y += rows[w] + GAP
    pos = {}
    for r in house.rooms.values():
        sx, sy = FLOOR_SHIFT[r.floor]
        c, w = r.map[0] + sx, r.map[1] + sy
        pos[r.id] = (cx[c] + (cols[c] - r.w) // 2, ry[w] + (rows[w] - r.d) // 2)
    return pos


# ----------------------------------------------------------------- one room
def render_room(g, r):
    """The room as the game draws it (cut-away walls), on a transparent
    WIN_W x WIN_H surface positioned by g.origin(r)."""
    keep_walls = r.walls
    r.walls = [o for o in r.walls if o.type != "cobweb"]   # cobwebs hang at the top of the wall
    bg = g.build_background(r)
    r.walls = keep_walls
    P = lambda x, y, z=0.0: g.P(x, y, z, r)
    t = 0.28
    surf = pygame.Surface(bg.get_size(), pygame.SRCALPHA, 32)
    surf.fill((0, 0, 0, 0))
    mask = pygame.Surface(bg.get_size(), pygame.SRCALPHA, 32)
    mask.fill((0, 0, 0, 0))
    hexa = [P(-t, -t, CUT_H), P(r.w, -t, CUT_H), P(r.w, -t, -G.SLAB), P(r.w, r.d, -G.SLAB),
            P(-t, r.d, -G.SLAB), P(-t, r.d, CUT_H)]
    if r.round:       # the conservatory: a circle, its glass wall cut down like the others
        b0, b1 = roundroom.BACK
        n = 48
        ring = [P(*roundroom.arc(r, b0 + (b1 - b0) * i / n, r.rad + 0.14), CUT_H) for i in range(n + 1)]
        ring += [P(*roundroom.arc(r, b1 + math.pi * i / n), -G.SLAB) for i in range(n + 1)]
        hexa = ring
        for x0, y0, x1, y1 in roundroom.door_aprons(r):
            pygame.draw.polygon(mask, (255, 255, 255, 255), [P(x0, y0, -G.SLAB), P(x1, y0, -G.SLAB), P(x1, y1, -G.SLAB),
                                                              P(x1, y1), P(x0, y1), P(x0, y0)])
            pygame.draw.polygon(mask, (255, 255, 255, 255), [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1),
                                                              P(x0, y1, -G.SLAB), P(x1, y1, -G.SLAB), P(x1, y0, -G.SLAB)])
    pygame.draw.polygon(mask, (255, 255, 255, 255), hexa)
    for side in ("S", "E"):            # the thresholds past the open doorways
        rng = r.door_range(side)
        if rng is not None:
            a, b = rng.start, rng.stop
            poly = ([P(a, r.d), P(b, r.d), P(b, r.d + .8), P(a, r.d + .8)] if side == "S" else
                    [P(r.w, a), P(r.w, b), P(r.w + .8, b), P(r.w + .8, a)])
            pygame.draw.polygon(mask, (255, 255, 255, 255), poly)
    surf.blit(bg, (0, 0))
    a = pygame.surfarray.pixels_alpha(surf)
    a[:] = pygame.surfarray.pixels_alpha(mask)
    del a
    # the cut tops of the walls
    cap = (92, 80, 72)
    if r.round:       # a curved cut along the glass wall's back half
        b0, b1 = roundroom.BACK
        n = 48
        for i in range(n):
            a0, a1 = b0 + (b1 - b0) * i / n, b0 + (b1 - b0) * (i + 1) / n
            pygame.draw.polygon(surf, art.shade(cap, roundroom.shade_for((a0 + a1) / 2) * 1.15),
                                [P(*roundroom.arc(r, a0), CUT_H), P(*roundroom.arc(r, a1), CUT_H),
                                 P(*roundroom.arc(r, a1, r.rad + 0.14), CUT_H), P(*roundroom.arc(r, a0, r.rad + 0.14), CUT_H)])
        pygame.draw.lines(surf, art.shade(cap, 0.6), False,
                          [P(*roundroom.arc(r, b0 + (b1 - b0) * i / n, r.rad + 0.14), CUT_H) for i in range(n + 1)], 2)
    else:
        pygame.draw.polygon(surf, cap, [P(0, 0, CUT_H), P(r.w, 0, CUT_H), P(r.w, -t, CUT_H), P(-t, -t, CUT_H)])
        pygame.draw.polygon(surf, art.shade(cap, 1.12), [P(0, 0, CUT_H), P(0, r.d, CUT_H), P(-t, r.d, CUT_H), P(-t, -t, CUT_H)])
        pygame.draw.lines(surf, art.shade(cap, 0.6), False,
                          [P(-t, r.d, CUT_H), P(-t, -t, CUT_H), P(r.w, -t, CUT_H)], 2)
    # furniture, as Game.draw does it (flat things first, then depth-sorted)
    g.room, g.screen = r, surf
    if r.grand:     # the grand staircase / gallery layers (grand.py); the drop and opening are in bg
        g.__dict__.pop("grand_cache", None)
    for o in r.objs:
        if r.grand and o.type in ("stairs_up", "stairs_down"):
            continue
        if o.t["kind"] == "flat" or o.type in ("stairs_down", "trapdoor"):
            g.blit_footprint(o.type, o, o.x, o.y)
    items = []
    if r.grand:
        items += [(box, ("grand", i)) for i, (box, _, _) in enumerate(grand.layers(g, r))]
    for o in r.objs:
        if r.grand and o.type in ("stairs_up", "stairs_down"):
            continue
        if o.t["kind"] == "furniture" or o.type in ("stairs_up", "ladder_up"):
            if o.t["kind"] == "furniture":
                g.draw_floor_shadow(o, o.x, o.y)
            items.append(((o.x, o.y, o.x + o.gx, o.y + o.gy), ("obj", o, o.x, o.y)))
    for _, what in G.depth_sort(items):
        g.draw_item(what)
    return surf


# ----------------------------------------------------------------- drawing helpers
def gradient(w, h):
    s = pygame.Surface((w, h))
    k = np.linspace(0, 1, h)[None, :, None]
    top, bot = np.array(BG_TOP)[None, None, :], np.array(BG_BOT)[None, None, :]
    col = top * (1 - k) + bot * k
    xx = np.linspace(-1, 1, w)[:, None, None]
    yy = np.linspace(-1, 1, h)[None, :, None]
    vig = 1.0 - 0.45 * np.clip(xx ** 2 + yy ** 2, 0, 1.6) / 1.6
    arr = np.broadcast_to(col, (w, h, 3)) * vig
    rnd = np.random.default_rng(3)          # a little fog and a few stars
    pygame.surfarray.blit_array(s, np.clip(arr, 0, 255).astype(np.uint8))
    for _ in range(int(w * h / 90000)):
        x, y = int(rnd.uniform(0, w)), int(rnd.uniform(0, h * 0.5))
        v = int(rnd.uniform(60, 150))
        s.set_at((x, y), (v, v, v + 20))
    return s


def dotted(s, a, b, col, dash=10, gap=8, width=3):
    ax, ay = a
    bx, by = b
    n = math.hypot(bx - ax, by - ay)
    if n < 1:
        return
    ux, uy = (bx - ax) / n, (by - ay) / n
    d = 0.0
    while d < n:
        e = min(n, d + dash)
        pygame.draw.line(s, col, (ax + ux * d, ay + uy * d), (ax + ux * e, ay + uy * e), width)
        d += dash + gap


def arrowhead(s, tip, frm, col, size=14):
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    pygame.draw.polygon(s, col, [tip, (tip[0] - ux * size + px * size * .55, tip[1] - uy * size + py * size * .55),
                                 (tip[0] - ux * size - px * size * .55, tip[1] - uy * size - py * size * .55)])


def pill(s, font, text, centre, fg=(236, 226, 200), bg=(10, 8, 14, 175), pad=(8, 3)):
    img = font.render(text, True, fg)
    w, h = img.get_width() + 2 * pad[0], img.get_height() + 2 * pad[1]
    box = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(box, bg, box.get_rect(), border_radius=h // 2)
    pygame.draw.rect(box, (200, 170, 110, 120), box.get_rect(), 1, border_radius=h // 2)
    box.blit(img, (pad[0], pad[1]))
    s.blit(box, (round(centre[0] - w / 2), round(centre[1] - h / 2)))


# ----------------------------------------------------------------- the house
class House:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
        self.g = G.Game(self.screen, seed=1, enemies=False, save=False, title=False, online=False)
        self.house = M.Mansion()
        self.pos = plan(self.house)
        self.surfs = {rid: render_room(self.g, r) for rid, r in self.house.rooms.items()}

    def floor_rooms(self, f):
        rooms = [r for r in self.house.rooms.values() if r.floor == f]
        return sorted(rooms, key=lambda r: (self.pos[r.id][0] + self.pos[r.id][1], self.pos[r.id][0]))

    @staticmethod
    def W(X, Y, z=0.0):
        """World tiles -> unshifted canvas px (before the margins and floor lift)."""
        return ((X - Y) * HW, (X + Y) * HH - z)

    def floor_layer(self, f):
        """(surface, (left, top)) of one floor drawn at lift 0, in unshifted px."""
        rooms = self.floor_rooms(f)
        boxes = []
        for r in rooms:
            s = self.surfs[r.id]
            ox, oy = self.g.origin(r)
            X0, Y0 = self.pos[r.id]
            wx, wy = self.W(X0, Y0)
            bb = s.get_bounding_rect()
            boxes.append(pygame.Rect(bb.x - ox + wx, bb.y - oy + wy, bb.w, bb.h))
        # the floor plate under the rooms
        xs = [self.pos[r.id][0] for r in rooms] + [self.pos[r.id][0] + r.w for r in rooms]
        ys = [self.pos[r.id][1] for r in rooms] + [self.pos[r.id][1] + r.d for r in rooms]
        x0, x1, y0, y1 = min(xs) - .8, max(xs) + .8, min(ys) - .8, max(ys) + .8
        plate = [self.W(x0, y0), self.W(x1, y0), self.W(x1, y1), self.W(x0, y1)]
        thick = 46
        pts = plate + [(p[0], p[1] + thick) for p in plate]
        bb = boxes[0].unionall(boxes[1:])
        px0, px1 = min(p[0] for p in pts), max(p[0] for p in pts)
        py0, py1 = min(p[1] for p in pts), max(p[1] for p in pts)
        left, top = int(min(bb.left, px0)) - 4, int(min(bb.top, py0)) - 4
        right, bottom = int(max(bb.right, px1)) + 4, int(max(bb.bottom, py1)) + 4
        layer = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA, 32)
        layer.fill((0, 0, 0, 0))
        L = lambda p: (p[0] - left, p[1] - top)
        base = (34, 28, 30)
        pygame.draw.polygon(layer, art.shade(base, 0.7),
                            [L(plate[3]), L(plate[2]), L((plate[2][0], plate[2][1] + thick)), L((plate[3][0], plate[3][1] + thick))])
        pygame.draw.polygon(layer, art.shade(base, 0.5),
                            [L(plate[2]), L(plate[1]), L((plate[1][0], plate[1][1] + thick)), L((plate[2][0], plate[2][1] + thick))])
        pygame.draw.polygon(layer, base, [L(p) for p in plate])
        pygame.draw.lines(layer, (90, 74, 60), True, [L(p) for p in plate], 2)
        # floor strips joining each pair of doorways
        for r in rooms:
            X0, Y0 = self.pos[r.id]
            for side in ("S", "E"):
                d = r.doors.get(side)
                if d is None:
                    continue
                o = self.house.rooms[d["to"]]
                OX, OY = self.pos[o.id]
                ra, oa = r.door_range(side), o.door_range(M.OPPOSITE[side])
                if side == "S":
                    quad = [(X0 + ra.start, Y0 + r.d), (X0 + ra.stop, Y0 + r.d), (OX + oa.stop, OY), (OX + oa.start, OY)]
                else:
                    quad = [(X0 + r.w, Y0 + ra.start), (X0 + r.w, Y0 + ra.stop), (OX, OY + oa.stop), (OX, OY + oa.start)]
                col = art.shade(r.style["f2"], 0.55)
                pygame.draw.polygon(layer, col, [L(self.W(*p)) for p in quad])
                pygame.draw.polygon(layer, art.shade(col, 0.6), [L(self.W(*p)) for p in quad], 2)
        for r in rooms:
            s = self.surfs[r.id]
            ox, oy = self.g.origin(r)
            wx, wy = self.W(*self.pos[r.id])
            layer.blit(s, (round(wx - ox - left), round(wy - oy - top)))
        return layer, (left, top)

    def lifts(self, layers):
        """Raise each floor (px) just enough to clear everything below it."""
        lift = {}
        below = None   # (mask array at 1/4 scale, origin) of the floors so far
        q = 4
        pad = FLOOR_GAP // q
        for f in FLOOR_ORDER:
            layer, (left, top) = layers[f]
            m = pygame.surfarray.array_alpha(pygame.transform.scale(layer, (layer.get_width() // q, layer.get_height() // q))) > 20
            if below is None:
                lift[f] = 0
                below = [(m, left // q, top // q)]
                continue
            z = 0
            while True:
                ok = True
                for zz in (z, z + 200 // q):         # clear here and a little further up
                    for bm, bl, bt in below:
                        if overlap(m, left // q, top // q - zz, bm, bl, bt, pad):
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    break
                z += 2
            lift[f] = z * q
            below.append((m, left // q, top // q - z))
        return lift


def overlap(m, l, t, bm, bl, bt, pad):
    """Do two masks (column-major, at offsets l/t) come within pad cells?"""
    x0, y0 = max(l, bl - pad), max(t, bt - pad)
    x1 = min(l + m.shape[0], bl + bm.shape[0] + pad)
    y1 = min(t + m.shape[1], bt + bm.shape[1] + pad)
    if x0 >= x1 or y0 >= y1:
        return False
    a = m[x0 - l:x1 - l, y0 - t:y1 - t]
    if not a.any():
        return False
    # dilate the lower mask by pad (a box) via a summed-area table
    bx0, by0 = x0 - bl - pad, y0 - bt - pad
    W, H = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    big = np.zeros((W, H), bool)
    sx0, sy0 = max(0, bx0), max(0, by0)
    sx1, sy1 = min(bm.shape[0], bx0 + W), min(bm.shape[1], by0 + H)
    if sx0 < sx1 and sy0 < sy1:
        big[sx0 - bx0:sx1 - bx0, sy0 - by0:sy1 - by0] = bm[sx0:sx1, sy0:sy1]
    c = np.pad(big.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    k = 2 * pad + 1
    win = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return bool((a & (win[:a.shape[0], :a.shape[1]] > 0)).any())


def compose(h, floors, width, title=True, subtitle=None):
    layers = {f: h.floor_layer(f) for f in floors}
    lift = h.lifts(layers) if len(floors) > 1 else {floors[0]: 0}
    # extent
    left = min(layers[f][1][0] for f in floors)
    right = max(layers[f][1][0] + layers[f][0].get_width() for f in floors)
    top = min(layers[f][1][1] - lift[f] for f in floors)
    bottom = max(layers[f][1][1] - lift[f] + layers[f][0].get_height() for f in floors)
    m_side, m_top, m_bot = 760, (520 if title else 200), 160
    Wf, Hf = right - left + 2 * m_side, bottom - top + m_top + m_bot
    k = width / Wf
    W, H = int(round(Wf * k)), int(round(Hf * k))
    big = pygame.Surface((Wf, Hf), pygame.SRCALPHA, 32)
    big.fill((0, 0, 0, 0))
    ox, oy = m_side - left, m_top - top
    for f in FLOOR_ORDER:
        if f in floors:
            layer, (l, t) = layers[f]
            big.blit(layer, (l + ox, t - lift[f] + oy))
    out = gradient(W, H)
    out.blit(pygame.transform.smoothscale(big, (W, H)), (0, 0))

    def C(X, Y, z, f):
        x, y = h.W(X, Y, z)
        return ((x + ox) * k, (y - lift[f] + oy) * k)

    # links between floors (dotted, with an arrow at the upper end)
    fs = max(14, int(28 * k / 0.9))
    f_room = G.load_font(max(12, int(26 * k)), bold=True)
    f_link = G.load_font(max(11, int(22 * k)))
    f_floor = G.load_font(max(20, int(96 * k)), bold=True, serif=True)
    f_title = G.load_font(max(28, int(210 * k)), bold=True, serif=True)
    f_sub = G.load_font(max(14, int(58 * k)), serif=True)
    del fs
    ov = pygame.Surface((W, H), pygame.SRCALPHA, 32)
    ov.fill((0, 0, 0, 0))
    done = set()
    links = []
    pending_tags = []
    for r in h.house.rooms.values():
        for o in r.objs:
            if o.type not in M.LINK_TYPES or o.link is None:
                continue
            pair = tuple(sorted((r.id, o.link)))
            if pair in done:
                continue
            done.add(pair)
            other, po = h.house.link_target(r, o)
            if r.floor not in floors and other.floor not in floors:
                continue
            if r.floor not in floors or other.floor not in floors:
                # one floor on its own: say where the link goes instead of a line
                room, obj, far = (r, o, other) if r.floor in floors else (other, po, r)
                X0, Y0 = h.pos[room.id]
                p = C(X0 + obj.x + obj.gx / 2, Y0 + obj.y + obj.gy / 2, 60, room.floor)
                up = FLOOR_ORDER.index(far.floor) > FLOOR_ORDER.index(room.floor)
                tag = f"{LINK_WORD[obj.type]} {'up' if up else 'down'} to {far.name} ({M.FLOOR_NAMES[far.floor]})"
                pending_tags.append((tag, p))
                continue
            ends = []
            for room, obj in ((r, o), (other, po)):
                X0, Y0 = h.pos[room.id]
                z = 40 if obj.type in ("stairs_up", "ladder_up") else 4
                ends.append((room.floor, C(X0 + obj.x + obj.gx / 2, Y0 + obj.y + obj.gy / 2, z, room.floor)))
            if ends[0][0] not in floors or ends[1][0] not in floors:
                continue
            ends.sort(key=lambda e: FLOOR_ORDER.index(e[0]))
            lo, hi = ends[0][1], ends[1][1]
            word = LINK_WORD[o.type]
            links.append((lo, hi, word, r, o))
            col = (236, 206, 120, 200)
            w = max(2, int(5 * k))
            dotted(ov, lo, hi, col, dash=max(4, int(16 * k)), gap=max(3, int(12 * k)), width=w)
            arrowhead(ov, hi, lo, col, size=max(8, int(26 * k)))
            arrowhead(ov, lo, hi, col, size=max(8, int(26 * k)))
            pygame.draw.circle(ov, col, (round(lo[0]), round(lo[1])), max(3, int(8 * k)))
            pygame.draw.circle(ov, col, (round(hi[0]), round(hi[1])), max(3, int(8 * k)))
    out.blit(ov, (0, 0))
    for lo, hi, word, r, o in links:
        mid = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        pill(out, f_link, word, (mid[0] + 8, mid[1]), fg=(240, 214, 140), pad=(6, 2))
    for tag, p in pending_tags:
        pill(out, f_link, tag, (p[0], p[1] - int(30 * k)), fg=(240, 214, 140), pad=(6, 2))
    # room labels: on the floor, towards the front of the room
    for f in floors:
        for r in h.floor_rooms(f):
            X0, Y0 = h.pos[r.id]
            pill(out, f_room, r.name, C(X0 + r.w * 0.5, Y0 + r.d * 0.5, 0, f))
    # floor labels, to the left of each floor
    for f in floors:
        rooms = h.floor_rooms(f)
        xs = [h.pos[r.id][0] for r in rooms]
        ys = [h.pos[r.id][1] for r in rooms] + [h.pos[r.id][1] + r.d for r in rooms]
        # west corner of the floor plate
        X, Y = min(xs) - .8, max(ys) + .8
        px, py = C(X, Y, 0, f)
        img = f_floor.render(M.FLOOR_NAMES[f], True, (230, 200, 140))
        sh = f_floor.render(M.FLOOR_NAMES[f], True, (0, 0, 0))
        x = max(int(30 * k), px - img.get_width() - int(60 * k))
        y = py - img.get_height() / 2
        out.blit(sh, (x + 3, y + 3))
        out.blit(img, (x, y))
        pygame.draw.line(out, (200, 170, 110), (x, y + img.get_height() + 2),
                         (x + img.get_width(), y + img.get_height() + 2), max(1, int(3 * k)))
    if title:
        t = f_title.render("Haunted Mansion", True, (236, 214, 160))
        tsh = f_title.render("Haunted Mansion", True, (0, 0, 0))
        tx = (W - t.get_width()) / 2
        ty = int(110 * k)
        out.blit(tsh, (tx + 4, ty + 4))
        out.blit(t, (tx, ty))
        if subtitle:
            st = f_sub.render(subtitle, True, (180, 166, 140))
            out.blit(st, ((W - st.get_width()) / 2, ty + t.get_height() + int(10 * k)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Exploded isometric picture of the whole mansion.")
    ap.add_argument("--out", default="/workspace/hm_house_iso.png")
    ap.add_argument("--small", default="/workspace/hm_house_iso_small.png")
    ap.add_argument("--width", type=int, default=5000)
    ap.add_argument("--small-width", type=int, default=2000)
    ap.add_argument("--floors-dir", default="/workspace", help="one PNG per floor here ('' to skip)")
    args = ap.parse_args(argv)
    h = House()
    n = len(h.house.rooms)
    sub = f"All {n} rooms on four floors \u2013 an exploded cut-away view"
    img = compose(h, FLOOR_ORDER, args.width, subtitle=sub)
    pygame.image.save(img, args.out)
    print(args.out, img.get_size())
    small = compose(h, FLOOR_ORDER, args.small_width, subtitle=sub)  # labels re-set at this size, so they stay crisp
    pygame.image.save(small, args.small)
    print(args.small, small.get_size())
    if args.floors_dir:
        for f in FLOOR_ORDER:
            rooms = h.floor_rooms(f)
            fimg = compose(h, (f,), 3000, title=True,
                           subtitle=f"{M.FLOOR_NAMES[f]} \u2013 {len(rooms)} rooms")
            path = os.path.join(args.floors_dir, f"hm_house_floor_{f}.png")
            pygame.image.save(fimg, path)
            print(path, fimg.get_size())
    pygame.quit()


if __name__ == "__main__":
    main()
