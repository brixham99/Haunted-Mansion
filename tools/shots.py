#!/usr/bin/env python3
"""Stage a few in-game moments and save screenshots (headless).

    python3 tools/shots.py [OUT_DIR]      # default /workspace
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import pygame  # noqa: E402

import game as G  # noqa: E402
from selftest import Pilot  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
os.makedirs(OUT, exist_ok=True)


def run(g, secs, d=(0, 0)):
    for _ in range(int(secs * 60)):
        g.update(1 / 60, auto=d)


def shot(g, name):
    g.draw()
    path = os.path.join(OUT, name)
    pygame.image.save(g.screen, path)
    print(path)


def main():
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    g = G.Game(screen, seed=7, save=False, title=False)

    # Ground floor: Archie searching a bookcase in the Library
    g.new_game(7)
    g.mode = "play"
    g.enter_room("library", None)
    g.px, g.py, g.facing = 1.5, 5.6, "W"
    g.spawn_enemies()
    g.grace = 99
    run(g, 0.3)
    g.interact()
    run(g, 0.2)
    shot(g, "hm_room_ground_library.png")

    # Basement: the Crypt, a skeleton and a ghost closing in
    g.god = True
    g.new_game(11)
    g.mode = "play"
    g.enter_room("crypt", None)
    g.px, g.py, g.facing = 6.5, 5.5, "W"
    g.spawn_enemies()
    run(g, 2.2)
    shot(g, "hm_room_basement_crypt.png")

    # First floor: Holly in the Nursery with a ghost and a bat
    g.character = "holly"
    g.new_game(12)
    g.character = "holly"
    g.mode = "play"
    g.enter_room("nursery", None)
    g.px, g.py, g.facing = 5.5, 6.4, "N"
    g.spawn_enemies()
    run(g, 1.6)
    shot(g, "hm_room_first_nursery.png")

    # Loft: Holly has pushed the chest in the Dusty Attic and found the key
    g.god = True
    g.enemies_on = False
    g.new_game(13)
    g.mode = "play"
    g.key_place = ("dusty_attic", "under", "dusty_attic:5")
    g.key_state = "hidden"
    g.enter_room("dusty_attic", None)
    g.px, g.py = 2.5, 6.5
    p = Pilot(g)
    p.walk_path((3, 5))
    p.press((1, 0), lambda: g.key_state == "revealed")
    run(g, 0.4)
    shot(g, "hm_room_loft_attic_key.png")
    pygame.quit()


if __name__ == "__main__":
    main()
