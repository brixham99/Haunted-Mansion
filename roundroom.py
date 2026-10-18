"""Round rooms (the conservatory): a circle of Victorian Gothic iron and
glass inscribed in the room's square grid.

Everything here is drawn in the game's own isometric projection, so it
stays strictly isometric: the floor circle comes out as a 2:1 ellipse and
every upright stays upright. The wall is a ring of flat panels (chords of
the circle); each panel is drawn in its own vertical plane, so its lancet
arches and tracery are exact projections too.

  back half (away from the viewer, the N/W side): the full wall - a stone
      plinth, pale green-blue glass in slender iron mullions, two lancet
      lights under a pointed arch with Y-tracery and a trefoil, an iron ring
      beam on top and the springing of the dome's ribs above it.
  front half (towards the viewer): cut away like every room's front walls,
      leaving only a low stone curb and stubs of the mullions, drawn over the
      room each frame (front_layer) so it hides feet behind it, and fading
      when someone stands close behind it.
"""
from __future__ import annotations

import math

import pygame

import art
from objects import WALL_H

GLASS = (170, 214, 206)       # pale green-blue
WARM_GLASS = (200, 196, 150)  # ...warmed by the lamplight inside, low down
IRON = (34, 38, 40)
IRON_HI = (78, 86, 88)
STONE = (148, 140, 126)
NIGHT_TOP, NIGHT_BOT = (30, 40, 64), (12, 16, 26)
PLINTH_H = 46                  # ~1/5 of the wall
SPRING = 138                   # where the arches spring (px up)
BAND = 18                      # iron ring beam at the top
Z_PER_TILE = 80                # px of height that look like one tile across (arch proportions)
BACK_PANELS = 14               # over the back half circle
FRONT_PANELS = 14
DOME_H = 170                   # rise of the (implied) dome above the ring beam
CURB_H = 24                    # the cut-away front: a low curb...
STUB_H = 30                    # ...with stubs of the mullions on it
FRONT_ALPHA = 215
FRONT_FADE_MIN = 0.45
SEG = 96                       # segments in a whole circle for the floor and slabs

BACK = (0.75 * math.pi, 1.75 * math.pi)     # t range of the back half (through W and N)
FRONT = (-0.25 * math.pi, 0.75 * math.pi)


def arc(r, t, rad=None):
    rad = r.rad if rad is None else rad
    return r.cx + rad * math.cos(t), r.cy + rad * math.sin(t)


def shade_for(t):
    """Brightness of a wall panel facing inwards at angle t, matching the
    square rooms (N wall 0.92, W wall 0.72)."""
    nx, ny = -math.cos(t), -math.sin(t)
    ax, ay = max(0.0, nx), max(0.0, ny)
    if ax + ay == 0:
        return 0.82
    return 0.72 + 0.20 * ay / (ax + ay)


def circle_poly(P, r, rad, z=0.0, n=SEG):
    return [P(*arc(r, 2 * math.pi * i / n, rad), z) for i in range(n)]


def door_aprons(r):
    """(x0, y0, x1, y1) floor rectangles joining the circle to the doorways
    on the straight edges (a step out through the cut-away wall)."""
    out = []
    for side in r.doors:
        rng = r.door_range(side)
        a, b = rng.start - 0.25, rng.stop + 0.25
        if side == "S":
            out.append((a, r.d - 1.0, b, r.d))
        elif side == "N":
            out.append((a, 0.0, b, 1.0))
        elif side == "E":
            out.append((r.w - 1.0, a, r.w, b))
        else:
            out.append((0.0, a, 1.0, b))
    return out


def in_apron(r, x, y, pad=0.0):
    return any(x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad for x0, y0, x1, y1 in door_aprons(r))


# ---------------------------------------------------------------- background
def draw_background(g, s, r, rnd):
    """Floor, front slab, back wall and dome springing onto the room's cached
    background surface `s` (the night gradient is already on it)."""
    P = lambda x, y, z=0.0: g.P(x, y, z, r)
    st = r.style
    _night_behind(s, P, r)
    _front_slab(s, P, r, st)
    _floor(g, s, P, r, st, rnd)
    _back_wall(s, P, r)
    _dome_springing(s, P, r)


def _night_behind(s, P, r):
    """The night outside, seen through the glass."""
    t0, t1 = BACK
    n = 48
    for i in range(n):
        a, b = t0 + (t1 - t0) * i / n, t0 + (t1 - t0) * (i + 1) / n
        for j in range(6):
            z0, z1 = WALL_H * j / 6, WALL_H * (j + 1) / 6 + 1
            c = art.lerp(NIGHT_BOT, NIGHT_TOP, (j + 0.5) / 6)
            pygame.draw.polygon(s, c, [P(*arc(r, a), z0), P(*arc(r, b), z0), P(*arc(r, b), z1), P(*arc(r, a), z1)])


def _front_slab(s, P, r, st):
    t0, t1 = FRONT
    n = SEG // 2
    for i in range(n):
        a, b = t0 + (t1 - t0) * i / n, t0 + (t1 - t0) * (i + 1) / n
        m = (a + b) / 2
        k = 0.385 + 0.065 * max(-1.0, min(1.0, math.sin(m) - math.cos(m)))
        pa, pb = arc(r, a), arc(r, b)
        pygame.draw.polygon(s, art.shade(st["f2"], k), [P(*pa), P(*pb), P(*pb, -18), P(*pa, -18)])
    for x0, y0, x1, y1 in door_aprons(r):   # the steps' own front faces
        if y1 >= r.d - 1e-6:
            pygame.draw.polygon(s, art.shade(st["f2"], 0.45), [P(x0, y1), P(x1, y1), P(x1, y1, -18), P(x0, y1, -18)])
        if x1 >= r.w - 1e-6:
            pygame.draw.polygon(s, art.shade(st["f2"], 0.32), [P(x1, y0), P(x1, y1), P(x1, y1, -18), P(x1, y0, -18)])


def _floor(g, s, P, r, st, rnd):
    """Victorian encaustic tiles: a chequer with inset diamonds, a radial
    border ring of alternating segments and a rosette in the middle; all
    clipped to the circle (plus the doorway steps)."""
    fl = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    fl.fill((0, 0, 0, 0))
    f1, f2 = st["f1"], st["f2"]
    cream, terra, ink = (214, 200, 170), (150, 70, 48), (40, 36, 34)
    _chequer(fl, P, r, f1, f2, terra, type(rnd)(r.id + "steps"))      # shows only on the doorway steps
    R = r.rad
    # border ring: outer and inner pinstripes with alternating segments between
    pygame.draw.polygon(fl, ink, circle_poly(P, r, R))
    pygame.draw.polygon(fl, cream, circle_poly(P, r, R - 0.08))
    n = 48
    for i in range(n):
        a, b = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        c = terra if i % 2 == 0 else ink
        pygame.draw.polygon(fl, c, [P(*arc(r, a, R - 0.12)), P(*arc(r, b, R - 0.12)), P(*arc(r, b, R - 0.5)), P(*arc(r, a, R - 0.5))])
    pygame.draw.polygon(fl, cream, circle_poly(P, r, R - 0.5))
    # the inner field, redrawn over the ring's inside
    inner = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    inner.fill((0, 0, 0, 0))
    pygame.draw.polygon(inner, (255, 255, 255, 255), circle_poly(P, r, R - 0.56))
    field = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    field.fill((0, 0, 0, 0))
    _chequer(field, P, r, f1, f2, terra, type(rnd)(r.id + "field"))
    field.blit(inner, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    fl.blit(field, (0, 0))
    # rosette
    for rr, c in ((1.15, ink), (1.08, cream), (0.98, terra), (0.62, cream)):
        pygame.draw.polygon(fl, c, circle_poly(P, r, rr, n=64))
    for i in range(8):
        t = 2 * math.pi * i / 8 + math.pi / 8
        tip, l, rgt = arc(r, t, 0.95), arc(r, t - 0.3, 0.42), arc(r, t + 0.3, 0.42)
        pygame.draw.polygon(fl, ink if i % 2 else terra, [P(r.cx, r.cy), P(*l), P(*tip), P(*rgt)])
    for rr, c in ((0.26, ink), (0.2, terra), (0.08, cream)):
        pygame.draw.polygon(fl, c, circle_poly(P, r, rr, n=32))
    # clip to the circle and the steps (the steps reach out past the circle)
    mask = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    mask.fill((0, 0, 0, 0))
    pygame.draw.polygon(mask, (255, 255, 255, 255), circle_poly(P, r, R))
    for x0, y0, x1, y1 in door_aprons(r):
        pygame.draw.polygon(mask, (255, 255, 255, 255), [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)])
    fl.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(fl, (0, 0))


def _chequer(surf, P, r, f1, f2, terra, rnd):
    """Half-tile chequer with a small inset diamond in every other tile."""
    for x in range(r.w):
        for y in range(r.d):
            for i in range(2):
                for k in range(2):
                    a, b = x + i / 2, y + k / 2
                    c = art.shade(f1 if (i + k) % 2 == 0 else f2, rnd.uniform(0.94, 1.05))
                    pygame.draw.polygon(surf, c, [P(a, b), P(a + .5, b), P(a + .5, b + .5), P(a, b + .5)])
                    if (i + k) % 2:
                        m = 0.25
                        pygame.draw.polygon(surf, art.shade(terra, 0.9), [P(a + m, b + .08), P(a + .42, b + m), P(a + m, b + .42), P(a + .08, b + m)])


def panel_plane(P, A, B):
    """W(s, z): a point s tiles along the chord A->B at height z."""
    L = math.hypot(B[0] - A[0], B[1] - A[1])
    ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
    return (lambda sl, z: P(A[0] + ux * sl, A[1] + uy * sl, z)), L


def lancet(W, s0, s1, z_spring, n=8):
    """Points of a pointed (equilateral) arch over s0..s1 springing at
    z_spring, left to right, in the plane W."""
    w = s1 - s0
    pts = []
    for i in range(n + 1):           # left arc: centred on the right springer
        a = math.pi - (math.pi / 3) * i / n
        pts.append(W(s1 + w * math.cos(a), z_spring + w * Z_PER_TILE * math.sin(a)))
    for i in range(1, n + 1):        # right arc: centred on the left springer
        a = (math.pi / 3) - (math.pi / 3) * i / n
        pts.append(W(s0 + w * math.cos(a), z_spring + w * Z_PER_TILE * math.sin(a)))
    return pts


def _back_wall(s, P, r):
    t0, t1 = BACK
    glass = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    glass.fill((0, 0, 0, 0))
    iron_layer = []                   # (colour, points, width or 0 for filled)
    streaks = []
    for i in range(BACK_PANELS):
        a = t0 + (t1 - t0) * i / BACK_PANELS
        b = t0 + (t1 - t0) * (i + 1) / BACK_PANELS
        k = shade_for((a + b) / 2)
        W, L = panel_plane(P, arc(r, a), arc(r, b))
        stone = art.shade(STONE, k)
        # plinth: ashlar blocks and a coping
        pygame.draw.polygon(s, stone, [W(0, 0), W(L, 0), W(L, PLINTH_H), W(0, PLINTH_H)])
        joint = art.shade(stone, 0.7)
        pygame.draw.line(s, joint, W(0, PLINTH_H / 2), W(L, PLINTH_H / 2), 1)
        pygame.draw.line(s, joint, W(L * 0.5, 0), W(L * 0.5, PLINTH_H / 2), 1)
        for sl in (L * 0.0, L * 0.25 if i % 2 else L * 0.75):
            pygame.draw.line(s, joint, W(sl, PLINTH_H / 2), W(sl, PLINTH_H), 1)
        pygame.draw.polygon(s, art.shade(stone, 1.18), [W(0, PLINTH_H), W(L, PLINTH_H), W(L, PLINTH_H + 6), W(0, PLINTH_H + 6)])
        pygame.draw.polygon(s, art.shade(IRON, k), [W(0, 0), W(L, 0), W(L, 6), W(0, 6)])     # dark joint at the floor
        # glass with a faint reflection: warmer and denser low down, cooler up top
        z_lo, z_hi = PLINTH_H + 6, WALL_H - BAND
        bands = 8
        for j in range(bands):
            u = j / bands
            za, zb = z_lo + (z_hi - z_lo) * u, z_lo + (z_hi - z_lo) * (u + 1 / bands) + 1
            c = art.lerp(WARM_GLASS, GLASS, u)          # the room's warm light low down, cool sky up top
            pygame.draw.polygon(glass, (*art.shade(c, k), int(150 - 55 * u)), [W(0, za), W(L, za), W(L, zb), W(0, zb)])
        sl0 = L * (0.18 + 0.1 * ((i * 7) % 3) / 2)          # a streak of reflected light
        streaks.append([W(sl0, z_lo + 10), W(sl0 + 0.07, z_lo + 10), W(sl0 + 0.2, z_hi - 8), W(sl0 + 0.13, z_hi - 8)])
        # iron: mullions, transom, arches and tracery
        iron = art.shade(IRON, 0.9 + 0.2 * k)
        hi = art.shade(IRON_HI, k)
        m = 0.05
        s0, s1 = m, L - m
        mid = L / 2
        iron_layer.append((iron, [W(-0.03, PLINTH_H + 6), W(0.03, PLINTH_H + 6), W(0.03, z_hi), W(-0.03, z_hi)], 0))
        iron_layer.append((hi, [W(0.03, PLINTH_H + 6), W(0.03, z_hi)], 1))
        outer = lancet(W, s0, s1, SPRING)
        inner_l = lancet(W, s0, mid - 0.015, SPRING - 6)
        inner_r = lancet(W, mid + 0.015, s1, SPRING - 6)
        iron_layer.append((iron, outer, 3))
        iron_layer.append((iron, [W(s0, PLINTH_H + 6), W(s0, SPRING)], 2))
        iron_layer.append((iron, [W(s1, PLINTH_H + 6), W(s1, SPRING)], 2))
        iron_layer.append((iron, inner_l, 2))
        iron_layer.append((iron, inner_r, 2))
        iron_layer.append((iron, [W(mid, PLINTH_H + 6), W(mid, SPRING - 6)], 2))
        iron_layer.append((iron, [W(s0, 100), W(s1, 100)], 2))         # transom
        # trefoil in the head of the arch
        apex_in = SPRING - 6 + (mid - s0) * Z_PER_TILE * 0.866
        apex_out = SPRING + (s1 - s0) * Z_PER_TILE * 0.866
        cz = (apex_in + apex_out) / 2 + 2
        rr = 0.11
        for lobe in range(3):
            ang = math.pi / 2 + lobe * 2 * math.pi / 3
            ls, lz = mid + rr * 0.55 * math.cos(ang), cz + rr * 0.55 * Z_PER_TILE * math.sin(ang)
            pts = [W(ls + rr * 0.5 * math.cos(q * math.pi / 6), lz + rr * 0.5 * Z_PER_TILE * math.sin(q * math.pi / 6)) for q in range(12)]
            iron_layer.append((iron, pts + pts[:1], 1))
        # ring beam over the panel
        iron_layer.append((art.shade(IRON, k), [W(0, z_hi), W(L, z_hi), W(L, WALL_H), W(0, WALL_H)], 0))
        iron_layer.append((hi, [W(0, z_hi + 4), W(L, z_hi + 4)], 1))
    s.blit(glass, (0, 0))
    shine = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    shine.fill((0, 0, 0, 0))
    for pts in streaks:
        pygame.draw.polygon(shine, (230, 242, 238, 30), pts)
    s.blit(shine, (0, 0))
    for c, pts, wdt in iron_layer:
        if wdt == 0:
            pygame.draw.polygon(s, c, pts)
        else:
            pygame.draw.lines(s, c, False, pts, wdt)
    # the end posts where the wall is cut away, and the cap on top
    for t in (t0, t1):
        x, y = arc(r, t)
        pygame.draw.line(s, IRON, P(x, y, PLINTH_H), P(x, y, WALL_H), 5)
    n = 48
    for i in range(n):
        a = t0 + (t1 - t0) * i / n
        b = t0 + (t1 - t0) * (i + 1) / n
        pygame.draw.polygon(s, (52, 56, 58), [P(*arc(r, a), WALL_H), P(*arc(r, b), WALL_H),
                                              P(*arc(r, b, r.rad + 0.14), WALL_H), P(*arc(r, a, r.rad + 0.14), WALL_H)])


def _dome_springing(s, P, r):
    """The dome's ribs rising from the ring beam towards a point over the
    middle of the room - only their springing, faint, so they never get in
    the way - with a little glass between them."""
    lay = pygame.Surface(s.get_size(), pygame.SRCALPHA, 32)
    lay.fill((0, 0, 0, 0))
    t0, t1 = BACK
    ribs = BACK_PANELS
    upto = 0.32
    def rib(t, q):
        rr = r.rad * math.cos(q * math.pi / 2)
        return P(*arc(r, t, rr), WALL_H + DOME_H * math.sin(q * math.pi / 2))
    for i in range(ribs + 1):
        t = t0 + (t1 - t0) * i / ribs
        if i < ribs:
            t2 = t0 + (t1 - t0) * (i + 1) / ribs
            for j in range(4):
                qa, qb = upto * j / 4, upto * (j + 1) / 4
                pygame.draw.polygon(lay, (*GLASS, int(34 * (1 - j / 4))), [rib(t, qa), rib(t2, qa), rib(t2, qb), rib(t, qb)])
        for j in range(6):
            qa, qb = upto * j / 6, upto * (j + 1) / 6
            pygame.draw.line(lay, (*IRON_HI, int(150 * (1 - j / 6))), rib(t, qa), rib(t, qb), 2)
    s.blit(lay, (0, 0))


# ---------------------------------------------------------------- the cut-away front
def front_layer(g, r):
    """(surface, (x, y)): the low curb and mullion stubs round the front
    half, with gaps at the doorway steps. Opaque here; the caller sets its
    alpha (it is drawn over the lit room, so its colours are pre-darkened)."""
    P = lambda x, y, z=0.0: g.P(x, y, z, r)
    t0, t1 = FRONT
    polys = []
    n = FRONT_PANELS * 3
    stone = art.shade(STONE, 0.62)
    for i in range(n):
        a, b = t0 + (t1 - t0) * i / n, t0 + (t1 - t0) * (i + 1) / n
        ma = (a + b) / 2
        if in_apron(r, *arc(r, ma), pad=0.02):
            continue
        k = 0.8 + 0.2 * max(0.0, math.sin(ma))
        pa, pb = arc(r, a), arc(r, b)
        qa, qb = arc(r, a, r.rad - 0.12), arc(r, b, r.rad - 0.12)
        polys.append((art.shade(stone, k * 1.25), [P(*qa, CURB_H), P(*qb, CURB_H), P(*pb, CURB_H), P(*pa, CURB_H)]))
        polys.append((art.shade(stone, k), [P(*pa, 0), P(*pb, 0), P(*pb, CURB_H), P(*pa, CURB_H)]))
        polys.append((art.shade(stone, k * 0.7), [P(*pa, CURB_H - 4), P(*pb, CURB_H - 4), P(*pb, CURB_H), P(*pa, CURB_H)]))
    for i in range(FRONT_PANELS + 1):
        t = t0 + (t1 - t0) * i / FRONT_PANELS
        x, y = arc(r, t, r.rad - 0.06)
        if in_apron(r, x, y, pad=0.05):
            continue
        ux, uy = -math.sin(t) * 0.035, math.cos(t) * 0.035
        iron = art.shade(IRON, 0.9)
        polys.append((iron, [P(x - ux, y - uy, CURB_H), P(x + ux, y + uy, CURB_H), P(x + ux, y + uy, CURB_H + STUB_H), P(x - ux, y - uy, CURB_H + STUB_H)]))
        polys.append((art.shade(IRON_HI, 0.8), [P(x - ux * 1.6, y - uy * 1.6, CURB_H + STUB_H), P(x + ux * 1.6, y + uy * 1.6, CURB_H + STUB_H),
                                                 P(x + ux * 1.6, y + uy * 1.6, CURB_H + STUB_H + 4), P(x - ux * 1.6, y - uy * 1.6, CURB_H + STUB_H + 4)]))
    xs = [p[0] for _, pts in polys for p in pts]
    ys = [p[1] for _, pts in polys for p in pts]
    x0, y0 = math.floor(min(xs)) - 2, math.floor(min(ys)) - 2
    surf = pygame.Surface((math.ceil(max(xs)) - x0 + 2, math.ceil(max(ys)) - y0 + 2), pygame.SRCALPHA, 32)
    surf.fill((0, 0, 0, 0))
    for c, pts in polys:
        pygame.draw.polygon(surf, (*c, 255), [(px - x0, py - y0) for px, py in pts])
    return surf, (x0, y0)


def front_fade(r, who):
    """1.0, or less when someone stands just inside the front curb."""
    f = 1.0
    for x, y in who:
        dx, dy = x - r.cx, y - r.cy
        t = math.atan2(dy, dx)
        if not (FRONT[0] <= t <= FRONT[1]):
            continue
        gap = r.rad - math.hypot(dx, dy)
        f = min(f, FRONT_FADE_MIN + (1 - FRONT_FADE_MIN) * max(0.0, min(1.0, gap / 1.2)))
    return f


def moon_pools(g, r):
    """Moonlight through the glass: light pools for the darkness map."""
    out = []
    for t in (0.85 * math.pi, 1.1 * math.pi, 1.4 * math.pi, 1.65 * math.pi):
        out.append((g.P(*arc(r, t, r.rad - 1.0), 0, r), 150))
    return out
