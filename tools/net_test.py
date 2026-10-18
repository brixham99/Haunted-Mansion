#!/usr/bin/env python3
"""Headless two-player test: a host and a joining game in one process,
talking over real TCP (and UDP discovery) on localhost.

    python3 tools/net_test.py [--shots DIR]

Checks: the joining game finds the host by discovery and joins through the
real lobbies; both build the same house (seed, key place, furniture); each
sees the other move (same room and different rooms); the joining player
finds the key (by whatever the house hid it under: search, push, rug or
floor) and the host registers it; each player walks out of the front door;
and both games keep their own scores and hearts; a player who escapes or is
caught watches the other until both are out; then each game shows its own
end screen and name entry; disconnects (a clean goodbye either way, a
dropped connection, silence) leave the remaining player carrying on alone,
or end the game for a player who was watching.
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
sys.path.insert(0, HERE)

import pygame  # noqa: E402

import coop as C  # noqa: E402
import game as G  # noqa: E402
import mansion as M  # noqa: E402
import net  # noqa: E402
import selftest as S  # noqa: E402

DT = 1 / 60
PORT = 50655
N_OK = 0
FAILS = []
net.STATE_HZ = 1000          # every frame: the test runs far faster than real time


def check(cond, msg):
    global N_OK
    if cond:
        N_OK += 1
    else:
        FAILS.append(msg)
        print("FAIL:", msg)
    return cond


def step(games, n=1, ctrls=None):
    for _ in range(n):
        for i, g in enumerate(games):
            g.update(DT, ctrl=(ctrls[i] if ctrls else (0, 0)))
        time.sleep(0.002)    # let the network threads run


def wait(games, cond, limit=600):
    for _ in range(limit):
        if cond():
            return True
        step(games)
    return cond()


class DuoPilot(S.Pilot):
    """The self-test pilot driving one game while the other keeps running."""

    def __init__(self, game, other):
        super().__init__(game)
        self.other = other

    def tick(self, d=(0, 0), back=True):
        self.other.update(DT, ctrl=(0, 0))
        super().tick(d, back)
        time.sleep(0.002)


def connect(screen, seed, port, host_char=0, via_scan=True, hidden=False):
    host = G.Game(screen, seed=1, enemies=True, god=True, save=False, title=True, online=False)   # god: the pilot can't dodge
    host.key_hidden = hidden                # the host decides where the key goes
    cli = G.Game(screen, seed=2, enemies=True, god=False, save=False, title=True, online=False)
    host.net_port = port
    host.coop_seed = seed
    host.title_pick = host_char
    host.title_opt = 1
    host.on_key(pygame.K_RETURN)
    cli.title_pick = host_char          # the joiner's own pick is ignored
    cli.title_opt = 2
    cli.on_key(pygame.K_RETURN)
    games = [host, cli]
    if via_scan:
        found = wait(games, lambda: any(a[1] == port for a, _ in cli.lobby.hosts()), 400)
        check(found, "the joining game hears the host's beacon")
        hosts = cli.lobby.hosts()
        cli.lobby.pick = next((i for i, (a, _) in enumerate(hosts) if a[1] == port), 0)
    else:
        cli.lobby.on_text(f"127.0.0.1:{port}")
    cli.on_key(pygame.K_RETURN)
    ok = wait(games, lambda: host.mode == "play" and cli.mode == "play", 600)
    check(ok, f"both games start (host {host.mode}, client {cli.mode}, status {getattr(cli.lobby, 'status', '')!r})")
    wait(games, lambda: host.coop and cli.coop and host.coop.partner.seen and cli.coop.partner.seen, 200)
    return host, cli, games


def same_house(host, cli):
    check(host.seed == cli.seed, f"same seed ({host.seed} / {cli.seed})")
    check(host.key_place == cli.key_place, f"same key place {host.key_place} / {cli.key_place}")
    check(host.key_hidden == cli.key_hidden and (host.key_hidden or host.key_place[1] == "open"),
          f"the joiner follows the host's key setting (hidden {host.key_hidden} / {cli.key_hidden}, {host.key_place[1]})")
    a = {(r.id, o.id, o.type, o.x, o.y) for r in host.house.rooms.values() for o in r.objs}
    b = {(r.id, o.id, o.type, o.x, o.y) for r in cli.house.rooms.values() for o in r.objs}
    check(a == b, "same furniture in every room")
    check(host.character != cli.character and cli.character == host.coop.partner.char,
          f"the joiner plays the other character ({host.character} / {cli.character})")


def kill(games, host, cli, who):
    """Catch one player for the last time (the host's enemies do it)."""
    host.god = False
    if who == "host":
        host.lives, host.invuln, host.grace = 1, 0.0, 0.0
        if host.coop.partner_here():
            host.coop.partner.grace = 0.0
        host.enemies.append(G.Enemy("ghost", host.px, host.py, host.rng))
        wait(games, lambda: host.out is not None, 120)
    else:
        host.coop.p_lives = 1
        hit_client(games, host, cli, until=lambda: cli.out is not None)
    host.god = True
    step(games, 5)


def hit_client(games, host, cli, until=None):
    cp = host.coop
    lives = cp.p_lives
    rid = cli.room.id
    if host.room.id == rid:
        ens = host.enemies
        host.grace = 0.0
    else:
        if cp.other_enemies is None:
            cp.other_enemies = []
        ens = cp.other_enemies
    cp.partner.grace = cp.partner.invuln = 0.0
    host.god = False
    ens.append(G.Enemy("ghost", cp.partner.tx, cp.partner.ty, host.rng))
    wait(games, until or (lambda: cp.p_lives < lives), 120)
    ens.pop()
    host.god = True
    step(games, 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default=None)
    args = ap.parse_args()
    t0 = time.time()
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))

    # ---- 1. join by discovery, same house, see each other move
    host, cli, games = connect(screen, 104, PORT)
    same_house(host, cli)
    check(C.COOP_LIVES == G.LIVES == 5, f"two-player hearts match one-player ({C.COOP_LIVES} / {G.LIVES})")
    check(host.lives == cli.lives == C.COOP_LIVES and host.max_lives == cli.max_lives == C.COOP_LIVES,
          f"each player has their own {C.COOP_LIVES} hearts ({host.lives} / {cli.lives})")
    check(host.coop.partner_here() and cli.coop.partner_here(), "both start in the Entrance Hall and see each other")
    hx, hy = host.px, host.py
    host.facing = "N"                         # into the hall, away from the doorway behind
    step(games, 75, [(0, 1), (0, 0)])
    step(games, 10)
    p = cli.coop.partner
    check(abs(p.tx - host.px) < 0.05 and abs(p.ty - host.py) < 0.05 and host.py < hy - 0.5,
          f"the client sees the host walk ({p.tx:.2f},{p.ty:.2f} vs {host.px:.2f},{host.py:.2f})")
    check(abs(p.x - host.px) < 0.1, "and draws them there (smoothed)")
    cx, cy = cli.px, cli.py
    cli.facing = "E"
    step(games, 30, [(0, 0), (0, 1)])
    step(games, 10)
    q = host.coop.partner
    check(abs(q.tx - cli.px) < 0.05 and abs(q.ty - cli.py) < 0.05 and cli.px > cx + 0.3,
          f"the host sees the client walk ({q.tx:.2f},{q.ty:.2f} vs {cli.px:.2f},{cli.py:.2f})")
    check(q.moving is False, "and stop")
    check(host.score == 1 and cli.score == 0,
          f"separate scores: the host walked over a second, the joiner half a second ({host.score} / {cli.score})")
    # a skeleton walking across the hall: the joiner animates it from the eased positions it is sent
    grace, host.grace = host.grace, 99.0       # the host's AI leaves it alone (moved by hand here)
    sk = G.Enemy("skeleton", 1.5, 1.5, host.rng)
    host.enemies.append(sk)
    step(games, 5)
    ce = [e for e in cli.enemies if e.kind == "skeleton"]
    clacks0 = sum(cli.sounds.requested.get(f"skel_clack{i}", 0) for i in (1, 2))
    seen = []
    for _ in range(120):                      # 2 s at 0.6 tiles/s: 1.2 tiles
        sk.x += 0.6 * DT
        step(games)
        if ce:
            seen.append(ce[-1].frame)
    clacks = sum(cli.sounds.requested.get(f"skel_clack{i}", 0) for i in (1, 2)) - clacks0
    check(len(ce) == 1 and set(seen) == {0, 1, 2, 3}, f"the joiner's skeleton walks through all four frames ({sorted(set(seen))})")
    check(1 <= clacks <= 3, f"and clacks on its footfalls ({clacks} for 1.2 tiles)")
    step(games, 60)                           # the joiner's easing settles, then it stands
    check(ce and ce[-1].frame == 1 and sk.frame == 1,
          f"standing still: the legs-together frame on both ({sk.frame} / {ce[-1].frame if ce else None})")
    host.enemies.remove(sk)
    # a vampire hovering in the hall: the joiner gets his kind and loops his frames (no shadow either side)
    vp = G.Enemy("vampire", 3.5, 3.5, host.rng)
    host.enemies.append(vp)
    step(games, 5)
    cv = [e for e in cli.enemies if e.kind == "vampire"]
    vseen = []
    for _ in range(60):
        step(games)
        if cv:
            vseen.append(cv[-1].frame)
    check(len(cv) == 1 and cv[-1].floats, "the joiner sees the vampire, floating")
    check(set(vseen) == {0, 1, 2, 3} and 5 <= sum(1 for a, b in zip(vseen, vseen[1:]) if a != b) <= 7,
          f"and loops his four frames at ~6 fps ({sorted(set(vseen))})")
    check(cv and abs(cv[-1].x - vp.x) < 0.2 and abs(cv[-1].y - vp.y) < 0.2 and cv[-1].left == vp.left,
          "where the host has him, facing the same way")
    drawn = []
    for gm in games:
        orig = gm.draw_enemy_shadow
        gm.draw_enemy_shadow = lambda *a, _o=orig, **k: (drawn.append((a[0].kind, gm)), _o(*a, **k))
        gm.draw()
        del gm.draw_enemy_shadow
    check("vampire" not in G.NO_SHADOW and {id(g) for k, g in drawn if k == "vampire"} >= {id(cli)},
          "and he casts a soft shadow, so you can judge his height")
    host.enemies.remove(vp)
    host.grace = grace
    step(games, 5)
    if args.shots:
        host.facing, cli.facing = "E", "S"
        step(games, 5)
        host.msg_t = cli.msg_t = 0
        host.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net2_host.png"))
        cli.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net2_client.png"))
        host.show_map = True
    # ---- the client goes to another room: the host simulates it; the joiner scores the room
    pc = DuoPilot(cli, host)
    other = next(d["to"] for d in cli.room.doors.values())
    hs, cs = host.score, cli.score
    pc.step_room(other)
    step(games, 10)
    check(cli.room.id == other and host.coop.partner.room == other, f"the host knows the client is in {other}")
    check(not host.coop.partner_here() and not cli.coop.partner_here(), "different rooms: neither draws the other")
    check(other in cli.visited and other not in host.visited, "each player keeps their own discovered rooms")
    check(cli.score >= cs + G.PTS_ROOM and host.score == hs, f"+5 to the joiner only ({cs} -> {cli.score}, host {hs} -> {host.score})")
    if args.shots:
        host.draw()
        pygame.image.save(screen, "/tmp/hm_net_map.png")
        host.show_map = False
    # ---- the conservatory is a safe room in two-player too: the host spawns nothing there for the joiner
    try:
        pc.go_to_room("conservatory")
        step(games, 30)
        check(cli.room.id == "conservatory" and host.coop.partner.room == "conservatory",
              "the joiner walks into the conservatory")
        check(not host.coop.other_enemies and not cli.enemies,
              f"and finds no baddies there ({host.coop.other_enemies} / {[e.kind for e in cli.enemies]})")
        check(cli.sounds.loop_name == "rain_glass", f"just rain on the glass ({cli.sounds.loop_name})")
    except S.Stuck as e:
        check(False, f"client stuck on the way to the conservatory: {e}")
    # ---- the client finds the key, wherever it is
    kind = host.key_place[1]
    hs, cs = host.score, cli.score
    try:
        got = pc.get_key()
    except S.Stuck as e:
        got = check(False, f"client key hunt stuck: {e}")
    step(games, 10)
    check(got and host.key_state == "carried" and cli.key_state == "carried",
          f"the client finds the key ({kind} in {host.key_place[0]}) and the host registers it ({host.key_state})")
    check(cli.score >= cs + G.PTS_KEY and host.score == hs, f"+50 to the finder only ({cs} -> {cli.score}, host {hs} -> {host.score})")
    # ---- the client walks out of the front door: they're out, the host plays on
    cs = cli.score
    try:
        pc.escape()
    except S.Stuck as e:
        check(False, f"client escape stuck: {e}")
    wait(games, lambda: cli.mode == "watch", 200)
    step(games, 5)
    check(cli.out == "won" and cli.mode == "watch" and host.mode == "play" and host.coop.p_out == "won",
          f"the joiner escapes and watches; the host plays on ({cli.mode} / {host.mode})")
    check(cli.score >= cs + G.PTS_ESCAPE and host.score == hs, f"+200 to the joiner only ({cs} -> {cli.score})")
    check(cli.room.id == host.room.id and cli.coop.partner_here() and not host.coop.partner_here(),
          "the watcher's view follows the host; the host no longer sees the joiner")
    check(f"Watching {G.CHARACTERS[host.character]}" in (cli.msg or ""), f"'Watching ...' ({cli.msg!r})")
    # the watcher can't touch anything
    wx, wy, cs2 = cli.px, cli.py, cli.score
    cli.on_key(pygame.K_SPACE)
    step(games, 30, [(0, 0), (0, 1)])
    check((cli.px, cli.py) == (wx, wy) and cli.score == cs2, "a watcher's keys do nothing")
    # ---- now the host escapes too (the key unlocked the door for both)
    ph = DuoPilot(host, cli)
    hs = host.score
    try:
        ph.escape()
    except S.Stuck as e:
        check(False, f"host escape stuck: {e}")
    wait(games, lambda: host.mode == "end" and cli.mode == "end", 200)
    check(host.mode == "end" and host.won and cli.mode == "end" and cli.won, "both out: both games end, both escaped")
    check(host.score >= hs + G.PTS_ESCAPE and any(t == f"+{G.PTS_ESCAPE}" for t, *_ in host.popups),
          f"+200 to the host for walking out ({hs} -> {host.score})")
    check(host.score != cli.score, f"own scores on the end screens ({host.score} / {cli.score})")
    check(cli.time < host.time, f"own times: the joiner got out first ({cli.time:.1f} / {host.time:.1f})")
    check(cli.partner_end and cli.partner_end[1] == "won" and host.partner_end and host.partner_end[1] == "won",
          f"each end screen says the other escaped ({cli.partner_end} / {host.partner_end})")
    # ---- each player types their own name, single-player rules
    check(host.entry_active and cli.entry_active, "both are offered the Top 10 name entry")
    for g, name in ((host, G.CHARACTERS[host.character]), (cli, G.CHARACTERS[cli.character])):
        g.board.online = False
        g.entry_name = ""
        g.entry_text("A+B" + name + "XXXXXXXX")
        check(g.entry_name == ("AB" + name + "XXXXXXXX")[:8], f"no '+' and at most 8 characters ({g.entry_name!r})")
        g.entry_name = name
        g.on_key(pygame.K_RETURN)
        top = g.board.top()
        check(top and (top[0][0], top[0][1]) == (name, g.score), f"{name}'s own entry with their own score ({top[:1]})")
    step(games, 5)
    if args.shots:
        cli.draw()
        pygame.image.save(screen, "/tmp/hm_net_end_client.png")
    host.to_title()
    step(games, 20)
    check(cli.coop is None and cli.mode == "end", "end screen: the host leaving closes the joiner's link quietly")
    cli.to_title()
    print(f"game 1: key {kind}, scores {host.score} / {cli.score}, {pc.frames} client frames")

    # ---- 2. other hiding kinds, typed address, Holly hosting; deaths and watching
    for seed in (102, 106, 101):
        host, cli, games = connect(screen, seed, PORT, host_char=1, via_scan=False, hidden=True)   # hidden-key mode
        check(host.character == "holly" and cli.character == "archie", "Holly hosts, Archie joins")
        same_house(host, cli)
        pc = DuoPilot(cli, host)
        kind = host.key_place[1]
        try:
            if seed == 102:
                # the host is caught for the last time straight away and watches the joiner
                kill(games, host, cli, "host")
                check(host.out == "dead" and host.mode == "watch" and cli.mode == "play",
                      f"seed {seed}: the host is out and watches ({host.mode})")
                check(cli.coop.partner_out() == "dead" and not cli.coop.partner_here(), "the joiner no longer sees them")
                hs = host.score
            got = pc.get_key()
            step(games, 10)
            check(got and host.key_state == "carried", f"seed {seed}: client found the key ({kind})")
            if seed == 102:
                check(host.room.id == cli.room.id and host.coop.partner_here(),
                      f"the watcher's view followed the joiner to the {cli.room.name}")
                if args.shots:
                    host.msg_t = 0
                    host.draw()
                    pygame.image.save(screen, os.path.join(args.shots, "hm_net2_spectate.png"))
            if seed == 101:
                # an enemy touches the joiner: one of THEIR lives, back to the doorway
                lives, hl = cli.lives, host.lives
                ex, ey = cli.entry[:2]
                hit_client(games, host, cli)
                check(host.coop.p_lives == lives - 1 and cli.lives == lives - 1 and host.lives == hl,
                      f"the joiner loses one of their own lives ({lives} -> {cli.lives}; host still {host.lives})")
                check(cli.invuln > 0 and abs(cli.px - ex) < 0.01 and abs(cli.py - ey) < 0.01, "the joiner goes back to where they came in")
            if seed == 106:
                # the joiner is caught for good while holding the key; then the host is caught: both out
                kill(games, host, cli, "client")
                check(cli.out == "dead" and cli.mode == "watch" and host.mode == "play" and cli.lives == 0,
                      f"seed {seed}: the joiner is out and watches the host ({cli.mode})")
                check(cli.room.id == host.room.id, "and sees the host's room")
                kill(games, host, cli, "host")
                wait(games, lambda: host.mode == "end" and cli.mode == "end", 200)
                check(host.lost and cli.lost and host.mode == "end" and cli.mode == "end", "both caught: the game ends for both")
                check(cli.partner_end == (G.CHARACTERS[host.character], "dead", "ghost") and host.partner_end[1] == "dead",
                      f"each end screen says the other was caught ({cli.partner_end} / {host.partner_end})")
                if args.shots:
                    cli.end_t = 2.0
                    cli.draw()
                    pygame.image.save(screen, "/tmp/hm_net_end_both_caught.png")
                check(host.entry_active == host.board.qualifies(host.score) and cli.entry_active == cli.board.qualifies(cli.score),
                      "each gets their own name entry if they qualify")
            else:
                pc.escape()
                if seed == 102:
                    wait(games, lambda: host.mode == "end" and cli.mode == "end", 200)
                    check(cli.won and host.lost and host.score == hs, f"seed {seed}: joiner escaped, host caught ({host.score} / {cli.score})")
                else:
                    wait(games, lambda: cli.mode == "watch", 200)
                    kill(games, host, cli, "host")
                    wait(games, lambda: host.mode == "end" and cli.mode == "end", 200)
                    check(cli.won and host.lost, f"seed {seed}: joiner escaped, then the host was caught")
            print(f"seed {seed}: key {kind} in {host.key_place[0]}, scores {host.score} / {cli.score}")
        except S.Stuck as e:
            check(False, f"seed {seed}: {e}")
        host.entry_active = cli.entry_active = False
        host.to_title()
        cli.to_title()
        step(games, 5)

    # ---- 2b. the survivor goes away while the other watches
    host, cli, games = connect(screen, 11, PORT, via_scan=False)
    kill(games, host, cli, "client")
    check(cli.mode == "watch", "the joiner is out and watching")
    host.to_title()
    wait([cli], lambda: cli.mode == "end", 200)
    check(cli.mode == "end" and cli.coop is None and "has gone" in cli.net_note,
          f"the host leaves while the joiner watches: the joiner's game ends ({cli.net_note!r})")
    cli.entry_active = False
    cli.to_title()
    host, cli, games = connect(screen, 12, PORT, via_scan=False)
    kill(games, host, cli, "host")
    check(host.mode == "watch", "the host is out and watching")
    cli.coop.link._shut("pulled the plug")
    wait([host], lambda: host.mode == "end", 400)
    check(host.mode == "end" and host.coop is None and "has gone" in host.net_note,
          f"the joiner drops out while the host watches: the host's game ends ({host.net_note!r})")
    host.entry_active = False
    host.to_title()
    cli.to_title()

    # ---- 2c. the front door: swings open (with its creak) on each game whose
    # player is in the Entrance Hall once the key is carried; open, silently,
    # on the other; the state follows across; no second swing
    host, cli, games = connect(screen, 13, PORT, via_scan=False)
    check(host.door_t is None and cli.door_t is None, "the front door starts shut")
    # the grand staircase: the joiner sees the host up the steps, drawn at their height
    host.enter_room("staircase_hall", None)
    cli.enter_room("staircase_hall", None)
    host.enemies, cli.enemies = [], []
    host.px, host.py, cli.px, cli.py = 3.0, 2.0, 6.5, 6.5
    wait(games, lambda: not cli.fade and not host.fade and cli.coop.partner_here()
         and abs(cli.coop.partner.x - 3.0) < 0.05 and abs(cli.coop.partner.y - 2.0) < 0.05, 240)
    seen = []
    orig = cli.draw_player_shadow
    cli.draw_player_shadow = lambda gx, gy, *a: (seen.append((gx, gy)), orig(gx, gy, *a))
    cli.draw()
    del cli.draw_player_shadow
    p = cli.coop.partner
    fx, fy = cli.P(p.x, p.y)
    up = [fy - gy for gx, gy in seen if abs(gx - fx) < 2]
    z = cli.room.floor_z(p.x, p.y)
    check(up and abs(up[0] - z) < 2 and z > 60, f"the joiner draws the host up the grand staircase ({up} px, z {z:.0f})")
    host.px, host.py = 3.0, 3.5
    for _ in range(30):
        host.move_player(0, -1, DT)
    check(host.py >= 3 + G.PLAYER_R - 1e-3, f"and its banisters stop either player ({host.py:.2f})")
    host.enter_room("entrance_hall", None)
    cli.enter_room("entrance_hall", None)
    wait(games, lambda: not cli.fade and not host.fade, 60)
    cli.enter_room("drawing_room", ("door", "E", 0))
    wait(games, lambda: not cli.fade and host.coop.partner.room == "drawing_room", 120)
    step(games, 5)
    host.key_state = "carried"               # (as if the host had just picked it up in the hall)
    host.coop.announce_key()
    step(games, 4)
    check(host.door_t is not None and host.door_t < G.DOOR_OPEN_S and host.sounds.requested.get("door_creak") == 1,
          f"the host is in the hall with the key: the door starts to swing, with one creak ({host.door_t})")
    wait(games, lambda: cli.door_t is not None, 60)
    check(cli.door_t == G.DOOR_OPEN_S and not cli.sounds.requested.get("door_creak"),
          f"the joiner, elsewhere, has it open without the swing or the creak ({cli.door_t})")
    step(games, int(G.DOOR_OPEN_S / DT) + 5)
    check(host.door_t == G.DOOR_OPEN_S, "the swing finishes and the door stays open")
    cli.enter_room("entrance_hall", ("door", "W", 0))
    host.enter_room("drawing_room", ("door", "E", 0))
    step(games, 40)
    host.enter_room("entrance_hall", ("door", "W", 0))
    step(games, 40)
    check(host.door_t == cli.door_t == G.DOOR_OPEN_S and host.sounds.requested.get("door_creak") == 1
          and not cli.sounds.requested.get("door_creak"), "coming back into the hall: still open, no replay")
    host.to_title()
    cli.to_title()
    step(games, 5)
    host, cli, games = connect(screen, 14, PORT, via_scan=False)
    host.key_state = "carried"               # both in the hall this time
    wait(games, lambda: host.door_t is not None and cli.door_t is not None, 60)
    check(cli.sounds.requested.get("door_creak") == 1 and host.sounds.requested.get("door_creak") == 1,
          "both players in the hall: the door swings, and creaks, on both games")
    host.to_title()
    cli.to_title()
    step(games, 5)

    # ---- 3. disconnects mid-game
    host, cli, games = connect(screen, 7, PORT, via_scan=False)
    host.to_title()                          # host quits: says goodbye
    wait([cli], lambda: cli.coop is None, 200)
    check(cli.coop is None and cli.mode == "play", "host leaves: the joiner carries on alone")
    check("Carrying on alone" in (cli.msg or ""), f"and is told ({cli.msg!r})")
    pc = S.Pilot(cli)
    cli.god = True                           # (the pilot can't dodge)
    try:
        ok = pc.get_key() and pc.escape()
        check(ok and cli.won, "the joiner can still find the key and escape on their own")
    except S.Stuck as e:
        check(False, f"solo after disconnect: {e}")
    cli.entry_active = False
    cli.to_title()

    host, cli, games = connect(screen, 8, PORT, via_scan=False)
    pc = DuoPilot(cli, host)
    pc.step_room(next(d["to"] for d in cli.room.doors.values()))
    cli.to_title()                           # joiner quits
    wait([host], lambda: host.coop is None, 200)
    check(host.coop is None and host.mode == "play" and "Carrying on alone" in (host.msg or ""),
          "joiner leaves: the host carries on alone")
    step([host], 30, [(0, 1)])
    check(host.mode == "play", "and keeps playing")
    host.to_title()

    host, cli, games = connect(screen, 9, PORT, via_scan=False)
    host.coop.link._shut("pulled the plug")  # dropped without a goodbye
    wait([cli], lambda: cli.coop is None, 200)
    check(cli.coop is None and cli.mode == "play" and cli.enemies_on, "dropped connection: the joiner carries on alone")
    step([host], 2)
    check(host.coop is None and host.mode == "play", "and so does the host")
    host.to_title()
    cli.to_title()

    host, cli, games = connect(screen, 10, PORT, via_scan=False)
    old = net.TIMEOUT_S
    net.TIMEOUT_S = 0.3
    t_end = time.time() + 0.8
    while time.time() < t_end and cli.coop is not None:
        cli.update(DT, ctrl=(0, 0))          # the host has frozen: no messages at all
        time.sleep(0.01)
    net.TIMEOUT_S = old
    check(cli.coop is None and cli.mode == "play", "a silent host times out and the joiner carries on")
    host.to_title()
    cli.to_title()

    # ---- 4. lobby errors
    a = G.Game(screen, save=False, title=True, online=False)
    a.net_port = PORT
    a.open_lobby("host")
    b = G.Game(screen, save=False, title=True, online=False)
    b.net_port = PORT
    b.open_lobby("host")
    check(a.lobby.error is None and b.lobby.error, f"a second host on the same port is refused ({b.lobby.error!r})")
    b.close_lobby()
    a.close_lobby()
    j = G.Game(screen, save=False, title=True, online=False)
    j.open_lobby("join")
    j.lobby.on_text("127.0.0.1:50999")
    j.on_key(pygame.K_RETURN)
    wait([j], lambda: "Can't connect" in j.lobby.status or "No answer" in j.lobby.status, 300)
    check("connect" in j.lobby.status.lower() or "answer" in j.lobby.status.lower(), f"nobody there: {j.lobby.status!r}")
    j.close_lobby()
    if args.shots:
        t = G.Game(screen, save=False, title=True, online=False)
        t.title_opt = 1
        t.title_t = 2.0
        t.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net_title.png"))
        t.net_port = PORT + 1
        t.on_key(pygame.K_RETURN)
        t.title_t = 2.0
        t.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net_lobby_host.png"))
        t.close_lobby()
        t.title_opt = 2
        t.on_key(pygame.K_RETURN)
        t.lobby.typed = "192.168.1.20"
        t.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net_lobby_join.png"))
        t.close_lobby()

    fails = FAILS + [f for f in S.FAILS]
    pygame.quit()
    print(f"{'PASS' if not fails else 'FAIL'}: {N_OK} checks passed, {len(fails)} failed, {time.time() - t0:.1f}s")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
