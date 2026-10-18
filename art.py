"""Sprites for Haunted Mansion: real art from assets/art/<name>.png when it
exists, otherwise a procedural placeholder drawn from simple 3D primitives
(supersampled, so the edges are antialiased).

Every name in objects.T can be replaced by dropping a PNG with that name
into assets/art/ (transparent background, facing as ART_MANIFEST.md says);
the loader crops it to its opaque area and scales it to the target size.
"""

from __future__ import annotations

import math
import os

import pygame

from objects import T, TILE_W, TILE_H, WALL_ART_W, footprint, canvas_size

HERE = os.path.dirname(os.path.abspath(__file__))
ART_DIR = os.path.join(HERE, "assets", "art")
CHAR_DIR = os.path.join(HERE, "assets", "characters")
SS = 3                     # supersampling factor for placeholders
HW, HH = TILE_W // 2, TILE_H // 2

# ----------------------------------------------------------------- colours
WOOD = (96, 58, 34)
DARK_WOOD = (62, 36, 22)
MAHOGANY = (104, 42, 30)
OAK = (132, 92, 54)
PINE = (176, 140, 92)
BRASS = (206, 168, 72)
IRON = (52, 52, 58)
STONE = (150, 148, 140)
MARBLE = (214, 210, 200)
VELVET_G = (52, 92, 60)
VELVET_R = (128, 34, 44)
CREAM = (222, 210, 180)
LINE = (20, 14, 12)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + tuple(c[3:])


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Painter:
    """Draws on a canvas laid out for an isometric footprint (gx, gy) tiles
    and height h px. Coordinates: x, y in tiles, z in px above the floor."""

    def __init__(self, gx, gy, h):
        self.gx, self.gy, self.h = gx, gy, h
        self.W, self.H = canvas_size(gx, gy, h)
        self.s = pygame.Surface((self.W * SS, self.H * SS), pygame.SRCALPHA, 32)
        self.s.fill((0, 0, 0, 0))

    def P(self, x, y, z=0.0):
        return ((self.gy * HW + (x - y) * HW) * SS, (self.h + (x + y) * HH - z) * SS)

    def poly(self, pts, col, outline=True):
        pygame.draw.polygon(self.s, col, pts)
        if outline:
            pygame.draw.polygon(self.s, shade(col, 0.45)[:3] + ((col[3],) if len(col) > 3 else ()), pts, max(1, SS - 1))

    def box(self, x0, y0, x1, y1, z0, z1, col, top=None, outline=True):
        P = self.P
        self.poly([P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1)], shade(col, 0.82), outline)
        self.poly([P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)], shade(col, 0.64), outline)
        self.poly([P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)], top or shade(col, 1.08), outline)
        return (x0, y0, x1, y1, z0, z1)

    # front (east, +x) face of a box: u across (0 = screen-left), v up
    def F(self, b, u, v):
        x0, y0, x1, y1, z0, z1 = b
        return self.P(x1, y1 - u * (y1 - y0), z0 + v * (z1 - z0))

    def fquad(self, b, u0, v0, u1, v1, col, outline=True):
        F = self.F
        self.poly([F(b, u0, v0), F(b, u1, v0), F(b, u1, v1), F(b, u0, v1)], col, outline)

    def fellipse(self, b, cu, cv, ru, rv, col, outline=True, n=28):
        pts = [self.F(b, cu + ru * math.cos(a), cv + rv * math.sin(a)) for a in (2 * math.pi * i / n for i in range(n))]
        self.poly(pts, col, outline)

    # left (south, +y) face
    def L(self, b, u, v):
        x0, y0, x1, y1, z0, z1 = b
        return self.P(x0 + u * (x1 - x0), y1, z0 + v * (z1 - z0))

    def lquad(self, b, u0, v0, u1, v1, col, outline=True):
        L = self.L
        self.poly([L(b, u0, v0), L(b, u1, v0), L(b, u1, v1), L(b, u0, v1)], col, outline)

    def cyl(self, cx, cy, r, z0, z1, col, top=None):
        X, Y0 = self.P(cx, cy, z0)
        _, Y1 = self.P(cx, cy, z1)
        rx, ry = r * HW * 1.414 * SS, r * HH * 1.414 * SS
        side = shade(col, 0.75)
        pygame.draw.ellipse(self.s, side, (X - rx, Y0 - ry, 2 * rx, 2 * ry))
        pygame.draw.rect(self.s, side, (X - rx, Y1, 2 * rx, Y0 - Y1))
        # a little cylinder shading: lighter left half
        pygame.draw.rect(self.s, shade(col, 0.9), (X - rx, Y1, rx * 0.8, Y0 - Y1))
        pygame.draw.ellipse(self.s, top or shade(col, 1.1), (X - rx, Y1 - ry, 2 * rx, 2 * ry))
        pygame.draw.ellipse(self.s, shade(col, 0.45), (X - rx, Y1 - ry, 2 * rx, 2 * ry), max(1, SS - 1))

    def ball(self, cx, cy, z, rpx, col):
        X, Y = self.P(cx, cy, z)
        pygame.draw.circle(self.s, shade(col, 0.7), (X, Y), rpx * SS)
        pygame.draw.circle(self.s, col, (X - rpx * SS * 0.2, Y - rpx * SS * 0.2), rpx * SS * 0.75)
        pygame.draw.circle(self.s, shade(col, 1.4), (X - rpx * SS * 0.4, Y - rpx * SS * 0.4), rpx * SS * 0.25)

    def line(self, a, b, col, w=2):
        pygame.draw.line(self.s, col, self.P(*a), self.P(*b), max(1, int(w * SS)))

    def floor_poly(self, pts, col, z=0.0, outline=True):
        self.poly([self.P(x, y, z) for x, y in pts], col, outline)

    def done(self):
        return pygame.transform.smoothscale(self.s, (self.W, self.H))


class Flat:
    """2D supersampled canvas (wall hangings, enemies, items)."""

    def __init__(self, w, h):
        self.W, self.H = w, h
        self.s = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA, 32)
        self.s.fill((0, 0, 0, 0))

    def p(self, x, y):
        return (x * SS, y * SS)

    def rect(self, x, y, w, h, col, width=0):
        pygame.draw.rect(self.s, col, (x * SS, y * SS, w * SS, h * SS), width * SS)

    def ell(self, x, y, w, h, col, width=0):
        pygame.draw.ellipse(self.s, col, (x * SS, y * SS, w * SS, h * SS), width * SS)

    def circ(self, x, y, r, col, width=0):
        pygame.draw.circle(self.s, col, (x * SS, y * SS), r * SS, width * SS)

    def poly(self, pts, col, width=0):
        pygame.draw.polygon(self.s, col, [(x * SS, y * SS) for x, y in pts], width * SS)

    def line(self, a, b, col, w=1):
        pygame.draw.line(self.s, col, (a[0] * SS, a[1] * SS), (b[0] * SS, b[1] * SS), max(1, int(w * SS)))

    def done(self):
        return pygame.transform.smoothscale(self.s, (self.W, self.H))


# =================================================================== furniture
# Each drawer gets a Painter laid out FACING EAST (front = +x face).

def _cabinet(p, col, h=None, doors=2, knob=BRASS, cornice=True):
    gx, gy = p.gx, p.gy
    h = h or p.h
    b = p.box(0.1, 0.05, gx - 0.05, gy - 0.05, 0, h - (10 if cornice else 0), col)
    if cornice:
        p.box(0.02, 0.0, gx, gy, h - 10, h, shade(col, 1.15))
    for i in range(doors):
        u0, u1 = i / doors + 0.04, (i + 1) / doors - 0.04
        p.fquad(b, u0, 0.06, u1, 0.94, shade(col, 0.72))
        p.fquad(b, u0 + 0.05, 0.12, u1 - 0.05, 0.88, shade(col, 0.6), outline=False)
        ku = u1 - 0.08 if i == 0 else u0 + 0.08
        p.fellipse(b, ku, 0.5, 0.025, 0.012, knob, outline=False)
    return b


def d_wardrobe(p):
    _cabinet(p, MAHOGANY)


def d_linen_press(p):
    b = _cabinet(p, CREAM, doors=2)
    p.fquad(b, 0.1, 0.55, 0.45, 0.88, (150, 170, 175))
    p.fquad(b, 0.55, 0.55, 0.9, 0.88, (150, 170, 175))
    for v in (0.62, 0.7, 0.78):
        p.fquad(b, 0.13, v, 0.42, v + 0.05, (236, 232, 220), outline=False)


def d_bookcase(p):
    b = p.box(0.1, 0.05, p.gx - 0.05, p.gy - 0.05, 0, p.h, DARK_WOOD)
    shelves = 5
    cols = [(120, 30, 30), (40, 70, 40), (40, 50, 100), (130, 100, 40), (90, 40, 80), (60, 40, 30)]
    k = 0
    for s in range(shelves):
        v0 = 0.04 + s * 0.19
        p.fquad(b, 0.05, v0, 0.95, v0 + 0.16, (30, 18, 12), outline=False)
        u = 0.06
        while u < 0.92:
            w = 0.035 + 0.025 * ((k * 7) % 3)
            hh = 0.12 + 0.03 * ((k * 5) % 2)
            if s == 3 and 0.4 < u < 0.55:
                p.fellipse(b, 0.48, v0 + 0.06, 0.05, 0.05, (230, 226, 210))  # skull
                u = 0.56
                continue
            p.fquad(b, u, v0 + 0.01, min(0.94, u + w), v0 + hh, cols[k % len(cols)], outline=False)
            u += w + 0.004
            k += 1


def d_grandfather_clock(p):
    p.box(0.15, 0.15, 0.85, 0.85, 0, 40, MAHOGANY)
    b = p.box(0.25, 0.25, 0.8, 0.75, 40, 160, MAHOGANY)
    p.fquad(b, 0.2, 0.1, 0.8, 0.85, (40, 24, 18))
    p.fellipse(b, 0.5, 0.25, 0.12, 0.08, BRASS)  # pendulum
    p.fquad(b, 0.48, 0.3, 0.52, 0.8, BRASS, outline=False)
    hb = p.box(0.15, 0.15, 0.85, 0.85, 160, 205, MAHOGANY)
    p.fellipse(hb, 0.5, 0.5, 0.33, 0.36, (232, 226, 200))
    p.line((0.85, 0.5, 182), (0.85, 0.42, 193), LINE, 1.2)
    p.line((0.85, 0.5, 182), (0.85, 0.62, 186), LINE, 1.2)
    p.box(0.2, 0.2, 0.8, 0.8, 205, p.h, shade(MAHOGANY, 1.1))


def d_chest_of_drawers(p):
    b = p.box(0.12, 0.05, p.gx - 0.05, p.gy - 0.05, 0, p.h - 18, (110, 70, 40))
    for i in range(4):
        v0 = 0.05 + i * 0.235
        p.fquad(b, 0.05, v0, 0.95, v0 + 0.2, (88, 54, 30))
        for ku in (0.3, 0.7):
            p.fellipse(b, ku, v0 + 0.1, 0.02, 0.025, BRASS, outline=False)
    p.cyl(0.5, 1.0, 0.07, p.h - 18, p.h, CREAM)  # candle


def d_kitchen_dresser(p):
    green = (126, 156, 130)
    base = p.box(0.1, 0.05, p.gx - 0.05, p.gy - 0.05, 0, 90, green)
    p.fquad(base, 0.05, 0.1, 0.48, 0.85, shade(green, 0.8))
    p.fquad(base, 0.52, 0.1, 0.95, 0.85, shade(green, 0.8))
    rack = p.box(0.05, 0.05, 0.3, p.gy - 0.05, 90, p.h, green)
    for v in (0.15, 0.5):
        for i in range(4):
            p.fellipse(rack, 0.15 + i * 0.23, v + 0.17, 0.09, 0.15, (230, 230, 240))


def d_fireplace(p):
    b = p.box(0.05, 0.0, p.gx - 0.1, p.gy, 0, 140, MARBLE)
    p.fquad(b, 0.22, 0.0, 0.78, 0.62, (14, 10, 10))
    p.fellipse(b, 0.5, 0.14, 0.18, 0.1, (90, 230, 140), outline=False)
    p.fellipse(b, 0.5, 0.22, 0.1, 0.12, (170, 255, 190), outline=False)
    mb = p.box(0.0, -0.02, p.gx, p.gy + 0.02, 140, 152, shade(MARBLE, 1.05))
    for y in (0.4, p.gy - 0.4):
        p.cyl(p.gx * 0.5, y, 0.07, 152, 172, BRASS)


def d_piano(p):
    b = p.box(0.15, 0.05, p.gx - 0.1, p.gy - 0.05, 0, p.h, (24, 22, 26))
    k = p.box(p.gx - 0.1, 0.1, p.gx + 0.05, p.gy - 0.1, 70, 78, (240, 236, 220))
    p.fquad(b, 0.1, 0.0, 0.14, 0.55, (14, 12, 14))
    p.fquad(b, 0.86, 0.0, 0.9, 0.55, (14, 12, 14))
    p.fquad(b, 0.3, 0.72, 0.7, 0.95, CREAM)


def d_desk(p):
    b = p.box(0.1, 0.05, p.gx - 0.05, p.gy - 0.05, 0, p.h - 6, WOOD)
    p.fquad(b, 0.05, 0.1, 0.35, 0.9, shade(WOOD, 0.8))
    p.fquad(b, 0.65, 0.1, 0.95, 0.9, shade(WOOD, 0.8))
    p.box(0.08, 0.03, p.gx - 0.03, p.gy - 0.03, p.h - 6, p.h, (40, 86, 50))
    p.cyl(0.5, 0.4, 0.06, p.h, p.h + 10, (20, 20, 30))


def d_wine_rack(p):
    b = p.box(0.1, 0.05, p.gx - 0.05, p.gy - 0.05, 0, p.h, (84, 56, 34))
    for r in range(6):
        for c in range(6):
            p.fellipse(b, 0.1 + c * 0.16, 0.08 + r * 0.165, 0.055, 0.055, (30, 50, 30) if (r + c) % 3 else (60, 20, 30))


def d_barrel(p):
    p.box(0.1, 0.15, 0.9, 0.3, 0, 22, DARK_WOOD)
    p.box(0.1, 0.7, 0.9, 0.85, 0, 22, DARK_WOOD)
    X, Y = p.P(0.55, 0.5, 48)
    rx, ry = 34 * SS, 40 * SS
    pygame.draw.ellipse(p.s, OAK, (X - rx, Y - ry, 2 * rx, 2 * ry))
    for k in (-0.55, 0.55):
        pygame.draw.line(p.s, IRON, (X + k * rx, Y - ry * 0.85), (X + k * rx, Y + ry * 0.85), 3 * SS)
    ex, ey = p.P(0.95, 0.5, 48)
    pygame.draw.ellipse(p.s, shade(OAK, 0.8), (ex - 12 * SS, ey - 30 * SS, 24 * SS, 60 * SS))
    pygame.draw.circle(p.s, BRASS, (ex, ey + 6 * SS), 3 * SS)


def d_coffin(p):
    gx, gy = p.gx, p.gy
    p.floor_poly([(0.2, 0.25), (0.55, 0.05), (0.85, 0.25), (0.85, gy - 0.1), (0.2, gy - 0.1)], (16, 10, 8), z=0, outline=False)
    b = p.box(0.2, 0.1, 0.85, gy - 0.1, 0, p.h - 12, (74, 46, 30))
    p.box(0.15, 0.05, 0.9, gy * 0.75, p.h - 12, p.h, (92, 58, 36))
    p.fquad(b, 0.4, 0.4, 0.6, 0.55, BRASS)


def d_tomb(p):
    b = p.box(0.12, 0.08, 0.88, p.gy - 0.08, 0, 52, STONE)
    p.fquad(b, 0.1, 0.2, 0.9, 0.8, shade(STONE, 0.8))
    p.box(0.08, 0.04, 0.92, p.gy - 0.04, 52, 62, shade(STONE, 1.05))
    p.box(0.35, 0.25, 0.65, p.gy - 0.35, 62, 76, shade(STONE, 1.15))
    p.ball(0.5, p.gy - 0.32, 74, 9, shade(STONE, 1.15))


def d_toy_box(p):
    b = p.box(0.15, 0.15, 0.85, 0.85, 0, p.h - 8, (180, 60, 60))
    p.fquad(b, 0.1, 0.3, 0.9, 0.6, (230, 200, 70))
    p.box(0.1, 0.12, 0.6, 0.88, p.h - 8, p.h, (200, 70, 70))
    p.ball(0.75, 0.6, p.h, 8, (160, 110, 60))


def d_trunk(p):
    b = p.box(0.12, 0.1, 0.88, 0.9, 0, p.h - 12, (90, 60, 40))
    for u in (0.25, 0.75):
        p.fquad(b, u - 0.05, 0, u + 0.05, 1, (50, 34, 24))
    p.fquad(b, 0.15, 0.4, 0.4, 0.7, (200, 190, 150))
    p.box(0.12, 0.1, 0.88, 0.9, p.h - 12, p.h, (104, 70, 46))


def d_suit_of_armour(p):
    steel = (170, 176, 186)
    p.box(0.15, 0.15, 0.85, 0.85, 0, 24, STONE)
    p.box(0.35, 0.3, 0.55, 0.45, 24, 90, steel)
    p.box(0.35, 0.55, 0.55, 0.7, 24, 90, steel)
    b = p.box(0.3, 0.25, 0.65, 0.75, 90, 150, steel)
    p.fquad(b, 0.45, 0.1, 0.55, 0.9, shade(steel, 0.8))
    p.ball(0.5, 0.5, 168, 16, steel)
    hx, hy = p.P(0.62, 0.5, 168)
    pygame.draw.rect(p.s, (200, 30, 30), (hx - 6 * SS, hy - 2 * SS, 12 * SS, 3 * SS))
    p.line((0.65, 0.95, 24), (0.65, 0.95, p.h), (90, 70, 50), 3)
    p.floor_poly([(0.6, 0.85), (0.7, 1.05), (0.7, 0.85)], steel, z=p.h - 30)


def d_bed(p):
    gx, gy = p.gx, p.gy  # facing E: x = length 3, y = width 2
    red = (110, 24, 32)
    for y in (0.1, gy - 0.1):
        p.box(0.05, y - 0.06, 0.17, y + 0.06, 0, p.h, DARK_WOOD)
    p.box(0.05, 0.1, 0.3, gy - 0.1, 0, 80, DARK_WOOD)
    p.box(0.25, 0.1, gx - 0.1, gy - 0.1, 0, 45, DARK_WOOD)
    p.box(0.3, 0.15, gx - 0.12, gy - 0.15, 45, 62, (210, 204, 196))
    p.box(0.3, 0.3, 0.75, gy - 0.3, 62, 74, (236, 232, 226))
    p.box(1.0, 0.12, gx - 0.08, gy - 0.12, 50, 66, red)
    for y in (0.1, gy - 0.1):
        p.box(gx - 0.17, y - 0.06, gx - 0.05, y + 0.06, 0, p.h, DARK_WOOD)
    p.box(0.05, 0.04, gx - 0.05, gy - 0.04, p.h - 10, p.h, red)


def d_coal_heap(p):
    gx, gy = p.gx, p.gy
    for i, (cx, cy, r) in enumerate([(0.6, 0.6, 30), (1.1, 1.2, 26), (0.5, 1.4, 22), (1.4, 0.6, 22), (1.0, 0.9, 30)]):
        p.ball(cx, cy, r * 0.7, r, (34, 34, 38))
    p.line((1.3, 1.2, 30), (1.6, 1.0, 90), (110, 80, 50), 3)


def d_cauldron(p):
    for a in (0.2, 0.8):
        p.line((a, 0.3, 0), (0.5, 0.5, 20), IRON, 2)
    p.cyl(0.5, 0.5, 0.36, 10, p.h - 10, (30, 30, 34), top=(70, 200, 90))
    X, Y = p.P(0.5, 0.5, p.h - 10)
    for dx, dy, r in ((-10, -2, 6), (8, 2, 5), (0, -8, 4)):
        pygame.draw.circle(p.s, (150, 255, 160), (X + dx * SS, Y + dy * SS), r * SS)


def d_chair(p):
    seat = (110, 36, 50)
    for x, y in ((0.3, 0.3), (0.3, 0.7), (0.75, 0.3), (0.75, 0.7)):
        p.box(x - 0.04, y - 0.04, x + 0.04, y + 0.04, 0, 42, DARK_WOOD, outline=False)
    p.box(0.25, 0.25, 0.8, 0.75, 42, 50, seat)
    b = p.box(0.22, 0.25, 0.32, 0.75, 50, p.h, DARK_WOOD)
    p.lquad(b, 0, 0, 1, 1, DARK_WOOD)


def d_armchair(p):
    v = VELVET_G
    p.box(0.15, 0.15, 0.9, 0.85, 0, 40, v)
    p.box(0.3, 0.25, 0.85, 0.75, 40, 50, shade(v, 1.1))
    p.box(0.1, 0.15, 0.32, 0.85, 0, p.h, v)
    p.box(0.3, 0.12, 0.9, 0.27, 0, 62, v)
    p.box(0.3, 0.73, 0.9, 0.88, 0, 62, v)
    p.ball(0.8, 0.8, 64, 5, (230, 220, 200))


def d_chest(p):
    b = p.box(0.2, 0.2, 0.8, 0.8, 0, p.h - 14, (110, 72, 40))
    for v in (0.2, 0.8):
        p.fquad(b, 0, v - 0.06, 1, v + 0.06, IRON, outline=False)
    p.fquad(b, 0.42, 0.45, 0.58, 0.7, BRASS)
    p.box(0.2, 0.2, 0.8, 0.8, p.h - 14, p.h, (124, 82, 46))


def d_crate(p):
    b = p.box(0.12, 0.12, 0.88, 0.88, 0, p.h, PINE)
    for u in (0.08, 0.92):
        p.fquad(b, u - 0.06, 0, u + 0.06, 1, shade(PINE, 0.8), outline=False)
    p.fquad(b, 0.0, 0.42, 1.0, 0.58, shade(PINE, 0.85), outline=False)
    p.lquad(b, 0.0, 0.42, 1.0, 0.58, shade(PINE, 0.75), outline=False)


def d_rocking_horse(p):
    p.line((0.2, 0.3, 4), (0.8, 0.3, 4), (130, 40, 30), 4)
    p.line((0.2, 0.7, 4), (0.8, 0.7, 4), (130, 40, 30), 4)
    for x in (0.35, 0.65):
        for y in (0.35, 0.65):
            p.line((x, y, 8), (x, y, 45), (220, 210, 200), 3)
    b = p.box(0.25, 0.4, 0.75, 0.6, 45, 70, (226, 220, 210))
    p.box(0.65, 0.42, 0.95, 0.58, 64, 92, (226, 220, 210))
    p.box(0.55, 0.45, 0.7, 0.55, 70, 95, (90, 60, 40))


def d_dining_table(p):
    for x, y in ((0.2, 0.2), (0.2, p.gy - 0.2), (p.gx - 0.2, 0.2), (p.gx - 0.2, p.gy - 0.2)):
        p.box(x - 0.06, y - 0.06, x + 0.06, y + 0.06, 0, p.h - 8, DARK_WOOD)
    p.box(0.05, 0.05, p.gx - 0.05, p.gy - 0.05, p.h - 20, p.h - 6, (236, 232, 224))
    p.box(0.05, 0.05, p.gx - 0.05, p.gy - 0.05, p.h - 6, p.h, (240, 238, 230))
    p.cyl(p.gx / 2, p.gy / 2, 0.06, p.h, p.h + 40, BRASS)
    for d in (-0.25, 0, 0.25):
        p.cyl(p.gx / 2, p.gy / 2 + d, 0.03, p.h + 40, p.h + 54, CREAM)
    p.ball(p.gx * 0.3, p.gy * 0.4, p.h + 8, 10, (120, 80, 40))
    p.ball(p.gx * 0.7, p.gy * 0.6, p.h + 8, 9, (90, 110, 50))


def d_round_table(p):
    p.cyl(0.5, 0.5, 0.06, 0, p.h - 6, DARK_WOOD)
    p.cyl(0.5, 0.5, 0.38, p.h - 10, p.h - 4, (230, 226, 216))
    p.ball(0.5, 0.5, p.h + 10, 11, (150, 140, 230))


def d_kitchen_table(p):
    for x, y in ((0.2, 0.2), (0.2, p.gy - 0.2), (p.gx - 0.2, 0.2), (p.gx - 0.2, p.gy - 0.2)):
        p.box(x - 0.06, y - 0.06, x + 0.06, y + 0.06, 0, p.h - 8, PINE)
    p.box(0.05, 0.05, p.gx - 0.05, p.gy - 0.05, p.h - 8, p.h, shade(PINE, 1.1))
    p.ball(p.gx * 0.4, p.gy * 0.5, p.h + 14, 16, (230, 120, 30))
    p.line((p.gx * 0.7, p.gy * 0.3, p.h + 1), (p.gx * 0.75, p.gy * 0.6, p.h + 1), (200, 200, 210), 3)


def d_sofa(p):
    c = (100, 34, 26)
    p.box(0.15, 0.08, 0.95, p.gy - 0.08, 0, 42, c)
    p.box(0.3, 0.2, 0.95, p.gy - 0.2, 42, 50, shade(c, 1.1))
    p.box(0.1, 0.08, 0.35, p.gy - 0.08, 0, p.h, c)
    p.box(0.3, 0.05, 0.95, 0.25, 0, 62, c)
    p.box(0.3, p.gy - 0.25, 0.95, p.gy - 0.05, 0, 62, c)


def d_billiard_table(p):
    for x, y in ((0.25, 0.25), (0.25, p.gy - 0.25), (p.gx - 0.25, 0.25), (p.gx - 0.25, p.gy - 0.25)):
        p.box(x - 0.08, y - 0.08, x + 0.08, y + 0.08, 0, p.h - 10, DARK_WOOD)
    p.box(0.05, 0.05, p.gx - 0.05, p.gy - 0.05, p.h - 18, p.h, DARK_WOOD, top=(40, 120, 60))
    p.floor_poly([(0.2, 0.2), (p.gx - 0.2, 0.2), (p.gx - 0.2, p.gy - 0.2), (0.2, p.gy - 0.2)], (36, 130, 64), z=p.h, outline=False)
    for i, c in enumerate([(230, 30, 30), (240, 240, 230), (240, 200, 40), (20, 20, 20)]):
        p.ball(0.8 + i * 0.4, 0.8 + (i % 2) * 0.3, p.h + 4, 4, c)


def d_range_cooker(p):
    b = p.box(0.15, 0.05, p.gx - 0.05, p.gy - 0.05, 0, p.h - 10, (30, 30, 34))
    p.fquad(b, 0.08, 0.15, 0.45, 0.7, (50, 50, 56))
    p.fquad(b, 0.55, 0.15, 0.92, 0.7, (50, 50, 56))
    p.box(0.1, 0.0, p.gx, p.gy, p.h - 10, p.h, (60, 60, 66))
    p.cyl(0.6, 0.6, 0.15, p.h, p.h + 20, (40, 40, 44))


def d_sink(p):
    for y in (0.2, 0.8):
        p.box(0.25, y - 0.1, 0.75, y + 0.1, 0, 50, (150, 60, 40))
    p.box(0.15, 0.1, 0.9, 0.9, 50, p.h, (236, 236, 230))
    p.line((0.2, 0.5, p.h), (0.2, 0.5, p.h + 22), BRASS, 3)


def d_boiler(p):
    p.cyl(1.0, 1.0, 0.75, 0, p.h - 30, (70, 64, 60))
    X, Y = p.P(1.6, 1.4, 40)
    pygame.draw.rect(p.s, (40, 30, 26), (X - 22 * SS, Y - 26 * SS, 40 * SS, 30 * SS))
    pygame.draw.rect(p.s, (255, 120, 40), (X - 16 * SS, Y - 20 * SS, 28 * SS, 18 * SS))
    for z in (120, 160):
        gx_, gy_ = p.P(1.45, 1.6, z)
        pygame.draw.circle(p.s, (230, 226, 200), (gx_, gy_), 9 * SS)
        pygame.draw.circle(p.s, LINE, (gx_, gy_), 9 * SS, SS)
    p.cyl(0.6, 0.6, 0.12, p.h - 30, p.h, (110, 70, 50))
    p.cyl(1.4, 0.6, 0.12, p.h - 30, p.h, (110, 70, 50))


def d_water_tank(p):
    b = p.box(0.1, 0.1, p.gx - 0.1, p.gy - 0.1, 0, p.h, (140, 144, 148))
    for v in (0.3, 0.65):
        p.fquad(b, 0, v, 1, v + 0.05, (120, 80, 50), outline=False)
        p.lquad(b, 0, v, 1, v + 0.05, (120, 80, 50), outline=False)
    p.floor_poly([(0.3, 0.3), (p.gx - 0.3, 0.3), (p.gx - 0.3, p.gy - 0.3), (0.3, p.gy - 0.3)], (40, 60, 70), z=p.h, outline=False)


def d_mangle(p):
    p.box(0.3, 0.2, 0.7, 0.3, 0, 80, IRON)
    p.box(0.3, 0.7, 0.7, 0.8, 0, 80, IRON)
    p.cyl(0.5, 0.5, 0.12, 50, 62, PINE)
    p.cyl(0.5, 0.5, 0.12, 64, 76, PINE)
    X, Y = p.P(0.5, 0.95, 80)
    pygame.draw.circle(p.s, IRON, (X, Y), 22 * SS, 3 * SS)


def d_washtub(p):
    p.cyl(0.5, 0.5, 0.38, 0, p.h - 6, (150, 156, 160), top=(110, 120, 110))
    p.box(0.4, 0.3, 0.45, 0.7, 20, p.h + 20, (180, 150, 110))


def d_bath(p):
    for x, y in ((0.2, 0.2), (0.2, p.gy - 0.2), (0.8, 0.2), (0.8, p.gy - 0.2)):
        p.ball(x, y, 6, 5, BRASS)
    p.box(0.1, 0.05, 0.92, p.gy - 0.05, 10, p.h, (236, 236, 232))
    p.floor_poly([(0.2, 0.15), (0.82, 0.15), (0.82, p.gy - 0.15), (0.2, p.gy - 0.15)], (90, 140, 80), z=p.h, outline=False)


def d_washstand(p):
    p.box(0.2, 0.15, 0.85, 0.85, 0, 70, OAK)
    p.box(0.15, 0.1, 0.9, 0.9, 70, 78, MARBLE)
    p.cyl(0.5, 0.5, 0.25, 78, 86, (230, 236, 240))
    p.cyl(0.4, 0.3, 0.1, 78, p.h, (230, 236, 240))


def d_cot(p):
    white = (236, 232, 222)
    top = 85
    p.box(0.15, 0.1, 0.85, p.gy - 0.1, 30, 36, white)
    for k in range(9):
        y = 0.1 + k * (p.gy - 0.2) / 8
        p.line((0.85, y, 0), (0.85, y, top - 10), white, 2)
    p.box(0.83, 0.1, 0.87, p.gy - 0.1, top - 14, top - 8, white)
    p.box(0.1, 0.05, 0.25, p.gy - 0.05, 0, top, white)
    p.line((0.2, p.gy / 2, top), (0.5, p.gy / 2, p.h - 4), DARK_WOOD, 2)
    for d in (-0.2, 0.2):
        X, Y = p.P(0.5, p.gy / 2 + d, p.h - 22)
        pygame.draw.polygon(p.s, (20, 20, 20), [(X - 9 * SS, Y), (X, Y - 4 * SS), (X + 9 * SS, Y), (X, Y + 3 * SS)])


def d_potted_palm(p):
    p.cyl(0.5, 0.5, 0.25, 0, 40, BRASS)
    p.line((0.5, 0.5, 40), (0.5, 0.5, 90), (90, 70, 40), 4)
    X, Y = p.P(0.5, 0.5, 90)
    for a in range(7):
        ang = -math.pi / 2 + (a - 3) * 0.45
        ex, ey = X + math.cos(ang) * 46 * SS, Y + math.sin(ang) * 30 * SS + 26 * SS
        mx, my = (X + ex) / 2, (Y + ey) / 2 - 14 * SS
        pygame.draw.polygon(p.s, (110, 90, 46), [(X, Y), (mx - 5 * SS, my), (ex, ey), (mx + 5 * SS, my + 4 * SS)])


def d_statue(p):
    p.box(0.15, 0.15, 0.85, 0.85, 0, 45, STONE)
    m = (206, 204, 198)
    p.cyl(0.5, 0.5, 0.22, 45, 140, m)
    p.ball(0.5, 0.5, 150, 14, m)
    X, Y = p.P(0.5, 0.5, 130)
    for s in (-1, 1):
        pygame.draw.polygon(p.s, shade(m, 0.92), [(X + s * 10 * SS, Y), (X + s * 40 * SS, Y - 30 * SS), (X + s * 30 * SS, Y + 30 * SS)])
    for (x, z) in ((0.3, 60), (0.7, 90), (0.4, 120)):
        p.ball(x, 0.75, z, 6, (60, 100, 50))


def d_candelabra(p):
    p.cyl(0.5, 0.5, 0.22, 0, 6, IRON)
    p.line((0.5, 0.5, 6), (0.5, 0.5, 112), IRON, 3)
    p.line((0.5, 0.15, 112), (0.5, 0.85, 112), IRON, 3)
    for y in (0.15, 0.32, 0.5, 0.68, 0.85):
        p.line((0.5, y, 112), (0.5, y, 130), CREAM, 4)
        X, Y = p.P(0.5, y, 136)
        pygame.draw.ellipse(p.s, (255, 200, 80), (X - 3 * SS, Y - 6 * SS, 6 * SS, 10 * SS))


def d_pumpkin(p):
    org = (230, 120, 30)
    X, Y = p.P(0.5, 0.5, 22)
    for dx in (-18, 18, 0):
        pygame.draw.ellipse(p.s, shade(org, 0.85 if dx else 1.0), (X + (dx - 16) * SS, Y - 20 * SS, 32 * SS, 40 * SS))
    pygame.draw.rect(p.s, (60, 90, 30), (X - 3 * SS, Y - 28 * SS, 6 * SS, 10 * SS))
    glow = (255, 230, 90)
    for ex in (-10, 10):
        pygame.draw.polygon(p.s, glow, [(X + (ex - 5) * SS, Y - 2 * SS), (X + (ex + 5) * SS, Y - 2 * SS), (X + ex * SS, Y - 10 * SS)])
    pygame.draw.polygon(p.s, glow, [(X - 14 * SS, Y + 6 * SS), (X + 14 * SS, Y + 6 * SS), (X + 8 * SS, Y + 13 * SS),
                                    (X, Y + 9 * SS), (X - 8 * SS, Y + 13 * SS)])


def d_dummy(p):
    p.line((0.5, 0.5, 0), (0.5, 0.5, 60), DARK_WOOD, 3)
    for a in (0.2, 0.8):
        p.line((0.5, 0.5, 0), (a, a, 0), DARK_WOOD, 3)
    X, Y = p.P(0.5, 0.5, 60)
    pygame.draw.polygon(p.s, (20, 18, 24), [(X - 30 * SS, Y), (X + 30 * SS, Y), (X + 14 * SS, Y - 50 * SS), (X - 14 * SS, Y - 50 * SS)])
    pygame.draw.ellipse(p.s, (200, 180, 150), (X - 18 * SS, Y - 90 * SS, 36 * SS, 44 * SS))
    pygame.draw.rect(p.s, DARK_WOOD, (X - 4 * SS, Y - 100 * SS, 8 * SS, 12 * SS))
    for k in range(4):
        pygame.draw.circle(p.s, (220, 40, 40), (X + (-8 + k * 5) * SS, Y - 70 * SS + k * 3 * SS), 2 * SS)


def d_harp(p):
    gold = (210, 170, 70)
    p.box(0.25, 0.3, 0.75, 0.7, 0, 16, gold)
    X0, Y0 = p.P(0.5, 0.65, 16)
    X1, Y1 = p.P(0.5, 0.65, p.h)
    X2, Y2 = p.P(0.5, 0.15, 30)
    pygame.draw.line(p.s, gold, (X0, Y0), (X1, Y1), 5 * SS)
    pygame.draw.line(p.s, gold, (X1, Y1), (X2, Y2 - 60 * SS), 4 * SS)
    pygame.draw.line(p.s, gold, (X2, Y2 - 60 * SS), (X2, Y2), 4 * SS)
    for k in range(1, 8):
        t = k / 8
        pygame.draw.line(p.s, (230, 230, 210), (X0, Y0 - (Y0 - Y1) * t), (X2, Y2 - 60 * SS * t), SS)


def d_sewing_machine(p):
    for y in (0.25, 0.75):
        p.box(0.3, y - 0.05, 0.7, y + 0.05, 0, 60, IRON)
    p.box(0.25, 0.15, 0.75, 0.85, 60, 66, WOOD)
    p.box(0.4, 0.3, 0.55, 0.75, 66, p.h, (20, 20, 22))


def d_rug(p, lifted=False):
    gx, gy = p.gx, p.gy
    red, gold = (130, 40, 36), (190, 150, 70)
    p.floor_poly([(0.08, 0.08), (gx - 0.08, 0.08), (gx - 0.08, gy - 0.08), (0.08, gy - 0.08)], red, z=1)
    p.floor_poly([(0.25, 0.25), (gx - 0.25, 0.25), (gx - 0.25, gy - 0.25), (0.25, gy - 0.25)], gold, z=1, outline=False)
    p.floor_poly([(0.35, 0.35), (gx - 0.35, 0.35), (gx - 0.35, gy - 0.35), (0.35, gy - 0.35)], shade(red, 0.9), z=1, outline=False)
    m = gx / 2
    p.floor_poly([(m, 0.5), (gx - 0.5, gy / 2), (m, gy - 0.5), (0.5, gy / 2)], (40, 50, 90), z=1, outline=False)
    if lifted:
        # front corner rolled back: dark floor shows, a roll of rug lies on top
        p.floor_poly([(gx * 0.45, gy - 0.08), (gx - 0.08, gy - 0.08), (gx - 0.08, gy * 0.45)], (30, 22, 18), z=1, outline=False)
        a, b = p.P(gx * 0.45, gy - 0.08, 8), p.P(gx - 0.08, gy * 0.45, 8)
        pygame.draw.line(p.s, shade(red, 0.7), a, b, 16 * SS)
        pygame.draw.line(p.s, gold, a, b, 5 * SS)


def d_rug_lifted(p):
    d_rug(p, lifted=True)


def d_stairs_up(p):
    # facing east: the steps rise towards the west wall (x = 0)
    gx, gy = p.gx, p.gy
    n = 9
    s = gx / n
    step = (120, 80, 50)
    for i in range(n - 1, -1, -1):
        x0, x1 = gx - (i + 1) * s, gx - i * s
        z1 = (i + 1) * p.h / n
        p.box(x0, 0.08, x1, gy - 0.08, 0, z1, shade(step, 0.9 + 0.02 * (i % 2)), top=(150, 46, 46))
    # banister along the near (south) side
    p.line((gx, gy - 0.05, 40), (0, gy - 0.05, p.h + 40), DARK_WOOD, 5)
    for i in range(n):
        x = gx - (i + 0.5) * s
        z = (i + 1) * p.h / n
        p.line((x, gy - 0.05, z), (x, gy - 0.05, z + 40), DARK_WOOD, 2)


def d_stairs_down(p):
    gx, gy = p.gx, p.gy
    p.floor_poly([(0.05, 0.05), (gx - 0.05, 0.05), (gx - 0.05, gy - 0.05), (0.05, gy - 0.05)], (60, 56, 52), z=1)
    n = 6
    for i in range(n):
        x0 = 0.15 + i * (gx - 0.3) / n
        c = shade((110, 104, 96), 1.0 - i * 0.14)
        p.floor_poly([(x0, 0.15), (x0 + (gx - 0.3) / n, 0.15), (x0 + (gx - 0.3) / n, gy - 0.15), (x0, gy - 0.15)], c, z=1, outline=False)
    p.floor_poly([(gx - 0.5, 0.15), (gx - 0.15, 0.15), (gx - 0.15, gy - 0.15), (gx - 0.5, gy - 0.15)], (8, 6, 8), z=1, outline=False)


def d_ladder_up(p):
    wood = (150, 110, 60)
    for y in (0.25, 0.75):
        p.line((0.75, y, 0), (0.2, y, p.h - 10), wood, 4)
    for k in range(1, 9):
        t = k / 9
        x = 0.75 - 0.55 * t
        p.line((x, 0.25, t * (p.h - 10)), (x, 0.75, t * (p.h - 10)), wood, 3)
    p.floor_poly([(0.0, 0.05), (0.6, 0.05), (0.6, 0.95), (0.0, 0.95)], (10, 8, 8), z=p.h, outline=False)


def d_trapdoor(p):
    p.floor_poly([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], (8, 6, 8), z=1)
    for k in range(1, 4):
        x = 0.1 + k * 0.2
        p.line((x, 0.25, 1), (x, 0.75, 1), (90, 66, 40), 2)
    p.box(0.02, 0.1, 0.1, 0.9, 0, 60, (110, 80, 50))


# ======================================================== wall hangings (flat)

def w_frame(f, inner):
    gold = (190, 150, 60)
    f.rect(0, 0, f.W, f.H, gold)
    f.rect(2, 2, f.W - 4, f.H - 4, shade(gold, 0.7), 1)
    f.rect(6, 6, f.W - 12, f.H - 12, inner)


def w_painting(f):
    w_frame(f, (40, 30, 26))
    cx = f.W / 2
    f.ell(cx - 14, 18, 28, 34, (200, 170, 140))
    f.poly([(cx - 22, f.H - 6), (cx + 22, f.H - 6), (cx + 16, 50), (cx - 16, 50)], (20, 20, 24))
    f.circ(cx - 6, 32, 2.5, (240, 220, 120))
    f.circ(cx + 6, 32, 2.5, (240, 220, 120))
    f.line((cx - 8, 44), (cx + 8, 44), (100, 40, 40), 1.5)


def w_painting_lady(f):
    w_frame(f, (30, 36, 44))
    cx = f.W / 2
    f.ell(cx - 18, 12, 36, 30, (30, 24, 20))
    f.ell(cx - 11, 18, 22, 28, (226, 214, 206))
    f.poly([(cx - 22, f.H - 6), (cx + 22, f.H - 6), (cx + 12, 48), (cx - 12, 48)], (14, 12, 16))
    f.circ(cx - 5, 30, 2, (40, 40, 60))
    f.circ(cx + 5, 30, 2, (40, 40, 60))


def w_painting_landscape(f):
    w_frame(f, (24, 30, 60))
    f.circ(f.W * 0.75, 22, 9, (240, 236, 200))
    f.poly([(6, f.H - 6), (f.W * 0.2, 34), (f.W * 0.45, 44), (f.W * 0.7, 30), (f.W - 6, f.H - 6)], (20, 30, 20))
    x = f.W * 0.4
    f.poly([(x, 40), (x + 10, 30), (x + 20, 40)], (10, 10, 12))
    f.rect(x + 1, 40, 18, 12, (10, 10, 12))
    f.rect(x + 6, 44, 3, 3, (255, 210, 90))


def w_mirror(f):
    f.ell(0, 0, f.W, f.H, (30, 26, 24))
    f.ell(5, 5, f.W - 10, f.H - 10, (130, 150, 156))
    f.ell(f.W * 0.3, f.H * 0.3, f.W * 0.4, f.H * 0.35, (176, 196, 200))
    f.circ(f.W * 0.43, f.H * 0.42, 2, (40, 40, 50))
    f.circ(f.W * 0.57, f.H * 0.42, 2, (40, 40, 50))


def w_window(f):
    W, H = f.W, f.H
    frame = (70, 60, 56)
    f.rect(0, 16, W, H - 16, frame)
    f.ell(0, 0, W, 34, frame)
    f.rect(5, 18, W - 10, H - 24, (30, 46, 80))
    f.ell(5, 5, W - 10, 28, (30, 46, 80))
    f.circ(W * 0.65, 30, 9, (230, 230, 200))
    f.line((W * 0.15, H - 8), (W * 0.35, 50), (14, 14, 18), 2)
    f.line((W * 0.3, 70), (W * 0.6, 60), (14, 14, 18), 1.5)
    f.line((W / 2, 8), (W / 2, H - 6), frame, 2)
    for y in (50, 85, 115):
        f.line((5, y), (W - 5, y), frame, 1.5)
    f.poly([(W - 5, 16), (W - 2, 16), (W - 2, H - 4), (W - 14, H - 4)], (90, 20, 30))


def w_cobweb(f):
    W, H = f.W, f.H
    c = (220, 220, 230, 170)
    for k in range(6):
        a = k / 5 * math.pi / 2
        f.line((0, 0), (math.cos(a) * W, math.sin(a) * H), c, 1)
    for r in (0.3, 0.55, 0.8):
        pts = [(math.cos(k / 5 * math.pi / 2) * W * r, math.sin(k / 5 * math.pi / 2) * H * r) for k in range(6)]
        for a, b in zip(pts, pts[1:]):
            f.line(a, b, c, 1)
    f.circ(W * 0.5, H * 0.45, 3, (10, 10, 10))


def w_front_door(f):
    W, H = f.W, f.H
    oak = (88, 52, 30)
    f.rect(0, 0, W, H, (60, 50, 44))
    f.ell(6, 2, W - 12, 40, (230, 200, 120))
    f.rect(6, 22, W - 12, H - 22, oak)
    f.line((W / 2, 22), (W / 2, H), (40, 24, 14), 2)
    for x in (12, W / 2 + 6):
        for y in range(36, int(H) - 10, 22):
            f.circ(x + 10, y, 2, (30, 30, 30))
            f.circ(x + 36, y, 2, (30, 30, 30))
    f.rect(W / 2 + 4, H * 0.55, 8, 14, BRASS)
    f.ell(W / 2 + 6, H * 0.6, 4, 6, (10, 10, 10))
    for y in (H * 0.3, H * 0.75):
        f.rect(6, y, 22, 4, IRON)
        f.rect(W - 28, y, 22, 4, IRON)


def w_door_frame(f):
    W, H = f.W, f.H
    f.rect(0, 0, W, H, (200, 190, 170))
    f.rect(8, 10, W - 16, H - 10, (0, 0, 0, 0))


# ===================================================================== enemies

def e_ghost(f):
    W, H = f.W, f.H
    body = (236, 240, 248, 215)
    f.ell(W * 0.2, 4, W * 0.6, H * 0.45, body)
    pts = [(W * 0.2, H * 0.25), (W * 0.8, H * 0.25), (W * 0.92, H * 0.85)]
    for k in range(7):
        x = W * 0.92 - k * W * 0.84 / 6
        pts.append((x, H * (0.98 if k % 2 == 0 else 0.86)))
    pts.append((W * 0.08, H * 0.85))
    f.poly(pts, body)
    f.poly([(W * 0.2, H * 0.4), (W * 0.02, H * 0.55), (W * 0.22, H * 0.55)], body)
    f.poly([(W * 0.8, H * 0.4), (W * 0.98, H * 0.5), (W * 0.78, H * 0.56)], body)
    f.ell(W * 0.32, H * 0.16, W * 0.13, H * 0.12, (10, 10, 20))
    f.ell(W * 0.55, H * 0.16, W * 0.13, H * 0.12, (10, 10, 20))
    f.ell(W * 0.43, H * 0.32, W * 0.14, H * 0.1, (20, 16, 30))


def e_goblin(f):
    W, H = f.W, f.H
    g = (90, 150, 60)
    f.rect(W * 0.32, H * 0.78, W * 0.12, H * 0.22, (60, 40, 30))
    f.rect(W * 0.56, H * 0.78, W * 0.12, H * 0.22, (60, 40, 30))
    f.poly([(W * 0.22, H * 0.82), (W * 0.78, H * 0.82), (W * 0.68, H * 0.42), (W * 0.32, H * 0.42)], (110, 74, 40))
    f.line((W * 0.3, H * 0.5), (W * 0.1, H * 0.66), g, 4)
    f.line((W * 0.7, H * 0.5), (W * 0.9, H * 0.6), g, 4)
    f.rect(W * 0.86, H * 0.5, 5, 10, CREAM)
    f.circ(W * 0.88, H * 0.47, 3, (255, 200, 80))
    f.poly([(W * 0.25, H * 0.2), (W * 0.0, H * 0.06), (W * 0.3, H * 0.3)], g)
    f.poly([(W * 0.75, H * 0.2), (W * 1.0, H * 0.06), (W * 0.7, H * 0.3)], g)
    f.ell(W * 0.24, H * 0.06, W * 0.52, H * 0.4, g)
    f.circ(W * 0.4, H * 0.22, 4, (250, 230, 60))
    f.circ(W * 0.6, H * 0.22, 4, (250, 230, 60))
    f.circ(W * 0.41, H * 0.22, 1.6, (0, 0, 0))
    f.circ(W * 0.61, H * 0.22, 1.6, (0, 0, 0))
    f.poly([(W * 0.36, H * 0.33), (W * 0.64, H * 0.33), (W * 0.5, H * 0.4)], (40, 20, 20))
    for k in range(4):
        x = W * (0.39 + k * 0.07)
        f.poly([(x, H * 0.33), (x + 3, H * 0.33), (x + 1.5, H * 0.36)], (240, 240, 220))


def e_bat(f):
    W, H = f.W, f.H
    k = (24, 20, 28)
    f.poly([(W * 0.5, H * 0.4), (W * 0.0, H * 0.1), (W * 0.1, H * 0.55), (W * 0.22, H * 0.45), (W * 0.32, H * 0.68)], k)
    f.poly([(W * 0.5, H * 0.4), (W * 1.0, H * 0.1), (W * 0.9, H * 0.55), (W * 0.78, H * 0.45), (W * 0.68, H * 0.68)], k)
    f.ell(W * 0.38, H * 0.3, W * 0.24, H * 0.5, k)
    f.poly([(W * 0.4, H * 0.32), (W * 0.42, H * 0.12), (W * 0.47, H * 0.3)], k)
    f.poly([(W * 0.6, H * 0.32), (W * 0.58, H * 0.12), (W * 0.53, H * 0.3)], k)
    f.circ(W * 0.45, H * 0.42, 2.2, (255, 40, 40))
    f.circ(W * 0.55, H * 0.42, 2.2, (255, 40, 40))


def e_spider(f):
    W, H = f.W, f.H
    k = (26, 22, 24)
    for s in (-1, 1):
        for i in range(4):
            y = H * (0.5 + i * 0.08)
            kx = W * 0.5 + s * W * (0.25 + i * 0.03)
            f.line((W * 0.5, y), (kx, y - H * 0.25), k, 2.5)
            f.line((kx, y - H * 0.25), (W * 0.5 + s * W * (0.45 + i * 0.01), H * 0.95), k, 2)
    f.ell(W * 0.3, H * 0.35, W * 0.4, H * 0.42, k)
    f.ell(W * 0.38, H * 0.62, W * 0.24, H * 0.22, k)
    f.poly([(W * 0.45, H * 0.45), (W * 0.55, H * 0.45), (W * 0.5, H * 0.58)], (200, 30, 30))
    for x in (0.44, 0.5, 0.56):
        f.circ(W * x, H * 0.7, 1.8, (255, 90, 90))


def e_skeleton(f):
    W, H = f.W, f.H
    b = (232, 228, 214)
    cx = W / 2
    f.line((cx - 6, H * 0.55), (cx - 10, H * 0.98), b, 3)
    f.line((cx + 6, H * 0.55), (cx + 10, H * 0.98), b, 3)
    f.ell(cx - 12, H * 0.5, 24, 12, b)
    f.line((cx, H * 0.22), (cx, H * 0.55), b, 3)
    for k in range(4):
        y = H * (0.28 + k * 0.05)
        f.ell(cx - 14 + k, y, 28 - 2 * k, 8, b, 1)
    f.line((cx - 14, H * 0.26), (cx - 26, H * 0.38), b, 3)
    f.line((cx - 26, H * 0.38), (cx - 12, H * 0.42), b, 3)
    f.line((cx + 14, H * 0.26), (cx + 30, H * 0.34), b, 3)
    f.line((cx + 30, H * 0.34), (cx + 38, H * 0.3), b, 3)
    f.ell(cx - 12, H * 0.08, 24, 26, b)
    f.circ(cx - 5, H * 0.14, 4, (20, 20, 20))
    f.circ(cx + 5, H * 0.14, 4, (20, 20, 20))
    f.rect(cx - 6, H * 0.2, 12, 3, (60, 60, 60))
    f.rect(cx - 10, 0, 20, H * 0.07, (20, 18, 22))
    f.rect(cx - 16, H * 0.065, 32, 4, (20, 18, 22))


def e_monster(f):
    W, H = f.W, f.H
    skin = (120, 150, 110)
    suit = (30, 30, 34)
    cx = W / 2
    f.rect(cx - 22, H * 0.7, 18, H * 0.3, suit)
    f.rect(cx + 4, H * 0.7, 18, H * 0.3, suit)
    f.rect(cx - 26, H * 0.97, 22, 6, (10, 10, 10))
    f.rect(cx + 4, H * 0.97, 22, 6, (10, 10, 10))
    f.rect(cx - 32, H * 0.3, 64, H * 0.42, suit)
    f.rect(cx - 44, H * 0.32, 14, H * 0.32, suit)
    f.rect(cx + 30, H * 0.32, 14, H * 0.32, suit)
    f.rect(cx - 44, H * 0.62, 14, 14, skin)
    f.rect(cx + 30, H * 0.62, 14, 14, skin)
    f.rect(cx - 20, H * 0.05, 40, H * 0.26, skin)
    f.rect(cx - 21, H * 0.04, 42, H * 0.06, (16, 16, 16))
    f.rect(cx - 28, H * 0.22, 8, 6, (150, 150, 160))
    f.rect(cx + 20, H * 0.22, 8, 6, (150, 150, 160))
    f.rect(cx - 12, H * 0.14, 8, 4, (20, 20, 20))
    f.rect(cx + 4, H * 0.14, 8, 4, (20, 20, 20))
    f.line((cx - 10, H * 0.26), (cx + 10, H * 0.26), (40, 40, 40), 2)
    for x in range(-8, 10, 5):
        f.line((cx + x, H * 0.1), (cx + x, H * 0.12), (30, 30, 30), 1)


def i_key(f):
    W, H = f.W, f.H
    c = (220, 190, 90)
    f.circ(W * 0.3, H * 0.3, W * 0.22, c)
    f.circ(W * 0.3, H * 0.3, W * 0.1, (0, 0, 0, 0))
    f.line((W * 0.42, H * 0.42), (W * 0.88, H * 0.88), c, 5)
    f.line((W * 0.75, H * 0.75), (W * 0.62, H * 0.88), c, 4)
    f.line((W * 0.85, H * 0.85), (W * 0.74, H * 0.97), c, 4)
    f.circ(W * 0.25, H * 0.24, 3, (255, 255, 230))


ENEMY_W = {"ghost": 100, "goblin": 80, "bat": 80, "spider": 80, "skeleton": 80, "monster": 110}
ITEM_W = {"key": 48}


def target_size(name):
    """(width, height) a sprite is drawn at in the game."""
    t = T[name]
    if t["kind"] in ("furniture", "flat", "link"):
        gx, gy = footprint(name, "E")
        return canvas_size(gx, gy, t["h"])
    if t["kind"] == "wall":
        return t["size"][0] * WALL_ART_W, t["h"]
    if t["kind"] == "enemy":
        return ENEMY_W[name], t["h"]
    return ITEM_W.get(name, 48), t["h"]


def make_placeholder(name):
    t = T[name]
    if t["kind"] in ("furniture", "flat", "link"):
        gx, gy = footprint(name, "E")
        p = Painter(gx, gy, t["h"])
        fn = globals().get("d_" + name)
        if fn is None:
            p.box(0.1, 0.1, gx - 0.1, gy - 0.1, 0, t["h"], (120, 100, 90))
        else:
            fn(p)
        return p.done()
    w, h = target_size(name)
    f = Flat(w, h)
    fn = globals().get({"wall": "w_", "enemy": "e_", "item": "i_"}.get(t["kind"], "x_") + name)
    if fn is not None:
        fn(f)
    else:
        f.rect(0, 0, w, h, (120, 100, 90))
    return f.done()


def _crop_alpha(img):
    r = img.get_bounding_rect(min_alpha=8)
    return img.subsurface(r).copy() if r.w and r.h else img


# Painted art is fitted to its footprint's width; a few pieces are painted with
# a lot of base or air around them, so they get a size correction to sit right
# next to the 160 px characters.
ART_SCALE = {"pumpkin": 0.6, "suit_of_armour": 1.4, "statue": 1.1, "mangle": 1.1, "cauldron": 0.9,
             "washtub": 0.9, "rocking_horse": 1.05}


# Built by tools/iso_box.py on the exact footprint canvas (the footprint's
# full width, its front corner at the bottom): loaded without cropping, so a
# piece shallower than its footprint still sits against the wall at the
# right size.
ISO_BOX_ART = {"fireplace", "kitchen_dresser", "chest_of_drawers", "bookcase", "wardrobe", "piano",
               "grandfather_clock", "linen_press", "desk", "toy_box"}


# Chairs and armchairs have a sprite per facing (front towards): E = lower
# right (front view), S = lower left (its mirror), N = upper right (rear
# view), W = upper left (its mirror). Files <name>_se/sw/ne/nw.png, made by
# tools/cut_sheets.py; each is sized like <name>.png (width = footprint).
FOUR_WAY = {"chair", "armchair"}
VIEW = {"E": "se", "S": "sw", "N": "ne", "W": "nw"}
# The rear views were painted a little squatter than the front views (a
# wider seat for the same height): a touch larger, so the backrests come up
# nearer the front view's height while the seat still fits its tile.
VIEW_SCALE = {"chair_ne": 1.08, "chair_nw": 1.08, "armchair_ne": 1.08, "armchair_nw": 1.08}


def load_real(name, file=None):
    """assets/art/<file or name>.png scaled to fit the target size of `name`
    (bottom-aligned for furniture: width matched to the footprint), or None."""
    path = os.path.join(ART_DIR, (file or name) + ".png")
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        if name not in ISO_BOX_ART:
            img = _crop_alpha(img)
    except Exception:
        return None
    tw, th = target_size(name)
    kind = T[name]["kind"]
    if kind in ("furniture", "flat", "link"):
        k = tw / img.get_width() * ART_SCALE.get(name, 1.0) * VIEW_SCALE.get(file, 1.0)   # footprint fixes the width
    elif kind == "wall":
        if name in ("front_door", "door_frame"):
            return pygame.transform.smoothscale(img, (tw, th))      # fills the doorway exactly
        k = min(tw / img.get_width(), th / img.get_height())      # keep its shape, centred
        small = pygame.transform.smoothscale(img, (max(1, round(img.get_width() * k)), max(1, round(img.get_height() * k))))
        out = pygame.Surface((tw, th), pygame.SRCALPHA)
        out.fill((0, 0, 0, 0))
        out.blit(small, ((tw - small.get_width()) // 2, (th - small.get_height()) // 2))
        return out
    else:
        k = th / img.get_height()                       # height fixes the scale
    size = (max(1, round(img.get_width() * k)), max(1, round(img.get_height() * k)))
    return pygame.transform.smoothscale(img, size)


def wall_shear(img, side, squeeze=True):
    """Flat-on art -> on the wall plane. N wall: rightwards goes down 1 px per
    2 px; W wall: rightwards goes up. Width squeezed to the screen run."""
    import numpy as np
    w, h = img.get_size()
    n = max(1, round(w * (TILE_W / 2) / WALL_ART_W)) if squeeze else w
    img = pygame.transform.smoothscale(img, (n, h))
    rise = n // 2
    out = pygame.Surface((n, h + rise), pygame.SRCALPHA, 32)
    out.fill((0, 0, 0, 0))
    src = pygame.surfarray.pixels3d(img)
    sa = pygame.surfarray.pixels_alpha(img)
    dst = pygame.surfarray.pixels3d(out)
    da = pygame.surfarray.pixels_alpha(out)
    for x in range(n):
        off = x * 0.5 if side == "N" else (n - 1 - x) * 0.5
        o0 = int(off)
        fr = off - o0
        # two-tap vertical interpolation keeps the slanted edges smooth
        col = src[x].astype(np.float32)
        a = sa[x].astype(np.float32)
        acc_c = np.zeros((h + rise, 3), np.float32)
        acc_a = np.zeros(h + rise, np.float32)
        acc_c[o0:o0 + h] += col * (a[:, None] * (1 - fr))
        acc_a[o0:o0 + h] += a * (1 - fr)
        acc_c[o0 + 1:o0 + 1 + h] += col * (a[:, None] * fr)
        acc_a[o0 + 1:o0 + 1 + h] += a * fr
        m = acc_a > 0
        dst[x][m] = (acc_c[m] / acc_a[m][:, None]).clip(0, 255).astype(np.uint8)
        da[x] = acc_a.clip(0, 255).astype(np.uint8)
    del src, sa, dst, da
    return out


# Animated enemies: enemy kind -> frame set written by tools/cut_anims.py
# (assets/art/<set>_<n>.png and anims.json with the in-game size and anchor).
# Painted facing screen right like every enemy; mirrored for screen left.
ENEMY_ANIMS = {"bat": "bat", "skeleton": "skeleton_walk"}


def load_anims():
    import json
    try:
        with open(os.path.join(ART_DIR, "anims.json")) as f:
            return json.load(f)
    except Exception:
        return {}


class Art:
    """Cache of every sprite in both facings."""

    def __init__(self):
        self.cache = {}
        self.real = set()

    def base(self, name):
        key = (name, "base")
        if key not in self.cache:
            img = load_real(name)
            if img is not None:
                self.real.add(name)
            else:
                img = make_placeholder(name)
            self.cache[key] = img.convert_alpha() if pygame.display.get_surface() else img
        return self.cache[key]

    def scale(self, name):
        """Size correction of the painted art (1 for placeholders)."""
        self.base(name)
        return ART_SCALE.get(name, 1.0) if name in self.real else 1.0

    def furniture(self, name, facing):
        """Image for an object facing E (as drawn) or S (mirrored); chairs
        and armchairs have their own image for each of the four facings."""
        if name in FOUR_WAY:
            key = (name, "view", facing)
            if key not in self.cache:
                img = load_real(name, f"{name}_{VIEW.get(facing, 'se')}")
                if img is not None:
                    self.real.add(name)
                    self.cache[key] = img.convert_alpha() if pygame.display.get_surface() else img
                else:      # no painted views: the old two-way mirror
                    self.cache[key] = self._two_way(name, facing)
            return self.cache[key]
        return self._two_way(name, facing)

    def _two_way(self, name, facing):
        flip = facing in ("S", "N")
        key = (name, flip)
        if key not in self.cache:
            img = self.base(name)
            self.cache[key] = pygame.transform.flip(img, True, False) if flip else img
        return self.cache[key]

    def wall(self, name, side):
        key = (name, "wall", side)
        if key not in self.cache:
            self.cache[key] = wall_shear(self.base(name), side)
        return self.cache[key]

    def enemy_frame(self, kind, i, left):
        """(image, anchor x, anchor y) of frame i (0-based) of kind's
        animation, mirrored when left, or None if it has none. The anchor is
        the bat's body centre or the skeleton's feet, in image pixels."""
        key = ("anim", kind, i, left)
        if key not in self.cache:
            if not hasattr(self, "anims"):
                self.anims = load_anims()
            name = ENEMY_ANIMS.get(kind)
            meta = self.anims.get(name) if name else None
            val = None
            if meta:
                path = os.path.join(ART_DIR, f"{name}_{i % meta['frames'] + 1}.png")
                try:
                    img = pygame.image.load(path)
                    img = img.convert_alpha() if pygame.display.get_surface() else img
                    img = pygame.transform.smoothscale(img, tuple(meta["size"]))
                    ax, ay = meta["anchor"]
                    if left:
                        img, ax = pygame.transform.flip(img, True, False), img.get_width() - ax
                    val = (img, ax, ay)
                except Exception:
                    val = None
            self.cache[key] = val
        return self.cache[key]

    def enemy(self, name, left):
        key = (name, "left" if left else "right")
        if key not in self.cache:
            img = self.base(name)
            self.cache[key] = pygame.transform.flip(img, True, False) if left else img
        return self.cache[key]


def glow(radius, colour, strength=1.0, squash=1.6):
    """Soft elliptical glow, premultiplied: blit it with BLEND_RGB_ADD."""
    import numpy as np
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - radius) ** 2 + ((yy - radius) * squash) ** 2) / max(1, radius)
    fall = (np.clip(1.0 - d, 0.0, 1.0) ** 2) * strength
    arr = (np.array(colour, np.float32)[None, None, :] * fall[..., None]).clip(0, 255).astype(np.uint8)
    s = pygame.Surface((size, size))
    pygame.surfarray.blit_array(s, arr.transpose(1, 0, 2))
    return s


def load_character(cid):
    """Archie or Holly: the standing frame and the walk cycle for each facing,
    plus the walk metadata (frame size, ground anchor, foot positions per
    frame, cycle length in tiles) written by tools/make_walk.py."""
    import json
    with open(os.path.join(CHAR_DIR, f"{cid}_walk.json")) as f:
        meta = json.load(f)
    fw, fh = meta["size"]
    alpha = pygame.display.get_surface() is not None
    stand, walk = {}, {}
    for k in ("se", "sw", "nw", "ne"):
        img = pygame.image.load(os.path.join(CHAR_DIR, f"{cid}_{k}.png"))
        sheet = pygame.image.load(os.path.join(CHAR_DIR, f"{cid}_{k}_walk.png"))
        if alpha:
            img, sheet = img.convert_alpha(), sheet.convert_alpha()
        stand[k] = img
        walk[k] = [sheet.subsurface((i * fw, 0, fw, fh)).copy() for i in range(meta["frames"])]
    return {"stand": stand, "walk": walk, "meta": meta}


_SHADOWS = {}


def soft_shadow(rw, rh, alpha):
    """A soft-edged dark ellipse (radii rw x rh), cached; plain alpha blit."""
    import numpy as np
    key = (int(rw), int(rh), int(alpha))
    if key not in _SHADOWS:
        w, h = max(2, key[0] * 2 + 2), max(2, key[1] * 2 + 2)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.sqrt(((xx + 0.5 - w / 2) / max(1, key[0])) ** 2 + ((yy + 0.5 - h / 2) / max(1, key[1])) ** 2)
        a = np.clip((1.0 - d) / 0.45, 0, 1)
        a = a * a * (3 - 2 * a) * key[2]
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        pa = pygame.surfarray.pixels_alpha(surf)
        pa[:, :] = a.T.astype(np.uint8)
        del pa
        _SHADOWS[key] = surf
    return _SHADOWS[key]
