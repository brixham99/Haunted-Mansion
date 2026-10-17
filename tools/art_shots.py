#!/usr/bin/env python3
"""Screenshots of rooms on every floor with the painted art, for review.

    python3 tools/art_shots.py [OUTDIR]         (default /workspace) -> hm_art_<floor>_<room>.png
    python3 tools/art_shots.py --iso [OUTDIR]   the rooms with the corner-view pieces -> hm_iso_<name>.png
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pygame  # noqa: E402

import game as G  # noqa: E402

ISO = "--iso" in sys.argv
ARGS = [a for a in sys.argv[1:] if a != "--iso"]
OUT = ARGS[0] if ARGS else "/workspace"
ROOMS = [("ground", "entrance_hall", "archie"), ("ground", "dining_room", "holly"), ("ground", "kitchen", "archie"),
         ("basement", "crypt", "holly"), ("basement", "boiler_room", "archie"),
         ("first", "master_bedroom", "holly"), ("first", "nursery", "archie"),
         ("loft", "dusty_attic", "holly"), ("loft", "servants_quarters", "archie")]

ISO_ROOMS = [("dining", "dining_room", "archie"), ("kitchen", "kitchen", "holly"),
             ("music_room_harp_piano", "music_room", "archie"), ("study_bookcase_armchair", "study", "holly"),
             ("entrance_hall_clock_front_door", "entrance_hall", "archie"),
             ("master_bedroom_wardrobe", "master_bedroom", "holly"), ("nursery_rocking_horse", "nursery", "archie"),
             ("drawing_room_piano_armchair", "drawing_room", "holly"), ("laundry_linen_press", "laundry", "archie"),
             ("staircase_hall_stairs", "staircase_hall", "holly"), ("coal_cellar_ladder", "coal_cellar", "archie")]


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    g = G.Game(screen, seed=3, enemies=True, god=True, save=False, title=False)
    for floor, rid, cid in (ISO_ROOMS if ISO else ROOMS):
        g.character = cid
        g.new_game(3)
        g.mode = "play"
        g.enter_room(rid, None)
        r = g.room                    # stand on open floor near the middle, not inside a table
        mx, my = r.w / 2 + .5, r.d / 2 + .5
        fx, fy = min(r.free_floor(), key=lambda c: (c[0] + .5 - mx) ** 2 + (c[1] + .5 - my) ** 2)
        g.px, g.py = fx + .5, fy + .5
        g.facing = "S"
        for _ in range(40):          # let the enemies move a little (they wait at first)
            g.update(1 / 60, ctrl=(0, 0))
        g.grace = 99
        for _ in range(30):
            g.update(1 / 60, ctrl=(0, 0))
        g.draw()
        path = os.path.join(OUT, f"hm_iso_{floor}.png" if ISO else f"hm_art_{floor}_{rid}.png")
        pygame.image.save(screen, path)
        print(path)
    pygame.quit()


if __name__ == "__main__":
    main()
