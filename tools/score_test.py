#!/usr/bin/env python3
"""Headless checks for scoring and the high score table (no real network).

    python3 tools/score_test.py

Points rules, each checked on its own through the real game code:
  * 1 point per whole second actually walking (forwards or back), from an
    accumulator; turning on the spot, standing still and walking into a
    wall earn nothing.
  * 5 points the first time each room is entered in a run (not the start).
  * 50 points for the front door key (picked up, or found by searching).
  * 200 points for escaping.
Then whole games driven by the self-test pilot, whose score must equal an
independent tally of the walking time plus the bonuses; then the Top 10:
qualifying, name entry, local file and the dreamlo calls (faked).
"""
import json
import math
import os
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import pygame  # noqa: E402

import game as G  # noqa: E402
import mansion as M  # noqa: E402
import scores  # noqa: E402
import selftest as S  # noqa: E402

DT = 1 / 60
N_OK = 0
FAILS = []


def check(cond, msg):
    global N_OK
    if cond:
        N_OK += 1
    else:
        FAILS.append(msg)
        print("FAIL:", msg)
    return cond


def run(g, frames, ctrl):
    for _ in range(frames):
        g.update(DT, ctrl=ctrl)


def open_spot(g):
    """Put the player mid-room facing E with at least 3 clear tiles each way along x."""
    r = g.room
    solid = r.solid_cells()
    for y in range(r.d):
        for x in range(3, r.w - 3):
            if all((xx, y) not in solid for xx in range(x - 3, x + 4)):
                g.px, g.py, g.facing = x + 0.5, y + 0.5, "E"
                return True
    return False


class TallyPilot(S.Pilot):
    """The self-test pilot, also adding up the time actually spent walking."""

    def __init__(self, game):
        super().__init__(game)
        self.walked = 0.0

    def tick(self, d=(0, 0), back=True):
        g = self.g
        before = (g.px, g.py, g.room.id, bool(g.fade), g.mode)
        super().tick(d, back)
        if before[4] == "play" and not before[3] and g.moving and g.room.id == before[2] and \
                math.hypot(g.px - before[0], g.py - before[1]) > 1e-6:
            self.walked += DT


def main():
    tmp = tempfile.mkdtemp()
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    g = G.Game(screen, seed=7, enemies=False, god=True, save=False, title=False)
    check(not g.board.online, "headless games stay offline")

    # ---- start of a run
    g.new_game(7)
    g.mode = "play"
    check(g.score == 0 and g.visited == {M.START_ROOM}, f"new run: score {g.score}, visited {g.visited}")

    # ---- walking
    g.enter_room("ballroom", None)
    g.score, g.popups = 0, []
    check(open_spot(g), "found an open strip in the ballroom")
    run(g, 120, (0, 0))
    check(g.score == 0, f"standing still for 2 s scores nothing (got {g.score})")
    run(g, 4 * int(G.TURN_S * 60 + 2), (1, 0))
    check(g.score == 0, f"turning on the spot scores nothing (got {g.score})")
    g.facing = "E"
    g.turning = False
    run(g, 30, (0, 1))
    check(g.score == 0, f"half a second walking: no point yet (got {g.score})")
    run(g, 30, (0, 1))
    check(g.score == 1, f"one second walking forwards = 1 point (got {g.score})")
    open_spot(g)
    g.px += 2.0                             # room to walk back
    run(g, 60, (0, -1))
    check(g.score == 2, f"another second walking backwards = 2 points (got {g.score})")
    open_spot(g)
    run(g, 20, (0, 1))
    run(g, 30, (0, 0))
    run(g, 40, (0, 1))
    check(g.score == 3, f"20 + 40 frames of walking with a pause between = 1 more point (got {g.score})")
    open_spot(g)
    g.px -= 1.25
    for i in range(9):                      # 9 x 50 frames back and forth = 7.5 s
        run(g, 50, (0, 1 if i % 2 == 0 else -1))
    check(g.score == 3 + 7, f"7.5 s more walking = 7 more points, exactly (got {g.score - 3})")
    check(abs(g.move_acc - 0.5) < 1e-6, f"the half second is carried over (acc {g.move_acc:.4f})")
    check(not g.popups, "no popups for walking points")
    # walking into a wall
    g.score, g.move_acc = 0, 0.0
    r = g.room
    g.px, g.py, g.facing = r.w - 0.3, 0.5, "E"
    while g.room.solid_cells().get((math.floor(g.px), 0)):
        g.px -= 1
    g.px = r.w - G.PLAYER_R - 0.001
    g.py = 0.5 if (r.w - 1, 0) not in r.solid_cells() else g.py
    if "E" in r.doors and 0 in r.door_range("E"):
        g.py = r.d - 0.5
    run(g, 180, (0, 1))
    check(g.score == 0 and g.room.id == "ballroom", f"3 s walking into a wall scores nothing (got {g.score})")

    # ---- rooms
    g.new_game(7)
    g.mode = "play"
    p = S.Pilot(g)
    first = g.house.route(M.START_ROOM, next(iter(d["to"] for d in g.room.doors.values())))[1]
    pre = g.score
    p.step_room(first)
    check(g.room.id == first, f"walked into {first}")
    walk_pts = g.score - pre - G.PTS_ROOM
    check(0 <= walk_pts <= 20 and any(t == "+5" for t, *_ in g.popups),
          f"first visit to {first}: +5 and a '+5' popup (score {pre} -> {g.score})")
    s1 = g.score
    p.step_room(M.START_ROOM)
    check(g.room.id == M.START_ROOM and not any(t == "+5" for t, *_ in g.popups[1:]),
          f"walking back to the start room: no room bonus (score {s1} -> {g.score})")
    m1 = g.score
    g.enter_room(M.START_ROOM, None)
    check(g.score == m1, f"re-entering the starting room scores nothing (got {g.score - m1})")
    g.enter_room(first, None)
    check(g.score == m1, f"re-entering {first} scores nothing (got {g.score - m1})")
    before = g.score
    fresh = [rid for rid in g.house.rooms if rid not in g.visited][:3]
    for rid in fresh:
        g.enter_room(rid, None)
    check(g.score == before + 3 * G.PTS_ROOM, f"three new rooms = 15 (got {g.score - before})")

    # ---- the key: picked up from the floor
    g.new_game(11)
    g.mode = "play"
    g.score, g.popups = 0, []
    g.key_place = (g.room.id, "open", (int(g.px), int(g.py)))
    g.key_state, g.key_pos = "revealed", (g.px, g.py)
    g.check_key_pickup()
    check(g.key_state == "carried" and g.score == G.PTS_KEY, f"picking up the key = 50 (got {g.score})")
    check(any(t == "+50" for t, *_ in g.popups), "a '+50' popup")
    g.check_key_pickup()
    check(g.score == G.PTS_KEY, "the key only scores once")
    # found by searching
    house = g.house
    place = next(pl for pl in house.hiding_places() if pl[1] == "search" and house.obtainable(pl))
    g.new_game(12)
    g.mode = "play"
    g.enter_room(place[0], None)
    g.score = 0
    g.key_place, g.key_state = place, "hidden"
    g.finish_search(house.find_obj(g.room, place[2]))
    check(g.key_state == "carried" and g.score == G.PTS_KEY, f"finding the key by searching = 50 (got {g.score})")

    # ---- escape
    g.score, g.popups = 0, []
    g.win()
    check(g.won and g.score == G.PTS_ESCAPE, f"escaping = 200 (got {g.score})")
    check(any(t == "+200" for t, *_ in g.popups), "a '+200' popup")
    g.draw()

    # ---- whole games: score = walking seconds + 5 per new room + 50 + 200
    for seed in (101, 102, 103, 104, 105, 106):
        g.new_game(seed)
        g.mode = "play"
        tp = TallyPilot(g)
        try:
            ok = tp.get_key() and tp.escape()
        except S.Stuck as e:
            ok = check(False, f"seed {seed}: {e}")
        if not ok:
            continue
        want = int(tp.walked + 1e-9) + G.PTS_ROOM * (len(g.visited) - 1) + G.PTS_KEY + G.PTS_ESCAPE
        check(g.score == want, f"seed {seed}: score {g.score}, expected {want} "
                               f"({tp.walked:.2f} s walking, {len(g.visited)} rooms)")
        print(f"  seed {seed}: {g.score} points = {int(tp.walked)} walking + {len(g.visited) - 1} rooms x 5 + 50 + 200"
              f"  (key {g.key_place[1]} in {g.key_place[0]})")

    # ---- Top 10: qualifying and name entry (offline board in a temp file)
    board = scores.Leaderboard(online=False, path=os.path.join(tmp, "s.json"))
    check(not board.qualifies(0) and board.qualifies(1), "empty table: any score above 0 qualifies")
    board.entries = [(f"P{i}", 1000 - i * 50, "GB") for i in range(10)]
    check(board.qualifies(600) and not board.qualifies(550) and not board.qualifies(10), "full table: must beat 10th")
    g.board = scores.Leaderboard(online=False, path=os.path.join(tmp, "g.json"))
    g.new_game(13)
    g.mode = "play"
    g.score = 300
    g.lose(G.Enemy("ghost", 1, 1, g.rng))
    check(g.entry_active, "name entry opens for a qualifying score")
    g.entry_name = ""
    g.entry_text("Holly!! Anderson")
    check(g.entry_name == "Holly An", f"name limited to 8 letters/digits/spaces (got {g.entry_name!r})")
    g.draw()
    g.entry_key(pygame.K_RETURN)
    check(not g.entry_active and g.board.top()[0] == ("Holly An", 300, ""), f"submitted: {g.board.top()}")
    check(g.entry_status() == "Saved as Holly An", f"status {g.entry_status()!r}")
    # a lowercase first letter is capitalised on the way in, and only that one
    check([scores.submit_name(n) for n in ("archie", "mcDuff", "Holly", "9lives", "  bob")] ==
          ["Archie", "McDuff", "Holly", "9lives", "Bob"], "submit_name capitalises only the first letter")
    g.score = 310
    g.lose(G.Enemy("ghost", 1, 1, g.rng))
    g.entry_name = ""
    g.entry_text("archie")
    g.entry_key(pygame.K_RETURN)
    check(("Archie", 310, "") in g.board.top() and g.entry_status() == "Saved as Archie",
          f"typed 'archie', saved as 'Archie': {g.board.top()[:2]} / {g.entry_status()!r}")
    g.board.entries = [(f"P{i}", 1000 - i * 50, "GB") for i in range(10)]
    g.board.pending = []
    g.score = 100
    g.lose(G.Enemy("ghost", 1, 1, g.rng))
    check(not g.entry_active, "no name entry when the score would not make the Top 10")
    check(g.best_score >= 1000, "best score includes the table")

    # ---- dreamlo calls (faked): offline keeps the score, online sends it with the flag code
    calls = []

    def offline_get(url):
        calls.append(url)
        raise OSError("offline")
    b = scores.Leaderboard(online=True, path=os.path.join(tmp, "o.json"))
    b._get = offline_get
    scores.lookup_country = lambda: "GB"
    b.submit("Nathan", 420)
    for _ in range(100):
        if not b.busy:
            break
        time.sleep(0.05)
    check(b.status == "offline" and ("Nathan", 420) in b.pending, "offline: kept for later")
    check(json.load(open(os.path.join(tmp, "o.json")))["pending"] == [["Nathan", 420]], "saved to disk")
    fake = {"dreamlo": {"leaderboard": {"entry": {"name": "Nathan", "score": "420", "text": "GB"}}}}

    def online_get(url):
        calls.append(url)
        return "OK" if "/add/" in url else json.dumps(fake)
    b._get = online_get
    b.refresh()
    for _ in range(100):
        if not b.busy:
            break
        time.sleep(0.05)
    check(any(u.endswith(scores.DREAMLO_PRIVATE + "/add/Nathan/420/0/GB") for u in calls), "add URL with country")
    check(any(u.endswith(scores.DREAMLO_PUBLIC + "/json") for u in calls), "fetch from the public JSON")
    check(b.pending == [] and b.top() == [("Nathan", 420, "GB")], f"sent and parsed: {b.top()}")
    calls.clear()
    b.submit("mcDuff", 77)
    for _ in range(100):
        if not b.busy:
            break
        time.sleep(0.05)
    check(any("/add/McDuff/77/0/GB" in u for u in calls), f"online: 'mcDuff' is sent as 'McDuff' ({calls[:1]})")
    check(scores.SAVE_DIR.endswith(".haunted_mansion"), "local scores live in ~/.haunted_mansion/")

    pygame.quit()
    print(f"{'PASS' if not FAILS else 'FAIL'}: {N_OK} checks passed, {len(FAILS)} failed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
