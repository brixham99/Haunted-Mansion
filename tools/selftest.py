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
   that go straight to the key (wherever it is hidden: searched, pushed,
   under a rug or in the open) and out of the front door.
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
        p = house.place_key(random.Random(seed))
        if not check(house.obtainable(p), f"seed {seed}: place_key chose an unobtainable spot {p}"):
            break
        picked[p[1]] = picked.get(p[1], 0) + 1
    print(f"place_key over 500 seeds: {picked}")
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
    # ---- key games: straight to the key and out, no enemies
    g.enemies_on = False
    kinds = {}
    n_games = 10 if args.quick else args.games
    for seed in range(100, 100 + n_games):
        g.new_game(seed)
        g.mode = "play"
        pilot = Pilot(g)
        try:
            got = pilot.get_key() and pilot.escape()
        except Stuck as e:
            check(False, f"seed {seed}: {e}")
            got = False
        k = g.key_place[1]
        kinds[k] = kinds.get(k, 0) + (1 if got else 0)
    print(f"key games won: {sum(kinds.values())}/{n_games} by hiding kind {kinds}")
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
