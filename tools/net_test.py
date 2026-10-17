#!/usr/bin/env python3
"""Headless two-player test: a host and a joining game in one process,
talking over real TCP (and UDP discovery) on localhost.

    python3 tools/net_test.py [--shots DIR]

Checks: the joining game finds the host by discovery and joins through the
real lobbies; both build the same house (seed, key place, furniture); each
sees the other move (same room and different rooms); the joining player
finds the key (by whatever the house hid it under: search, push, rug or
floor) and the host registers it; the joining player opens the front door
and both games end with the same team score; an enemy touching the joining
player costs a shared life; and disconnects (a clean goodbye either way, a
dropped connection, silence) leave the remaining player carrying on alone.
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


def connect(screen, seed, port, host_char=0, via_scan=True):
    host = G.Game(screen, seed=1, enemies=True, god=True, save=False, title=True, online=False)   # god: the pilot can't dodge
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
    a = {(r.id, o.id, o.type, o.x, o.y) for r in host.house.rooms.values() for o in r.objs}
    b = {(r.id, o.id, o.type, o.x, o.y) for r in cli.house.rooms.values() for o in r.objs}
    check(a == b, "same furniture in every room")
    check(host.character != cli.character and cli.character == host.coop.partner.char,
          f"the joiner plays the other character ({host.character} / {cli.character})")


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
    check(host.lives == cli.lives == C.COOP_LIVES, f"shared lives {host.lives} / {cli.lives}")
    check(host.coop.partner_here() and cli.coop.partner_here(), "both start in the Entrance Hall and see each other")
    hx, hy = host.px, host.py
    host.facing = "N"                         # into the hall, away from the doorway behind
    step(games, 40, [(0, 1), (0, 0)])
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
    host_score = host.score
    check(cli.score == host.score, f"one team score on both screens ({host.score} / {cli.score})")
    if args.shots:
        host.facing, cli.facing = "E", "S"
        step(games, 5)
        host.msg_t = cli.msg_t = 0
        host.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net_host.png"))
        cli.draw()
        pygame.image.save(screen, os.path.join(args.shots, "hm_net_client.png"))
        host.show_map = True
    # ---- the client goes to another room: the host simulates it
    pc = DuoPilot(cli, host)
    other = next(d["to"] for d in cli.room.doors.values())
    pc.step_room(other)
    step(games, 10)
    check(cli.room.id == other and host.coop.partner.room == other, f"the host knows the client is in {other}")
    check(not host.coop.partner_here() and not cli.coop.partner_here(), "different rooms: neither draws the other")
    check(other in host.visited and host.score >= host_score + G.PTS_ROOM, "the client's new room scores 5 for the team")
    if args.shots:
        host.draw()
        pygame.image.save(screen, "/tmp/hm_net_map.png")
        host.show_map = False
    # ---- the client finds the key, wherever it is
    kind = host.key_place[1]
    s0 = host.score
    try:
        got = pc.get_key()
    except S.Stuck as e:
        got = check(False, f"client key hunt stuck: {e}")
    step(games, 10)
    check(got and host.key_state == "carried" and cli.key_state == "carried",
          f"the client finds the key ({kind} in {host.key_place[0]}) and the host registers it ({host.key_state})")
    check(host.score >= s0 + G.PTS_KEY, f"+50 for the team ({s0} -> {host.score})")
    # ---- the client opens the front door: both escape
    try:
        pc.escape()
    except S.Stuck as e:
        check(False, f"client escape stuck: {e}")
    wait(games, lambda: host.mode == "end" and cli.mode == "end", 200)
    check(host.mode == "end" and host.won and cli.mode == "end" and cli.won, "both games end with an escape")
    check(host.score == cli.score and host.score > 250, f"same final team score ({host.score} / {cli.score})")
    check(cli.opened_by == G.CHARACTERS[cli.character], f"the joiner opened the door ({cli.opened_by})")
    check(host.entry_active and host.entry_name == f"{G.CHARACTERS[host.character]}+{G.CHARACTERS[cli.character]}",
          f"the host is offered the team name ({host.entry_name!r})")
    step(games, 5)
    check("typing the team name" in cli.coop.end_note, f"the joiner is told ({cli.coop.end_note!r})")
    host.board.online = False
    host.on_key(pygame.K_RETURN)
    step(games, 10)
    check(host.board.top() and host.board.top()[0][0] == host.entry_name, f"team entry saved {host.board.top()[:1]}")
    check(cli.coop.end_note.startswith("Team score sent as"), f"joiner sees {cli.coop.end_note!r}")
    if args.shots:
        cli.draw()
        pygame.image.save(screen, "/tmp/hm_net_end_client.png")
    host.to_title()
    step(games, 20)
    check(cli.coop is None, "end screen: the host leaving closes the joiner's link quietly")
    cli.to_title()
    print(f"game 1: key {kind}, team score {host.score}, {pc.frames} client frames")

    # ---- 2. other hiding kinds, typed address; Holly hosting
    for seed in (102, 106, 101):
        host, cli, games = connect(screen, seed, PORT, host_char=1, via_scan=False)
        check(host.character == "holly" and cli.character == "archie", "Holly hosts, Archie joins")
        same_house(host, cli)
        pc = DuoPilot(cli, host)
        kind = host.key_place[1]
        try:
            got = pc.get_key()
            step(games, 10)
            check(got and host.key_state == "carried", f"seed {seed}: client found the key ({kind})")
            if seed == 101:
                # an enemy touches the joiner: one shared life, back to the doorway
                host.god = False
                lives = host.lives
                rid = cli.room.id
                ens = host.enemies if host.room.id == rid else host.coop.other_enemies
                if not ens:
                    host.coop.other_enemies = ens = host.make_enemies(cli.room, cli.px, cli.py) or \
                        [G.Enemy("ghost", cli.px, cli.py, host.rng)]
                host.coop.partner.grace = 0
                host.coop.partner.invuln = 0
                ens[0].x, ens[0].y = host.coop.partner.tx, host.coop.partner.ty
                ex, ey = cli.entry[:2]
                wait(games, lambda: host.lives < lives, 60)
                step(games, 5)
                check(host.lives == lives - 1 and cli.lives == lives - 1, f"shared life lost ({lives} -> {host.lives}/{cli.lives})")
                check(cli.invuln > 0 and abs(cli.px - ex) < 0.01 and abs(cli.py - ey) < 0.01, "the joiner goes back to where they came in")
                host.god = True
            pc.escape()
            wait(games, lambda: host.mode == "end" and cli.mode == "end", 200)
            check(host.won and cli.won and host.score == cli.score, f"seed {seed}: escaped together ({host.score})")
            print(f"seed {seed}: key {kind} in {host.key_place[0]}, team score {host.score}")
        except S.Stuck as e:
            check(False, f"seed {seed}: {e}")
        host.entry_active = False
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
