#!/usr/bin/env python3
"""Screenshots of rooms on every floor with the painted art, for review.

    python3 tools/art_shots.py [OUTDIR]     (default /workspace) -> hm_art_<floor>_<room>.png
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pygame  # noqa: E402

import game as G  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
ROOMS = [("ground", "entrance_hall", "archie"), ("ground", "dining_room", "holly"), ("ground", "kitchen", "archie"),
         ("basement", "crypt", "holly"), ("basement", "boiler_room", "archie"),
         ("first", "master_bedroom", "holly"), ("first", "nursery", "archie"),
         ("loft", "dusty_attic", "holly"), ("loft", "servants_quarters", "archie")]


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    g = G.Game(screen, seed=3, enemies=True, god=True, save=False, title=False)
    for floor, rid, cid in ROOMS:
        g.character = cid
        g.new_game(3)
        g.mode = "play"
        g.enter_room(rid, None)
        g.facing = "S"
        for _ in range(40):          # let the enemies move a little (they wait at first)
            g.update(1 / 60, ctrl=(0, 0))
        g.grace = 99
        for _ in range(30):
            g.update(1 / 60, ctrl=(0, 0))
        g.draw()
        path = os.path.join(OUT, f"hm_art_{floor}_{rid}.png")
        pygame.image.save(screen, path)
        print(path)
    pygame.quit()


if __name__ == "__main__":
    main()
