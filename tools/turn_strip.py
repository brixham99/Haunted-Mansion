#!/usr/bin/env python3
"""Review images for Archie's and Holly's quarter turns.

    python3 tools/turn_strip.py [OUTDIR]     # default /workspace

Writes hm_turn_<name>.png (a full 360 degree turn to the right, held key,
sampled 8 times per quarter turn, plus the start pose) and hm_turn.gif
(both characters turning in a real room: four quarter turns right, a pause,
four left, a pause), all through the game's own drawing code.
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import pygame  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import game as G  # noqa: E402

CELL_W, CELL_H = 104, 206
PER_QUARTER = 8
ROOM = "drawing_room"


def make_game(screen, cid):
    g = G.Game(screen, seed=3, character=cid, enemies=False, save=False, title=False, online=False)
    g.mode = "play"
    g.enter_room(ROOM, None)
    g.facing = "E"
    g.grace = 0
    return g


def pose_cell(g):
    """The player alone on a dark floor colour, drawn by the game's own code."""
    cell = pygame.Surface((CELL_W, CELL_H))
    cell.fill((40, 30, 34))
    pygame.draw.line(cell, (70, 56, 60), (0, CELL_H - 30), (CELL_W, CELL_H - 30))
    gx, gy = CELL_W / 2, CELL_H - 30
    img, ax, ay, feet, k, sx, lift = g.player_pose()
    screen, g.screen = g.screen, cell
    g.draw_player_shadow(gx, gy, feet, g.chars[g.character]["meta"]["facings"][k], sx)
    g.screen = screen
    cell.blit(img, (round(gx - ax), round(gy - ay - lift)))
    return Image.frombytes("RGB", cell.get_size(), pygame.image.tobytes(cell, "RGB"))


def strip(g, path):
    """One row per quarter turn: from the old facing (left) to the new (right)."""
    dt = G.TURN_S / PER_QUARTER
    frames = [pose_cell(g)]
    names = [G.FACING_SPRITE[g.facing]]
    for i in range(4 * PER_QUARTER):
        g.update(dt, ctrl=(1, 0))
        frames.append(pose_cell(g))
        names.append(G.FACING_SPRITE[g.pose_facing()])
    cols, label_h = PER_QUARTER + 1, 16
    sheet = Image.new("RGB", (cols * CELL_W, 4 * (CELL_H + label_h)), (20, 14, 18))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for q in range(4):
        a, b = names[q * PER_QUARTER], names[(q + 1) * PER_QUARTER]
        for j in range(cols):
            x, y = j * CELL_W, q * (CELL_H + label_h)
            sheet.paste(frames[q * PER_QUARTER + j], (x, y))
            label = a if j == 0 else b if j == PER_QUARTER else f"{a}>{b} {j}/{PER_QUARTER}"
            d.text((x + 4, y + CELL_H + 2), label, fill=(230, 210, 170), font=font)
    sheet.save(path)
    return path


def gif(screen, path):
    games = [make_game(screen, cid) for cid in G.CHAR_ORDER]
    for g in games:
        g.px, g.py = g.room.w / 2.0 + 0.5, g.room.d / 2.0 + 0.5
    dt = 0.02
    plan = [((0, 0), 0.3), ((1, 0), 4 * G.TURN_S), ((0, 0), 0.5), ((-1, 0), 4 * G.TURN_S), ((0, 0), 0.4)]
    frames = []
    for ctrl, secs in plan:
        for _ in range(round(secs / dt)):
            row = []
            for g in games:
                g.update(dt, ctrl=ctrl)
                g.draw()
                cx, cy = g.P(g.px, g.py)
                rect = pygame.Rect(round(cx - 100), round(cy - 220), 200, 260)
                sub = g.screen.subsurface(rect.clip(g.screen.get_rect())).copy()
                row.append(Image.frombytes("RGB", sub.get_size(), pygame.image.tobytes(sub, "RGB")))
            fr = Image.new("RGB", (sum(r.width for r in row), max(r.height for r in row)))
            x = 0
            for r in row:
                fr.paste(r, (x, 0))
                x += r.width
            frames.append(fr.quantize(128, dither=Image.Dither.NONE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(dt * 1000), loop=0, optimize=True)
    return path


def main(argv):
    out = argv[0] if argv else "/workspace"
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    for cid in G.CHAR_ORDER:
        print(strip(make_game(screen, cid), os.path.join(out, f"hm_turn_{cid}.png")))
    print(gif(screen, os.path.join(out, "hm_turn.gif")))


if __name__ == "__main__":
    main(sys.argv[1:])
