#!/usr/bin/env python3
"""Record a gameplay video of a real two-player game (Archie hosting, Holly
joining, both in this process over localhost TCP), following Archie's screen.

    python3 tools/record_video.py [--out /workspace/hm_gameplay.mp4] [--stills /workspace]

Both players are driven by an autopilot that works through the real game:
it decides a world direction, turns that into held arrow keys exactly as a
keyboard would give them (a KEYDOWN to on_key() when a key goes down, then
the held-key state to update()), and Space / Tab / typed letters go through
on_key() / on_text() too. Holly's autopilot runs in lock-step on a thread.
The game steps at 60 Hz and every other frame is captured (30 fps). Audio
is rebuilt from the sounds Archie's game asked for (the same wav files and
volumes, music loops with their fades), mixed at their timestamps.
Nothing in the game itself is changed.
"""
import argparse
import json
import math
import os
import queue
import random
import subprocess
import sys
import threading
import time
import wave

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import game as G  # noqa: E402
import mansion as M  # noqa: E402
import net  # noqa: E402
import scores  # noqa: E402
import selftest as S  # noqa: E402

DT = 1 / 60
FPS = 30
PORT = 50755
SEED = 50                      # the key is in the Water Tank Loft
WORK = "/tmp/hmrec"
net.STATE_HZ = 1000            # (the recording runs at its own pace, not real time: send every frame)


class Keys:
    """Stands in for pygame.key.get_pressed()."""

    def __init__(self, held):
        self.held = held

    def __getitem__(self, k):
        return k in self.held


def ctrl_keys(ctrl):
    turn, move = ctrl
    held = set()
    if turn < 0:
        held.add(pygame.K_LEFT)
    elif turn > 0:
        held.add(pygame.K_RIGHT)
    if move > 0:
        held.add(pygame.K_UP)
    elif move < 0:
        held.add(pygame.K_DOWN)
    return frozenset(held)


class Keyboard:
    """One player's keyboard: KEYDOWN events and held keys into the game."""

    def __init__(self, g):
        self.g = g
        self.held = frozenset()

    def frame(self, held):
        for k in held - self.held:
            self.g.on_key(k)          # the main loop's KEYDOWN
        self.held = held
        self.g.update(DT, keys=Keys(self.held))


class Stop(Exception):
    pass


class Lockstep:
    """Holly's autopilot thread: hands over one frame of keys at a time."""

    def __init__(self):
        self.req = queue.Queue(maxsize=1)
        self.go = threading.Semaphore(0)
        self.active = False
        self.pending = False
        self.stop = False

    def start(self, fn):
        self.active = True

        def run():
            try:
                fn()
            except Stop:
                pass
            except Exception as e:      # noqa: BLE001
                print("holly pilot:", type(e).__name__, e)
            finally:
                self.req.put(None)
        threading.Thread(target=run, daemon=True).start()

    def request(self):
        if not self.active:
            return frozenset()
        v = self.req.get(timeout=10)
        if v is None:
            self.active = False
            return frozenset()
        self.pending = True
        return v

    def release(self):
        if self.pending:
            self.pending = False
            self.go.release()

    def tick(self, held):              # called on Holly's thread
        if self.stop:
            raise Stop()
        self.req.put(held)
        self.go.acquire()
        if self.stop:
            raise Stop()


class World:
    def __init__(self, screen, A, H, out, stills):
        self.screen = screen
        self.A, self.H = A, H
        self.ka, self.kh = Keyboard(A), Keyboard(H)
        self.holly = Lockstep()
        self.n = 0
        self.vt = 0.0
        self.marks = []
        self.sounds = []              # (t, name, vol)
        self.loops = [(0.0, A.sounds.loop_name)]
        self.stills = stills
        self.want_still = None
        self.still_n = 0
        self.rooms = []
        self.together = []            # [start, end, room]: Holly in Archie's room, on his screen
        self.home = False             # Archie is on his way home: Holly goes to the front door
        self.meet = None              # a room where Holly waits for Archie
        self.met = False
        self.enc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{G.WIN_W}x{G.WIN_H}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "3500k",
             "-bufsize", "7000k", "-pix_fmt", "yuv420p", os.path.join(WORK, "video.mp4")], stdin=subprocess.PIPE)
        snd = A.sounds
        play0, loop0 = snd.play, snd.loop

        def play(name, vol=1.0):
            self.sounds.append((self.vt, name, vol))
            play0(name, vol)

        def loop(name):
            if name != snd.loop_name:
                self.loops.append((self.vt, name))
            loop0(name)
        snd.play, snd.loop = play, loop

    def mark(self, label):
        self.marks.append((round(self.vt, 1), label))
        print(f"{self.vt:6.1f}s  {label}")

    def still(self, name):
        self.want_still = name

    def frame(self, held=frozenset()):
        hh = self.holly.request()
        self.ka.frame(held)
        self.kh.frame(hh)
        self.holly.release()
        time.sleep(0.0005)
        self.n += 1
        if self.A.mode in ("play", "watch") and (not self.rooms or self.rooms[-1] != self.A.room.id):
            self.rooms.append(self.A.room.id)
        cp = self.A.coop
        if cp is not None and self.A.mode == "play" and cp.partner_here():
            if self.together and self.together[-1][2] == self.A.room.id and self.vt - self.together[-1][1] < 0.5:
                self.together[-1][1] = round(self.vt, 1)
            else:
                self.together.append([round(self.vt, 1), round(self.vt, 1), self.A.room.id])
        if self.n % 2 == 0:
            self.A.draw()
            self.enc.stdin.write(pygame.image.tobytes(self.screen, "RGB"))
            self.vt += 1 / FPS
            if self.want_still:
                self.still_n += 1
                pygame.image.save(self.screen, os.path.join(self.stills, f"hm_vid_still_{self.still_n}_{self.want_still}.png"))
                self.want_still = None

    def wait(self, seconds, held=frozenset()):
        for _ in range(int(seconds * 60)):
            self.frame(held)

    def tap(self, key, gap=0.25):
        self.frame(frozenset([key]))
        self.wait(gap)

    def close(self):
        self.enc.stdin.close()
        self.enc.wait()


class GoHome(Exception):
    pass


class KeyPilot(S.Pilot):
    """The self-test pilot, but through the keyboard."""

    def __init__(self, g, send):
        super().__init__(g)
        self.send = send

    home_flag = None                  # Holly: drop what she's doing once this says so

    def tick(self, d=(0, 0), back=True):
        if self.home_flag is not None and self.home_flag():
            self.home_flag = None
            raise GoHome()
        g = self.g
        ctrl = g.steer(d, back) if g.mode == "play" else (0, 0)
        self.send(ctrl_keys(ctrl))
        self.frames += 1

    def steer_to(self, tx, ty, tol=0.25):
        # a tap of Up/Down always walks STEP_MIN (0.45 tiles): stop within a quarter tile, so no see-sawing
        return super().steer_to(tx, ty, tol)


# ------------------------------------------------------------------ audio
def load_wav(name):
    with wave.open(os.path.join(G.SOUND_DIR, name + ".wav")) as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return rate, a


def mix_audio(world, total, path):
    rate = 22050
    out = np.zeros(int(total * rate) + rate, dtype=np.float32)
    cache = {}

    def get(name):
        if name not in cache:
            r, a = load_wav(name)
            assert r == rate, (name, r)
            cache[name] = a
        return cache[name]
    for t, name, vol in world.sounds:
        if name not in G.SOUND_VOL:
            continue
        a = get(name) * G.SOUND_VOL[name] * vol
        i = int(t * rate)
        j = min(len(out), i + len(a))
        out[i:j] += a[: j - i]
    loops = world.loops + [(total, None)]
    for (t0, name), (t1, _) in zip(loops, loops[1:]):
        if not name or name not in G.SOUND_VOL:
            continue
        a = get(name) * G.SOUND_VOL[name]
        i0, i1 = int(t0 * rate), min(len(out), int((t1 + 0.3) * rate))
        n = i1 - i0
        if n <= 0:
            continue
        seg = np.tile(a, n // len(a) + 1)[:n].copy()
        fin = min(n, int(0.6 * rate))
        seg[:fin] *= np.linspace(0, 1, fin)
        fo = min(n, int(0.3 * rate))
        seg[n - fo:] *= np.linspace(1, 0, fo)
        out[i0:i1] += seg
    out = np.tanh(out * 1.1) * 0.9          # gentle limiter
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(out[: int(total * rate)], -1, 1) * 32767).astype(np.int16).tobytes())


# ------------------------------------------------------------------ the script
def holly_script(world, ph, A, H):
    """Holly: show herself to Archie in the hall, then wander, sometimes
    joining Archie; once the key is found, wait at the front door and leave
    when Archie arrives."""
    rng = random.Random(4)
    hall = H.house.rooms[M.START_ROOM]
    for cell in ((5, 6), (6, 4), (3, 5), (4, 7)):
        if cell in hall.free_floor():
            try:
                ph.walk_path(cell)
            except S.Stuck:
                pass
            for _ in range(rng.randint(30, 80)):
                ph.tick()
    legs = 0
    while not world.home:
        ph.home_flag = lambda: world.home or (world.meet and not world.met)
        try:
            wander(world, ph, A, H, rng, legs)
        except GoHome:
            pass
        ph.home_flag = None
        if world.meet and not world.met and not world.home:
            meet(world, ph, A, H, rng)
    home(world, ph, A, H)


def meet(world, ph, A, H, rng):
    """Wait for Archie in world.meet, strolling about, until he has been and gone."""
    while True:
        try:
            ph.go_to_room(world.meet)
            break
        except S.Stuck:
            for _ in range(30):
                ph.tick()
    seen = False
    while not (seen and A.room.id != world.meet):
        seen = seen or A.room.id == world.meet
        try:
            ph.walk_path(rng.choice(H.room.free_floor()))
        except S.Stuck:
            pass
        for _ in range(rng.randint(10, 40)):
            ph.tick()
    world.met = True


def wander(world, ph, A, H, rng, legs):
    while True:
        legs += 1
        try:
            if legs % 2 == 0 and A.mode == "play":
                target = A.room.id                 # go and find Archie
            else:
                r = H.room
                nbrs = [d["to"] for d in r.doors.values()] + [o.link for o in r.objs if o.type in M.LINK_TYPES]
                target = rng.choice(nbrs)
            if target != H.room.id:
                ph.go_to_room(target)
            free = H.room.free_floor()
            ph.walk_path(rng.choice(free))
            for _ in range(rng.randint(20, 90)):
                ph.tick()
        except S.Stuck:
            for _ in range(30):
                ph.tick()


def home(world, ph, A, H):
    """To the front door, and out when Archie comes in with the key."""
    while True:
        try:
            ph.go_to_room(M.START_ROOM)
            break
        except S.Stuck:
            for _ in range(30):
                ph.tick()
    fd = H.room.front_door()
    ph.walk_path((fd.index + 1, 1))
    while not (A.room.id == M.START_ROOM and not A.fade and A.key_state == "carried"):
        ph.tick()
    for _ in range(40):
        ph.tick()
    ph.walk_path((fd.index, 0))
    ph.press((0, -1), lambda: H.mode != "play", limit=400)
    while True:
        ph.tick()


def obj(g, room, typ):
    return next(o for o in g.house.rooms[room].objs + g.house.rooms[room].walls if o.type == typ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/workspace/hm_gameplay.mp4")
    ap.add_argument("--stills", default="/workspace")
    args = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    # the online Top 10 as it stands (the box can't reach dreamlo: a copy of the real board, read from another computer)
    board = os.path.join(WORK, "scores.json")
    with open(board, "w") as f:
        json.dump({"top": [["holly", 182, "GB"], ["Nathan", 66, "GB"]], "pending": [], "local_best": 0, "last_name": ""}, f)
    pygame.init()
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    A = G.Game(screen, seed=1, character="archie", enemies=True, god=True, save=False, title=True,
               online=False, scores_file=board)
    H = G.Game(screen, seed=2, character="holly", enemies=True, god=True, save=False, title=True,
               online=False, scores_file=os.path.join(WORK, "scores_h.json"))
    A.flags = scores.Flags(folder=os.path.join(WORK, "flags"), download=False)
    A.net_port = PORT
    A.coop_seed = SEED
    random.seed(7)
    w = World(screen, A, H, args.out, args.stills)
    pa = KeyPilot(A, w.frame)
    ph = KeyPilot(H, w.holly.tick)

    # ---- title: the Top 10, then the menu
    A.title_t = G.TOP10_TIME + 0.01          # straight onto the Top 10 page
    w.mark("title screen: Top 10")
    w.wait(1.5)
    w.still("top10")
    w.wait(5.5)
    w.mark("title: controls page, menu")
    w.wait(1.2)
    w.tap(pygame.K_DOWN, 1.0)
    w.mark("menu: Host a game")
    w.tap(pygame.K_DOWN, 1.0)
    w.mark("menu: Join a game")
    w.tap(pygame.K_UP, 0.8)
    w.tap(pygame.K_RETURN, 0.0)
    w.mark("host lobby: waiting for the other player")
    w.wait(2.2)
    H.title_pick = 1
    H.title_opt = 2
    H.on_key(pygame.K_RETURN)
    H.lobby.on_text(f"127.0.0.1:{PORT}")
    H.on_key(pygame.K_RETURN)
    n = 0
    while not (A.mode == "play" and H.mode == "play"):
        w.frame()
        n += 1
        if n > 900:
            raise SystemExit("the two games did not connect")
    w.mark("game starts: Archie and Holly in the Entrance Hall")
    A.msg_t = min(A.msg_t, 2.5)

    # ---- Holly's autopilot starts; Archie shows the controls in the hall
    w.holly.start(lambda: holly_script(w, ph, A, H))
    w.wait(1.0)
    w.mark("tank controls: turning on the spot")
    for k in (pygame.K_RIGHT, pygame.K_RIGHT, pygame.K_LEFT, pygame.K_LEFT, pygame.K_LEFT):
        w.tap(k, 0.35)
    w.wait(0.4)
    w.still("holly_in_hall")
    clock = obj(A, M.START_ROOM, "grandfather_clock")
    w.mark("walking (walk cycle, footsteps) to the grandfather clock")
    if clock.side == "N":
        stand = next(c for c in [(clock.index + i, 0) for i in range(clock.gx)] if c in A.room.free_floor() or True)
        pa.walk_path(stand)
        pa.face((0, -1))
    elif clock.side == "W":
        pa.walk_path((0, clock.index))
        pa.face((-1, 0))
    else:
        pa.stand_and_face(set(clock.cells()))
    w.mark("searching the grandfather clock")
    w.tap(pygame.K_SPACE, 0.1)
    while A.searching:
        w.frame()
    w.wait(1.6)
    w.mark("walking backwards")
    w.wait(1.3, frozenset([pygame.K_DOWN]))
    w.wait(0.5)
    rug = next(o for o in A.room.objs if o.t.get("lift"))
    cells = sorted(rug.cells(), key=lambda c: abs(c[0] - A.px) + abs(c[1] - A.py))
    pa.walk_path(cells[0])
    w.mark("lifting the rug")
    w.tap(pygame.K_SPACE, 2.0)
    w.tap(pygame.K_SPACE, 0.8)      # and put it back
    route = ["study", "library", "billiard_room", "east_corridor", "scullery", "coal_cellar", "wine_cellar", "crypt",
             "wine_cellar", "cellar_passage", "kitchen", "staircase_hall", "landing", "upper_corridor", "sewing_room",
             "upper_corridor", "loft_landing", "dusty_attic", "water_tank_loft", "servants_quarters", "linen_room",
             "upper_corridor", "landing", "staircase_hall", M.START_ROOM]
    seen_pop = False
    map_done = False
    for route_i, nxt in enumerate(route):
        if nxt == "crypt":
            w.meet = "staircase_hall"   # (Holly will be there when Archie comes through)
        if nxt == "loft_landing":
            w.home = True             # (Holly makes for the front door)
        here = A.room.id
        how = next((o.type for o in A.room.objs if o.type in M.LINK_TYPES and o.link == nxt), "door")
        pa.step_room(nxt)
        if A.room.id != nxt:
            raise SystemExit(f"expected {nxt}, in {A.room.id}")
        w.mark(f"{here} -> {nxt} ({how.replace('_', ' ')})")
        if not seen_pop:
            seen_pop = True
            w.wait(0.3)
            w.still("room_bonus")
        if nxt == "scullery":
            crate = next(o for o in A.room.objs if o.t.get("push") and A.house.push_plan(A.room, o))
            stand, d = A.house.push_plan(A.room, crate)
            pa.walk_path(stand)
            start = (crate.x, crate.y)
            w.mark(f"pushing the {crate.type}")
            pa.press(d, lambda: (crate.x, crate.y) != start, limit=400)
            w.wait(0.8)
            w.still("push")
        elif nxt == "crypt":
            w.mark("crypt: enemies close in; Archie can be hurt here")
            A.god = False
            lives = A.lives
            t0 = w.vt
            mid = (A.room.w // 2, A.room.d // 2)
            try:
                pa.walk_path(mid if mid in A.room.free_floor() else A.room.free_floor()[0])
            except S.Stuck:
                pass
            while A.lives == lives and w.vt - t0 < 15:
                w.frame()
            A.god = True
            w.mark(f"Archie loses a heart ({lives} -> {A.lives})")
            w.wait(0.2)
            w.still("hurt")
            w.wait(1.5)
        elif not map_done and ((A.coop and A.coop.partner.room in A.visited and A.coop.partner.room != A.room.id)
                               or nxt == "landing") and route_i >= 10:
            map_done = True
            w.wait(0.3)
            w.tap(pygame.K_TAB, 0.1)
            w.mark("Tab map: Holly's room outlined in green")
            w.wait(0.6)
            w.still("map")
            w.wait(3.0)
            w.tap(pygame.K_TAB, 0.4)
        elif nxt == "water_tank_loft":
            kx, ky = A.key_pos
            pa.walk_path((math.floor(kx), math.floor(ky)))
            n = 0
            while A.key_state != "carried" and n < 120:
                pa.tick()
                n += 1
            w.mark("picking up the key (+50)")
            w.wait(0.25)
            w.still("key")
            w.wait(1.5)
    # ---- the front door: Holly goes first, then Archie
    w.wait(0.5)
    n = 0
    while H.out is None and n < 60 * 25:
        w.frame()
        n += 1
    w.mark("Holly escapes through the front door")
    w.wait(1.0)
    fd = A.room.front_door()
    pa.walk_path((fd.index + 1, 0))
    pa.press((0, -1), lambda: A.mode != "play", limit=600)
    w.mark("Archie unlocks the front door and escapes (+200): end screen")
    w.wait(2.5)
    w.mark("name entry: typing ARCHIE")
    for ch in "ARCHIE":
        A.on_text(ch)
        w.wait(0.3)
    w.wait(0.5)
    w.tap(pygame.K_RETURN, 0.4)
    w.still("end")
    w.wait(3.0)
    w.holly.stop = True
    w.frame()
    A.to_title()
    A.title_t = G.TOP10_TIME + 0.01
    w.mark("back to the title: ARCHIE in the Top 10")
    w.wait(4.0)
    total = w.vt
    w.close()
    mix_audio(w, total, os.path.join(WORK, "audio.wav"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(WORK, "video.mp4"), "-i",
                    os.path.join(WORK, "audio.wav"), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", args.out], check=True)
    uniq = []
    for r in w.rooms:
        if r not in uniq:
            uniq.append(r)
    floors = sorted({A.house.rooms[r].floor for r in uniq})
    info = {"together": w.together, "duration": total, "rooms": uniq, "floors": floors, "marks": w.marks, "lives": A.lives, "score": A.score,
            "sounds": len(w.sounds)}
    with open(os.path.join(WORK, "info.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(f"{total:.1f}s, {len(uniq)} rooms on floors {floors}, score {A.score}, lives {A.lives}")


if __name__ == "__main__":
    main()
