#!/usr/bin/env python3
"""Headless self-test for Haunted Mansion.

    python3 tools/selftest.py              # everything (about a minute)
    python3 tools/selftest.py --quick      # data checks + 10 key games
    python3 tools/selftest.py --shots DIR  # also save one screenshot per room on the tour

1. Data: every room validates (bounds, overlaps, doorways clear, every
   doorway and stair landing joined on foot); doors pair up; stairs pair up.
2. Every room is reachable from the Entrance Hall.
3. Every candidate key spot is obtainable, and place_key() only ever
   chooses obtainable spots (checked for many seeds).
4. Autoplay, using the real game code and real movement/collision:
   a full tour that walks into every room (enemies on, invulnerable, to
   exercise their AI), then finds the key and escapes; then many more games
   that go straight to the key and out of the front door, first with the
   key out in the open (the setting for now), then hidden (KEY_HIDDEN:
   searched, pushed, under a rug or in the open), and one game for every
   hiding place.
3b. With the key in the open it is always on a reachable floor tile that
   no furniture hides from the camera, and searching finds nothing.
"""
import argparse
import math
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import random  # noqa: E402

import pygame  # noqa: E402

import game as G  # noqa: E402
import mansion as M  # noqa: E402
import roundroom  # noqa: E402
import art  # noqa: E402
from objects import T, WALL_H  # noqa: E402

DT = 1 / 60
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)
    return cond


class Stuck(Exception):
    pass


class Pilot:
    """Drives a Game through its normal update() with steering input."""

    def __init__(self, game, shots=None):
        self.g = game
        self.frames = 0
        self.shots = shots
        self.shot_rooms = set()

    # --- low level
    def tick(self, d=(0, 0), back=True):
        """One frame heading in world direction d with the tank controls
        (turn the shorter way, then walk; walk backwards if facing away)."""
        g = self.g
        g.update(DT, ctrl=g.steer(d, back))
        self.frames += 1
        if self.shots and g.mode == "play" and not g.fade and g.room.id not in self.shot_rooms and g.grace <= 0.5:
            self.shot_rooms.add(g.room.id)
            g.draw()
            pygame.image.save(g.screen, os.path.join(self.shots, f"room_{g.room.id}.png"))

    def settle(self):
        n = 0
        while self.g.fade and n < 120:
            self.tick()
            n += 1

    def steer_to(self, tx, ty, tol=0.06):
        """One axis at a time (tank controls cannot walk diagonally); the axis
        already being faced goes first, to save turns."""
        g = self.g
        dx = 0 if abs(tx - g.px) <= tol else (1 if tx > g.px else -1)
        dy = 0 if abs(ty - g.py) <= tol else (1 if ty > g.py else -1)
        if dx and dy:
            return (dx, 0) if g.facing in ("E", "W") else (0, dy)
        return dx, dy

    def face(self, d):
        """Turn to face world direction d, then lean into it a moment."""
        g = self.g
        n = 0
        while g.facing != G.FACING_DIR_NAME[tuple(d)] or g.turning:
            self.tick(d, back=False)
            n += 1
            if n > 200:
                raise Stuck(f"{g.room.id}: could not turn to {d}")
        for _ in range(3):
            self.tick(d, back=False)

    def walk_path(self, goal, limit=1500):
        """Walk tile by tile to `goal` (a tile) inside the current room."""
        g = self.g
        r = g.room
        start = (math.floor(g.px), math.floor(g.py))
        path = r.path(start, goal)
        if path is None:
            raise Stuck(f"{r.id}: no path {start} -> {goal}")
        n = 0
        for cell in path:
            tx, ty = cell[0] + 0.5, cell[1] + 0.5
            while True:
                d = self.steer_to(tx, ty)
                if d == (0, 0):
                    break
                self.tick(d)
                n += 1
                if g.room is not r or g.mode != "play":
                    return
                if n > limit:
                    raise Stuck(f"{r.id}: walking to {goal} stuck at ({g.px:.2f},{g.py:.2f})")

    def press(self, d, until, limit=240):
        n = 0
        while not until():
            self.tick(d, back=False)   # into doors, stairs, furniture: facing it
            n += 1
            if n > limit:
                raise Stuck(f"{self.g.room.id}: pressing {d} did not work at ({self.g.px:.2f},{self.g.py:.2f})")

    # --- room to room
    def go_to_room(self, target):
        g = self.g
        route = g.house.route(g.room.id, target)
        for nxt in route[1:]:
            self.step_room(nxt)
            if not check(g.room.id == nxt, f"expected to arrive in {nxt}, in {g.room.id}"):
                raise Stuck("wrong room")

    def step_room(self, nxt):
        g = self.g
        r = g.room
        for side, d in r.doors.items():
            if d["to"] == nxt:
                cells = r.door_cells(side)
                reach = r.flood((math.floor(g.px), math.floor(g.py)))
                cell = next((c for c in cells if c in reach), cells[0])
                self.walk_path(cell)
                self.press(M.SIDE_DIR[side], lambda: g.room is not r or g.fade)
                self.settle()
                return
        for o in r.objs:
            if o.type in M.LINK_TYPES and o.link == nxt:
                if o.type in ("stairs_down", "trapdoor"):
                    reach = r.flood((math.floor(g.px), math.floor(g.py)))
                    ex, ey = o.exit_pos()
                    self.walk_path((math.floor(ex), math.floor(ey)))
                    fx, fy = M.FACING_DIR[o.facing]
                    self.press((-fx, -fy), lambda: g.room is not r or g.fade)
                else:
                    ex, ey = o.exit_pos()
                    self.walk_path((math.floor(ex), math.floor(ey)))
                    fx, fy = M.FACING_DIR[o.facing]
                    self.press((-fx, -fy), lambda: g.room is not r or g.fade)
                self.settle()
                return
        raise Stuck(f"no way from {r.id} to {nxt}")

    # --- the key
    def stand_and_face(self, obj_cells):
        """Walk to the nearest reachable tile beside obj_cells and face them."""
        g = self.g
        r = g.room
        reach = r.flood((math.floor(g.px), math.floor(g.py)))
        best = None
        for c in obj_cells:
            for dname, (dx, dy) in G.DIRS.items():
                stand = (c[0] - dx, c[1] - dy)
                if stand in reach and stand not in obj_cells:
                    p = r.path((math.floor(g.px), math.floor(g.py)), stand)
                    if p and (best is None or len(p) < best[0]):
                        best = (len(p), stand, (dx, dy))
        if best is None:
            raise Stuck(f"{r.id}: nowhere to stand by {obj_cells}")
        self.walk_path(best[1])
        self.face(best[2])

    def get_key(self):
        g = self.g
        rid, how, what = g.key_place
        self.go_to_room(rid)
        r = g.room
        if how == "open":
            self.walk_path(tuple(what))
        elif how == "search":
            o = g.house.find_obj(r, what)
            if o.side == "N":
                cells = [(o.index + i, -1) for i in range(o.gx)]
                stand = next(c for c in [(o.index + i, 0) for i in range(o.gx)] if c in r.flood((math.floor(g.px), math.floor(g.py))))
                self.walk_path(stand)
                self.face((0, -1))
            elif o.side == "W":
                stand = next(c for c in [(0, o.index + i) for i in range(o.gy)] if c in r.flood((math.floor(g.px), math.floor(g.py))))
                self.walk_path(stand)
                self.face((-1, 0))
            else:
                self.stand_and_face(set(o.cells()))
            g.interact()
            self.press((0, 0), lambda: g.searching is None)
        elif how == "under":
            o = g.house.find_obj(r, what)
            stand, d = g.house.push_plan(r, o)
            self.walk_path(stand)
            start = (o.x, o.y)
            self.press(d, lambda: (o.x, o.y) != start, limit=300)
            for _ in range(20):
                self.tick()
            check(g.key_state == "revealed", f"{rid}: pushing {o.type} did not reveal the key")
            self.walk_path((math.floor(g.key_pos[0]), math.floor(g.key_pos[1])))
        elif how == "rug":
            o = g.house.find_obj(r, what)
            reach = r.flood((math.floor(g.px), math.floor(g.py)))
            cell = next(c for c in o.cells() if c in reach)
            self.walk_path(cell)
            g.interact()
            self.press((0, 0), lambda: g.key_state != "hidden", limit=60)   # (two players: the host answers)
            check(g.key_state == "revealed", f"{rid}: lifting the rug did not reveal the key")
            self.walk_path((math.floor(g.key_pos[0]), math.floor(g.key_pos[1])))
        for _ in range(5):
            self.tick()
        if g.key_state != "carried":   # two players: wait for the host to hand it over
            self.press((0, 0), lambda: g.key_state == "carried", limit=60)
        return check(g.key_state == "carried", f"key {g.key_place} not obtained (state {g.key_state})")

    def escape(self):
        g = self.g
        self.go_to_room(M.START_ROOM)
        fd = g.room.front_door()
        self.walk_path((fd.index, 0))
        self.press((0, -1), lambda: g.mode != "play")   # ("watch": two players, the other is still in)
        return check(g.won, "walked into the front door with the key but did not win")


def data_checks():
    house = M.Mansion()
    errs = house.validate()
    for e in errs:
        check(False, "data: " + e)
    n = len(house.rooms)
    check(25 <= n <= 35, f"{n} rooms (want 25-35)")
    reach = house.reachable_rooms()
    check(len(reach) == n, f"unreachable rooms: {sorted(set(house.rooms) - reach)}")
    floors = {f: sum(1 for r in house.rooms.values() if r.floor == f) for f in M.FLOORS}
    check(all(floors.values()), f"every floor has rooms: {floors}")
    links = sum(1 for r in house.rooms.values() for o in r.objs if o.type in M.LINK_TYPES)
    places = house.hiding_places()
    ok = [p for p in places if house.obtainable(p)]
    kinds = {}
    for p in ok:
        kinds[p[1]] = kinds.get(p[1], 0) + 1
    print(f"rooms {n} {floors}; doors {len(M.DOORS)}; stair/ladder/trapdoor ends {links}")
    print(f"hiding places {len(places)}, obtainable {len(ok)}: {kinds}")
    picked = {}
    for seed in range(500):
        p = house.place_key(random.Random(seed), hidden=True)
        if not check(house.obtainable(p), f"seed {seed}: place_key chose an unobtainable spot {p}"):
            break
        picked[p[1]] = picked.get(p[1], 0) + 1
    print(f"place_key (hidden mode) over 500 seeds: {picked}")
    # the key out in the open (KEY_HIDDEN False, for now): always a visible, reachable floor tile
    check(M.KEY_HIDDEN is False, "the key is out in the open for now (KEY_HIDDEN False)")
    opens = set(house.open_places())
    rooms = set()
    for seed in range(500):
        p = house.place_key(random.Random(seed))
        r = house.rooms[p[0]]
        ok = (p[1] == "open" and p in opens and house.obtainable(p) and house.in_view(r, p[2])
              and tuple(p[2]) in r.free_floor() and p[0] != M.START_ROOM)
        if not check(ok, f"seed {seed}: open key on a hidden or unreachable tile {p}"):
            break
        rooms.add(p[0])
    check(len(rooms) >= 30, f"open keys turn up all over the house ({len(rooms)} rooms in 500 games)")
    print(f"open key: {len(opens)} visible floor tiles; 500 seeds used {len(rooms)} rooms")
    return house


WORLD_STEP = {"se": (56, 28), "sw": (-56, 28), "ne": (56, -28), "nw": (-56, -28)}  # screen px per tile walked


def walk_checks(g):
    """Animation: planted feet must not slide, footsteps must match touch-
    downs, idle must show the standing frame, and the frames must be there."""
    worst = 0.0
    for cid, ch in g.chars.items():
        meta = ch["meta"]
        n = meta["frames"]
        check(all(len(ch["walk"][k]) == n for k in WORLD_STEP), f"{cid}: {n} walk frames for every facing")
        check(all(ch["walk"][k][0].get_size() == tuple(meta["size"]) for k in WORLD_STEP), f"{cid}: frame size")
        for k, (sx, sy) in WORLD_STEP.items():
            feet = meta["facings"][k]["feet"]
            body = (sx * meta["cycle_tiles"] / n, sy * meta["cycle_tiles"] / n)   # body moves this far per frame
            for i in range(n):
                a, b = feet[i], feet[(i + 1) % n]
                for leg in ("near", "far"):
                    if a[leg]["down"] and b[leg]["down"]:
                        # on screen: foot = body + sprite offset, so the sprite offset must cancel the body's move
                        slide = math.hypot(b[leg]["x"] - a[leg]["x"] + body[0], b[leg]["y"] - a[leg]["y"] + body[1])
                        worst = max(worst, slide)
            check(feet[0]["near"]["down"] and feet[n // 2]["far"]["down"], f"{cid} {k}: touch-downs at frames 0 and {n // 2}")
    check(worst < 0.75, f"planted feet slide up to {worst:.2f} px per frame")
    # footsteps: walk a known distance and count them
    g.new_game(7)
    g.mode = "play"
    g.enter_room("ballroom", None)
    g.enemies = []
    g.px, g.py, g.facing = 1.5, 2.5, "E"
    def nsteps():
        return sum(g.sounds.requested.get(f"step{i}", 0) for i in (1, 2, 3))
    before = nsteps()
    x0 = g.px
    for _ in range(60):
        g.update(DT, ctrl=(0, 1))
    walked = g.px - x0
    steps = nsteps() - before
    cyc = g.chars[g.character]["meta"]["cycle_tiles"]
    check(abs(walked - G.PLAYER_SPEED) < 0.05, f"Up walks forward along the facing (moved {walked:.2f} tiles east)")
    check(abs(steps - math.floor(G.WALK_START * 2 + walked / cyc * 2)) <= 1,
          f"footsteps {steps} for {walked:.2f} tiles (cycle {cyc} tiles)")
    img_walk, feet = g.walk_frame()
    check(g.moving and feet is not None, "walking shows a walk frame")
    g.update(DT, ctrl=(0, 0))
    img, feet = g.walk_frame()
    check(feet is None and img is g.chars[g.character]["stand"]["se"], "standing still shows the standing frame")
    # backwards: Down walks back along the facing, the cycle runs in reverse, steps still sound
    x0, before = g.px, nsteps()
    phases = []
    for _ in range(30):
        g.update(DT, ctrl=(0, -1))
        phases.append(g.walk_phase)
    back_steps = nsteps() - before
    check(g.facing == "E" and g.px < x0 - 1.4, f"Down steps backwards without turning (facing {g.facing}, moved {g.px - x0:.2f})")
    dec = sum(1 for a, b in zip(phases, phases[1:]) if (b - a) % 1.0 > 0.5)
    check(dec >= len(phases) - 3, "walking backwards plays the walk cycle in reverse")
    check(back_steps >= 2, f"footsteps when walking backwards ({back_steps})")
    # turning: a quarter turn per press, clockwise for Right, TURN_S each; pose settles halfway
    g.update(DT, ctrl=(0, 0))
    order = []
    t = 0.0
    while len(order) < 4 and t < 2.0:
        g.update(DT, ctrl=(1, 0))
        t += DT
        if not order or order[-1] != g.facing:
            order.append(g.facing)
    check(order == ["S", "W", "N", "E"], f"holding Right turns clockwise S, W, N, E (got {order})")
    check(abs(t - 3 * G.TURN_S) < 0.1, f"held turns repeat every {G.TURN_S}s (4 facings reached in {t:.2f}s)")
    while g.turning:
        g.update(DT, ctrl=(0, 0))
    g.update(DT, ctrl=(-1, 0))
    check(g.facing == "N" and g.pose_facing() == "E", "Left turns anticlockwise; the sprite keeps the old facing at first")
    for _ in range(int(G.TURN_S / 2 / DT) + 1):
        g.update(DT, ctrl=(0, 0))
    check(g.pose_facing() == "N", "half way through a turn the sprite settles on the new facing")
    px0 = (g.px, g.py)
    still = True
    while g.turning:
        g.update(DT, ctrl=(0, 1))
        still = still and (not g.turning or (g.px, g.py) == px0)
    check(still, "no walking while turning")
    # a tap: one whole step; a tap during a turn is queued
    g.facing = "E"
    g.px, g.py = 2.5, 2.5
    g.try_action(("step", 1))
    for _ in range(60):
        g.update(DT, ctrl=(0, 0))
    check(abs(g.px - 2.5 - G.STEP_MIN) < 0.08, f"a tap of Up takes one step ({g.px - 2.5:.2f} tiles)")
    g.try_action(("turn", 1))
    g.try_action(("step", 1))
    for _ in range(60):
        g.update(DT, ctrl=(0, 0))
    check(g.facing == "S" and g.py > 2.5 + G.STEP_MIN - 0.08, "a step tapped during a turn happens after it")
    # blocked: walking into a wall does not animate or step
    g.facing = "W"
    g.px, g.py = 0.3, 2.5
    ph = g.walk_phase
    before = nsteps()
    for _ in range(30):
        g.update(DT, ctrl=(0, 1))
    check(nsteps() == before and abs(g.walk_phase - ph) < 0.05, "walking into a wall should not move the legs or step")
    print(f"walk cycles: {', '.join(f'{c} {ch['meta']['cycle_tiles']:.2f} tiles' for c, ch in g.chars.items())}; "
          f"worst planted-foot slide {worst:.2f} px/frame; {steps} footsteps over {walked:.2f} tiles; "
          f"turns {G.TURN_S}s each")


def _figure_h(img):
    a = pygame.surfarray.array_alpha(img)
    rows = (a > 40).any(axis=0).nonzero()[0]
    return int(rows.max() - rows.min() + 1)


def anim_checks(g):
    """The bat's wing beat and the skeleton's distance-driven walk."""
    g.new_game(1)
    g.mode = "play"
    for kind, n in (("bat", 4), ("skeleton", 4)):
        for left in (False, True):
            fr = [g.art.enemy_frame(kind, i, left) for i in range(n)]
            check(all(f is not None for f in fr), f"{kind}: {n} animation frames ({'left' if left else 'right'})")
            check(len({f[0].get_size() for f in fr if f}) == 1, f"{kind}: every frame the same size")
    img, ax, ay = g.art.enemy_frame("skeleton", 1, False)
    img2, ax2, _ = g.art.enemy_frame("skeleton", 1, True)
    check(abs((ax + ax2) - img.get_width()) < 1e-6, "mirrored for screen left about the same anchor")
    check(abs(img.get_height() - 202) <= 4 and abs(g.art.enemy_frame("bat", 1, False)[0].get_width() - 111) <= 4,
          f"frames at their in-game sizes (skeleton {img.get_height()} px tall, 20% over the old sprite)")
    archie = g.chars["archie"]["stand"]["se"]
    check(_figure_h(img) > _figure_h(archie) * 1.15, f"the skeleton stands well over Archie ({_figure_h(img)} / {_figure_h(archie)} px)")
    check(_figure_h(img) <= G.WALL_H - 20, "and still well under the walls")
    g.enemies = [G.Enemy("bat", 3.0, 3.0, g.rng), G.Enemy("skeleton", 2.0, 2.0, g.rng)]
    bat, sk = g.enemies
    bat.phase, frames = 0.0, []
    for _ in range(60):
        bat.phase += DT
        g.animate_enemies(DT)
        frames.append(bat.frame)
    flips = sum(1 for a, b in zip(frames, frames[1:]) if a != b)
    check(8 <= flips <= 10, f"the bat flaps at {flips} frames a second (want 8-10)")
    req = lambda: sum(g.sounds.requested.get(f"skel_clack{i}", 0) for i in (1, 2))
    g.px, g.py = 2.0, 4.0
    c0, seen, walked = req(), [], 0.0
    for _ in range(120):                      # 1.2 tiles at 0.6 tiles/s
        sk.x += 0.6 * DT
        walked += 0.6 * DT
        g.animate_enemies(DT)
        seen.append(sk.frame)
    changes = sum(1 for a, b in zip(seen, seen[1:]) if a != b)
    check(abs(changes - walked / G.SKEL_FRAME_D) <= 1, f"skeleton frames follow distance ({changes} over {walked:.2f} tiles)")
    falls = sum(1 for a, b in zip(seen, seen[1:]) if a != b and b in (0, 2))
    check(req() - c0 == falls and falls >= 1, f"a clack on every footfall ({req() - c0} / {falls})")
    for _ in range(30):
        g.animate_enemies(DT)
    check(sk.frame == 1, "standing still: the legs-together frame")
    print(f"anims: bat {flips} frames/s, skeleton {changes} frames over {walked:.2f} tiles, {falls} footfalls")


def exit_frame_checks(g):
    """The door frames marking exits: strictly isometric, and the front-edge
    ghost frames fade when someone stands behind them."""
    worst, edges, exits = 0.0, 0, 0
    for r in M.Mansion().rooms.values():
        for side in ("N", "W", "S", "E"):
            rng = r.door_range(side)
            if rng is None:
                continue
            exits += 1
            W = {"N": lambda u, z, n: g.P(u, n, z, r), "W": lambda u, z, n: g.P(n, u, z, r),
                 "S": lambda u, z, n: g.P(u, r.d + n, z, r), "E": lambda u, z, n: g.P(r.w + n, u, z, r)}[side]
            for _, poly in G.door_frame_polys(W, rng.start, rng.stop, (100, 80, 60), 0.0, 0.07):
                for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
                    dx, dy = x1 - x0, y1 - y0
                    if abs(dx) < 1e-9:
                        continue            # an upright
                    edges += 1
                    worst = max(worst, abs(abs(dy / dx) - 0.5) if abs(dy) > 1e-9 else 0.0)
    check(worst < 1e-9, f"door frame edges are upright or exactly 2:1 isometric ({edges} sloped edges, worst error {worst:.2g})")
    check(exits >= 60, f"every exit gets a frame ({exits} exits)")
    g.new_game(1)
    g.mode = "play"
    g.enter_room("staircase_hall", None)
    g.fade = None
    r = g.room
    rng = r.door_range("S")
    lay, at = g.ghost_frame(r, "S")
    rect = lay.get_rect(topleft=at)
    keep = g.enemies
    g.enemies = []
    g.px, g.py = (rng.start + rng.stop) / 2, r.d - 0.3
    behind = g.ghost_fade(r, "S", rect)
    near = g.exit_near(r, "S")
    g.px, g.py = 1.0, 1.0
    far = g.ghost_fade(r, "S", rect)
    g.enemies = keep
    check(behind < 0.6 and far == 1.0, f"the ghost frame fades when the player is behind it ({behind:.2f} vs {far:.2f})")
    check(near > 0.5 and g.exit_near(r, "S") == 0.0, "the exit glow only comes on near the doorway")
    lands = [r for r in M.Mansion().rooms.values() if "landing" in r.id]
    check(len(lands) == 2 and all(r.style["floor"] == "parquet" for r in lands), "both landings have parquet floors")
    check(G.GHOST_FRAME_ALPHA / 255 <= 0.45, "the front-edge ghost frames stay see-through")
    check(G.BACK_FRAME_ALPHA == 255 and G.BACK_VOID_ALPHA == 255, "back-wall frames and openings are solid")
    # no wall shows through a back-wall doorway: the opening is pure void colour in every room
    bad, n = [], 0
    for rr in M.Mansion().rooms.values():
        bg = None
        for side in ("N", "W"):
            rng = rr.door_range(side)
            if rng is None:
                continue
            if bg is None:
                bg = g.build_background(rr)
            a, b = rng.start, rng.stop
            for fu in (0.45, 0.6, 0.75, 0.9):
                for z in (30, 70, 110, 150):
                    u = a + (b - a) * fu
                    x, y = g.P(u, 0, z, rr) if side == "N" else g.P(0, u, z, rr)
                    n += 1
                    if tuple(bg.get_at((int(x), int(y))))[:3] != G.BACK_VOID:
                        bad.append((rr.id, side, round(u, 2), z, tuple(bg.get_at((int(x), int(y))))[:3]))
    check(n > 100 and not bad, f"back-wall doorways are solid black ({n} samples, wall showing at {bad[:4]})")


def shadow_checks(g):
    """No floating shadows: only legged furniture gets a (tight) contact
    shadow, no painted ground shadow is left in the art, baddies' shadows
    are soft, the loft ladder reaches the ceiling, and no window shows the moon."""
    import numpy as np
    for name in ("piano", "fireplace", "wardrobe", "bookcase", "kitchen_dresser", "grandfather_clock",
                 "range_cooker", "boiler", "chest_of_drawers", "desk", "kitchen_island"):
        check(name not in G.CONTACT_SHADOW, f"{name}: no floor shadow")
    check(all(n in T for n in G.CONTACT_SHADOW), "contact shadows only name real pieces")
    baked = []
    for name, t in T.items():
        if t["kind"] not in ("furniture", "link"):
            continue
        p = os.path.join(art.ART_DIR, name + ".png")
        if not os.path.exists(p):
            continue
        a = pygame.surfarray.pixels3d(pygame.image.load(p)).copy()
        al = pygame.surfarray.pixels_alpha(pygame.image.load(p)).copy()
        h = a.shape[1]
        band = (slice(None), slice(int(h * 0.65), None))
        m = (a[band].max(2) < 12) & (al[band] > 10) & (al[band] < 230)
        if m.sum() > 400:      # translucent black: a painted ground shadow
            baked.append((name, int(m.sum())))
    check(not baked, f"no painted ground shadows left in the art {baked}")
    sh = art.soft_shadow(30, 12, 120)
    alpha = pygame.surfarray.pixels_alpha(sh)
    check(alpha.max() <= 120 and 0 < alpha[2, 12] < alpha[30, 12], "enemy shadows are soft (fade out to the rim)")
    del alpha
    lad = g.art.base("ladder_up")
    check(lad.get_height() >= 1.0 * WALL_H, f"the loft ladder reaches the ceiling ({lad.get_height()} px)")
    win = pygame.surfarray.pixels3d(pygame.image.load(os.path.join(art.ART_DIR, "window.png"))).astype(int)
    check(int((win.mean(2) > 200).sum()) < 40, f"no moon in the window ({int((win.mean(2) > 200).sum())} bright px)")


def kitchen_checks(house):
    """The kitchen: no table and chairs, an island in their place, the range
    and dresser apart, and the doorways, stairs and sink all reachable."""
    k = house.rooms["kitchen"]
    types = [o.type for o in k.objs]
    check("kitchen_table" not in types and "chair" not in types, f"no table or chairs in the kitchen {types}")
    isl = [o for o in k.objs if o.type == "kitchen_island"]
    check(len(isl) == 1 and isl[0].gx == isl[0].gy >= 2, "a large square kitchen island in their place")
    check(T["kitchen_island"]["solid"] and "kitchen_island" in art.ISO_BOX_ART, "the island is solid iso-box art")
    rng_ = next(o for o in k.objs if o.type == "range_cooker")
    dres = next(o for o in k.objs if o.type == "kitchen_dresser")
    gap = min(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in rng_.cells() for b in dres.cells())
    check(gap >= 3, f"the range and the dresser are well apart ({gap} tiles)")
    doors = [c for side in "NSEW" for c in k.door_cells(side)]
    reach = k.flood(doors[0])
    check(all(c in reach for c in doors), "every kitchen doorway reaches every other")
    near = lambda o: any((c[0] + dx, c[1] + dy) in reach for c in o.cells()
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    for t in ("sink", "stairs_down", "kitchen_island", "range_cooker", "kitchen_dresser"):
        o = next(o for o in k.objs if o.type == t)
        check(near(o), f"kitchen: the {t} can be reached")
    opens = [p for p in house.open_places() if p[0] == "kitchen"]
    check(len(opens) >= 10, f"the key can still turn up in the kitchen ({len(opens)} tiles)")
    # windows only on outside walls: never on a wall shared with another room on the house plan
    from mansion import ROOMS
    occ = {(r["floor"], r["map"]) for r in ROOMS.values()}
    dirs = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
    inner = [(key, w[1]) for key, r in ROOMS.items() for w in r["wall"] if w[0] == "window"
             and (r["floor"], (r["map"][0] + dirs[w[1]][0], r["map"][1] + dirs[w[1]][1])) in occ]
    check(not inner, f"every window is on an outside wall {inner}")
    check(not any(w[0] == "window" for w in ROOMS["kitchen"]["wall"]), "no window in the kitchen (an inside wall)")
    print(f"kitchen: island at {isl[0].cells()}, range-dresser gap {gap}, {len(opens)} open key tiles")


def grand_stairs_checks(g):
    """The grand staircase: walked up from the hall's floor to the top, where
    it leads on to the Landing; banisters you can't pass through; a gallery
    round an open stairwell nobody can walk into; no key, baddie or path on
    the stairs or in the drop; the banisters fade in front of the player."""
    import grand
    h = g.house
    hall, land = h.rooms["staircase_hall"], h.rooms["landing"]
    solid, psolid = hall.solid_cells(), hall.player_solid()
    check(hall.flight and all(c in solid for c in hall.flight), f"the flight is solid to baddies, pushing and the key ({len(hall.flight)} tiles)")
    check(not any(c in psolid for c in hall.flight), "but the player walks on it")
    trig = land.trigger_cells()
    lsolid = land.solid_cells()
    check(land.well and all((c in lsolid) != (c in trig) for c in land.well),
          f"the stairwell is solid, but for the top of the stairs in the gap ({sorted(trig)})")
    for r in (hall, land):
        doors = [c for side in "NSEW" for c in r.door_cells(side)]
        reach = r.flood(doors[0])
        check(all(c in reach for c in doors), f"{r.name}: every doorway reaches every other round the stairs")
        link = r.grand_link()
        ex, ey = link.exit_pos()
        check((int(ex), int(ey)) in reach, f"{r.name}: the stairs' end is reachable ({ex}, {ey})")
        bad = [p for p in h.open_places() if p[0] == r.id and tuple(p[2]) in (r.flight | r.well)]
        check(not bad, f"{r.name}: the key never turns up on the stairs or in the drop {bad[:3]}")
        free = set(r.free_floor())
        check(not (free & (r.flight | r.well)), f"{r.name}: no free floor (baddie spawns) on the stairs or in the drop")
    p = hall.path((1, 0), (1, 6))
    check(p is not None and not (set(p) & hall.flight), f"baddies path round the foot of the stairs ({len(p or [])} tiles)")
    p = land.path((1, 3), (6, 4))
    check(p is not None and not (set(p) & land.well), f"and round the gallery ({len(p or [])} tiles)")
    # heights: up the steps to the top, flat floor off them
    zs = [hall.floor_z(5.0 - k * 0.25, 4.0) for k in range(1, 20)]
    check(all(b >= a for a, b in zip(zs, zs[1:])) and zs[-1] >= hall.STAIR_TOP * 0.8 and hall.floor_z(3, 5.5) == 0
          and hall.floor_z(5.2, 4.0) == 0 and hall.STAIR_TOP == G.WALL_H, f"the steps rise to the top ({zs[0]:.0f} -> {zs[-1]:.0f} px), the floor beside them is flat")
    # walking: banisters stop you both ways, then up the stairs to the Landing
    god = g.god
    g.god = True
    g.enter_room("staircase_hall", None)
    g.enemies, g.fade = [], None
    g.px, g.py = 3.0, 5.5
    for _ in range(60):
        g.move_player(0, -1, DT)
    check(g.py >= 5 + G.PLAYER_R - 1e-3, f"the banister stops you climbing on from the side ({g.py:.2f})")
    g.px, g.py = 3.0, 4.0
    for _ in range(60):
        g.move_player(0, 1, DT)
    check(g.py <= 5 - G.PLAYER_R + 1e-3, f"and stepping off the side of the flight ({g.py:.2f})")
    g.px, g.py = 5.6, 5.15
    for _ in range(40):
        g.move_player(-1, 0, DT)
    check(g.px >= 5.0, f"the newel posts stand at the foot ({g.px:.2f})")
    g.px, g.py, g.facing = 5.6, 4.0, "W"
    zs, n = [], 0
    while g.room is hall and n < 400:
        g.update(DT, ctrl=g.steer((-1, 0), False))
        zs.append(hall.floor_z(g.px, g.py))
        n += 1
    check(g.room is land, f"up the grand staircase to the Landing ({n} frames)")
    check(max(zs) >= hall.STAIR_TOP * 0.8, f"climbing all the way up ({max(zs):.0f} px)")
    for _ in range(40):
        g.update(DT)
    check(abs(g.py - 4.0) < 0.6 and g.px < 2.0 and g.facing == "W", f"arriving on the gallery by the gap ({g.px:.2f}, {g.py:.2f})")
    # the gallery: the drop stops you; the gap takes you back down
    g.px, g.py = 4.0, 1.5
    for _ in range(60):
        g.move_player(0, 1, DT)
    check(g.py <= 2 - G.PLAYER_R + 1e-3, f"the banister keeps you out of the stairwell ({g.py:.2f})")
    # the stairs and the banister are always solid: every layer blitted at full alpha,
    # with someone behind them, in front of them, beside, on or nowhere near them
    class Spy(pygame.Surface):
        def blit(self, src, *a, **k):
            if id(src) in mine:
                drawn.append(src.get_alpha())
            return super().blit(src, *a, **k)
    real = g.screen
    for rid, spots in (("landing", [(2.6, 1.7), (4.0, 1.5), (6.6, 6.6), (1.5, 4.0), (6.5, 3.0)]),
                       ("staircase_hall", [(3.0, 2.4), (1.0, 2.5), (5.6, 4.0), (3.0, 4.0), (6.6, 6.6), (2.0, 5.6)])):
        g.enter_room(rid, None)
        g.enemies, g.fade = [], None
        mine = {id(img) for _, img, _ in grand.layers(g, g.room)}
        drawn = []
        g.screen = Spy(real.get_size(), pygame.SRCALPHA)
        for x, y in spots:
            for _ in range(20):
                g.px, g.py = x, y
                g.time += DT
                g.draw()
        g.screen = real
        n = len(grand.layers(g, g.room))
        check(len(drawn) == n * 20 * len(spots) and all(a is None or a == 255 for a in drawn),
              f"the {g.room.name}'s {'flight' if rid == 'staircase_hall' else 'banister'} is always drawn solid ({len(drawn)} blits, alphas {sorted(set(drawn), key=str)})")
    g.enter_room("landing", None)
    g.enemies, g.fade = [], None
    # depth: on the flight, drawn over the row underfoot and under the rows below
    box = grand.figure_box(hall, 3.3, 4.0, G.PLAYER_R)
    order = G.depth_sort([((3, 3, 4, 5), "row3"), ((4, 3, 5, 5), "row4"), (box, "me")])
    check([w for _, w in order] == ["row3", "me", "row4"], f"on the stairs: the step underfoot behind, the lower steps in front {[w for _, w in order]}")
    g.px, g.py, g.fade = 1.5, 4.0, None
    g.facing = "E"
    n = 0
    while g.room is land and n < 200:
        g.update(DT, ctrl=g.steer((1, 0), False))
        n += 1
    check(g.room is hall, f"down through the gap to the Staircase Hall ({n} frames)")
    for _ in range(40):
        g.update(DT)
    check(not hall.on_flight(g.px, g.py) and g.px > 5.0, f"arriving at the foot of the stairs ({g.px:.2f}, {g.py:.2f})")
    g.god = god
    # the West Corridor lines up: the hall's door, both of its doors and the Music Room's
    wc, mr = h.rooms["west_corridor"], h.rooms["music_room"]
    offs = [r.doors[sd]["at"] - (r.side_len(sd) - M.DOOR_W) // 2 for r, sd in ((hall, "W"), (wc, "E"), (wc, "W"), (mr, "E"))]
    check(offs == [2, 2, 2, 2], f"the West Corridor's doorways all line up, two tiles south of centre {offs}")
    hw = hall.door_cells("W")
    check(all(c[1] >= 5 for c in hw) and hall.doors["N"]["at"] == 3, f"the corridor door beside the stairs, the Entrance Hall door back in the middle {hw}")
    gd = hall.grand
    check(gd["x0"] + gd["x1"] == hall.d, f"the flight is centred across the hall (banisters at y {gd['x0']} and {gd['x1']})")
    wc_doors = set(wc.doors)
    check(wc_doors == {"E", "W"} and "S" not in h.rooms["drawing_room"].doors and "N" not in h.rooms["dining_room"].doors,
          f"the West Corridor has no doors to the Drawing Room or the Dining Room ({sorted(wc_doors)})")
    for rid in ("drawing_room", "dining_room"):
        check(len(h.route("staircase_hall", rid)) > 1, f"the {h.rooms[rid].name} still has a way in")
    check("S" not in h.rooms["east_corridor"].doors and "N" not in h.rooms["scullery"].doors,
          "no door between the East Corridor and the Scullery")
    check(len(h.route("staircase_hall", "scullery")) > 1, "the Scullery still has a way in (Kitchen, Coal Cellar)")
    # open underneath: the floor shows through under the high end, between the posts
    g.enter_room("staircase_hall", None)
    g.enemies, g.px, g.py, g.fade = [], 6.5, 6.5, None
    g.draw()
    seen = 0
    for x in (1.0, 1.4, 1.8):
        qx, qy = (round(v) for v in g.P(x, 4.0, 4))
        covered = False
        for _, img, (lx, ly) in grand.layers(g, hall):
            if 0 <= qx - lx < img.get_width() and 0 <= qy - ly < img.get_height() and img.get_at((qx - lx, qy - ly))[3] > 0:
                covered = True
        seen += not covered
    check(seen >= 2, f"the floor runs on under the stairs ({seen}/3 points show the floor)")
    check(all(c in hall.solid_cells() for c in hall.flight), "but nobody walks underneath (the flight stays solid below)")
    print(f"grand stairs: flight {len(hall.flight)} tiles up to {hall.STAIR_TOP} px, well {len(land.well)} tiles, "
          f"{len(grand.layers(g, hall))}+{len(grand.layers(g, land))} layers")


def vampire_checks(g):
    """The Crypt's vampire: a floater, animated, hovering, with a soft shadow that shrinks with height."""
    import numpy as np
    check("vampire" in g.house.rooms["crypt"].enemies, "a vampire haunts the Crypt")
    e = G.Enemy("vampire", 3.0, 3.0, g.rng)
    check(e.floats and e.z0 >= 30, f"the vampire floats, well clear of the floor (z {e.z0})")
    for left in (False, True):
        fr = [g.art.enemy_frame("vampire", i, left) for i in range(4)]
        check(all(f is not None for f in fr) and len({f[0].get_size() for f in fr}) == 1,
              f"vampire: 4 frames ({'left' if left else 'right'})")
    img = g.art.enemy_frame("vampire", 0, False)[0]
    skel = g.art.enemy_frame("skeleton", 1, False)[0]
    check(abs(_figure_h(img) - _figure_h(skel)) <= 0.15 * _figure_h(skel),
          f"about the skeleton's height ({_figure_h(img)} / {_figure_h(skel)} px)")
    e.phase, frames = 0.0, []
    g.enemies = [e]
    for _ in range(60):                       # one second
        e.phase += DT
        g.animate_enemies(DT)
        frames.append(e.frame)
    flips = sum(1 for a, b in zip(frames, frames[1:]) if a != b)
    check(5 <= flips <= 7 and set(frames) == {0, 1, 2, 3}, f"the vampire loops its 4 frames at ~6 fps ({flips}/s)")
    # no shadow: draw_enemy_shadow is never called for him, and the floor under him is untouched
    g.new_game(1)
    g.mode = "play"
    g.enter_room("crypt", None)
    calls = []
    orig = g.draw_enemy_shadow
    g.draw_enemy_shadow = lambda *a, **k: (calls.append(a[0].kind), orig(*a, **k))
    g.enemies, g.px, g.py = [], 6.5, 1.5
    g.draw()
    bare = pygame.surfarray.array3d(g.screen).astype(int)
    v = G.Enemy("vampire", 4.5, 5.5, g.rng)
    g.enemies = [v]
    zs, sizes = [], []
    osh = art.soft_shadow
    for i in range(40):
        v.phase = i * 0.1
        z = v.z0 + G.VAMP_BOB * math.sin(v.phase * G.VAMP_BOB_RATE)
        zs.append(z)
        got = []
        art.soft_shadow = lambda *a, **k: (got.append(a), osh(*a, **k))[1]
        g.draw()
        art.soft_shadow = osh
        sz = [a for a in got if len(a) >= 3]
        if calls and sz:
            sizes.append((z, sz[-1][0], sz[-1][2]))
    check(calls.count("vampire") == 40, f"a shadow is drawn for the vampire every frame ({len(calls)})")
    lo, hi = min(sizes), max(sizes)
    check(hi[1] < lo[1] and hi[2] < lo[2], f"his shadow shrinks and fades as he rises ({lo[1]:.1f}->{hi[1]:.1f})")
    check(min(zs) > 25 and max(zs) - min(zs) > 6, f"he bobs slowly, always clear of the floor (z {min(zs):.0f}-{max(zs):.0f})")
    v.phase = 0.0
    g.draw()
    now = pygame.surfarray.array3d(g.screen).astype(int)
    fx, fy = g.P(v.x, v.y, 0)
    fx, fy = int(fx), int(fy)
    win = (slice(fx - 30, fx + 30), slice(fy - 8, fy + 8))
    diff = int((np.abs(now[win] - bare[win]).sum(2) > 6).sum())
    check(diff > 20, f"a soft shadow darkens the floor beneath him ({diff} px changed)")
    check((now[win].sum(2) <= bare[win].sum(2) + 3).all(), "the shadow only darkens")
    del g.draw_enemy_shadow
    for k in ("bat", "skeleton", "vampire"):
        check(k not in G.NO_SHADOW, f"{k}s keep their soft shadows")
    check("vampire" in G.SOUND_VOL and G.SOUND_VOL["vampire"] <= 0.4, "a quiet hiss for him")
    # behaviour: drifts slowly, glides at you when close, hisses once, and hurts
    g.grace, g.invuln, god = 0.0, 0.0, g.god
    v = G.Enemy("vampire", 2.0, 2.0, g.rng)
    g.enemies, g.px, g.py = [v], 6.5, 6.5
    x0, y0 = v.x, v.y
    hiss0 = g.sounds.requested.get("vampire", 0)
    for _ in range(60):
        g.update(DT)
    drift = math.hypot(v.x - x0, v.y - y0)
    check(not v.chasing and drift <= v.speed * 0.5 + 1e-6, f"far off he drifts slowly ({drift:.2f} tiles/s)")
    check(g.sounds.requested.get("vampire", 0) == hiss0, "silently")
    g.px, g.py = v.x + 2.5, v.y
    d0 = 2.5
    for _ in range(30):
        g.update(DT)
    d1 = math.hypot(g.px - v.x, g.py - v.y)
    check(v.chasing and d0 - d1 > 0.5 * v.speed * 0.5 * 0.9, f"close by he glides at you ({d0:.2f} -> {d1:.2f})")
    check(abs(v.speed - 1.15 * G.ENEMY_SPEED_SCALE) < 1e-9, f"at the global speed scale ({v.speed:.2f} tiles/s)")
    for _ in range(120):
        g.update(DT)
    check(g.sounds.requested.get("vampire", 0) - hiss0 == 1, "one quiet hiss as he starts the chase, not a stream")
    g.god, lives = False, g.lives
    g.px, g.py, v.x, v.y, g.invuln = v.x + 0.3, v.y, v.x, v.y, 0.0
    for _ in range(10):
        g.update(DT)
    check(g.lives == lives - 1, f"his touch hurts ({lives} -> {g.lives})")
    g.god = god
    print(f"vampire: {flips} frames/s, hover z {min(zs):.0f}-{max(zs):.0f}, floor diff {diff}")


def round_room_checks(g):
    """The round conservatory: floor, collision, key and enemies all keep
    to the circle, and its drawn outline is a true 2:1 iso ellipse."""
    house = M.Mansion()
    r = house.rooms["conservatory"]
    check(r.round and len(r.void) == 20, f"the conservatory is round ({len(r.void)} void corner cells)")
    check(not any(c in r.void for o in r.objs for c in o.cells()), "conservatory furniture stands inside the circle")
    check(not any(p[0] == r.id and p[1] == "open" and tuple(p[2]) in r.void for p in house.hiding_places()),
          "the key never lies in the conservatory's void corners")
    reach = house.room_reach(r)
    check(not (reach & r.void), "nothing paths through the void corners")
    for side in ("S", "E"):
        check(all(c in reach for c in r.door_cells(side)), f"the conservatory's {side} doorway is reachable")
    g.new_game(1)
    g.mode = "play"
    g.enter_room("conservatory", None)
    g.fade = None
    keep = g.enemies
    g.enemies = []
    worst = 0.0
    for ang in range(0, 360, 10):
        g.px, g.py = r.cx, r.cy
        dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        for _ in range(240):
            g.move_player(dx, dy, 1 / 60)
            if r.in_door_way(g.px, g.py, G.PLAYER_R):
                break
            worst = max(worst, math.hypot(g.px - r.cx, g.py - r.cy))
    check(worst <= r.rad - G.PLAYER_R + 1e-6, f"you can't walk through the curved glass ({worst:.3f} <= {r.rad - G.PLAYER_R:.2f})")
    out = 0
    for start, d in (((3.3, 6.0), (0, 1)), ((6.0, 3.3), (1, 0))):
        g.enter_room("conservatory", None)
        g.fade = None
        g.enemies = []
        g.px, g.py = start
        for _ in range(240):
            g.move_player(*d, 1 / 60)
            g.check_exits()
            if g.fade:
                out += 1
                break
    check(out == 2, f"both conservatory doorways lead out ({out}/2)")
    bat = G.Enemy("bat", 4, 4, random.Random(2))
    for _ in range(600):
        g._float(bat, r, False, 1 / 30, 4, 4)
    check(math.hypot(bat.x - r.cx, bat.y - r.cy) <= r.rad - 0.35 + 1e-6, "a bat in the conservatory stays inside the glass")
    g.enemies = keep
    ox, oy = g.P(r.cx, r.cy, 0, r)
    err = 0.0
    for i in range(36):
        x, y = g.P(*roundroom.arc(r, i * math.pi / 18), 0, r)
        hw, hh = r.rad * math.sqrt(2) * G.HW, r.rad * math.sqrt(2) * G.HH
        err = max(err, abs(((x - ox) / hw) ** 2 + ((y - oy) / hh) ** 2 - 1))
    check(err < 1e-9 and abs(G.HW / G.HH - 2) < 1e-9, f"the conservatory's circle is drawn as an exact 2:1 ellipse (err {err:.1g})")


def safe_room_checks(g):
    """The conservatory is a calm, safe room: nothing ever spawns there (from
    any doorway, any seed, even if its data named a baddie), the baddies next
    door can't follow you in, and it has its own gentle rain-on-glass loop."""
    house = g.house
    r = house.rooms["conservatory"]
    check(r.safe and r.enemies == [], f"the conservatory is safe, with no baddies listed ({r.enemies})")
    check([rid for rid, x in house.rooms.items() if x.safe] == ["conservatory"], "and it is the only safe room")
    spawned = 0
    for seed in range(40):
        g.new_game(seed)
        g.mode = "play"
        for side in ("N", "S", "E", "W"):
            if r.door_range(side) is None:
                continue
            g.enter_room("conservatory", ("door", side, 0.0))
            spawned += len(g.enemies)
        g.enter_room("conservatory", None)
        spawned += len(g.enemies)
    check(spawned == 0, f"nothing spawns in the conservatory over 40 games ({spawned})")
    r.enemies = ["goblin", "bat"]                 # even a data slip can't put one there
    check(g.make_enemies(r, r.cx, r.cy) == [], "a safe room refuses any baddie its data names")
    r.enemies = []
    # a ghost in the drawing room chases you to the conservatory door: it stays behind
    g.new_game(3)
    g.mode = "play"
    g.enter_room("drawing_room", None)
    dr = g.room
    side = next(s for s, d in dr.doors.items() if d["to"] == "conservatory")
    g.enter_room("drawing_room", ("door", side, 0.0))
    g.grace = 0.0
    gh = G.Enemy("ghost", g.px + (1.5 if side == "W" else 0), g.py + (1.5 if side == "N" else 0), g.rng)
    g.enemies = [gh]
    for _ in range(30):
        g.update(DT)
    chased = gh.chasing
    nxt = dr.doors[side]["to"]
    g.enter_room(nxt, ("door", M.OPPOSITE[side], 0.0))
    check(chased and g.room.id == "conservatory" and g.enemies == [] and gh not in g.enemies,
          "a baddie chasing you to the conservatory door can't follow you in")
    god, g.god, lives, g.grace = g.god, False, g.lives, 0.0
    for _ in range(120):
        g.update(DT)
    check(g.enemies == [] and g.lives == lives, "and nothing finds you in there")
    g.god = god
    # its ambience: soft rain on the glass, back to the house's wind outside
    g.sounds.loop_name = "ambience"
    g.enter_room("conservatory", None)
    check(g.sounds.loop_name == "rain_glass" and os.path.exists(os.path.join(G.SOUND_DIR, "rain_glass.wav")),
          f"rain on the glass in the conservatory ({g.sounds.loop_name})")
    check(G.SOUND_VOL["rain_glass"] <= G.SOUND_VOL["ambience"], "played softly")
    g.enter_room("music_room", None)
    check(g.sounds.loop_name == "ambience", f"and the house's own ambience again outside ({g.sounds.loop_name})")
    g.sounds.loop_name = "title_theme"
    g.enter_room("conservatory", None)
    check(g.sounds.loop_name == "title_theme", "(only swapped in play, never over the title music)")
    g.sounds.loop_name = None
    print(f"safe room: conservatory, {spawned} spawns over 40 games")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--shots", default=None)
    args = ap.parse_args()
    t0 = time.time()
    data_checks()
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    g = G.Game(screen, seed=1, enemies=True, god=True, save=False, title=False)
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    walk_checks(g)
    anim_checks(g)
    exit_frame_checks(g)
    round_room_checks(g)
    shadow_checks(g)
    kitchen_checks(g.house)
    safe_room_checks(g)
    vampire_checks(g)
    grand_stairs_checks(g)
    # ---- full tour with enemies (invulnerable)
    if not args.quick:
        g.new_game(1)
        pilot = Pilot(g, args.shots)
        order = list(M.Mansion().rooms)
        try:
            for rid in order:
                if rid not in g.visited:
                    pilot.go_to_room(rid)
            check(len(g.visited) == len(g.house.rooms), f"tour visited {len(g.visited)} rooms")
            pilot.get_key()
            pilot.escape()
            print(f"tour: visited {len(g.visited)}/{len(g.house.rooms)} rooms, key {g.key_place[1]} in {g.key_place[0]}, "
                  f"won in {G.fmt_time(g.time)} game time ({pilot.frames} frames)")
        except Stuck as e:
            check(False, f"tour stuck: {e}")
        # one mortal game: enemies must be able to hurt you, and losing must end the game
        g.god = False
        g.new_game(5)
        g.mode = "play"
        g.enter_room("boiler_room", None)
        e = g.enemies[0]
        e.x, e.y = g.px + 0.2, g.py
        g.grace = 0
        g.update(DT, auto=(0, 0))
        check(G.LIVES == 5 and g.max_lives == 5, f"five hearts at the start (LIVES {G.LIVES})")
        check(g.lives == G.LIVES - 1, f"touching the {e.kind} should cost a life (lives {g.lives})")
        g.lives = 1
        g.invuln = 0
        e = g.enemies[0]
        e.x, e.y = g.px, g.py
        g.grace = 0
        g.update(DT, auto=(0, 0))
        check(g.mode == "end" and g.lost, "last life lost should end the game")
        g.god = True
    # ---- key games: straight to the key and out, no enemies (key in the open, then hidden mode)
    g.enemies_on = False
    n_games = 10 if args.quick else args.games
    for hidden in (False, True):
        g.key_hidden = hidden
        kinds = {}
        for seed in range(100, 100 + n_games):
            g.new_game(seed)
            g.mode = "play"
            check(hidden or (g.key_place[1] == "open" and g.key_state == "revealed"),
                  f"seed {seed}: the key starts out in the open ({g.key_place})")
            pilot = Pilot(g)
            try:
                got = pilot.get_key() and pilot.escape()
            except Stuck as e:
                check(False, f"seed {seed}: {e}")
                got = False
            k = g.key_place[1]
            kinds[k] = kinds.get(k, 0) + (1 if got else 0)
        print(f"key games won ({'hidden' if hidden else 'open'} key): {sum(kinds.values())}/{n_games} by kind {kinds}")
    g.key_hidden = M.KEY_HIDDEN
    # ---- with the key in the open, searching, lifting and pushing still work but never find it
    g.new_game(77)
    g.mode = "play"
    n_s = 0
    for r in g.house.rooms.values():
        g.room = r
        for o in r.objs + r.walls:
            if o.t.get("search"):
                g.finish_search(o)
                n_s += 1
            elif o.t.get("lift"):
                g.room = r
                o.lifted = True
        r.reset_pushables()
    check(g.key_state == "revealed" and g.key_place[1] == "open" and g.score == 0,
          f"searching all {n_s} hiding places finds nothing when the key is in the open ({g.key_state})")
    check(any(o.searched for r in g.house.rooms.values() for o in r.objs + r.walls), "and they still get searched")
    for r in g.house.rooms.values():
        for o in r.objs:
            o.lifted = False
            o.searched = False
    # ---- every single hiding place, one by one (the slow, thorough part)
    if not args.quick:
        house = M.Mansion()
        places = [p for p in house.hiding_places() if house.obtainable(p) and p[1] != "open"]
        opens = [p for p in house.hiding_places() if p[1] == "open" and house.obtainable(p)]
        places += random.Random(3).sample(opens, min(40, len(opens)))
        okc = 0
        for i, p in enumerate(places):
            g.new_game(1000 + i)
            g.key_place = p
            g.key_state = "revealed" if p[1] == "open" else "hidden"
            g.key_pos = (p[2][0] + 0.5, p[2][1] + 0.5) if p[1] == "open" else None
            g.mode = "play"
            pilot = Pilot(g)
            try:
                if pilot.get_key() and pilot.escape():
                    okc += 1
            except Stuck as e:
                check(False, f"hiding place {p}: {e}")
        print(f"every non-open hiding place (+40 open tiles): {okc}/{len(places)} found and escaped")
    # ---- screens draw without errors
    bd = pygame.image.load(G.TITLE_BACKDROP)
    check(bd.get_width() / bd.get_height() >= G.WIN_W / G.WIN_H - 1e-6 and bd.get_height() >= G.WIN_H * 0.7,
          f"the title backdrop painting is there and wide enough to cover-fit {G.WIN_W}x{G.WIN_H} ({bd.get_size()})")
    g.title_bg = None
    tb = g.build_title_bg()
    mean = pygame.transform.average_color(tb)
    check(tb.get_size() == (G.WIN_W, G.WIN_H) and 15 < sum(mean[:3]) / 3 < 110, f"title backdrop covers the window, dimmed (mean {mean[:3]})")
    for scene in ("title", "room", "map", "end"):
        g.mode = {"title": "title", "end": "end"}.get(scene, "play")
        g.show_map = scene == "map"
        g.draw()
    print(f"sounds requested: {sorted(g.sounds.requested)}")
    pygame.quit()
    print(f"{'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failures, {time.time() - t0:.1f}s")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
