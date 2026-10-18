"""The grand central staircase: the Staircase Hall's flight up the middle of
the room to the back wall, and the Landing's gallery round the open
stairwell above it.

Everything is drawn in the game's own isometric projection (Game.P), so it
stays strictly isometric: treads are flat 2:1 quads, risers and the
panelled side of the flight stand in their own vertical planes, balusters
and newel posts are upright.

  Staircase Hall (room.grand kind "stairs"): a two-tile flight between
      banisters at x0 and x1, rising from its foot (y1) to the back wall in
      half-tile steps. Dark oak treads with a lighter nosing, oak risers, a
      red runner held by brass stair rods, turned balusters (two a tile) under
      a sloping dark oak handrail, and carved newel posts with ball finials at
      the foot. The player walks up it (Room.floor_z gives the height) and
      goes on to the Landing at the top; the flight disappears up through a
      dark opening in the back wall.
  Landing (kind "well"): the open stairwell, a dark drop with the top steps of
      the flight coming up into it, balustraded all round (turned balusters, a
      handrail and a bottom rail, square newels with ball finials at the
      corners and either side of the gap where the stairs arrive).

Both are depth-sorted with the player and baddies as many small layers (a
flight row, a tile of balustrade, a post), each pre-drawn once per room and
cached; a layer in front of a player who stands behind it fades (fades),
like the front-edge ghost door frames.
"""
from __future__ import annotations

import math

import pygame

import art
from objects import WALL_H

OAK = (74, 46, 28)          # dark oak: handrail, newels, stringer
OAK_LIGHT = (112, 74, 44)   # treads
OAK_DARK = (52, 32, 20)     # risers, shadowed faces
BALUSTER = (96, 64, 38)
RUNNER = (128, 24, 30)
RUNNER_DARK = (92, 16, 22)
BRASS = (214, 172, 84)
RAIL_STAIRS = 72            # px: the stair handrail above the nosings
RAIL_GALLERY = 82           # px: the gallery handrail above its floor
NEWEL_H = 104
FADE_ALPHA = 105
FADE_FLIGHT = 190          # the flight itself (someone beside it, behind its side)
WELL_DEPTH = 260


def _P(g, r):
    return lambda x, y, z=0.0: g.P(x, y, z, r)


def layers(g, r):
    """[(box, surface, (x, y))] for the room, built once and cached."""
    cache = g.__dict__.setdefault("grand_cache", {})
    if r.id not in cache:
        cache[r.id] = _build(g, r)
    return cache[r.id]


def _build(g, r):
    out = []
    scratch = pygame.Surface((g.screen.get_width(), g.screen.get_height()), pygame.SRCALPHA)

    def grab(box, draw):
        scratch.fill((0, 0, 0, 0))
        draw(scratch)
        rect = scratch.get_bounding_rect(min_alpha=1)
        if rect.w and rect.h:
            out.append((box, scratch.subsurface(rect).copy(), (rect.x, rect.y)))

    gd = r.grand
    if gd["kind"] == "stairs":
        for j in range(gd["y1"]):
            grab((gd["x0"], j, gd["x1"], j + 1), lambda s, j=j: _flight_row(g, r, s, j))
    else:
        for box, fn in _gallery_parts(g, r):
            grab(box, fn)
    return out


# ------------------------------------------------------------------ helpers
def _quad(s, col, pts, edge=None):
    pygame.draw.polygon(s, col, pts)
    if edge is not None:
        pygame.draw.polygon(s, edge, pts, 1)


def _baluster(s, P, x, y, z0, z1, col=BALUSTER):
    """A turned baluster from z0 up to z1: a square foot, a vase-shaped turned
    body and a collar under the rail."""
    bx, by = P(x, y, z0)
    _, ty = P(x, y, z1)
    h = by - ty
    if h <= 6:
        return
    dark, light = art.shade(col, 0.6), art.shade(col, 1.35)
    pygame.draw.line(s, dark, (bx, by), (bx, ty), 5)
    pygame.draw.line(s, col, (bx - 1, by), (bx - 1, ty), 3)
    # square foot and collar
    pygame.draw.rect(s, dark, (bx - 3, by - h * 0.16, 7, h * 0.16))
    pygame.draw.rect(s, col, (bx - 3, by - h * 0.16, 4, h * 0.16))
    pygame.draw.rect(s, dark, (bx - 3, ty, 7, max(2, h * 0.08)))
    # the turned vase
    vy = by - h * 0.42
    pygame.draw.ellipse(s, dark, (bx - 4, vy - h * 0.13, 9, h * 0.26))
    pygame.draw.ellipse(s, col, (bx - 4, vy - h * 0.13, 6, h * 0.24))
    pygame.draw.line(s, light, (bx - 2, vy - h * 0.08), (bx - 2, vy + h * 0.06), 1)
    for k in (0.22, 0.62, 0.8):          # turned rings
        yy = by - h * k
        pygame.draw.line(s, light, (bx - 3, yy), (bx + 2, yy), 1)


def _rail(s, P, a, b, col=OAK, thick=6):
    """A handrail between two (x, y, z) points: a moulded band with a lit top."""
    (ax, ay), (bx, by) = P(*a), P(*b)
    pygame.draw.polygon(s, art.shade(col, 0.7), [(ax, ay), (bx, by), (bx, by + thick), (ax, ay + thick)])
    pygame.draw.polygon(s, col, [(ax, ay), (bx, by), (bx, by + thick * 0.55), (ax, ay + thick * 0.55)])
    pygame.draw.line(s, art.shade(col, 1.7), (ax, ay), (bx, by), 1)


def _newel(s, P, x, y, z0=0.0, h=NEWEL_H, w=0.2):
    """A carved square newel post (plinth, panelled shaft, cap) with a ball
    finial, standing on (x, y) at z0. Drawn as an iso box: S and E faces."""
    def box(x0, y0, x1, y1, za, zb, col):
        _quad(s, art.shade(col, 0.72), [P(x0, y1, za), P(x1, y1, za), P(x1, y1, zb), P(x0, y1, zb)])   # S face
        _quad(s, art.shade(col, 0.55), [P(x1, y0, za), P(x1, y1, za), P(x1, y1, zb), P(x1, y0, zb)])   # E face
        _quad(s, art.shade(col, 1.15), [P(x0, y0, zb), P(x1, y0, zb), P(x1, y1, zb), P(x0, y1, zb)])   # top
    hw = w / 2
    box(x - hw * 1.25, y - hw * 1.25, x + hw * 1.25, y + hw * 1.25, z0, z0 + h * 0.14, OAK)        # plinth
    box(x - hw, y - hw, x + hw, y + hw, z0 + h * 0.14, z0 + h * 0.84, OAK)                         # shaft
    # sunk panels on the shaft's two faces
    for face in ("S", "E"):
        if face == "S":
            pts = [P(x - hw * 0.55, y + hw, z0 + h * 0.24), P(x + hw * 0.55, y + hw, z0 + h * 0.24),
                   P(x + hw * 0.55, y + hw, z0 + h * 0.74), P(x - hw * 0.55, y + hw, z0 + h * 0.74)]
        else:
            pts = [P(x + hw, y - hw * 0.55, z0 + h * 0.24), P(x + hw, y + hw * 0.55, z0 + h * 0.24),
                   P(x + hw, y + hw * 0.55, z0 + h * 0.74), P(x + hw, y - hw * 0.55, z0 + h * 0.74)]
        pygame.draw.polygon(s, art.shade(OAK, 0.4), pts, 1)
    box(x - hw * 1.3, y - hw * 1.3, x + hw * 1.3, y + hw * 1.3, z0 + h * 0.84, z0 + h * 0.92, OAK)  # cap
    cx, cy = P(x, y, z0 + h * 0.92)
    pygame.draw.rect(s, art.shade(OAK, 0.6), (cx - 3, cy - 6, 7, 6))                               # neck
    rad = 8
    by = cy - 6 - rad + 1
    pygame.draw.circle(s, art.shade(OAK, 0.62), (round(cx), round(by)), rad)
    pygame.draw.circle(s, OAK, (round(cx - 1), round(by - 1)), rad - 2)
    pygame.draw.circle(s, art.shade(OAK, 1.9), (round(cx - 3), round(by - 3)), 2)


# ------------------------------------------------------------------ the flight
def step_z(r, i):
    """Tread height of step i (0 = the top step, against the back wall)."""
    n = 2 * r.grand["y1"]
    return r.STAIR_TOP * (n - i) / n


def rail_z(r, y):
    y1 = r.grand["y1"]
    rise = r.STAIR_TOP / (2 * y1)
    return r.STAIR_TOP * (y1 - y) / y1 + rise / 2 + RAIL_STAIRS


def _flight_row(g, r, s, j):
    P = _P(g, r)
    gd = r.grand
    x0, x1, y1 = gd["x0"], gd["x1"], gd["y1"]
    n = 2 * y1
    ra, rb = x0 + 0.34, x1 - 0.34           # the runner
    for i in (2 * j, 2 * j + 1):
        a, b = i / 2, i / 2 + 0.5
        z = step_z(r, i)
        zn = step_z(r, i + 1) if i + 1 < n else 0.0
        # the panelled side of the flight (the open E side, under the banister)
        _quad(s, art.shade(OAK, 0.62), [P(x1, a, 0), P(x1, b, 0), P(x1, b, z), P(x1, a, z)])
        pygame.draw.line(s, art.shade(OAK, 0.38), P(x1, b, 0), P(x1, b, z), 1)
        # the string along the top of the side
        _quad(s, art.shade(OAK, 0.85), [P(x1, a, z + 9), P(x1, b, zn + 9 if i + 1 < n else 9), P(x1, b, zn if i + 1 < n else 0), P(x1, a, z)])
        # riser
        _quad(s, OAK_DARK, [P(x0, b, z), P(x1, b, z), P(x1, b, zn), P(x0, b, zn)])
        _quad(s, RUNNER_DARK, [P(ra, b, z), P(rb, b, z), P(rb, b, zn), P(ra, b, zn)])
        # tread with a lighter nosing on its front edge
        _quad(s, OAK_LIGHT, [P(x0, a, z), P(x1, a, z), P(x1, b, z), P(x0, b, z)])
        _quad(s, RUNNER, [P(ra, a, z), P(rb, a, z), P(rb, b, z), P(ra, b, z)])
        pygame.draw.line(s, art.shade(RUNNER, 1.4), P(ra + 0.05, a, z), P(ra + 0.05, b, z), 1)   # woven border
        pygame.draw.line(s, art.shade(RUNNER, 1.4), P(rb - 0.05, a, z), P(rb - 0.05, b, z), 1)
        pygame.draw.line(s, art.shade(OAK_LIGHT, 1.35), P(x0, b, z), P(x1, b, z), 2)
        # the brass stair rod at the back of the tread, with its eyes
        pygame.draw.line(s, BRASS, P(ra - 0.04, a + 0.05, z + 2), P(rb + 0.04, a + 0.05, z + 2), 2)
        for xe in (ra - 0.04, rb + 0.04):
            pygame.draw.circle(s, art.shade(BRASS, 0.8), [round(v) for v in P(xe, a + 0.05, z + 2)], 2)
        # turned balusters, two a tread: on the treads at both sides
        for xr in (x0 + 0.07, x1 - 0.07):
            _baluster(s, P, xr, a + 0.25, z, rail_z(r, a + 0.25) - 2)
    for xr in (x0 + 0.07, x1 - 0.07):
        _rail(s, P, (xr, j, rail_z(r, j)), (xr, j + 1, rail_z(r, j + 1)))
    if j == y1 - 1:      # carved newels at the foot, the handrails dying into them
        for xr in (x0 + 0.07, x1 - 0.07):
            _newel(s, P, xr, y1 - 0.1)


def draw_wall_opening(g, s, r):
    """Hall: the flight goes on up through a dark opening in the back wall;
    the landing: nothing on the walls."""
    gd = r.grand
    if gd["kind"] != "stairs":
        return
    P = _P(g, r)
    x0, x1 = gd["x0"], gd["x1"]
    top = r.STAIR_TOP
    _quad(s, (10, 7, 10), [P(x0, 0, top), P(x1, 0, top), P(x1, 0, WALL_H - 6), P(x0, 0, WALL_H - 6)])
    for k in range(1, 5):        # faint steps going on up into the dark
        z = top + k * 13
        c = art.shade((60, 40, 26), 0.8 - k * 0.14)
        pygame.draw.line(s, c, P(x0 + 0.05, 0, z), P(x1 - 0.05, 0, z), 2)
        pygame.draw.line(s, art.shade(RUNNER, 0.7 - k * 0.12), P(x0 + 0.34, 0, z), P(x1 - 0.34, 0, z), 2)
    # a dark oak architrave round it
    for xa in (x0, x1):
        _quad(s, OAK, [P(xa - 0.08, 0, top - 10), P(xa + 0.08, 0, top - 10), P(xa + 0.08, 0, WALL_H - 6), P(xa - 0.08, 0, WALL_H - 6)])
    _quad(s, OAK, [P(x0 - 0.08, 0, WALL_H - 18), P(x1 + 0.08, 0, WALL_H - 18), P(x1 + 0.08, 0, WALL_H - 6), P(x0 - 0.08, 0, WALL_H - 6)])


# ------------------------------------------------------------------ the gallery
def _gallery_parts(g, r):
    P = _P(g, r)
    gd = r.grand
    x0, x1, y0, y1 = gd["x0"], gd["x1"], gd["y0"], gd["y1"]
    link = r.grand_link()
    gap = set(range(link.x, link.x + link.gx)) if link is not None else set()
    inset = 0.08
    parts = []

    def seg(a, b):
        """One tile of balustrade from a to b (floor points)."""
        def fn(s):
            ax, ay = a
            bx, by = b
            pygame.draw.line(s, art.shade(OAK, 0.6), P(ax, ay, 4), P(bx, by, 4), 5)      # bottom rail
            pygame.draw.line(s, OAK, P(ax, ay, 6), P(bx, by, 6), 2)
            for k in range(4):
                t = (k + 0.5) / 4
                _baluster(s, P, ax + (bx - ax) * t, ay + (by - ay) * t, 7, RAIL_GALLERY - 2)
            _rail(s, P, (ax, ay, RAIL_GALLERY), (bx, by, RAIL_GALLERY), thick=7)
        return fn

    for x in range(x0, x1):
        if x not in gap:
            parts.append(((x, y0, x + 1, y0 + 0.06), seg((x, y0 + inset), (x + 1, y0 + inset))))
        parts.append(((x, y1 - 0.06, x + 1, y1), seg((x, y1 - inset), (x + 1, y1 - inset))))
    for y in range(y0, y1):
        parts.append(((x0, y, x0 + 0.06, y + 1), seg((x0 + inset, y), (x0 + inset, y + 1))))
        parts.append(((x1 - 0.06, y, x1, y + 1), seg((x1 - inset, y), (x1 - inset, y + 1))))
    posts = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    if gap:
        posts += [(min(gap), y0), (max(gap) + 1, y0)]
    for (px, py) in posts:
        qx = min(max(px, x0 + inset), x1 - inset)
        qy = min(max(py, y0 + inset), y1 - inset)
        parts.append(((qx - 0.1, qy - 0.1, qx + 0.1, qy + 0.1), lambda s, qx=qx, qy=qy: _newel(s, P, qx, qy, h=NEWEL_H + 6)))
    return parts


def draw_background(g, s, r):
    """The landing's stairwell: a dark drop with its far walls panelled, and
    the top steps of the flight coming up through the gap (clipped to the
    hole). The hall: nothing under the flight (it is drawn as layers)."""
    gd = r.grand
    if gd["kind"] != "well":
        return
    P = _P(g, r)
    x0, x1, y0, y1 = gd["x0"], gd["x1"], gd["y0"], gd["y1"]
    hole = [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]
    tmp = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    tmp.fill((0, 0, 0, 0))
    pygame.draw.polygon(tmp, (6, 4, 7, 255), hole)
    wall = (46, 66, 52)
    D = WELL_DEPTH
    bands = 12
    for k in range(bands):          # the far walls, darkening as they drop away
        za, zb = -D * k / bands, -D * (k + 1) / bands
        f = max(0.0, 0.62 - k * 0.07)
        _quad(tmp, art.shade(wall, f), [P(x0, y0, za), P(x1, y0, za), P(x1, y0, zb), P(x0, y0, zb)])
        _quad(tmp, art.shade(wall, f * 0.75), [P(x0, y0, za), P(x0, y1, za), P(x0, y1, zb), P(x0, y0, zb)])
    _quad(tmp, art.shade(OAK, 0.7), [P(x0, y0, 0), P(x1, y0, 0), P(x1, y0, -14), P(x0, y0, -14)])   # the floor's edge
    _quad(tmp, art.shade(OAK, 0.5), [P(x0, y0, 0), P(x0, y1, 0), P(x0, y1, -14), P(x0, y0, -14)])
    link = r.grand_link()
    if link is not None:            # the top of the flight, coming up into the gap
        a0, a1 = link.x, link.x + link.gx
        ra, rb = a0 + 0.34, a1 - 0.34
        rise = r.STAIR_TOP / 12 if hasattr(r, "STAIR_TOP") else 12.5
        for i in range(10):
            ya, yb = y0 + i * 0.5, y0 + i * 0.5 + 0.5
            z, zn = -rise * (i + 1), -rise * (i + 2)
            f = max(0.08, 1.0 - i * 0.11)
            _quad(tmp, art.shade(OAK, 0.6 * f), [P(a1, ya, z), P(a1, yb, z), P(a1, yb, -D), P(a1, ya, -D)])
            _quad(tmp, art.shade(OAK_LIGHT, f), [P(a0, ya, z), P(a1, ya, z), P(a1, yb, z), P(a0, yb, z)])
            _quad(tmp, art.shade(RUNNER, f), [P(ra, ya, z), P(rb, ya, z), P(rb, yb, z), P(ra, yb, z)])
            _quad(tmp, art.shade(OAK_DARK, f), [P(a0, yb, z), P(a1, yb, z), P(a1, yb, zn), P(a0, yb, zn)])
            _quad(tmp, art.shade(RUNNER_DARK, f), [P(ra, yb, z), P(rb, yb, z), P(rb, yb, zn), P(ra, yb, zn)])
            pygame.draw.line(tmp, art.shade(BRASS, f), P(ra, ya + 0.05, z + 2), P(rb, ya + 0.05, z + 2), 2)
            pygame.draw.line(tmp, art.shade(OAK_LIGHT, 1.3 * f), P(a0, yb, z), P(a1, yb, z), 1)
    mask = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.polygon(mask, (255, 255, 255, 255), hole)
    tmp.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(tmp, (0, 0))
    # an oak edging round the hole on the gallery floor
    for a, b in ((P(x0, y0), P(x1, y0)), (P(x1, y0), P(x1, y1)), (P(x1, y1), P(x0, y1)), (P(x0, y1), P(x0, y0))):
        pygame.draw.line(s, OAK, a, b, 3)


# ------------------------------------------------------------------ drawing
def figure_box(r, x, y, rad):
    """Depth-sort box for a person. On the grand flight they stand on the
    row under their feet: sorted just in front of it (that row and the ones
    behind are drawn first), behind the lower rows nearer the viewer."""
    if r.on_flight(x, y):
        j = math.floor(y)
        return (x - rad, j + 1, x + rad, j + 1 + 1e-3)
    return (x - rad, y - rad, x + rad, y + rad)


def _figure_rects(g, r):
    """Screen rects of the people in the room (player, partner)."""
    out = []
    if g.out is None:
        gx, gy = g.P(g.px, g.py, r.floor_z(g.px, g.py))
        out.append(("player", pygame.Rect(gx - 26, gy - 165, 52, 170)))
    if g.coop is not None and g.coop.partner_here():
        p = g.coop.partner
        gx, gy = g.P(p.x, p.y, r.floor_z(p.x, p.y))
        out.append(("partner", pygame.Rect(gx - 26, gy - 165, 52, 170)))
    return out


def fades(g, r, order):
    """{layer index: alpha}: a layer drawn after (in front of) someone whose
    figure it overlaps fades, so nobody is hidden behind the banisters."""
    lays = layers(g, r)
    figs = _figure_rects(g, r)
    pos = {w[0]: k for k, (_, w) in enumerate(order) if w[0] in ("player", "partner")}
    on = set()
    if g.out is None and r.on_flight(g.px, g.py):
        on.add("player")
    if g.coop is not None and g.coop.partner_here() and r.on_flight(g.coop.partner.x, g.coop.partner.y):
        on.add("partner")
    out = {}
    for k, (_, w) in enumerate(order):
        if w[0] != "grand":
            continue
        _, img, (lx, ly) = lays[w[1]]
        rect = pygame.Rect(lx, ly, img.get_width(), img.get_height())
        flight = r.grand["kind"] == "stairs"
        for who, fr in figs:
            if flight and who in on:     # climbing: the steps in front are below the feet, nothing to fade
                continue
            if who in pos and pos[who] < k and rect.colliderect(fr):
                # only if something of the layer is actually over the figure
                sub = fr.clip(rect)
                part = img.subsurface(sub.move(-lx, -ly))
                if part.get_bounding_rect(min_alpha=20).w:
                    out[w[1]] = FADE_FLIGHT if flight else FADE_ALPHA
    return out


def draw_layer(g, r, i, alpha=255):
    _, img, at = layers(g, r)[i]
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    g.screen.blit(img, at)
