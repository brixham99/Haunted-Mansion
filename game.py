#!/usr/bin/env python3
"""Haunted Mansion (working title): a Halloween isometric flip-screen game.

Play:  python3 game.py
Test:  python3 tools/selftest.py            (headless, SDL_VIDEODRIVER=dummy)
Shot:  SDL_VIDEODRIVER=dummy python3 game.py --scene room --room library --screenshot out.png

Find the front door key, hidden somewhere new every game (in the open, under
something you can move, or inside/behind furniture), then get back to the
front door in the Entrance Hall. Native 1280x800, drawn at full resolution.
"""

from __future__ import annotations

import argparse
import heapq
import types
import json
import math
import os
import random
import sys
import time

if os.environ.get("SDL_VIDEODRIVER") == "dummy":
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

import art
import coop as C
import mansion as M
import net
import scores
from objects import (T, TILE_W, TILE_H, WALL_H, DOOR_H, ENEMY_STATS, SEARCH_LINES, SEARCH_PHRASE, nice)

WIN_W, WIN_H = 1280, 800
HUD_H = 56
HW, HH = TILE_W // 2, TILE_H // 2
SLAB = 18                      # floor thickness shown along the open front edges
PLAYER_R = 0.24                # half-size of the player's collision box (tiles)
PLAYER_SPEED = 3.0             # tiles per second
ENEMY_SPEED_SCALE = 0.6        # every baddie's speed (ENEMY_STATS, wander and chase) times this; 1.0 = original
ENEMY_BOB_RATE = 8.0 * ENEMY_SPEED_SCALE ** 0.5   # walkers' step bob follows their (slower) pace
# Animated enemies (frames cut by tools/cut_anims.py; art.ENEMY_ANIMS). Like
# every enemy sprite they are painted facing screen right and mirrored when
# the enemy heads screen left (e.left); there are no separate up/down views.
BAT_FPS = 9.0                  # wing beat: up, outstretched, down, folded, looped
BAT_BOB = 3.0                  # px; the body rises on the downstroke, in step with the frames
BAT_FLAP_NEAR = 3.5            # tiles: the leathery flap is only heard this close
SKEL_FRAME_D = 0.36            # tiles walked per frame (stride, together, other stride, jolt): no foot slide
                               # (0.3 at the old size; the stride grew with the 20% bigger skeleton)
SKEL_IDLE_S = 0.3              # standing this long -> the legs-together frame
SKEL_JOLT_S = 0.1              # the 1-2 px drop on each footfall
SKEL_CLACK_FAR = 9.0           # tiles: the footfall clack fades out by this distance
# The front door: once the key is carried and someone is in the Entrance Hall
# it swings open (both leaves, inwards on their outer hinges) and stays open.
DOOR_OPEN_S = 1.8              # length of the swing
DOOR_SWING = math.radians(96)  # how far each leaf opens
# Where the two leaves are in front_door.png (fractions of the art): the
# stone surround and the fanlight above stay put.
DOOR_LEAF_X = (43 / 222, 113 / 222, 183 / 222)   # left edge, the seam, right edge
DOOR_LEAF_Y = (102 / 319, 302 / 319)             # top (under the fanlight), bottom
PUSH_DELAY = 0.25              # s of shoving before a pushable moves
SLIDE_TIME = 0.22
SEARCH_TIME = 0.55
FADE = 0.18                    # each half of the flip-screen fade
ENTRY_GRACE = 0.9              # s enemies wait when you come into a room
INVULN = 2.2                   # s after losing a life
LIVES = 5                  # hearts at the start (each player has 5 in a two-player game too)
MSG_TIME = 3.2
# Scoring
PTS_MOVE = 1                   # per whole second spent actually walking (forwards or back)
PTS_ROOM = 5                   # the first time each room is entered in a run (not the starting room)
PTS_KEY = 50                   # picking up the front door key
PTS_ESCAPE = 200               # out through the front door
POPUP_TIME = 1.3               # s a "+5" floats above the player
TOP10_TIME = 7.0               # s the title screen shows the controls, then the Top 10, in turn
BOARD_REFRESH = 3600.0         # re-fetch the Top 10 (and retry unsent scores) hourly
TITLE_NAME = "Haunted Mansion"
TITLE_OPTIONS = ("Play alone", "Host a game", "Join a game")
COPYRIGHT = "\u00a92026 Nathan, Archie & Holly Anderson. Working title."
TITLE_BACKDROP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "art", "title_backdrop.jpg")
TITLE_DIM = 0.64                  # the painting at ~64% brightness, before the vignette
TITLE_MOON = (198, 146)           # where the moon is in the painting (px)
TITLE_WINDOWS = ((169, 540), (262, 540), (375, 540), (440, 232), (619, 288), (819, 238), (800, 352), (825, 352), (1087, 525))
TITLE_CHARS_X = 44                # the character picker, left
TITLE_OPTS_XY = (948, 150)        # alone / host / join, top right
TITLE_PANEL_Y = 560               # Top 10 / controls / lobby panel, under the front door's arch

HERE = os.path.dirname(os.path.abspath(__file__))
SOUND_DIR = os.path.join(HERE, "assets", "sounds")
SAVE_DIR = os.path.join(os.path.expanduser("~"), ".haunted_mansion")
SAVE_FILE = os.path.join(SAVE_DIR, "best.json")

CHARACTERS = {"archie": "Archie", "holly": "Holly"}
CHAR_ORDER = ("archie", "holly")
FACING_SPRITE = {"N": "ne", "E": "se", "S": "sw", "W": "nw"}
FACING_DIR_XY = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
WALK_START = 0.2               # a fresh walk starts just before the feet pass (no leap from standing)
DIRS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
FACING_DIR_NAME = {v: k for k, v in DIRS.items()}
# Tank controls, as in Daleks in Hedges: Left/Right (A/D) turn a quarter turn
# between the four isometric facings, Up/Down (W/S) walk forward/back.
FACING_ORDER = ("E", "S", "W", "N")   # clockwise on screen: SE, SW, NW, NE (Right = +1)
TURN_S = 0.22                  # Daleks' TURN_MS: a quarter turn; held keys repeat at this pace
STEP_MIN = 0.45                # a tap of Up/Down still takes a whole step (tiles)
TURN_KEYS = {pygame.K_LEFT: -1, pygame.K_a: -1, pygame.K_RIGHT: 1, pygame.K_d: 1}
MOVE_KEYS = {pygame.K_UP: 1, pygame.K_w: 1, pygame.K_DOWN: -1, pygame.K_s: -1}
ACTION_KEYS = (pygame.K_SPACE, pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER)
MAP_KEYS = (pygame.K_TAB, pygame.K_m)

SOUND_VOL = {"door_creak": 0.85, "ambience": 0.35, "title_theme": 0.5, "creak1": 0.35, "creak2": 0.35, "door": 0.4,
             "search": 0.5, "key_found": 0.7, "locked": 0.6, "unlock": 0.8, "win": 0.7, "gameover": 0.7,
             "push": 0.5, "ghost": 0.45, "goblin": 0.5, "bat": 0.35, "spider": 0.4, "skeleton": 0.5,
             "monster": 0.6, "stairs": 0.5, "rug": 0.5, "hurt": 0.5, "step1": 0.25, "step2": 0.25,
             "step3": 0.25, "ow_archie": 0.5, "ow_holly": 0.5, "skel_clack1": 0.3, "skel_clack2": 0.3,
             "bat_flap": 0.22}


def load_font(size, bold=False, serif=False):
    for name in (("dejavuserif", "georgia", "timesnewroman") if serif else ("dejavusans", "helvetica", "arial")):
        try:
            f = pygame.font.SysFont(name, size, bold=bold)
            if f is not None:
                return f
        except Exception:
            pass
    return pygame.font.Font(None, size)


def fmt_time(s):
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


# ===================================================================== sound
class Sounds:
    """Fail-safe mixer wrapper: missing device or file = silence."""

    def __init__(self):
        self.ok = False
        self.s = {}
        self.requested = {}
        self.loop_ch = None
        self.loop_name = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 2, 512)
            self.ok = bool(pygame.mixer.get_init())
        except Exception:
            self.ok = False
        if not self.ok:
            return
        try:
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(1)
            self.loop_ch = pygame.mixer.Channel(0)
        except Exception:
            self.loop_ch = None
        for name, vol in SOUND_VOL.items():
            try:
                snd = pygame.mixer.Sound(os.path.join(SOUND_DIR, name + ".wav"))
                snd.set_volume(vol)
                self.s[name] = snd
            except Exception:
                pass

    def play(self, name, vol=1.0):
        self.requested[name] = self.requested.get(name, 0) + 1
        snd = self.s.get(name) if self.ok else None
        if snd is None:
            return
        try:
            ch = snd.play()
            if ch is not None and vol != 1.0:
                ch.set_volume(vol)
        except Exception:
            pass

    def loop(self, name):
        if self.loop_name == name:
            return
        self.loop_name = name
        if not self.ok or self.loop_ch is None:
            return
        try:
            self.loop_ch.fadeout(300)
            if name and name in self.s:
                self.loop_ch.play(self.s[name], loops=-1, fade_ms=600)
        except Exception:
            pass


# ===================================================================== actors
class Enemy:
    def __init__(self, kind, x, y, rng):
        self.kind = kind
        st = ENEMY_STATS[kind]
        self.speed, self.sense, self.floats, self.r, self.z0 = st["speed"], st["sense"], st["floats"], st["r"], st["z"]
        self.speed *= ENEMY_SPEED_SCALE   # tiles/s; the host runs every enemy, so two-player matches
        self.x, self.y = x, y
        self.left = rng.random() < 0.5
        self.path = []
        self.think = 0.0
        self.chasing = False
        self.cried = False
        self.cry_cd = rng.uniform(1.0, 3.0)
        self.phase = rng.uniform(0, 6.28)
        self.wander = None
        self.rng = rng
        # animation (game.animate_enemies; runs on both sides of a two-player game)
        self.frame = 1                  # skeleton: legs together; bat: wings out
        self.anim_xy = None             # where it was last frame (walk distance)
        self.walk_d = 1.5 * SKEL_FRAME_D
        self.still = SKEL_IDLE_S
        self.jolt = 0.0
        self.foot = 0
        self.flap_cd = 1.0

    def box(self):
        return (self.x - self.r, self.y - self.r, self.x + self.r, self.y + self.r)


def depth_sort(items):
    """Back-to-front order of (box, payload) with box = (x0, y0, x1, y1).
    A is behind B when it ends before B starts along x or along y; only
    pairs that overlap on screen are ordered; ties fall back to x + y."""
    n = len(items)
    key = [b[0] + b[1] + b[2] + b[3] for b, _ in items]
    sx = [((b[0] - b[3]) * HW, (b[2] - b[1]) * HW) for b, _ in items]
    after = [[] for _ in range(n)]
    indeg = [0] * n
    eps = 1e-6
    for i in range(n):
        a = items[i][0]
        for j in range(i + 1, n):
            b = items[j][0]
            if sx[i][1] <= sx[j][0] or sx[j][1] <= sx[i][0]:
                continue
            ab = a[2] <= b[0] + eps or a[3] <= b[1] + eps
            ba = b[2] <= a[0] + eps or b[3] <= a[1] + eps
            if ab and not ba:
                first, second = i, j
            elif ba and not ab:
                first, second = j, i
            else:
                first, second = (i, j) if key[i] <= key[j] else (j, i)
            after[first].append(second)
            indeg[second] += 1
    heap = [(key[i], i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(heap)
    out = []
    done = [False] * n
    while len(out) < n:
        if not heap:  # a cycle: take the furthest-back remaining one
            i = min((k for k in range(n) if not done[k]), key=lambda k: key[k])
            heap.append((key[i], i))
        _, i = heapq.heappop(heap)
        if done[i]:
            continue
        done[i] = True
        out.append(items[i])
        for j in after[i]:
            indeg[j] -= 1
            if indeg[j] == 0 and not done[j]:
                heapq.heappush(heap, (key[j], j))
    return out


# ---------------------------------------------------------------- exit door frames
# Every way through to another room is marked by a door frame: a semi-
# transparent architrave on the back (N/W) walls, baked into the room
# background, and a fainter "ghost" frame standing on the open front (S/E)
# edges, drawn over the room each frame so it can fade out of the way.
PARQUET_W = 0.25                 # tiles: parquet block width (blocks are twice as long)
FRAME_WOOD = (104, 70, 44)
FRAME_STONE = (132, 126, 116)
BACK_FRAME_ALPHA = 150           # ~59% on the back walls
BACK_VOID_ALPHA = 222            # the doorway itself: a dark, faintly see-through void
GHOST_FRAME_ALPHA = 100          # ~39% on the open front edges
GHOST_FADE_MIN = 0.4             # share kept when someone is right behind a ghost frame
GHOST_FADE_D = 2.6               # ...rising back to full this many tiles in from the edge
EXIT_NEAR = 2.2                  # tiles: a soft pulse when the player is this close to an exit


def frame_material(style):
    """Stone frames in brick, stone and plaster rooms; dark wood elsewhere."""
    return FRAME_STONE if style["wall"] in ("brick", "stone", "plaster") else FRAME_WOOD


def door_frame_boxes(a, b, n0, n1):
    """The pieces of a door frame round the opening u in [a, b] (tiles along
    the wall), z up from the floor (px), n out of the wall towards the
    viewer (tiles, n0..n1 is the frame's depth). (u0, u1, z0, z1, n0, n1, k)
    with k the brightness of that piece; back-to-front drawing order."""
    mid = (a + b) / 2
    d = n1 - n0
    return [
        (a - .16, a, 0, DOOR_H, n0, n1, 1.0),                         # left post
        (b, b + .16, 0, DOOR_H, n0, n1, 1.0),                         # right post
        (a - .19, a + .02, 0, 26, n0, n1 + .3 * d, 0.85),              # plinth blocks
        (b - .02, b + .19, 0, 26, n0, n1 + .3 * d, 0.85),
        (a - .22, b + .22, DOOR_H, DOOR_H + 24, n0, n1 + .1 * d, 1.0),  # lintel
        (a - .28, b + .28, DOOR_H + 24, DOOR_H + 32, n0, n1 + .6 * d, 1.18),  # cornice
        (mid - .1, mid + .1, DOOR_H - 12, DOOR_H + 26, n0, n1 + .4 * d, 1.25),  # keystone
    ]


def box_faces(W, box, col):
    """Visible faces of one frame piece as (colour, polygon) back to front:
    the +u end (faces the viewer's right), the top, then the front face.
    W(u, z, n) -> screen point on the frame's wall plane."""
    u0, u1, z0, z1, n0, n1, k = box
    c = art.shade(col, k)
    return [
        (art.shade(c, 0.6), [W(u1, z0, n0), W(u1, z0, n1), W(u1, z1, n1), W(u1, z1, n0)]),
        (art.shade(c, 1.3), [W(u0, z1, n0), W(u1, z1, n0), W(u1, z1, n1), W(u0, z1, n1)]),
        (c, [W(u0, z0, n1), W(u1, z0, n1), W(u1, z1, n1), W(u0, z1, n1)]),
    ]


def door_frame_polys(W, a, b, col, n0, n1):
    """All the (colour, polygon) pieces of a door frame, mouldings included."""
    out = []
    for box in door_frame_boxes(a, b, n0, n1):
        out += box_faces(W, box, col)
    dark, light = art.shade(col, 0.55), art.shade(col, 1.45)
    for u in (a - .11, a - .06, b + .06, b + .11):   # fluting on the posts
        out.append((dark, [W(u - .008, 34, n1), W(u + .008, 34, n1), W(u + .008, DOOR_H - 8, n1), W(u - .008, DOOR_H - 8, n1)]))
    for u0, u1 in ((a - .03, a - .012), (b + .012, b + .03)):   # bead along the inner edge
        out.append((light, [W(u0, 26, n1), W(u1, 26, n1), W(u1, DOOR_H + 4, n1), W(u0, DOOR_H + 4, n1)]))
    out.append((light, [W(a - .03, DOOR_H + 2, n1), W(b + .03, DOOR_H + 2, n1), W(b + .03, DOOR_H + 5, n1), W(a - .03, DOOR_H + 5, n1)]))
    return out


def polys_layer(polys, pad=2):
    """Render (colour, polygon) pieces onto their own transparent surface.
    -> (surface, (x, y)) where (x, y) is the screen position of its corner."""
    xs = [p[0] for _, poly in polys for p in poly]
    ys = [p[1] for _, poly in polys for p in poly]
    x0, y0 = math.floor(min(xs)) - pad, math.floor(min(ys)) - pad
    w, h = math.ceil(max(xs)) - x0 + pad, math.ceil(max(ys)) - y0 + pad
    surf = pygame.Surface((w, h), pygame.SRCALPHA, 32)
    surf.fill((0, 0, 0, 0))
    for c, poly in polys:
        pygame.draw.polygon(surf, (*c, 255), [(x - x0, y - y0) for x, y in poly])
    return surf, (x0, y0)


class Game:
    def __init__(self, screen, seed=None, character="archie", enemies=True, god=False, save=True, title=True,
                 online=None, scores_file=None):
        self.screen = screen
        self.seed = seed if seed is not None else int(time.time() * 1000) % 1_000_000
        self.character = character
        self.enemies_on = enemies
        self.god = god
        self.save_ok = save
        self.sounds = Sounds()
        self.art = art.Art()
        self.chars = {cid: art.load_character(cid) for cid in CHAR_ORDER}
        self.f_hud = load_font(22, bold=True)
        self.f_hud_small = load_font(17)
        self.f_msg = load_font(24)
        self.f_title = load_font(84, bold=True, serif=True)
        self.f_sub = load_font(30, serif=True)
        self.f_help = load_font(21)
        self.f_small = load_font(16)
        self.f_big = load_font(60, bold=True, serif=True)
        self.f_map = load_font(14)
        self.f_map_b = load_font(20, bold=True)
        self.title_pick = CHAR_ORDER.index(character)
        self.best = self._load_best()
        self.new_best = False
        # High scores: online only when saving (headless tests never touch the network or the file)
        online = save if online is None else online
        self.board = scores.Leaderboard(online=online, **({"path": scores_file} if scores_file else {}))
        self.flags = scores.Flags(download=online)
        self.board.refresh()
        self.board_t = 0.0
        self.show_top10 = False            # debug: keep the Top 10 on the title screen
        self.entry_active = False
        self.entry_name = ""
        self.entry_note = ""
        self.new_high = False
        self.best_score = self.board.high_score()
        # Two players over the network (coop.py); None in a one-player game
        self.coop = None
        self.lobby = None
        self.title_opt = 0                 # 0 play alone, 1 host, 2 join
        self.net_port = net.GAME_PORT
        self.coop_seed = None              # testing: the house a hosted game uses
        self.key_hidden = M.KEY_HIDDEN     # hide the key in/behind/under things (a two-player host decides)
        self.killer = None
        self.bg_cache = {}
        self.dark_cache = {}
        self.glow_cache = {}
        self.ghost_cache = {}     # (room, side) -> the front-edge ghost door frame layer
        self.text_cache = {}
        self.player_light = self._make_player_light()
        self.mode = "title" if title else "play"
        self.title_t = 0.0
        self.title_bg = None
        self.new_game(self.seed)
        if title:
            self.sounds.loop("title_theme")

    # ------------------------------------------------------------ set-up
    def _load_best(self):
        if not self.save_ok:
            return None
        try:
            with open(SAVE_FILE) as f:
                return float(json.load(f).get("best"))
        except Exception:
            return None

    def _save_best(self, t):
        if not self.save_ok:
            return
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            with open(SAVE_FILE, "w") as f:
                json.dump({"best": t}, f)
        except Exception:
            pass

    def new_game(self, seed, start_room=M.START_ROOM):
        self.seed = seed
        self.rng = random.Random(seed)
        self.house = M.Mansion()
        self.key_place = self.house.place_key(self.rng, hidden=self.key_hidden)
        self.key_state = "hidden"         # hidden | revealed | carried
        self.door_t = None                # front door: None = shut, else seconds into its swing (open at DOOR_OPEN_S)
        self.key_pos = None               # floor position once revealed
        if self.key_place[1] == "open":
            self.key_state = "revealed"
            self.key_pos = (self.key_place[2][0] + 0.5, self.key_place[2][1] + 0.5)
        self.lives = LIVES
        self.max_lives = LIVES
        self.time = 0.0
        self.score = 0
        self.move_acc = 0.0               # seconds of walking not yet paid out as points
        self.popups = []                  # [text, x, y, age] floating "+5"s (world position)
        self.scoring = False              # the starting room is discovered for nothing
        self.qualified = False
        self.visited = set()
        self.msg = None
        self.msg_t = 0.0
        self.fade = None                  # (phase, t, callback)
        self.searching = None
        self.invuln = 0.0
        self.grace = 0.0
        self.push_t = 0.0
        self.push_obj = None
        self.step_n = 0
        self.creak_t = 8.0
        self.won = False
        self.lost = False
        self.out = None                   # two players: None, or "won" / "dead" once we're out
        self.out_time = 0.0
        self.net_note = ""                # two players: a line for the end screen
        self.partner_end = None           # two players: (name, "won" / "dead" / None, killer)
        self.end_t = 0.0
        self.show_map = False
        self.paused = False
        self.locked_cd = 0.0
        self.room = None
        self.facing = "N"
        self.moving = False
        self.turning = False
        self.turn_t = 0.0
        self.turn_from = self.facing
        self.queued = None             # one tapped action waiting for a turn/step to finish
        self.step_left = 0.0           # distance still owed to a tapped step
        self.step_sign = 0
        self.walk_phase = WALK_START   # walk cycle position (0..1), advanced by distance walked
        self.enter_room(start_room, None)
        self.scoring = True
        if start_room == M.START_ROOM:
            r = self.room
            self.px, self.py = r.w / 2.0, r.d - 1.5
            self.entry = (self.px, self.py, self.facing)
            self.spawn_enemies()

    def enter_room(self, rid, arrive, facing=None):
        """arrive: ("door", side, offset) | ("link", obj) | None (middle)."""
        prev = self.room
        self.room = self.house.rooms[rid]
        r = self.room
        shared = self.coop is not None and self.coop.partner.seen and self.coop.partner.room == rid
        if not shared:   # rooms tidy themselves, unless the other player is in there
            r.reset_pushables()
            for o in r.objs:
                o.slide_t = 0.0
        first = rid not in self.visited
        self.visited.add(rid)
        if facing:
            self.facing = facing
        if arrive is None:
            self.px, self.py = r.w / 2.0, r.d / 2.0
        elif arrive[0] == "door":
            side, off = arrive[1], arrive[2]
            ex, ey = r.door_entry(side)
            if side in ("N", "S"):
                ex += max(-0.7, min(0.7, off))
            else:
                ey += max(-0.7, min(0.7, off))
            self.px, self.py = ex, ey
        else:
            self.px, self.py = arrive[1].exit_pos()
            self.facing = arrive[1].facing
        self.entry = (self.px, self.py, self.facing)
        if self.coop is not None and self.coop.host:
            self.coop_host_enter(prev, shared)
        else:
            self.spawn_enemies()
        self.grace = ENTRY_GRACE
        self.push_t = 0.0
        self.step_left = 0.0
        self.queued = None
        self.searching = None
        if first and self.scoring:
            self.add_points(PTS_ROOM)

    def coop_host_enter(self, prev, shared):
        """Host moving room: share the partner's enemies if they are in here,
        and keep the old room's enemies going if the partner stayed behind."""
        cp = self.coop
        old = self.enemies
        if shared and cp.other_enemies is not None:
            self.enemies, cp.other_enemies = cp.other_enemies, None
        else:
            self.spawn_enemies()
            if cp.partner.seen and prev is not None and cp.partner.room == prev.id:
                cp.other_enemies = old

    def add_points(self, n, popup=True):
        """Score n points; a floating "+n" over the player for the bonuses."""
        self.score += n
        if popup:
            self.popups.append([f"+{n}", self.px, self.py, 0.0])

    def spawn_enemies(self):
        if self.coop is not None and self.coop.client:
            self.enemies = []          # the host sends them
            return
        self.enemies = self.make_enemies(self.room, self.px, self.py)

    def make_enemies(self, r, px, py):
        """Room r's enemies, placed well away from someone coming in at (px, py)."""
        out = []
        if not self.enemies_on or not r.enemies:
            return out
        rng = random.Random(f"{self.seed}:{r.id}")
        reach = r.flood((int(px), int(py)))
        free = [c for c in r.free_floor() if c in reach]
        ex, ey = px, py
        far = [c for c in free if abs(c[0] + 0.5 - ex) + abs(c[1] + 0.5 - ey) >= 4.0] or free
        rng.shuffle(far)
        for i, kind in enumerate(r.enemies):
            if not far:
                break
            c = far[i % len(far)]
            out.append(Enemy(kind, c[0] + 0.5, c[1] + 0.5, rng))
        return out

    def say(self, text):
        self.msg = text
        self.msg_t = MSG_TIME

    # ------------------------------------------------------------ geometry
    def origin(self, room=None):
        r = room or self.room
        ox = WIN_W / 2 - (r.w - r.d) * HW / 2
        total = WALL_H + (r.w + r.d) * HH + SLAB
        top = HUD_H + (WIN_H - HUD_H - 8 - total) / 2
        return ox, top + WALL_H

    def P(self, x, y, z=0.0, room=None):
        ox, oy = self.origin(room)
        return (ox + (x - y) * HW, oy + (x + y) * HH - z)

    # ------------------------------------------------------------ input
    def on_key(self, key):
        if self.entry_active:
            self.entry_key(key)
            return
        if self.mode == "title":
            if key in (pygame.K_LEFT, pygame.K_a, pygame.K_1):
                self.title_pick = 0
            elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_2):
                self.title_pick = 1
            elif key in (pygame.K_UP, pygame.K_w):
                self.title_opt = (self.title_opt - 1) % len(TITLE_OPTIONS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.title_opt = (self.title_opt + 1) % len(TITLE_OPTIONS)
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                if self.title_opt == 0:
                    self.start_play()
                else:
                    self.open_lobby("host" if self.title_opt == 1 else "join")
            return
        if self.mode == "lobby":
            if isinstance(self.lobby, C.JoinLobby):
                self.lobby.on_key(key, pygame)
            return
        if self.mode == "end":
            if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER) and self.end_t > 1.0:
                self.to_title()
            return
        if self.mode == "watch":          # out of the game: look, don't touch
            if key in MAP_KEYS:
                self.show_map = not self.show_map
            return
        if key in MAP_KEYS:
            self.show_map = not self.show_map
        elif key == pygame.K_p:
            if self.coop is not None:
                self.say("No pausing in a two-player game: the house carries on!")
            else:
                self.paused = not self.paused
        elif key in ACTION_KEYS and not self.show_map and not self.paused:
            self.interact()
        elif (key in TURN_KEYS or key in MOVE_KEYS) and not self.show_map and not self.paused:
            action = ("turn", TURN_KEYS[key]) if key in TURN_KEYS else ("step", MOVE_KEYS[key])
            self.try_action(action)

    # ------------------------------------------------------------ name entry (as Dinosaur vs Bees)
    def entry_text(self, text):
        if not self.entry_active:
            return
        for ch in text:
            if ch.isascii() and (ch.isalnum() or ch == " ") and len(self.entry_name) < scores.NAME_MAX:
                if ch == " " and (not self.entry_name or self.entry_name.endswith(" ")):
                    continue
                self.entry_name += ch

    def entry_key(self, key):
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            name = scores.clean_name(self.entry_name)
            if not name:
                return          # type a name first (Esc skips)
            self.entry_active = False
            self.entry_note = name
            self.board.submit(name, self.score)
            self.end_t = min(self.end_t, 0.5)
            self._stop_text()
        elif key == pygame.K_ESCAPE:
            self.entry_active = False
            self.entry_note = ""
            self._stop_text()
        elif key == pygame.K_BACKSPACE:
            self.entry_name = self.entry_name[:-1]

    @staticmethod
    def _stop_text():
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass

    def entry_status(self):
        """End-screen line about the Top 10 once the name step is over."""
        name = self.entry_note
        if self.score <= 0:
            return ""
        if not name:
            return "Score not sent" if self.qualified else ""
        if not self.board.online:
            return f"Saved as {name}"
        if (name, self.score) in self.board.pending:
            return f"Sending as {name}\u2026" if self.board.busy else "Offline \u2013 will send later"
        return f"Score sent as {name}"

    def end_scores(self):
        """At the end of a run: best score, and the name prompt if it makes the Top 10."""
        prev = max(self.best_score, self.board.high_score())
        self.new_high = self.score > prev
        self.best_score = max(prev, self.score)
        self.qualified = self.board.qualifies(self.score)
        self.board.record_local(self.score)
        self.entry_note = ""
        self.entry_active = self.qualified
        if self.entry_active:
            self.entry_name = self.board.last_name
            try:
                pygame.key.start_text_input()
            except Exception:
                pass

    # --------------------------------------------------- tank controls (as Daleks in Hedges)
    def busy(self):
        return self.turning or self.step_left > 0

    def try_action(self, action):
        """A tap: start it now, or queue it (one deep) if a turn/step is under way."""
        if self.mode != "play" or self.searching or self.fade:
            return False
        if self.busy():
            self.queued = action
            return False
        kind, sign = action
        if kind == "turn":
            self.start_turn(sign)
        else:
            self.step_left, self.step_sign = STEP_MIN, sign
        return True

    def start_turn(self, sign):
        i = FACING_ORDER.index(self.facing)
        self.turn_from = self.facing
        self.facing = FACING_ORDER[(i + (1 if sign > 0 else -1)) % 4]
        self.turning = True
        self.turn_t = 0.0
        self.step_left = 0.0
        self.push_t = 0.0

    def stop_controls(self):
        self.turning = False
        self.queued = None
        self.step_left = 0.0
        self.push_t = 0.0

    def pose_facing(self):
        """Mid-turn the sprite keeps the old facing, then settles on the new one."""
        if self.turning and self.turn_t < TURN_S / 2:
            return self.turn_from
        return self.facing

    @staticmethod
    def controls(keys):
        """(turn, move) from held keys. A held turn wins over a held step."""
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        fwd = keys[pygame.K_UP] or keys[pygame.K_w]
        back = keys[pygame.K_DOWN] or keys[pygame.K_s]
        turn = (1 if right else 0) - (1 if left else 0)
        move = 0 if turn else (1 if fwd else 0) - (1 if back else 0)
        return turn, move

    def steer(self, d, back=True):
        """(turn, move) that heads in world direction d with the tank controls:
        walk if already facing it (or backwards if facing away and back is
        allowed), otherwise turn the shorter way. Used by the autopilot."""
        if d == (0, 0):
            return 0, 0
        want = next(k for k, v in DIRS.items() if v == tuple(d))
        if self.facing == want:
            return 0, 1
        diff = (FACING_ORDER.index(want) - FACING_ORDER.index(self.facing)) % 4
        if diff == 2:
            return (0, -1) if back else (1, 0)
        return (1 if diff == 1 else -1), 0

    # ------------------------------------------------------------ two players
    def open_lobby(self, kind):
        self.character = CHAR_ORDER[self.title_pick]
        self.lobby = C.HostLobby(self, self.net_port) if kind == "host" else C.JoinLobby(self)
        self.mode = "lobby"
        self.title_t = 0.0
        if kind == "join":
            try:
                pygame.key.start_text_input()
            except Exception:
                pass

    def close_lobby(self):
        if self.lobby is not None:
            self.lobby.close()
            self.lobby = None
        if self.mode == "lobby":
            self.mode = "title"

    def on_text(self, text):
        """Typed characters: the Top 10 name, or a host address in the join lobby."""
        if self.entry_active:
            self.entry_text(text)
        elif self.mode == "lobby" and isinstance(self.lobby, C.JoinLobby):
            self.lobby.on_text(text)

    def start_coop(self, role, link, seed, mine, theirs):
        """Both games: build the same house from the host's seed and start."""
        self.lobby = None
        self._stop_text()
        self.character = mine
        self.title_pick = CHAR_ORDER.index(mine)
        self.new_game(seed)
        self.coop = C.Coop(self, link, role, theirs)
        self.lives = self.max_lives = C.COOP_LIVES      # each player has their own hearts
        if role == "client":
            self.enemies = []
            self.px += 1.2                  # stand beside the host, not on top of them
            self.entry = (self.px, self.py, self.facing)
        self.mode = "play"
        self.sounds.loop("ambience")
        self.sounds.play("door")
        self.say(f"You are {CHARACTERS[mine]}, with {CHARACTERS[theirs]}. Find the key and both get out!")

    def client_hurt(self, kind, lives):
        """Client: the host says an enemy touched us."""
        self.lives = lives
        self.sounds.play(f"ow_{self.character}")
        self.sounds.play("hurt", 0.7)
        self.say(f"Ow! The {kind} got you! {lives} {'life' if lives == 1 else 'lives'} left.")
        self.invuln = INVULN
        self.px, self.py, self.facing = self.entry
        self.stop_controls()
        self.searching = None

    def go_out(self, how, killer=None):
        """Two players: we escaped ("won") or were caught for the last time
        ("dead"). Watch the other player until they are out too."""
        if self.out is not None:
            return
        self.out = how
        self.out_time = self.time
        self.won, self.lost = how == "won", how == "dead"
        if killer:
            self.killer = killer
        self.searching = None
        self.stop_controls()
        self.popups = [p for p in self.popups if p[0] == f"+{PTS_ESCAPE}"]
        if self.won:
            self.sounds.play("unlock")
            self.sounds.play("win")
        else:
            self.sounds.play("gameover")
        cp = self.coop
        if cp is not None and cp.partner_out() is None:
            self.mode = "watch"
            self.fade = None
            name = cp.partner_name
            self.say(f"You escaped! Watching {name}..." if self.won
                     else f"The {self.killer} got you! Watching {name}...")
            if cp.partner.seen and cp.partner.room != self.room.id:
                self.watch_room(cp.partner.room)
            if cp.host:
                cp.check_end()
        elif cp is not None and cp.host:
            cp.check_end()                # both out: the end for both
        elif cp is None:
            self.finish_end()
        # (a joining game waits for the host's "end")

    def watch_room(self, rid):
        """Watching: the view follows the other player into room rid."""
        cp = self.coop
        self.room = self.house.rooms[rid]
        if cp is not None and cp.host:
            if cp.other_enemies is not None:
                self.enemies, cp.other_enemies = cp.other_enemies, None
            else:
                self.enemies = self.make_enemies(self.room, cp.partner.tx, cp.partner.ty)
        else:
            self.enemies = []             # the host sends them

    def update_watch(self, dt):
        cp = self.coop
        if not self.fade:
            self.update_door(dt)
        for o in self.room.objs:
            if o.slide_t > 0:
                o.slide_t = max(0.0, o.slide_t - dt)
        if cp is None:
            return
        p = cp.partner
        if p.seen and p.room != self.room.id and not p.fade:
            self.watch_room(p.room)
        self.time += dt                   # the house clock (our own time stopped when we got out)
        if cp.host and self.mode == "watch" and cp.partner_out() is None:
            self.run_enemies(self.enemies, self.room, [cp.partner_target()], p.grace, dt)
        self.animate_enemies(dt)

    def finish_end(self):
        """The game is over: our own end screen and Top 10 name entry."""
        if self.out is None:              # (only if the other game ended it oddly)
            self.out, self.out_time, self.lost = "dead", self.time, True
        self.time = self.out_time
        cp = self.coop
        if cp is not None:                # remember how the other one got on (the link may go)
            self.partner_end = (cp.partner_name, cp.partner_out(), cp.partner_killer())
        self.msg_t = 0.0
        self.mode = "end"
        self.end_t = 0.0
        self.show_map = False
        self.fade = None
        self.sounds.loop(None)
        if self.won:
            self.new_best = self.best is None or self.time < self.best
            if self.new_best:
                self.best = self.time
                self._save_best(self.time)
        self.end_scores()

    def end_coop(self):
        if self.coop is not None:
            self.coop.close()
            self.coop = None

    def start_play(self, seed=None):
        self.character = CHAR_ORDER[self.title_pick]
        self.new_game(seed if seed is not None else int(time.time() * 1000) % 1_000_000)
        self.mode = "play"
        self.sounds.loop("ambience")
        self.sounds.play("door")
        self.say("Find the front door key, then escape through the front door!")

    def to_title(self):
        if self.entry_active:
            self.entry_active = False
            self._stop_text()
        self.end_coop()
        self.close_lobby()
        self.mode = "title"
        self.title_t = 0.0
        self.board.refresh()
        self.show_map = False
        self.paused = False
        self.sounds.loop("title_theme")

    # ------------------------------------------------------------ collision
    def blocked_cell(self, c, solid):
        r = self.room
        x, y = c
        if r.inside(c):
            return c in solid
        for side in r.doors:   # outside the room only the doorway gaps are open
            rng = r.door_range(side)
            if (side == "N" and y == -1 and x in rng) or (side == "S" and y == r.d and x in rng) or \
                    (side == "W" and x == -1 and y in rng) or (side == "E" and x == r.w and y in rng):
                return False
        return True

    def box_hits(self, x, y, solid):
        """The first blocking cell overlapped by the player's box at (x, y)."""
        r = PLAYER_R
        for cx in range(math.floor(x - r), math.floor(x + r - 1e-6) + 1):
            for cy in range(math.floor(y - r), math.floor(y + r - 1e-6) + 1):
                if self.blocked_cell((cx, cy), solid):
                    return (cx, cy)
        return None

    def advance_walk(self, dist):
        """Move the walk cycle on by the distance actually walked (so the
        planted foot never slides) and play a footstep at each touch-down."""
        if dist == 0:
            return
        meta = self.chars[self.character]["meta"]
        old = self.walk_phase
        new = old + dist / meta["cycle_tiles"]
        # touch-downs at phase 0 (near foot) and 0.5 (far foot), either direction
        for _ in range(abs(int(math.floor(new * 2)) - int(math.floor(old * 2)))):
            self.step_n += 1
            self.sounds.play(("step1", "step2", "step3")[self.step_n % 3])
        self.walk_phase = new % 1.0

    def walk_frame(self):
        """(image, foot info or None) for the player right now."""
        ch = self.chars[self.character]
        k = FACING_SPRITE[self.pose_facing()]
        if not self.moving:
            return ch["stand"][k], None
        n = ch["meta"]["frames"]
        i = int(self.walk_phase * n) % n
        return ch["walk"][k][i], ch["meta"]["facings"][k]["feet"][i]

    def move_player(self, dx, dy, dt):
        """Axis-separated move with corner sliding; returns the cell bumped."""
        solid = self.room.solid_cells()
        bumped = None
        step = PLAYER_SPEED * dt * (0.7071 if (dx and dy) else 1.0)
        for axis, d in ((0, dx), (1, dy)):
            if not d:
                continue
            nx = self.px + (d * step if axis == 0 else 0)
            ny = self.py + (d * step if axis == 1 else 0)
            hit = self.box_hits(nx, ny, solid)
            if hit is None:
                self.px, self.py = nx, ny
                continue
            bumped = bumped or hit
            if axis == 0:   # snap flush against the obstacle
                self.px = (hit[0] - PLAYER_R - 1e-4) if d > 0 else (hit[0] + 1 + PLAYER_R + 1e-4)
            else:
                self.py = (hit[1] - PLAYER_R - 1e-4) if d > 0 else (hit[1] + 1 + PLAYER_R + 1e-4)
            if dx and dy:
                continue
            # corner assist: slide sideways towards an opening right beside us
            perp = self.py if axis == 0 else self.px
            base = math.floor(perp)
            for cand in (base, base - 1, base + 1):
                centre = cand + 0.5
                if abs(centre - perp) > 0.55:
                    continue
                ahead = (math.floor(self.px + d * (PLAYER_R + 0.05)), cand) if axis == 0 else \
                        (cand, math.floor(self.py + d * (PLAYER_R + 0.05)))
                if self.blocked_cell(ahead, solid):
                    continue
                move = max(-step, min(step, centre - perp))
                if axis == 0 and self.box_hits(self.px, self.py + move, solid) is None:
                    self.py += move
                elif axis == 1 and self.box_hits(self.px + move, self.py, solid) is None:
                    self.px += move
                break
        return bumped

    # ------------------------------------------------------------ update
    def update(self, dt, keys=None, auto=None, ctrl=None):
        """keys: held keys (tank controls); ctrl: (turn, move) directly;
        auto: a world direction, steered to with the tank controls."""
        self.board_t += dt
        if self.board_t > BOARD_REFRESH:
            self.board_t = 0.0
            self.board.refresh()
        for p in self.popups:
            p[3] += dt
        self.popups = [p for p in self.popups if p[3] < POPUP_TIME]
        if self.mode in ("title", "lobby"):
            self.title_t += dt
            if self.mode == "lobby" and self.lobby is not None:
                self.lobby.update(dt)
            return
        if self.coop is not None:
            self.coop.tick(dt)        # network in, other room's enemies, network out
        if self.mode == "end":
            self.end_t += dt
            return
        if self.msg_t > 0:
            self.msg_t -= dt
        if self.mode == "watch":
            self.update_watch(dt)
            return
        if self.fade:
            phase, t, cb = self.fade
            t += dt
            if phase == "out" and t >= FADE:
                cb()
                self.fade = ("in", 0.0, None)
            elif phase == "in" and t >= FADE:
                self.fade = None
            else:
                self.fade = (phase, t, cb)
            return
        if self.paused or (self.show_map and self.coop is None):
            return
        if self.show_map:           # two players: the house carries on behind the map
            keys, auto, ctrl = None, None, (0, 0)
        self.time += dt
        self.update_door(dt)
        self.locked_cd = max(0.0, self.locked_cd - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.grace = max(0.0, self.grace - dt)
        for o in self.room.objs:
            if o.slide_t > 0:
                o.slide_t = max(0.0, o.slide_t - dt)
        if self.searching:
            self.searching[1] -= dt
            if self.searching[1] <= 0:
                o = self.searching[0]
                self.searching = None
                self.finish_search(o)
            self.update_enemies(dt)
            return
        if ctrl is not None:
            turn, move = ctrl
        elif auto is not None:
            turn, move = self.steer(auto)
        elif keys is not None:
            turn, move = self.controls(keys)
        else:
            turn, move = 0, 0
        if self.turning:
            self.turn_t += dt
            if self.turn_t >= TURN_S:
                extra = self.turn_t - TURN_S
                self.turning = False
                q, self.queued = self.queued, None
                if q is not None:
                    self.try_action(q)
                elif turn:                 # still held: the next quarter turn follows straight on
                    self.start_turn(turn)
                    self.turn_t = extra
        elif turn and self.step_left <= 0:
            self.start_turn(turn)
        sign = 0
        if not self.turning:
            sign = move if move else (self.step_sign if self.step_left > 0 else 0)
        self.moving = bool(sign)
        if sign:
            dx, dy = DIRS[self.facing][0] * sign, DIRS[self.facing][1] * sign
            ox, oy = self.px, self.py
            bumped = self.move_player(dx, dy, dt)
            dist = math.hypot(self.px - ox, self.py - oy)
            self.advance_walk(dist * sign)          # backwards plays the cycle in reverse
            if dist > 1e-6:                         # actually walking, not shoving a wall
                self.move_acc += dt
                whole = int(self.move_acc + 1e-9)   # 60 x (1/60 s) is a whole second
                if whole:
                    self.move_acc -= whole
                    self.add_points(whole * PTS_MOVE, popup=False)
            if self.step_left > 0:
                self.step_left = 0.0 if dist < 1e-4 else max(0.0, self.step_left - dist)
                if self.step_left <= 0:
                    q, self.queued = self.queued, None
                    if q is not None:
                        self.try_action(q)
            if sign > 0:
                self.handle_bump(bumped, dx, dy, dt)   # push, climb, front door: facing it only
            else:
                self.push_t = 0.0
            if self.fade or self.mode != "play":
                return
        else:
            self.push_t = 0.0
            self.walk_phase = WALK_START   # idle: standing frame; the next walk starts mid-stride
        self.check_exits()
        if self.fade:
            return
        self.check_key_pickup()
        self.update_enemies(dt)
        self.creak_t -= dt
        if self.creak_t <= 0:
            self.sounds.play(random.choice(("creak1", "creak2")), 0.6)
            self.creak_t = random.uniform(9, 22)

    # ------------------------------------------------------------ the front door
    def someone_in_hall(self):
        """Is a player who is still in the house standing in the Entrance Hall?"""
        if self.mode == "play" and self.out is None and self.room.id == M.START_ROOM:
            return True
        cp = self.coop
        if cp is not None:
            p = cp.partner
            if p.seen and not p.fade and p.room == M.START_ROOM and cp.partner_out() is None:
                return True
        return False

    def open_front_door(self):
        """Start the door's swing (with the creak) if we are looking at the
        Entrance Hall; anywhere else it is simply open by the time we get there.
        Once open it stays open: no second swing."""
        if self.door_t is not None:
            return
        if self.mode in ("play", "watch") and self.room.id == M.START_ROOM:
            self.door_t = 0.0
            self.sounds.play("door_creak")
        else:
            self.door_t = DOOR_OPEN_S

    def update_door(self, dt):
        if self.door_t is None:
            if self.key_state == "carried" and self.someone_in_hall():
                self.open_front_door()
        elif self.door_t < DOOR_OPEN_S:
            self.door_t = min(DOOR_OPEN_S, self.door_t + dt)

    def door_angle(self):
        """How far the leaves have swung (radians): a heavy start, a long
        swing, and a slow settle."""
        if self.door_t is None:
            return 0.0
        u = max(0.0, min(1.0, self.door_t / DOOR_OPEN_S))
        u = u * u * (3 - 2 * u)                       # ease in and out
        u = u + 0.035 * math.sin(u * math.pi * 3) * (1 - u)   # it judders as the hinges catch
        return DOOR_SWING * max(0.0, min(1.0, u))

    def at_front_door(self):
        fd = self.room.front_door()
        return fd is not None and self.py < PLAYER_R + 0.08 and fd.index <= self.px < fd.index + 2

    def handle_bump(self, cell, dx, dy, dt):
        r = self.room
        if dy < 0 and self.at_front_door():
            self.try_front_door()
            return
        if cell is None or not r.inside(cell):
            self.push_t = 0.0
            return
        obj = r.solid_cells().get(cell)
        if obj is None:
            return
        if obj.type in ("stairs_up", "ladder_up"):
            self.take_link(obj)
            return
        if obj.t.get("push") and (bool(dx) != bool(dy)):
            if self.push_obj is not obj:
                self.push_obj, self.push_t = obj, 0.0
            self.push_t += dt
            if self.push_t >= PUSH_DELAY:
                self.push_t = 0.0
                self.try_push(obj, (dx, dy))
        else:
            self.push_t = 0.0

    def try_push(self, obj, d, room=None, say=None, others=()):
        """Shove obj one tile along d. room/say/others: the host acting for the
        other player (their room, their messages, players to keep clear of)."""
        if self.coop is not None and self.coop.client and room is None:
            self.coop.request("push", obj=obj.id, d=list(d))
            return False
        r = room or self.room
        say = say or self.say
        solid = r.solid_cells()
        trig = r.trigger_cells()
        clear = r.keep_clear()
        dest = [(c[0] + d[0], c[1] + d[1]) for c in obj.cells()]
        ok = all(r.inside(c) and (c not in solid or solid[c] is obj) and c not in trig and c not in clear for c in dest)
        enemies = self.enemies if r is self.room else (self.coop.other_enemies or [] if self.coop else [])
        if ok and any(not e.floats and (int(e.x), int(e.y)) in dest for e in enemies):
            ok = False
        if ok and self.coop is not None:   # never shove furniture onto a player
            people = list(others)
            p = self.coop.partner
            if room is None and p.seen and p.room == r.id:
                people.append((p.tx, p.ty))
            if any((math.floor(x), math.floor(y)) in dest for x, y in people):
                ok = False
        if ok and self.key_state == "revealed" and self.key_place[0] == r.id and \
                (math.floor(self.key_pos[0]), math.floor(self.key_pos[1])) in dest:
            ok = False   # never shove furniture on top of the key
        if not ok:
            if room is not None:
                say(f"The {nice(obj.type)} won't budge any further.")
            elif self.locked_cd <= 0:
                self.say(f"The {nice(obj.type)} won't budge any further.")
                self.locked_cd = 2.0
            return False
        old = (obj.x, obj.y)
        obj.x += d[0]
        obj.y += d[1]
        obj.dx, obj.dy = -d[0], -d[1]
        obj.slide_t = SLIDE_TIME
        if r is self.room:
            self.sounds.play("push")
        if self.key_state == "hidden" and self.key_place[:3] == (r.id, "under", obj.id):
            self.key_state = "revealed"
            self.key_pos = (old[0] + 0.5, old[1] + 0.5)
            obj.home = (obj.x, obj.y)   # stays moved, so it never covers the key again
            if room is None:
                self.sounds.play("key_found")
            say(f"Something glints where the {nice(obj.type)} was!")
        return True

    def target_object(self):
        """What the player would search or lift: something just in front."""
        r = self.room
        fx, fy = DIRS[self.facing]
        solid = r.solid_cells()
        for reach in (0.5, 0.85):
            o = solid.get((math.floor(self.px + fx * reach), math.floor(self.py + fy * reach)))
            if o is not None and o.t.get("search"):
                return o
        for o in r.walls:   # wall hangings: stand by the wall and face it
            if not o.t.get("search"):
                continue
            n = T[o.type]["size"][0]
            if o.side == "N" and self.facing == "N" and self.py < 1.0 and o.index - 0.2 <= self.px <= o.index + n + 0.2:
                return o
            if o.side == "W" and self.facing == "W" and self.px < 1.0 and o.index - 0.2 <= self.py <= o.index + n + 0.2:
                return o
        for o in r.objs:    # a rug you are standing on or beside
            if o.t.get("lift") and o.x - 0.6 <= self.px <= o.x + o.gx + 0.6 and o.y - 0.6 <= self.py <= o.y + o.gy + 0.6:
                return o
        for d in DIRS.values():   # a searchable right beside you, even if you face slightly wrong
            o = solid.get((math.floor(self.px + d[0] * 0.6), math.floor(self.py + d[1] * 0.6)))
            if o is not None and o.t.get("search"):
                return o
        return None

    def interact(self):
        if self.searching or self.fade or self.mode != "play":
            return
        r = self.room
        fd = r.front_door()
        if fd is not None and self.py < 1.0 and fd.index <= self.px < fd.index + 2 and self.facing == "N":
            self.try_front_door()
            return
        o = self.target_object()
        if o is None:
            self.say("Nothing to search here. Face a piece of furniture and try again.")
            return
        if o.t.get("lift") and self.coop is not None and self.coop.client:
            self.sounds.play("rug")
            self.coop.request("lift", obj=o.id)   # the host lifts it (and checks underneath)
            return
        if o.t.get("lift"):
            o.lifted = not o.lifted
            self.sounds.play("rug")
            if o.lifted and self.key_state == "hidden" and self.key_place[:3] == (r.id, "rug", o.id):
                self.key_state = "revealed"
                self.key_pos = (o.x + o.gx - 0.5, o.y + o.gy - 0.5)
                self.sounds.play("key_found")
                self.say("There's something under the rug!")
            elif o.lifted:
                self.say("You lift the corner of the rug. Just dust.")
            return
        self.searching = [o, SEARCH_TIME]
        self.sounds.play("search")
        self.say(f"Searching the {nice(o.type)}...")

    def finish_search(self, o):
        r = self.room
        if self.key_state == "hidden" and self.key_place[:3] == (r.id, "search", o.id):
            if self.coop is not None and self.coop.client:
                self.coop.request("search", obj=o.id)   # the host hands it over
                o.searched = True
                return
            self.key_state = "carried"
            self.sounds.play("key_found")
            self.add_points(PTS_KEY)
            if self.coop is not None:
                self.coop.announce_key()
            how = SEARCH_PHRASE[o.t["search"]].format(n=nice(o.type))
            self.say(f"You found the front door key {how}!")
            return
        if o.searched:
            self.say(f"You've already searched the {nice(o.type)}. Nothing.")
        else:
            self.say(random.choice(SEARCH_LINES.get(o.type, ["Nothing here."])))
        o.searched = True

    def try_front_door(self):
        if self.key_state == "carried" and self.coop is not None and self.coop.client:
            if self.locked_cd <= 0:
                self.coop.request("escape")
                self.locked_cd = 0.5
        elif self.key_state == "carried":
            self.win()
        elif self.locked_cd <= 0:
            self.sounds.play("locked")
            self.say("The front door is locked. You need the key!")
            self.locked_cd = 2.0

    def check_key_pickup(self):
        if self.key_state != "revealed" or self.key_place[0] != self.room.id:
            return
        kx, ky = self.key_pos
        if abs(self.px - kx) < 0.55 and abs(self.py - ky) < 0.55:
            if self.coop is not None and self.coop.client:
                self.coop.want_pickup()
                return
            self.key_state = "carried"
            self.sounds.play("key_found")
            self.add_points(PTS_KEY)
            if self.coop is not None:
                self.coop.announce_key()
            self.say("You picked up the front door key! Back to the Entrance Hall!")

    def check_exits(self):
        r = self.room
        side = "N" if self.py < 0 else "S" if self.py > r.d else "W" if self.px < 0 else "E" if self.px > r.w else None
        if side and side in r.doors:
            rng = r.door_range(side)
            off = (self.px if side in ("N", "S") else self.py) - (rng.start + M.DOOR_W / 2.0)
            to, back, facing = r.doors[side]["to"], M.OPPOSITE[side], self.facing
            self.sounds.play("door", 0.5)
            self.fade = ("out", 0.0, lambda: self.enter_room(to, ("door", back, off), facing))
            return
        trig = r.trigger_cells().get((math.floor(self.px), math.floor(self.py)))
        if trig is not None:
            self.take_link(trig)

    def take_link(self, obj):
        other, partner = self.house.link_target(self.room, obj)
        self.sounds.play("stairs")
        self.say(f"You go {M.LINK_VERB[obj.type]}: {M.FLOOR_NAMES[other.floor]}.")
        self.fade = ("out", 0.0, lambda: self.enter_room(other.id, ("link", partner)))

    # ------------------------------------------------------------ enemies
    def update_enemies(self, dt):
        if self.coop is not None and self.coop.client:
            self.animate_enemies(dt)
            return                       # the host moves them (coop.tick eases them along)
        targets = [types.SimpleNamespace(x=self.px, y=self.py, invuln=self.invuln, hit=self.hurt)]
        grace = self.grace
        if self.coop is not None and self.coop.partner_here():
            targets.append(self.coop.partner_target())
            grace = max(grace, self.coop.partner.grace)
        self.run_enemies(self.enemies, self.room, targets, grace, dt)
        self.animate_enemies(dt)

    def animate_enemies(self, dt):
        """Animation frames for the enemies in view, from how far each has
        moved since the last frame, so the joiner animates from the eased
        positions the host sends exactly as the host does from its own."""
        for e in self.enemies:
            if e.kind == "bat":
                self._animate_bat(e, dt)
            elif e.kind == "skeleton":
                self._animate_skeleton(e, dt)

    def _animate_bat(self, e, dt):
        f = int(e.phase * BAT_FPS) % 4
        e.flap_cd -= dt
        if f != e.frame:
            e.frame = f
            if f == 1 and e.flap_cd <= 0:          # mid-downstroke: the wings bite the air
                d = math.hypot(self.px - e.x, self.py - e.y)
                if d < BAT_FLAP_NEAR and self.enemy_on_screen(e):
                    self.sounds.play("bat_flap", 0.35 + 0.65 * (1 - d / BAT_FLAP_NEAR))
                    e.flap_cd = 1.0 + 0.8 * ((e.phase * 7.31) % 1.0)   # now and then, not every beat

    def _animate_skeleton(self, e, dt):
        moved = 0.0 if e.anim_xy is None else math.hypot(e.x - e.anim_xy[0], e.y - e.anim_xy[1])
        e.anim_xy = (e.x, e.y)
        if moved > 1.0:                             # a jump (placed, resynced), not a walk
            moved = 0.0
        e.jolt = max(0.0, e.jolt - dt)
        if moved > 1e-4:
            e.still = 0.0
            e.walk_d += moved
            f = int(e.walk_d / SKEL_FRAME_D) % 4
            if f != e.frame:                        # snap to the next pose (no blending)
                e.frame = f
                if f in (0, 2):                     # a stride: a foot comes down
                    e.jolt = SKEL_JOLT_S
                    e.foot ^= 1
                    d = math.hypot(self.px - e.x, self.py - e.y)
                    if d < SKEL_CLACK_FAR and self.enemy_on_screen(e):
                        self.sounds.play(f"skel_clack{e.foot + 1}", 0.25 + 0.75 * (1 - d / SKEL_CLACK_FAR) ** 1.5)
        else:
            e.still += dt
            if e.still >= SKEL_IDLE_S and e.frame != 1:
                e.frame = 1                         # standing: legs together
                e.walk_d = 1.5 * SKEL_FRAME_D       # the next step starts with the other stride

    def enemy_on_screen(self, e):
        if self.mode not in ("play", "watch") or self.fade:
            return False
        x, y = self.P(e.x, e.y, e.z0)
        return -60 < x < WIN_W + 60 and HUD_H - 60 < y < WIN_H + 60

    def run_enemies(self, enemies, r, targets, grace, dt, audible=True):
        """Move room r's enemies after the nearest target that can be hurt;
        a touch calls that target's hit(enemy). One player: one target."""
        if not enemies:
            return
        solid = r.solid_cells()
        for e in enemies:
            e.phase += dt
            e.cry_cd -= dt
            if grace > 0:
                continue
            t = targets[0] if len(targets) == 1 else \
                min(targets, key=lambda t: (t.invuln > 0, math.hypot(t.x - e.x, t.y - e.y)))
            dist = math.hypot(t.x - e.x, t.y - e.y)
            chase = dist < e.sense and t.invuln <= 0
            if chase and not e.cried and e.cry_cd <= 0:
                if audible:
                    self.sounds.play(e.kind, 0.8)   # one cry each time it starts hunting you
                e.cried = True
                e.cry_cd = 4.0
            elif not chase:
                e.cried = False
            e.chasing = chase
            if e.floats:
                self._float(e, r, chase, dt, t.x, t.y)
            else:
                self._walk(e, r, solid, chase, dist, dt, t.x, t.y)
            for t in targets:
                if math.hypot(t.x - e.x, t.y - e.y) < e.r + PLAYER_R and t.invuln <= 0 and not self.god:
                    t.hit(e)
                    return

    def _float(self, e, r, chase, dt, px, py):
        if chase:
            tx, ty = px, py
        else:
            if e.wander is None or math.hypot(e.wander[0] - e.x, e.wander[1] - e.y) < 0.2:
                e.wander = (e.rng.uniform(0.6, r.w - 0.6), e.rng.uniform(0.6, r.d - 0.6))
            tx, ty = e.wander
        vx, vy = tx - e.x, ty - e.y
        n = math.hypot(vx, vy) or 1
        sp = e.speed * (1.0 if chase else 0.5)
        if e.kind == "bat":   # erratic, swooping flight
            a = math.sin(e.phase * 7.0) * 1.1
            vx, vy = vx * math.cos(a) - vy * math.sin(a), vx * math.sin(a) + vy * math.cos(a)
        e.x = min(r.w - 0.3, max(0.3, e.x + vx / n * sp * dt))
        e.y = min(r.d - 0.3, max(0.3, e.y + vy / n * sp * dt))
        if abs(vx - vy) > 0.01:
            e.left = (vx - vy) < 0

    def _walk(self, e, r, solid, chase, dist, dt, px, py):
        e.think -= dt
        if e.think <= 0:
            e.think = 0.45
            goal = None
            if chase:
                goal = (min(r.w - 1, max(0, int(px))), min(r.d - 1, max(0, int(py))))
            elif not e.path:
                free = r.free_floor()
                goal = e.rng.choice(free) if free else None
            if goal is not None:
                p = r.path((int(e.x), int(e.y)), goal, solid)
                if p:
                    e.path = p[1:]
                elif chase:
                    e.path = []
        if chase and not e.path and dist < 1.2:
            tx, ty = px, py
        elif e.path:
            tx, ty = e.path[0][0] + 0.5, e.path[0][1] + 0.5
        else:
            return
        vx, vy = tx - e.x, ty - e.y
        n = math.hypot(vx, vy)
        sp = e.speed * (1.0 if chase else 0.55) * dt
        if n <= sp:
            e.x, e.y = tx, ty
            if e.path:
                e.path.pop(0)
        else:
            nx, ny = e.x + vx / n * sp, e.y + vy / n * sp
            if (int(nx), int(ny)) not in solid:
                e.x, e.y = nx, ny
            else:
                e.path = []
        if abs(vx - vy) > 0.01:
            e.left = (vx - vy) < 0

    def hurt(self, e):
        self.lives -= 1
        self.sounds.play(f"ow_{self.character}")
        self.sounds.play("hurt", 0.7)
        if self.lives <= 0:
            self.lose(e)
            return
        self.say(f"Ow! The {e.kind} got you! {self.lives} {'life' if self.lives == 1 else 'lives'} left.")
        self.invuln = INVULN
        self.px, self.py, self.facing = self.entry
        self.stop_controls()
        self.spawn_enemies()
        self.grace = ENTRY_GRACE

    def key_where(self):
        rid, how, what = self.key_place
        room = self.house.rooms[rid]
        if how == "open":
            return f"on the floor in the {room.name}"
        o = self.house.find_obj(room, what)
        if how == "under":
            return f"under the {nice(o.type)} in the {room.name}"
        if how == "rug":
            return f"under the rug in the {room.name}"
        return SEARCH_PHRASE[o.t["search"]].format(n=nice(o.type)) + f" in the {room.name}"

    def win(self):
        self.add_points(PTS_ESCAPE)
        if self.coop is not None:
            self.go_out("won")
            return
        self.won = True
        self.mode = "end"
        self.end_t = 0.0
        self.sounds.play("unlock")
        self.sounds.play("win")
        self.sounds.loop(None)
        self.new_best = self.best is None or self.time < self.best
        if self.new_best:
            self.best = self.time
            self._save_best(self.time)
        self.end_scores()

    def lose(self, e):
        if self.coop is not None:
            self.go_out("dead", e.kind)
            return
        self.lost = True
        self.mode = "end"
        self.end_t = 0.0
        self.killer = e.kind
        self.sounds.play("gameover")
        self.sounds.loop(None)
        self.end_scores()

    # ================================================================ drawing
    def build_background(self, r):
        s = pygame.Surface((WIN_W, WIN_H)).convert()
        top, bot = np.array((14, 10, 22)), np.array((4, 3, 8))
        k = np.linspace(0, 1, WIN_H)[:, None]
        col = top[None, :] * (1 - k) + bot[None, :] * k
        pygame.surfarray.blit_array(s, np.repeat(col[None, :, :], WIN_W, axis=0).astype(np.uint8))
        st = r.style
        rnd = random.Random(r.id)
        P = lambda x, y, z=0.0: self.P(x, y, z, r)
        # floor slab along the open front edges
        pygame.draw.polygon(s, art.shade(st["f2"], 0.45), [P(0, r.d), P(r.w, r.d), P(r.w, r.d, -SLAB), P(0, r.d, -SLAB)])
        pygame.draw.polygon(s, art.shade(st["f2"], 0.32), [P(r.w, 0), P(r.w, r.d), P(r.w, r.d, -SLAB), P(r.w, 0, -SLAB)])
        kind = st["floor"]
        if kind == "parquet":
            self._draw_parquet(s, r, rnd)
        for x in range(r.w if kind != "parquet" else 0):
            for y in range(r.d):
                j = rnd.uniform(0.92, 1.06)
                quad = [P(x, y), P(x + 1, y), P(x + 1, y + 1), P(x, y + 1)]
                if kind == "marble":
                    pygame.draw.polygon(s, art.shade(st["f1"] if (x + y) % 2 == 0 else st["f2"], j), quad)
                elif kind == "tiles":
                    for i in range(2):
                        for kk in range(2):
                            c = st["f1"] if (i + kk) % 2 == 0 else st["f2"]
                            a, b = x + i / 2, y + kk / 2
                            pygame.draw.polygon(s, art.shade(c, j), [P(a, b), P(a + .5, b), P(a + .5, b + .5), P(a, b + .5)])
                elif kind == "flagstone":
                    pygame.draw.polygon(s, art.lerp(st["f1"], st["f2"], rnd.random()), quad)
                    pygame.draw.polygon(s, art.shade(st["f2"], 0.6), quad, 2)
                elif kind == "carpet":
                    edge = x == 0 or y == 0 or x == r.w - 1 or y == r.d - 1
                    pygame.draw.polygon(s, art.shade(st["f2"] if edge else st["f1"], 0.97 + 0.03 * ((x + y) % 2)), quad)
                    if not edge and (x + y) % 2 == 0:
                        cx, cy = P(x + .5, y + .5)
                        pygame.draw.polygon(s, art.shade(st["f1"], 1.25), [(cx, cy - 9), (cx + 18, cy), (cx, cy + 9), (cx - 18, cy)])
                else:  # boards / planks run along x
                    for kk in range(3):
                        a = y + kk / 3
                        c = art.shade(st["f1"] if (x + kk) % 2 else st["f2"], rnd.uniform(0.9, 1.08))
                        pygame.draw.polygon(s, c, [P(x, a), P(x + 1, a), P(x + 1, a + 1 / 3), P(x, a + 1 / 3)])
                    pygame.draw.line(s, art.shade(st["f2"], 0.55), P(x, y), P(x, y + 1), 1)
        if kind in ("boards", "planks"):
            for kk in range(r.d * 3 + 1):
                pygame.draw.line(s, art.shade(st["f2"], 0.6), P(0, kk / 3), P(r.w, kk / 3), 1)
        # thresholds beyond the open (front) doorways, fading into the dark
        for side in ("S", "E"):
            rng = r.door_range(side)
            if rng is None:
                continue
            a, b = rng.start, rng.stop
            for kk in range(6):
                t0, t1 = kk / 6 * 0.8, (kk + 1) / 6 * 0.8
                c = art.shade(st["f2"], 0.6 * (1 - kk / 6))
                if side == "S":
                    poly = [P(a, r.d + t0), P(b, r.d + t0), P(b, r.d + t1), P(a, r.d + t1)]
                else:
                    poly = [P(r.w + t0, a), P(r.w + t0, b), P(r.w + t1, b), P(r.w + t1, a)]
                pygame.draw.polygon(s, c, poly)
        self._draw_wall(s, r, "N")
        self._draw_wall(s, r, "W")
        for o in r.walls:
            img = self.art.wall(o.type, o.side)
            n = T[o.type]["size"][0]
            top_z = o.mount + T[o.type]["h"]
            if o.side == "N":
                x0, y0 = P(o.index, 0)[0], P(o.index, 0, top_z)[1]
            else:
                x0, y0 = P(0, o.index + n)[0], P(0, o.index, top_z)[1]
            s.blit(img, (round(x0), round(y0)))
        return s

    def _draw_parquet(self, s, r, rnd):
        """Oak herringbone parquet. Every block runs along one of the two
        floor axes, so all its edges sit on the 2:1 isometric lines: blocks
        are PARQUET_W x 2*PARQUET_W tiles, a lengthways (x) block at cell
        (ox, oy) with a crossways (y) one tucked under its left end, the pair
        repeated on the lattice (1, 1) and (2, -2) cells."""
        st = r.style
        w = PARQUET_W
        P = lambda x, y: self.P(x, y, 0, r)
        gap, f1, f2 = art.shade(st["f2"], 0.5), st["f1"], st["f2"]
        nx, ny = int(math.ceil(r.w / w)), int(math.ceil(r.d / w))
        span = nx + ny + 4
        for i in range(-span, span + 1):
            for j in range(-span // 2 - 2, span // 2 + 3):
                ox, oy = i + 2 * j, i - 2 * j
                for along_x, (cx, cy) in ((True, (ox, oy)), (False, (ox, oy + 1))):
                    x0, y0 = cx * w, cy * w
                    x1, y1 = (x0 + 2 * w, y0 + w) if along_x else (x0 + w, y0 + 2 * w)
                    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(r.w, x1), min(r.d, y1)
                    if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
                        continue
                    pr = random.Random(f"{r.id}{cx},{cy}")
                    c = art.shade(art.lerp(f1, f2, pr.uniform(0.0, 0.7)), pr.uniform(0.92, 1.06) * (1.04 if along_x else 0.93))
                    pygame.draw.polygon(s, c, [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)])
                    g = pr.uniform(0.3, 0.7)   # a grain line down the block
                    if along_x:
                        pygame.draw.line(s, art.shade(c, 0.86), P(x0 + .02, y0 + g * (y1 - y0)), P(x1 - .02, y0 + g * (y1 - y0)), 1)
                    else:
                        pygame.draw.line(s, art.shade(c, 0.86), P(x0 + g * (x1 - x0), y0 + .02), P(x0 + g * (x1 - x0), y1 - .02), 1)
                    pygame.draw.polygon(s, gap, [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)], 1)

    def _draw_wall(self, s, r, side):
        st = r.style
        n = r.side_len(side)
        Q = (lambda u, z: self.P(u, 0, z, r)) if side == "N" else (lambda u, z: self.P(0, u, z, r))
        k = 0.92 if side == "N" else 0.72
        base, alt = art.shade(st["w1"], k), art.shade(st["w2"], k)
        pygame.draw.polygon(s, base, [Q(0, 0), Q(n, 0), Q(n, WALL_H), Q(0, WALL_H)])
        rnd = random.Random(r.id + side)
        pat = st["wall"]
        if pat == "stripe":
            for i in range(0, n * 3, 2):
                a, b = i / 3, (i + 1) / 3
                pygame.draw.polygon(s, alt, [Q(a, 0), Q(b, 0), Q(b, WALL_H), Q(a, WALL_H)])
        elif pat == "damask":
            for i in range(n * 2):
                for j in range(5):
                    u = (i + 0.5 + (j % 2) * 0.5) / 2
                    if u < n:
                        cx, cy = Q(u, 30 + j * 42)
                        pygame.draw.polygon(s, alt, [(cx, cy - 12), (cx + 8, cy - 2), (cx, cy + 12), (cx - 8, cy + 2)])
        elif pat == "panel":
            for i in range(n):
                quad = [Q(i + .12, 20), Q(i + .88, 20), Q(i + .88, 100), Q(i + .12, 100)]
                pygame.draw.polygon(s, alt, quad)
                pygame.draw.polygon(s, art.shade(alt, 0.7), quad, 2)
            pygame.draw.polygon(s, art.shade(alt, 1.15), [Q(0, 106), Q(n, 106), Q(n, 114), Q(0, 114)])
        elif pat in ("brick", "stone"):
            rows = 12 if pat == "brick" else 6
            hgt = WALL_H / rows
            per = 3 if pat == "brick" else 1.5
            for j in range(rows):
                u = -(j % 2) * 0.5 / per
                while u < n:
                    a, b = max(0, u), min(n, u + 1 / per)
                    c = art.shade(art.lerp(st["w1"], st["w2"], rnd.random()), k)
                    quad = [Q(a, j * hgt + 1), Q(b, j * hgt + 1), Q(b, (j + 1) * hgt - 1), Q(a, (j + 1) * hgt - 1)]
                    pygame.draw.polygon(s, c, quad)
                    pygame.draw.polygon(s, art.shade(c, 0.55), quad, 1)
                    u += 1 / per
        elif pat == "beams":
            for i in range(0, n + 1, 2):
                pygame.draw.polygon(s, alt, [Q(max(0, i - .12), 0), Q(min(n, i + .12), 0), Q(min(n, i + .12), WALL_H), Q(max(0, i - .12), WALL_H)])
            for z0, z1 in ((WALL_H - 26, WALL_H - 10), (120, 132)):
                pygame.draw.polygon(s, alt, [Q(0, z0), Q(n, z0), Q(n, z1), Q(0, z1)])
        else:  # plaster with cracks
            for _ in range(n):
                u, z = rnd.uniform(0.3, n - 0.3), rnd.uniform(60, WALL_H - 30)
                pts = [Q(u, z)]
                for _ in range(4):
                    u += rnd.uniform(-0.15, 0.15)
                    z -= rnd.uniform(8, 18)
                    pts.append(Q(u, z))
                pygame.draw.lines(s, art.shade(base, 0.7), False, pts, 2)
        pygame.draw.polygon(s, art.shade(st["w2"], 0.5 * k), [Q(0, 0), Q(n, 0), Q(n, 14), Q(0, 14)])   # skirting
        cap = (64, 56, 52)
        t = 0.28
        if side == "N":
            pygame.draw.polygon(s, cap, [self.P(0, 0, WALL_H, r), self.P(n, 0, WALL_H, r), self.P(n, -t, WALL_H, r), self.P(-t, -t, WALL_H, r)])
            pygame.draw.polygon(s, art.shade(cap, 0.55), [self.P(n, 0, WALL_H, r), self.P(n, -t, WALL_H, r), self.P(n, -t, -SLAB, r), self.P(n, 0, -SLAB, r)])
        else:
            pygame.draw.polygon(s, art.shade(cap, 1.15), [self.P(0, 0, WALL_H, r), self.P(0, n, WALL_H, r), self.P(-t, n, WALL_H, r), self.P(-t, -t, WALL_H, r)])
            pygame.draw.polygon(s, art.shade(cap, 0.75), [self.P(-t, n, WALL_H, r), self.P(0, n, WALL_H, r), self.P(0, n, -SLAB, r), self.P(-t, n, -SLAB, r)])
        rng = r.door_range(side)
        if rng is not None:   # the way through: a dark doorway in a semi-transparent frame
            a, b = rng.start, rng.stop
            W = (lambda u, z, nn: self.P(u, nn, z, r)) if side == "N" else (lambda u, z, nn: self.P(nn, u, z, r))
            void = [((8, 6, 12), [W(a, 0, 0), W(b, 0, 0), W(b, DOOR_H, 0), W(a, DOOR_H, 0)]),
                    (art.shade(st["f2"], 0.4), [W(a, 0, 0), W(b, 0, 0), W(b, 0, -t), W(a, 0, -t)]),          # threshold
                    (art.shade(st["w1"], 0.45 * k), [W(a, 0, 0), W(a, 0, -t), W(a, DOOR_H, -t), W(a, DOOR_H, 0)])]  # reveal
            layer, at = polys_layer(void)
            layer.set_alpha(BACK_VOID_ALPHA)
            s.blit(layer, at)
            col = art.shade(frame_material(st), 1.0 if side == "N" else 0.8)
            layer, at = polys_layer(door_frame_polys(W, a, b, col, 0.0, 0.07))
            layer.set_alpha(BACK_FRAME_ALPHA)
            s.blit(layer, at)

    def build_darkness(self, r):
        """Per-room darkness: a vignette with pools of light round lamps,
        fires, pumpkins and windows (moonlight)."""
        w, h = WIN_W, WIN_H
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = self.P(r.w / 2, r.d / 2, 60, r)
        d = np.sqrt(((xx - cx) / (w * 0.55)) ** 2 + ((yy - cy) / (h * 0.62)) ** 2)
        a = 55 + 145 * np.clip(d, 0, 1) ** 1.7
        lights = []
        for o in r.objs:
            if o.t.get("glow"):
                lights.append((self.P(o.x + o.gx / 2, o.y + o.gy / 2, o.t["h"] * 0.7, r), 230))
        for o in r.walls:
            if o.type == "window":
                lights.append((self.P(o.index + .5, 1.2, 0, r) if o.side == "N" else self.P(1.2, o.index + .5, 0, r), 170))
        for (lx, ly), rad in lights:
            dd = np.sqrt((xx - lx) ** 2 + ((yy - ly) * 1.6) ** 2) / rad
            a -= 75 * np.clip(1 - dd, 0, 1)
        s = pygame.Surface((w, h), pygame.SRCALPHA, 32)
        s.fill((4, 2, 10, 0))
        al = pygame.surfarray.pixels_alpha(s)
        al[:] = np.clip(a, 0, 235).astype(np.uint8).T
        del al
        return s

    @staticmethod
    def _make_player_light():
        rad = 260
        yy, xx = np.mgrid[0:rad * 2, 0:rad * 2].astype(np.float32)
        d = np.sqrt((xx - rad) ** 2 + ((yy - rad) * 1.5) ** 2) / rad
        s = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA, 32)
        s.fill((0, 0, 0, 0))
        al = pygame.surfarray.pixels_alpha(s)
        al[:] = (np.clip(1 - d, 0, 1) ** 1.3 * 120).astype(np.uint8).T
        del al
        return s

    def glow_sprite(self, colour, radius):
        key = (colour, radius)
        if key not in self.glow_cache:
            self.glow_cache[key] = art.glow(radius, colour, 0.35)
        return self.glow_cache[key]

    def text(self, font, s, colour, shadow=True):
        key = (id(font), s, colour, shadow)
        if key not in self.text_cache:
            img = font.render(s, True, colour)
            if shadow:
                out = pygame.Surface((img.get_width() + 2, img.get_height() + 2), pygame.SRCALPHA)
                out.blit(font.render(s, True, (0, 0, 0)), (2, 2))
                out.blit(img, (0, 0))
                img = out
            if len(self.text_cache) > 400:
                self.text_cache.clear()
            self.text_cache[key] = img
        return self.text_cache[key]

    def draw(self):
        if self.mode in ("title", "lobby"):
            self.draw_title()
            return
        r = self.room
        s = self.screen
        if r.id not in self.bg_cache:
            self.bg_cache[r.id] = self.build_background(r)
            self.dark_cache[r.id] = self.build_darkness(r)
        s.blit(self.bg_cache[r.id], (0, 0))
        fd = r.front_door()
        if fd is not None and self.door_t is not None:
            self.draw_front_door(fd)      # swinging (or standing) open on the moonlit night
        elif fd is not None and self.won:   # the front door stands open on the moonlit night
            Q = lambda u, z: self.P(u, 0, z)
            pygame.draw.polygon(s, (50, 70, 120), [Q(fd.index + .1, 0), Q(fd.index + 1.9, 0), Q(fd.index + 1.9, DOOR_H - 12), Q(fd.index + .1, DOOR_H - 12)])
        for o in r.objs:   # flat floor things first
            if o.t["kind"] == "flat" or o.type in ("stairs_down", "trapdoor"):
                self.blit_footprint("rug_lifted" if (o.t.get("lift") and o.lifted) else o.type, o, o.x, o.y)
        items = []
        for o in r.objs:
            if o.t["kind"] == "furniture" or o.type in ("stairs_up", "ladder_up"):
                ox, oy = o.x, o.y
                if o.slide_t > 0:
                    k = o.slide_t / SLIDE_TIME
                    ox, oy = o.x + o.dx * k, o.y + o.dy * k
                if o.t["kind"] == "furniture":
                    self.draw_floor_shadow(o, ox, oy)   # on the floor, under everything standing
                items.append(((ox, oy, ox + o.gx, oy + o.gy), ("obj", o, ox, oy)))
        key_here = self.key_state == "revealed" and self.key_place[0] == r.id
        if key_here:
            kx, ky = self.key_pos
            items.append(((kx - .2, ky - .2, kx + .2, ky + .2), ("key",)))
        for e in self.enemies:
            items.append((e.box(), ("enemy", e)))
        if self.out is None:   # (two players: once out, we only watch)
            items.append(((self.px - PLAYER_R, self.py - PLAYER_R, self.px + PLAYER_R, self.py + PLAYER_R), ("player",)))
        if self.coop is not None and self.coop.partner_here():
            p = self.coop.partner
            items.append(((p.x - PLAYER_R, p.y - PLAYER_R, p.x + PLAYER_R, p.y + PLAYER_R), ("partner",)))
        for _, what in depth_sort(items):
            self.draw_item(what)
        dark = self.dark_cache[r.id].copy()
        lx, ly = self.P(self.px, self.py, 70)
        lr = self.player_light.get_width() // 2
        if self.out is None:
            dark.blit(self.player_light, (lx - lr, ly - lr), special_flags=pygame.BLEND_RGBA_SUB)
        if key_here:   # the key catches the light: a small pool round it, so it shows even in a dark corner
            if "key_light" not in self.glow_cache:
                self.glow_cache["key_light"] = pygame.transform.smoothscale(self.player_light, (220, 220))
            kl = self.glow_cache["key_light"]
            kx, ky = self.P(*self.key_pos, 14)
            dark.blit(kl, (kx - 110, ky - 110), special_flags=pygame.BLEND_RGBA_SUB)
        if self.coop is not None and self.coop.partner_here():   # the other player carries a light too
            qx, qy = self.P(self.coop.partner.x, self.coop.partner.y, 70)
            dark.blit(self.player_light, (qx - lr, qy - lr), special_flags=pygame.BLEND_RGBA_SUB)
        s.blit(dark, (0, 0))
        if fd is not None and self.door_t is not None:
            self.draw_moonlight(fd)
        self.draw_exit_frames(r)
        t = self.time
        for o in r.objs:
            g = o.t.get("glow")
            if g:
                fl = 1.0 + 0.08 * math.sin(t * 9 + sum(map(ord, o.id)) % 7)
                gs = self.glow_sprite(g, int(70 * fl) if o.gx == 1 else 110)
                gx, gy = self.P(o.x + o.gx / 2, o.y + o.gy / 2, o.t["h"] * 0.75)
                s.blit(gs, (gx - gs.get_width() / 2, gy - gs.get_height() / 2), special_flags=pygame.BLEND_RGB_ADD)
        for e in self.enemies:
            if e.kind == "ghost":
                gs = self.glow_sprite((90, 110, 140), 70)
                gx, gy = self.P(e.x, e.y, e.z0 + 70 + 8 * math.sin(e.phase * 2))
                s.blit(gs, (gx - 70, gy - 70), special_flags=pygame.BLEND_RGB_ADD)
        if key_here:
            gs = self.glow_sprite((255, 220, 110), 52)
            kx, ky = self.P(*self.key_pos, 20)
            s.blit(gs, (kx - 52, ky - 52), special_flags=pygame.BLEND_RGB_ADD)
            tw = max(0.0, math.sin(self.time * 4.0))   # a twinkle on the key, to catch the eye
            if tw > 0.05:
                sx, sy = self.P(*self.key_pos, 34)
                sx, sy = round(sx + 7), round(sy - 2)
                n = int(5 + 9 * tw)
                c = (int(200 * tw), int(180 * tw), int(110 * tw))
                pygame.draw.line(s, c, (sx - n, sy), (sx + n, sy), 2)
                pygame.draw.line(s, c, (sx, sy - n), (sx, sy + n), 2)
        self.draw_popups()
        self.draw_hud()
        if self.mode == "watch" and self.coop is not None:
            self.draw_watching()
        if self.show_map:
            self.draw_map()
        if self.paused:
            self.banner("Paused", "Press P to carry on")
        if self.fade:
            phase, ft, _ = self.fade
            k = ft / FADE if phase == "out" else 1 - ft / FADE
            veil = pygame.Surface((WIN_W, WIN_H))
            veil.set_alpha(int(255 * max(0, min(1, k))))
            s.blit(veil, (0, 0))
        if self.mode == "end":
            self.draw_end()

    # ------------------------------------------------------------ exit door frames
    def ghost_frame(self, r, side):
        """The see-through door frame standing on an open front edge (S/E)."""
        key = (r.id, side)
        if key not in self.ghost_cache:
            rng = r.door_range(side)
            a, b = rng.start, rng.stop
            if side == "S":
                W = lambda u, z, nn: self.P(u, r.d + nn, z, r)
            else:
                W = lambda u, z, nn: self.P(r.w + nn, u, z, r)
            col = art.lerp(frame_material(r.style), (150, 170, 200), 0.25)   # a little cold: a ghost of a frame
            col = art.shade(col, 1.0 if side == "S" else 0.8)
            layer, at = polys_layer(door_frame_polys(W, a, b, col, -0.05, 0.05))
            self.ghost_cache[key] = (layer, at)
        return self.ghost_cache[key]

    def exit_centre(self, r, side):
        """The middle of an exit's doorway on the floor, in tiles."""
        rng = r.door_range(side)
        mid = (rng.start + rng.stop) / 2
        return {"N": (mid, 0.0), "W": (0.0, mid), "S": (mid, float(r.d)), "E": (float(r.w), mid)}[side]

    def ghost_fade(self, r, side, rect):
        """1.0, or less when the player, the other player or an enemy is
        behind the front-edge frame on screen and close to it, so the frame
        never hides them."""
        who = [(e.x, e.y) for e in self.enemies]
        if self.out is None:
            who.append((self.px, self.py))
        if self.coop is not None and self.coop.partner_here():
            who.append((self.coop.partner.x, self.coop.partner.y))
        f = 1.0
        for x, y in who:
            fx, fy = self.P(x, y, 0, r)
            if not rect.colliderect(pygame.Rect(fx - 42, fy - 200, 84, 210)):
                continue
            depth = (r.d - y) if side == "S" else (r.w - x)
            f = min(f, GHOST_FADE_MIN + (1 - GHOST_FADE_MIN) * max(0.0, min(1.0, depth / GHOST_FADE_D)))
        return f

    def exit_near(self, r, side):
        """0..1: how close the player is to this exit (1 = in the doorway)."""
        if self.out is not None:
            return 0.0
        cx, cy = self.exit_centre(r, side)
        return max(0.0, 1.0 - math.hypot(self.px - cx, self.py - cy) / EXIT_NEAR)

    def draw_exit_frames(self, r):
        """Over the lit room: the ghost frames on the open front edges, and a
        soft pulsing glow in any doorway the player is close to."""
        s = self.screen
        pulse = 0.5 + 0.5 * math.sin(self.time * 3.6)
        for side in ("N", "W", "S", "E"):
            if r.door_range(side) is None:
                continue
            near = self.exit_near(r, side)
            if side in ("S", "E"):
                layer, at = self.ghost_frame(r, side)
                rect = layer.get_rect(topleft=at)
                alpha = GHOST_FRAME_ALPHA * self.ghost_fade(r, side, rect) + 30 * near * pulse
                layer.set_alpha(int(max(0, min(255, alpha))))
                s.blit(layer, at)
            if near > 0:
                lvl = round(near * (0.55 + 0.45 * pulse) * 8) / 8   # quantised: a handful of cached sprites
                if lvl > 0:
                    cx, cy = self.exit_centre(r, side)
                    z = 4 if side in ("S", "E") else DOOR_H * 0.45
                    gs = self.glow_sprite(tuple(int(c * lvl) for c in (150, 128, 84)), 64)
                    gx, gy = self.P(cx, cy, z, r)
                    s.blit(gs, (gx - 64, gy - 64), special_flags=pygame.BLEND_RGB_ADD)

    # ------------------------------------------------------------ the open front door
    def _door_geom(self, fd):
        """(u0, seam, u1) along the north wall and (z0, z1) of the leaves."""
        h = T["front_door"]["h"]
        u0, us, u1 = (fd.index + 2 * f for f in DOOR_LEAF_X)
        z0, z1 = h * (1 - DOOR_LEAF_Y[1]), h * (1 - DOOR_LEAF_Y[0])
        return u0, us, u1, z0, z1

    def _plane_blit(self, img, top, dx, dy, hinge_left=True, k=1.0):
        """Blit flat art onto a vertical plane in the room: its top edge runs
        from `top` (screen) by (dx, dy) px, its height is the image's. The
        isometric view is a parallel projection, so this column-by-column
        shear is exact. hinge_left: image column 0 sits at `top`."""
        w, h = img.get_size()
        cols = max(1, int(round(abs(dx))))
        rise = int(math.ceil(abs(dy))) + 1
        src = pygame.surfarray.pixels3d(img)
        sa = pygame.surfarray.pixels_alpha(img)
        out = pygame.Surface((cols, h + rise), pygame.SRCALPHA, 32)
        out.fill((0, 0, 0, 0))
        dst = pygame.surfarray.pixels3d(out)
        da = pygame.surfarray.pixels_alpha(out)
        for i in range(cols):
            t = (i + 0.5) / cols
            if dx < 0:
                t = 1.0 - t                        # screen columns run back towards the hinge
            c = min(w - 1, int((t if hinge_left else 1 - t) * w))
            off = int(round(t * dy - min(0.0, dy)))
            dst[i, off:off + h] = src[c] * k
            da[i, off:off + h] = sa[c]
        del src, sa, dst, da
        x = top[0] + min(0.0, dx)
        y = top[1] + min(0.0, dy)
        self.screen.blit(out, (round(x), round(y)))

    def _night(self, w, h):
        """The view out of the front door: moonlit garden in the fog."""
        key = ("night", w, h)
        img = self.glow_cache.get(key)
        if img is not None:
            return img
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        v = yy / max(1, h - 1)
        sky = np.stack([26 + 34 * v, 36 + 44 * v, 74 + 42 * v], -1)
        mx, my, mr = w * 0.68, h * 0.22, max(4.0, w * 0.13)
        d = np.sqrt((xx - mx) ** 2 + (yy - my) ** 2)
        sky += (np.clip(1 - d / (mr * 4.5), 0, 1) ** 2 * 70)[..., None] * np.array([0.8, 0.9, 1.0])
        moon = d < mr
        sky[moon] = (226, 230, 214)
        rnd = random.Random(5)
        for _ in range(w * h // 260):                  # a few stars
            sx, sy = rnd.randrange(w), rnd.randrange(int(h * 0.45))
            if not moon[sy, sx]:
                sky[sy, sx] = (170, 176, 200)
        # bare trees and a garden wall in silhouette
        ground = h * 0.72
        sil = np.zeros((h, w), bool)
        for tx, th, tw in ((0.15, 0.62, 0.05), (0.88, 0.5, 0.045), (0.42, 0.32, 0.03)):
            cx = tx * w
            top = ground - th * h
            sil |= (np.abs(xx - cx) < tw * w) & (yy > top) & (yy < ground)
            for b in range(5):                         # branches
                by = top + (b + 0.5) / 5 * (ground - top) * 0.6
                ang = (1 if b % 2 else -1) * (0.55 + 0.1 * b)
                ln = th * h * 0.35 * (1 - b / 6)
                t = np.clip(((xx - cx) * math.sin(ang) - (yy - by) * -math.cos(ang)) / ln, 0, 1)
                px_, py_ = cx + t * ln * math.sin(ang), by - t * ln * math.cos(ang)
                sil |= ((xx - px_) ** 2 + (yy - py_) ** 2 < 1.2) & (t > 0) & (t < 1)
        sil |= yy > ground + np.sin(xx * 0.4) * 1.5
        sky[sil] = (10, 12, 20)
        # the path to the gate, catching the moon
        path = (yy > ground + 2) & (np.abs(xx - w * 0.5) < (yy - ground) * 0.9 + 3)
        sky[path] = (54, 60, 74)
        # low fog, thicker near the ground
        fog = np.clip((yy - h * 0.5) / (h * 0.5), 0, 1) ** 1.5
        wav = 0.5 + 0.5 * np.sin(xx * 0.21 + yy * 0.07) * np.sin(xx * 0.05 - yy * 0.11)
        f = (fog * (0.35 + 0.35 * wav))[..., None]
        sky = sky * (1 - f) + np.array([120, 132, 150]) * f
        img = pygame.Surface((w, h), pygame.SRCALPHA, 32)
        pygame.surfarray.blit_array(img, np.clip(sky, 0, 255).astype(np.uint8).transpose(1, 0, 2))
        img.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MAX)
        self.glow_cache[key] = img
        return img

    def _leaf(self, which, h):
        key = ("leaf", which, h)
        img = self.glow_cache.get(key)
        if img is None:
            base = self.art.base("front_door")
            bw, bh = base.get_size()
            a, b = (DOOR_LEAF_X[0], DOOR_LEAF_X[1]) if which == "left" else (DOOR_LEAF_X[1], DOOR_LEAF_X[2])
            rect = pygame.Rect(round(a * bw), round(DOOR_LEAF_Y[0] * bh), round((b - a) * bw), round((DOOR_LEAF_Y[1] - DOOR_LEAF_Y[0]) * bh))
            img = pygame.transform.smoothscale(base.subsurface(rect).copy(), (rect.w, h))
            self.glow_cache[key] = img
        return img

    def draw_front_door(self, fd):
        """The double front door, swinging inwards on its outer hinges."""
        u0, us, u1, z0, z1 = self._door_geom(fd)
        hpx = int(round(z1 - z0))
        span = u1 - u0
        self._plane_blit(self._night(max(2, int(round(span * HW))), hpx), self.P(u0, 0, z1), span * HW, span * HH)
        a = self.door_angle()
        ca, sa = math.cos(a), math.sin(a)
        for which, hinge, w, sgn in (("left", u0, us - u0, 1), ("right", u1, u1 - us, -1)):
            ex, ey = sgn * w * ca, w * sa                       # free edge, relative to the hinge (tiles)
            top = self.P(hinge, 0, z1)
            dx, dy = (ex - ey) * HW, (ex + ey) * HH
            k = 1.0 - 0.38 * sa if sgn > 0 else 1.0 - 0.22 * sa   # turning out of the light
            self._plane_blit(self._leaf(which, hpx), top, dx, dy, hinge_left=(sgn > 0), k=k)
            # the leaf's thickness along its free edge
            fx, fy = hinge + ex, ey
            pygame.draw.line(self.screen, (40, 24, 14), self.P(fx, fy, z0), self.P(fx, fy, z1), 3 if a > 0.2 else 1)

    def draw_moonlight(self, fd):
        """Pale moonlight through the opening, spilling across the floor."""
        k = self.door_angle() / DOOR_SWING
        if k <= 0.02:
            return
        u0, us, u1, z0, z1 = self._door_geom(fd)
        P = self.P
        glow = pygame.Surface((WIN_W, WIN_H))
        glow.fill((0, 0, 0))
        for i in reversed(range(5)):                   # widest and faintest first
            reach = 0.6 + i * 0.7
            c = 16 * k * (1 - i / 5) + 3 * k
            spread = 0.25 + i * 0.18
            near = min(reach, 0.68)                    # keep off the open leaves by the jambs
            poly = [P(u0 + .1, 0.02), P(u1 - .1, 0.02), P(u1 - .1, near), P(u1 + spread * 0.5, reach),
                    P(u0 - spread * 0.2, reach), P(u0 + .1, near)]
            pygame.draw.polygon(glow, (int(c), int(c * 1.1), int(c * 1.4)), poly)
        self.screen.blit(glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def blit_footprint(self, name, o, x, y):
        """Bottom of the sprite on the front corner of the footprint, centred
        on it (an item drawn smaller than its tile sits further back)."""
        img = self.art.furniture(name, o.facing)
        cx = (self.P(x, y + o.gy)[0] + self.P(x + o.gx, y)[0]) / 2
        bottom = self.P(x + o.gx, y + o.gy)[1]
        k = self.art.scale(name)
        if k < 1:
            bottom -= (1 - k) * (o.gx + o.gy) * HH / 2
        self.screen.blit(img, (round(cx - img.get_width() / 2), round(bottom - img.get_height())))

    def draw_floor_shadow(self, o, x, y):
        """A soft dark patch under a piece of furniture, so it stands on the floor."""
        key = ("fshadow", o.gx, o.gy)
        sh = self.glow_cache.get(key)
        if sh is None:
            w, h = (o.gx + o.gy) * HW, (o.gx + o.gy) * HH
            pad = 14
            big = pygame.Surface((w + 2 * pad, h + 2 * pad), pygame.SRCALPHA)
            big.fill((0, 0, 0, 0))
            pts = [(pad + o.gy * HW, pad), (pad + w, pad + o.gy * HH), (pad + o.gx * HW, pad + h), (pad, pad + o.gx * HH)]
            pygame.draw.polygon(big, (0, 0, 0, 120), pts)
            small = pygame.transform.smoothscale(big, (max(1, big.get_width() // 6), max(1, big.get_height() // 6)))
            sh = pygame.transform.smoothscale(small, big.get_size())
            self.glow_cache[key] = sh
        left = self.P(x, y + o.gy)[0] - 14
        top = self.P(x, y)[1] - 14
        self.screen.blit(sh, (round(left), round(top)))

    def draw_shadow(self, x, y, w=0.5):
        cx, cy = self.P(x, y)
        rw = max(4, int(w * TILE_W * 0.55))
        sh = pygame.Surface((rw * 2, rw), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 90), sh.get_rect())
        self.screen.blit(sh, (cx - rw, cy - rw / 2))

    def draw_item(self, what):
        s = self.screen
        kind = what[0]
        if kind == "obj":
            _, o, x, y = what
            self.blit_footprint(o.type, o, x, y)
        elif kind == "key":
            img = self.art.base("key")
            kx, ky = self.P(*self.key_pos)
            self.draw_shadow(*self.key_pos, 0.35)
            s.blit(img, (kx - img.get_width() / 2, ky - img.get_height() - 6 + 4 * math.sin(self.time * 3)))
        elif kind == "enemy":
            e = what[1]
            if self.draw_anim_enemy(e):
                return
            img = self.art.enemy(e.kind, e.left)
            z = e.z0 + (8 * math.sin(e.phase * 2) if e.floats else 0)
            bob = 0 if e.floats else abs(math.sin(e.phase * ENEMY_BOB_RATE)) * 3
            self.draw_shadow(e.x, e.y, e.r * 2)
            ex, ey = self.P(e.x, e.y, z + bob)
            if e.kind == "ghost":
                img = img.copy()
                img.set_alpha(int(170 + 50 * math.sin(e.phase * 3)))
            s.blit(img, (ex - img.get_width() / 2, ey - img.get_height() + 4))
        elif kind == "partner":
            self.draw_partner()
        elif kind == "player":
            if self.invuln > 0 and int(self.invuln * 10) % 2 == 0:
                return
            k = FACING_SPRITE[self.pose_facing()]
            img, feet = self.walk_frame()
            meta = self.chars[self.character]["meta"]
            ax, ay = meta["facings"][k]["anchor"]
            px, py = self.px, self.py
            if feet is not None:
                # Root motion: draw the figure where this frame was posed, so a
                # planted foot stays put between frames instead of creeping.
                n = meta["frames"]
                frac = self.walk_phase * n - int(self.walk_phase * n)
                back = frac * meta["cycle_tiles"] / n
                ddx, ddy = FACING_DIR_XY[self.facing]
                px, py = px - back * ddx, py - back * ddy
            gx, gy = self.P(px, py)
            x0, y0 = round(gx - ax), round(gy - ay)
            self.draw_player_shadow(gx, gy, x0, y0, feet, meta["facings"][k])
            s.blit(img, (x0, y0))

    def draw_watching(self):
        """Out of the game: say whose view this is."""
        s = self.screen
        im = self.text(self.f_sub, f"Watching {self.coop.partner_name}", (190, 230, 255))
        how = "You escaped" if self.out == "won" else f"The {self.killer} got you"
        sub = self.text(self.f_small, f"{how}. The game ends when {self.coop.partner_name} gets out or is caught.",
                        (200, 190, 170))
        w = max(im.get_width(), sub.get_width()) + 40
        panel = pygame.Surface((w, im.get_height() + sub.get_height() + 18), pygame.SRCALPHA)
        panel.fill((10, 6, 14, 190))
        pygame.draw.rect(panel, (90, 130, 170), panel.get_rect(), 2, border_radius=6)
        x0, y0 = (WIN_W - w) / 2, HUD_H + 12
        s.blit(panel, (x0, y0))
        s.blit(im, ((WIN_W - im.get_width()) / 2, y0 + 6))
        s.blit(sub, ((WIN_W - sub.get_width()) / 2, y0 + 10 + im.get_height()))

    def draw_anim_enemy(self, e):
        """The bat and the skeleton from their animation frames (False when
        there are none: the single painted sprite is used as before)."""
        fr = self.art.enemy_frame(e.kind, e.frame, e.left)
        if fr is None:
            return False
        img, ax, ay = fr
        s = self.screen
        self.draw_shadow(e.x, e.y, e.r * 2)
        if e.floats:
            c = (e.phase * BAT_FPS / 4) % 1.0          # 0 wings up .. 0.5 wings down
            z = e.z0 + 8 * math.sin(e.phase * 2) - BAT_BOB * math.cos(2 * math.pi * c)
            ex, ey = self.P(e.x, e.y, z)
            s.blit(img, (round(ex - ax), round(ey - 26 - ay)))   # body centre where the old sprite's was
        else:
            ex, ey = self.P(e.x, e.y, e.z0)
            jy = 0 if e.jolt <= 0 else (2 if e.jolt > SKEL_JOLT_S / 2 else 1)
            s.blit(img, (round(ex - ax), round(ey + 4 - ay + jy)))
        return True

    def draw_partner(self):
        """The other player, from their reported position, facing and walking."""
        p = self.coop.partner
        if p.invuln > 0 and int(p.invuln * 10) % 2 == 0:
            return
        ch = self.chars[p.char]
        meta = ch["meta"]
        k = FACING_SPRITE[p.facing]
        feet = None
        if p.moving:
            n = meta["frames"]
            i = int(p.walk_phase * n) % n
            img, feet = ch["walk"][k][i], meta["facings"][k]["feet"][i]
        else:
            img = ch["stand"][k]
        ax, ay = meta["facings"][k]["anchor"]
        gx, gy = self.P(p.x, p.y)
        x0, y0 = round(gx - ax), round(gy - ay)
        self.draw_player_shadow(gx, gy, x0, y0, feet, meta["facings"][k])
        self.screen.blit(img, (x0, y0))

    def draw_player_shadow(self, gx, gy, x0, y0, feet, fmeta):
        """Ground the figure: a soft pool where they stand, and a small dark
        contact shadow under each shoe that fades and shrinks as it lifts."""
        s = self.screen
        pool = art.soft_shadow(30, 12, 70)
        s.blit(pool, (gx - pool.get_width() / 2, gy - pool.get_height() / 2))
        spots = feet if feet is not None else fmeta["feet"][0]
        for leg in ("far", "near"):
            f = spots[leg]
            lift = f["lift"] if feet is not None else 0.0
            if feet is None:   # standing: use the rest positions (frame 0 is not at rest)
                f = fmeta.get("rest", {}).get(leg, f)
            k = max(0.0, 1.0 - lift / 9.0)
            if k <= 0.05:
                continue
            sh = art.soft_shadow(11 * (0.65 + 0.35 * k), 4.5 * (0.65 + 0.35 * k), 150 * k)
            fx, fy = x0 + f["x"], y0 + f["y"] + lift
            s.blit(sh, (fx - sh.get_width() / 2, fy - sh.get_height() / 2 - 1))

    def draw_popups(self):
        """Floating "+5" / "+50" / "+200" over the player's head, rising and fading."""
        for txt, x, y, age in self.popups:
            k = age / POPUP_TIME
            big = txt != f"+{PTS_ROOM}"
            img = self.text(self.f_sub if big else self.f_hud, txt, (255, 210, 80)).copy()
            img.set_alpha(int(255 * min(1.0, (1 - k) / 0.35)))
            px, py = self.P(x, y, 178 + 46 * k)
            self.screen.blit(img, (round(px - img.get_width() / 2), round(py - img.get_height())))

    # ------------------------------------------------------------ HUD
    def draw_hud(self):
        s = self.screen
        bar = pygame.Surface((WIN_W, HUD_H), pygame.SRCALPHA)
        bar.fill((10, 6, 14, 225))
        pygame.draw.line(bar, (150, 90, 30), (0, HUD_H - 2), (WIN_W, HUD_H - 2), 2)
        s.blit(bar, (0, 0))
        s.blit(self.text(self.f_hud, "Lives:", (255, 200, 120)), (18, 14))
        x = 18 + self.f_hud.size("Lives:")[0] + 22
        hearts = max(LIVES, self.max_lives)
        for i in range(hearts):
            self.heart(s, x + i * 32, 26, (230, 50, 60) if i < self.lives else (70, 50, 56))
        if self.coop is None:
            s.blit(self.text(self.f_hud, f"Score: {self.score:,}", (255, 200, 120)), (x + hearts * 32 + 30, 14))
        else:
            s.blit(self.text(self.f_hud, f"Score: {self.score:,}", (255, 200, 120)), (x + hearts * 32 + 24, 4))
            cp = self.coop
            p = cp.partner
            gone = cp.partner_out()
            if gone == "won":
                where = "has escaped!"
            elif gone == "dead":
                where = f"was caught by the {cp.partner_killer() or 'ghost'}"
            elif not p.seen:
                where = "is on the way"
            elif p.room == self.room.id:
                where = "is here" if self.out is not None else "is here with you"
            else:
                where = f"is in the {self.house.rooms[p.room].name}"
            s.blit(self.text(self.f_hud_small, f"{cp.partner_name} {where}", (190, 220, 200)),
                   (x + hearts * 32 + 24, 31))
        r = self.room
        name = self.text(self.f_hud, r.name, (255, 236, 190))
        fl = self.text(self.f_hud_small, M.FLOOR_NAMES[r.floor], (200, 170, 130))
        s.blit(name, ((WIN_W - name.get_width()) / 2, 4))
        s.blit(fl, ((WIN_W - fl.get_width()) / 2, 31))
        tm = self.text(self.f_hud, f"Time: {fmt_time(self.out_time if self.out else self.time)}", (255, 200, 120))
        s.blit(tm, (WIN_W - tm.get_width() - 18, 14))
        kx = WIN_W - tm.get_width() - 18 - 130
        s.blit(self.text(self.f_hud, "Key:", (255, 200, 120)), (kx, 14))
        if "hud_key" not in self.glow_cache:
            k = pygame.transform.smoothscale(self.art.base("key"), (30, 31))
            dim = k.copy()
            dim.fill((70, 60, 70, 255), special_flags=pygame.BLEND_RGBA_MIN)
            self.glow_cache["hud_key"] = (k, dim)
        k, dim = self.glow_cache["hud_key"]
        s.blit(k if self.key_state == "carried" else dim, (kx + 54, 11))
        hint = self.text(self.f_small, "Tab: map" if self.coop else "Tab: map   P: pause", (150, 130, 110), shadow=False)
        s.blit(hint, (kx - hint.get_width() - 36, 19))
        if self.msg and self.msg_t > 0:
            img = self.text(self.f_msg, self.msg, (255, 240, 210))
            a = min(1.0, self.msg_t / 0.4)
            w = img.get_width() + 40
            panel = pygame.Surface((w, 46), pygame.SRCALPHA)
            panel.fill((10, 6, 14, int(205 * a)))
            pygame.draw.rect(panel, (150, 90, 30, int(255 * a)), panel.get_rect(), 2)
            img = img.copy()
            img.set_alpha(int(255 * a))
            px = (WIN_W - w) / 2
            s.blit(panel, (px, WIN_H - 62))
            s.blit(img, (px + 20, WIN_H - 62 + (46 - img.get_height()) / 2))

    @staticmethod
    def heart(s, x, y, col):
        pygame.draw.circle(s, col, (x - 6, y - 4), 7)
        pygame.draw.circle(s, col, (x + 6, y - 4), 7)
        pygame.draw.polygon(s, col, [(x - 13, y - 1), (x + 13, y - 1), (x, y + 12)])

    def banner(self, title, sub):
        s = self.screen
        panel = pygame.Surface((640, 170), pygame.SRCALPHA)
        panel.fill((10, 6, 14, 225))
        pygame.draw.rect(panel, (230, 130, 40), panel.get_rect(), 3)
        s.blit(panel, ((WIN_W - 640) / 2, (WIN_H - 170) / 2))
        t = self.text(self.f_big, title, (255, 170, 60))
        s.blit(t, ((WIN_W - t.get_width()) / 2, WIN_H / 2 - 72))
        u = self.text(self.f_help, sub, (230, 214, 180))
        s.blit(u, ((WIN_W - u.get_width()) / 2, WIN_H / 2 + 22))

    def draw_map(self):
        s = self.screen
        veil = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        veil.fill((4, 2, 8, 220))
        s.blit(veil, (0, 0))
        t = self.text(self.f_big, "Map of the mansion", (255, 170, 60))
        s.blit(t, ((WIN_W - t.get_width()) / 2, 64))
        cw, ch, gap = 108, 50, 8
        panels = {"loft": (60, 200), "first": (680, 200), "ground": (60, 470), "basement": (680, 470)}
        for fl, (x0, y0) in panels.items():
            s.blit(self.text(self.f_map_b, M.FLOOR_NAMES[fl], (255, 210, 140)), (x0, y0 - 32))
            for r in (r for r in self.house.rooms.values() if r.floor == fl):
                mx, my = r.map
                rx, ry = x0 + mx * (cw + gap), y0 + my * (ch + gap)
                seen = r.id in self.visited
                here = r.id == self.room.id
                fill = (160, 86, 30) if here else ((72, 56, 64) if seen else (24, 20, 28))
                pygame.draw.rect(s, fill, (rx, ry, cw, ch), border_radius=4)
                pygame.draw.rect(s, (200, 150, 90) if seen else (56, 46, 56), (rx, ry, cw, ch), 2, border_radius=4)
                if self.coop is not None and self.coop.partner.seen and self.coop.partner.room == r.id:
                    pygame.draw.rect(s, (110, 220, 170), (rx - 3, ry - 3, cw + 6, ch + 6), 3, border_radius=6)
                    ini = self.text(self.f_map, self.coop.partner_name, (150, 255, 200))
                    s.blit(ini, (rx + 4, ry + ch - 16))
                    continue
                words = r.name.split()
                lines = [r.name] if self.f_map.size(r.name)[0] < cw - 8 else [" ".join(words[:-1]), words[-1]]
                for i, ln in enumerate(lines):
                    im = self.text(self.f_map, ln, (255, 240, 220), shadow=False)
                    yy = ry + (ch - 17 * len(lines)) / 2 + i * 17
                    s.blit(im, (rx + (cw - im.get_width()) / 2, yy))
                for o in r.objs:
                    if o.type in M.LINK_TYPES:
                        up = o.type in ("stairs_up", "ladder_up")
                        cx, cy = rx + cw - 11, ry + ch - 11
                        pts = [(cx - 6, cy + 4), (cx + 6, cy + 4), (cx, cy - 6)] if up else [(cx - 6, cy - 4), (cx + 6, cy - 4), (cx, cy + 6)]
                        pygame.draw.polygon(s, (255, 220, 120), pts)
                if r.front_door():
                    pygame.draw.rect(s, (255, 220, 120), (rx + cw / 2 - 12, ry - 5, 24, 7))
                for side, d in r.doors.items():
                    if d["to"] in self.visited and side == "E":
                        pygame.draw.rect(s, (200, 150, 90), (rx + cw, ry + ch / 2 - 5, gap, 10))
                    elif d["to"] in self.visited and side == "S":
                        pygame.draw.rect(s, (200, 150, 90), (rx + cw / 2 - 5, ry + ch, 10, gap))
        foot = self.text(self.f_help, f"Rooms explored: {len(self.visited)} of {len(self.house.rooms)}      "
                                      "Arrows: stairs, ladders and trapdoors      Tab / M: close", (230, 214, 180))
        s.blit(foot, ((WIN_W - foot.get_width()) / 2, WIN_H - 52))

    def draw_end(self):
        s = self.screen
        veil = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        veil.fill((4, 2, 8, int(min(1.0, self.end_t / 0.6) * 205)))
        s.blit(veil, (0, 0))
        n_rooms = len(self.house.rooms)
        label = "Score"
        if self.new_high:
            best = (self.f_sub, f"{label}: {self.score:,}      A new best score!", (255, 210, 120))
        else:
            best = (self.f_sub, f"{label}: {self.score:,}      Best: {self.best_score:,}", (255, 210, 120))
        friend = None                     # two players: how the other one got on
        if self.partner_end is not None:
            pname, how, pk = self.partner_end
            friend = (f"{pname} escaped too!" if self.won else f"{pname} escaped!") if how == "won" \
                else f"The {pk or 'ghost'} got {pname}." if how == "dead" else None
        if self.net_note:
            friend = self.net_note
        if friend and self.won:
            lines = [(self.f_big, "You escaped!", (255, 190, 80)),
                     (self.f_sub, f"Time taken: {fmt_time(self.time)}      {friend}", (255, 236, 190)),
                     (self.f_help, f"Lives left: {self.lives}      Rooms you explored: {len(self.visited)} of {n_rooms}", (230, 214, 180)),
                     (self.f_help, "A new best time!" if self.new_best else f"Best time: {fmt_time(self.best)}", (255, 210, 120)),
                     best]
        elif friend:
            lines = [(self.f_big, "Game over", (230, 70, 60)),
                     (self.f_sub, f"The {self.killer} got you.      {friend}", (255, 236, 190)),
                     (self.f_help, f"The key was {self.key_where()}." if self.key_state != "carried"
                      else "The key had been found.", (230, 214, 180)),
                     (self.f_help, f"Time: {fmt_time(self.time)}      Rooms you explored: {len(self.visited)} of {n_rooms}", (230, 214, 180)),
                     best]
        elif self.won:
            lines = [(self.f_big, "You escaped!", (255, 190, 80)),
                     (self.f_sub, f"Time taken: {fmt_time(self.time)}", (255, 236, 190)),
                     (self.f_help, f"Lives left: {self.lives}      Rooms explored: {len(self.visited)} of {n_rooms}", (230, 214, 180)),
                     (self.f_help, "A new best time!" if self.new_best else f"Best time: {fmt_time(self.best)}", (255, 210, 120)),
                     best]
        else:
            lines = [(self.f_big, "Game over", (230, 70, 60)),
                     (self.f_sub, f"The {self.killer} got you. The mansion keeps you for ever...", (255, 236, 190)),
                     (self.f_help, f"The key was {self.key_where()}.", (230, 214, 180)),
                     (self.f_help, f"Time: {fmt_time(self.time)}      Rooms explored: {len(self.visited)} of {n_rooms}", (230, 214, 180)),
                     best]
        y = 190
        for font, txt, col in lines:
            im = self.text(font, txt, col)
            s.blit(im, ((WIN_W - im.get_width()) / 2, y))
            y += im.get_height() + 26
        y += 4
        if self.entry_active:
            pw, ph = 560, 150
            panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
            panel.fill((10, 6, 14, 225))
            pygame.draw.rect(panel, (230, 130, 40), panel.get_rect(), 2, border_radius=6)
            s.blit(panel, ((WIN_W - pw) / 2, y))
            im = self.text(self.f_help, "You're in the Top 10! Type your name:", (255, 236, 190))
            s.blit(im, ((WIN_W - im.get_width()) / 2, y + 14))
            caret = "_" if int(self.end_t * 2.5) % 2 == 0 else " "
            im = self.text(self.f_big, (self.entry_name + caret) if (self.entry_name or caret != " ") else " ", (255, 190, 80))
            s.blit(im, ((WIN_W - im.get_width()) / 2, y + 40))
            hint = f"Up to {scores.NAME_MAX} letters or numbers"
            im = self.text(self.f_small, f"{hint}      Enter: send      Esc: skip", (200, 180, 150))
            s.blit(im, ((WIN_W - im.get_width()) / 2, y + ph - 28))
            return
        note = self.entry_status()
        if note:
            im = self.text(self.f_help, note, (190, 215, 255))
            s.blit(im, ((WIN_W - im.get_width()) / 2, y))
        if self.end_t > 1.0:
            im = self.text(self.f_help, "Press Enter to return to the title screen", (200, 180, 150))
            s.blit(im, ((WIN_W - im.get_width()) / 2, WIN_H - 120))

    # ------------------------------------------------------------ title
    def build_title_bg(self):
        """The painted house front (assets/art/title_backdrop.jpg), cover-fitted
        to the window, dimmed and vignetted so the text on top reads; the old
        procedural night scene if the painting is missing."""
        try:
            img = pygame.image.load(TITLE_BACKDROP).convert()
        except (pygame.error, FileNotFoundError):
            return self.build_title_bg_procedural()
        w, h = img.get_size()
        k = max(WIN_W / w, WIN_H / h)                       # cover, not contain
        if (round(w * k), round(h * k)) != (w, h):
            img = pygame.transform.smoothscale(img, (round(w * k), round(h * k)))
        w, h = img.get_size()
        out = pygame.Surface((WIN_W, WIN_H)).convert()
        out.blit(img, (-(w - WIN_W) // 2, -(h - WIN_H) // 2))
        a = pygame.surfarray.array3d(out).astype(np.float32)
        xx = (np.arange(WIN_W, dtype=np.float32)[:, None] - WIN_W / 2) / (WIN_W / 2)
        yy = (np.arange(WIN_H, dtype=np.float32)[None, :] - WIN_H * 0.45) / (WIN_H / 2)
        vig = 1.0 - 0.5 * np.clip(xx ** 2 * 0.8 + yy ** 2, 0, 1) ** 1.3
        y = np.arange(WIN_H, dtype=np.float32)[None, :]
        band = 1.0 - 0.3 * np.clip((175 - y) / 175, 0, 1) - 0.35 * np.clip((y - 540) / 140, 0, 1)   # under the title and the panels
        a *= (TITLE_DIM * vig * band)[:, :, None]
        pygame.surfarray.blit_array(out, np.clip(a, 0, 255).astype(np.uint8))
        return out

    def draw_title_life(self):
        """Cheap, quiet life on the painting: the moon's glow breathing slowly
        and candlelight flickering in a few of the windows."""
        s, t = self.screen, self.title_t
        lvl = round((0.55 + 0.45 * math.sin(t * 0.5)) * 6) / 6
        mx, my = TITLE_MOON
        gs = self.glow_sprite(tuple(int(c * lvl) for c in (70, 72, 84)), 120)
        s.blit(gs, (mx - 120, my - 120), special_flags=pygame.BLEND_RGB_ADD)
        for i, (wx, wy) in enumerate(TITLE_WINDOWS):
            f = math.sin(t * (2.3 + i * 0.37) + i * 1.7) * math.sin(t * (3.1 + i * 0.21) + i)
            f = round(max(0.0, f) * 4) / 4
            if f > 0:
                gs = self.glow_sprite(tuple(int(c * f) for c in (60, 38, 12)), 22)
                s.blit(gs, (wx - 22, wy - 22), special_flags=pygame.BLEND_RGB_ADD)

    def build_title_bg_procedural(self):
        s = pygame.Surface((WIN_W, WIN_H)).convert()
        top, bot = np.array((30, 16, 50)), np.array((120, 50, 30))
        k = np.linspace(0, 1, WIN_H)[:, None] ** 1.6
        pygame.surfarray.blit_array(s, np.repeat((top[None, :] * (1 - k) + bot[None, :] * k)[None], WIN_W, axis=0).astype(np.uint8))
        rnd = random.Random(7)
        for _ in range(140):
            c = rnd.randint(140, 255)
            s.set_at((rnd.randrange(WIN_W), rnd.randrange(int(WIN_H * 0.5))), (c, c, c))
        mx, my = 1060, 140
        halo = art.glow(200, (120, 110, 90), 1.0, squash=1.0)
        s.blit(halo, (mx - 200, my - 200 * 1.0), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(s, (250, 240, 214), (mx, my), 70)
        pygame.draw.circle(s, (226, 214, 188), (mx - 20, my - 14), 14)
        pygame.draw.circle(s, (230, 220, 194), (mx + 22, my + 18), 10)
        sil = (14, 8, 18)
        pts = [(0, WIN_H)] + [(x, 660 - 50 * math.sin(x / WIN_W * math.pi) + 8 * math.sin(x / 37)) for x in range(0, WIN_W + 1, 16)] + [(WIN_W, WIN_H)]
        pygame.draw.polygon(s, sil, pts)
        bx, by = 320, 640
        body = [(bx, by), (bx, by - 170), (bx + 60, by - 230), (bx + 120, by - 170), (bx + 120, by - 200), (bx + 200, by - 290),
                (bx + 280, by - 200), (bx + 280, by - 330), (bx + 300, by - 380), (bx + 320, by - 330), (bx + 320, by - 200),
                (bx + 400, by - 280), (bx + 480, by - 200), (bx + 480, by - 170), (bx + 560, by - 240), (bx + 640, by - 170), (bx + 640, by)]
        pygame.draw.polygon(s, sil, body)
        for cx in (bx + 90, bx + 450):
            pygame.draw.rect(s, sil, (cx, by - 270, 16, 60))
        rnd = random.Random(3)
        for row in range(3):
            for col in range(12):
                x, y = bx + 30 + col * 50, by - 150 + row * 50
                if rnd.random() < 0.35:
                    c = (255, 190, 80) if rnd.random() < 0.7 else (140, 220, 160)
                    pygame.draw.rect(s, c, (x, y, 18, 26))
                    pygame.draw.line(s, sil, (x + 9, y), (x + 9, y + 26), 2)
                    pygame.draw.line(s, sil, (x, y + 13), (x + 18, y + 13), 2)
        pygame.draw.rect(s, (255, 170, 60), (bx + 290, by - 340, 20, 26))
        for tx, h in ((120, 320), (1160, 280)):
            self._tree(s, tx, 690, h, sil)
        for gx in (200, 990, 1070):
            pygame.draw.rect(s, sil, (gx, 668, 34, 50), border_top_left_radius=16, border_top_right_radius=16)
        for px_ in (60, 1190):
            pygame.draw.ellipse(s, (230, 110, 30), (px_, 712, 54, 42))
            for ex in (14, 32):
                pygame.draw.polygon(s, (255, 230, 90), [(px_ + ex, 728), (px_ + ex + 8, 728), (px_ + ex + 4, 720)])
            pygame.draw.polygon(s, (255, 230, 90), [(px_ + 12, 738), (px_ + 42, 738), (px_ + 27, 746)])
        return s

    def _tree(self, s, x, y, h, col, depth=0, ang=-math.pi / 2, w=14):
        if depth > 5 or h < 12:
            return
        ex, ey = x + math.cos(ang) * h * 0.45, y + math.sin(ang) * h * 0.45
        pygame.draw.line(s, col, (x, y), (ex, ey), max(1, int(w)))
        for da in (-0.5, 0.45):
            self._tree(s, ex, ey, h * 0.72, col, depth + 1, ang + da + 0.1 * math.sin(depth * 3 + x), w * 0.65)

    def draw_title(self):
        s = self.screen
        if self.title_bg is None:
            self.title_bg = self.build_title_bg()
        s.blit(self.title_bg, (0, 0))
        t = self.title_t
        self.draw_title_life()
        for i in range(6):   # bats
            bx = (i * 230 + t * (60 + i * 9)) % (WIN_W + 200) - 100
            by = 120 + 50 * math.sin(t * 0.7 + i * 2) + i * 18
            fl = math.sin(t * 12 + i) * 10
            pygame.draw.polygon(s, (10, 6, 12), [(bx, by), (bx - 22, by - 6 - fl), (bx - 10, by + 4), (bx, by + 8), (bx + 10, by + 4), (bx + 22, by - 6 - fl)])
        for i in range(3):   # drifting fog
            fx = (t * (14 + i * 6) + i * 400) % (WIN_W + 600) - 600
            fog = pygame.Surface((600, 90), pygame.SRCALPHA)
            pygame.draw.ellipse(fog, (200, 190, 210, 16), fog.get_rect())
            s.blit(fog, (fx, 600 + i * 40))
        title = self.text(self.f_title, TITLE_NAME, (255, 150, 40))
        s.blit(title, ((WIN_W - title.get_width()) / 2, 28))
        sub = self.text(self.f_sub, "Find the key. Escape the house.", (230, 210, 180))
        s.blit(sub, ((WIN_W - sub.get_width()) / 2, 28 + title.get_height()))
        ch = self.text(self.f_help, "Choose Archie or Holly", (255, 220, 160))
        bw, bh, gap = 160, 262, 40
        x0 = TITLE_CHARS_X                 # left, clear of the tower and the front door
        s.blit(ch, (x0 + (bw * 2 + gap - ch.get_width()) / 2, 180))
        for i, cid in enumerate(CHAR_ORDER):
            sel = i == self.title_pick
            ch = self.chars[cid]
            k = "se" if i == 0 else "sw"
            # the chosen character walks on the spot
            img = ch["walk"][k][int(self.time * 9) % ch["meta"]["frames"]] if sel else ch["stand"][k]
            bx, by = x0 + i * (bw + gap), 240
            frame = pygame.Surface((bw, bh), pygame.SRCALPHA)
            frame.fill((20, 10, 24, 220 if sel else 150))
            pygame.draw.rect(frame, (255, 170, 60) if sel else (120, 80, 60), frame.get_rect(), 3 if sel else 1, border_radius=6)
            s.blit(frame, (bx, by))
            ax, ay = ch["meta"]["facings"][k]["anchor"]
            s.blit(img, (round(bx + bw / 2 - ax), round(by + 184 - ay)))
            nm = self.text(self.f_sub, CHARACTERS[cid], (255, 220, 160) if sel else (180, 150, 120))
            s.blit(nm, (bx + (bw - nm.get_width()) / 2, by + bh - 52))
            if sel:
                mk = self.text(self.f_small, "SELECTED", (255, 170, 60))
                s.blit(mk, (bx + (bw - mk.get_width()) / 2, by - 24))
        self.draw_title_options()
        if self.mode == "lobby" and self.lobby is not None:
            self.draw_lobby()
        elif self.show_top10 or int(self.title_t / TOP10_TIME) % 2 == 1:
            self.draw_top10()
        else:
            self.draw_controls()
        cp = self.text(self.f_small, COPYRIGHT, (190, 170, 150))
        s.blit(cp, ((WIN_W - cp.get_width()) / 2, WIN_H - 28))

    def draw_title_options(self):
        """Play alone / Host a game / Join a game, to the right of the characters."""
        s = self.screen
        x, y = TITLE_OPTS_XY             # top right, above the conservatory
        hd = self.text(self.f_small, "Up / Down: choose", (200, 170, 130))
        s.blit(hd, (x + (300 - hd.get_width()) / 2, y - 26))
        for i, label in enumerate(TITLE_OPTIONS):
            sel = i == self.title_opt
            box = pygame.Surface((300, 50), pygame.SRCALPHA)
            box.fill((20, 10, 24, 220 if sel else 140))
            pygame.draw.rect(box, (255, 170, 60) if sel else (120, 80, 60), box.get_rect(), 3 if sel else 1, border_radius=6)
            s.blit(box, (x, y + i * 62))
            im = self.text(self.f_sub, label, (255, 220, 160) if sel else (180, 150, 120))
            s.blit(im, (x + (300 - im.get_width()) / 2, y + i * 62 + (50 - im.get_height()) / 2))
        if self.title_opt == 2:
            im = self.text(self.f_small, "You'll play whoever the host doesn't", (200, 170, 130))
            s.blit(im, (x + (300 - im.get_width()) / 2, y + 3 * 62))

    def draw_lobby(self):
        """Host or join, in place of the controls panel."""
        s = self.screen
        lines = self.lobby.lines()
        pw = 960
        ph = 46 + 30 * (len(lines) - 1) + 14
        py = min(TITLE_PANEL_Y, WIN_H - 40 - ph)     # a long list grows upwards
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((8, 4, 12, 215))
        pygame.draw.rect(panel, (230, 130, 40, 230), panel.get_rect(), 2, border_radius=6)
        s.blit(panel, ((WIN_W - pw) / 2, py))
        hd = self.text(self.f_sub, lines[0], (255, 170, 60))
        s.blit(hd, ((WIN_W - hd.get_width()) / 2, py + 8))
        for i, ln in enumerate(lines[1:]):
            im = self.text(self.f_help, ln, (235, 220, 190))
            s.blit(im, ((WIN_W - im.get_width()) / 2, py + 50 + i * 30))

    def best_line(self):
        self.best_score = max(self.best_score, self.board.high_score())
        bits = []
        if self.best_score:
            bits.append(f"Best score: {self.best_score:,}")
        if self.best is not None:
            bits.append(f"Best time: {fmt_time(self.best)}")
        return "      ".join(bits)

    def draw_top10(self):
        """The shared Top 10 (two columns of five) in place of the controls panel."""
        s = self.screen
        pw, ph, py = 960, 196, TITLE_PANEL_Y
        px = (WIN_W - pw) / 2
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((8, 4, 12, 190))
        pygame.draw.rect(panel, (150, 90, 40, 220), panel.get_rect(), 1, border_radius=6)
        s.blit(panel, (px, py))
        hd = self.text(self.f_sub, "Top 10 Scores", (255, 170, 60))
        s.blit(hd, ((WIN_W - hd.get_width()) / 2, py + 4))
        rows = self.board.top(scores.TOP_N)
        if not rows:
            msg = {"loading": "Fetching the scores\u2026", "offline": "Scores unavailable offline"}.get(
                self.board.status, "No scores yet \u2013 be the first!")
            im = self.text(self.f_help, msg, (235, 220, 190))
            s.blit(im, ((WIN_W - im.get_width()) / 2, py + 88))
        for i, (name, score, country) in enumerate(rows):
            col_x = px + (60 if i < 5 else pw / 2 + 30)
            y = py + 44 + (i % 5) * 26
            colour = (255, 200, 90) if i == 0 else (235, 220, 190)
            num = self.text(self.f_help, f"{i + 1}.", colour)
            s.blit(num, (col_x + 34 - num.get_width(), y))
            flag = self.flags.get(country) if country else None
            if flag:
                s.blit(flag, (col_x + 46, y + 5))
            s.blit(self.text(self.f_help, name, colour), (col_x + 84, y))
            sc = self.text(self.f_help, f"{score:,}", colour)
            s.blit(sc, (col_x + 380 - sc.get_width(), y))
        bl = self.best_line()
        if bl:
            im = self.text(self.f_small, bl, (255, 200, 110))
            s.blit(im, ((WIN_W - im.get_width()) / 2, py + ph - 23))

    def draw_controls(self):
        s = self.screen
        lines = ["Left / Right (or 1 / 2): choose character      Up / Down: alone, host or join      Enter: start",
                 "Left / Right (A / D): turn      Up / Down (W / S): walk forwards / backwards",
                 "Space / E: search or lift      Walk into chairs, chests and crates to push them",
                 "Tab / M: map      P: pause      Esc: title screen"]
        bl = self.best_line()
        ph = 30 * len(lines) + (34 if bl else 0) + 14
        panel = pygame.Surface((960, ph), pygame.SRCALPHA)
        panel.fill((8, 4, 12, 170))
        pygame.draw.rect(panel, (120, 70, 40, 200), panel.get_rect(), 1, border_radius=6)
        s.blit(panel, ((WIN_W - 960) / 2, TITLE_PANEL_Y + 6))
        y = TITLE_PANEL_Y + 14
        for ln in lines:
            im = self.text(self.f_help, ln, (235, 220, 190))
            s.blit(im, ((WIN_W - im.get_width()) / 2, y))
            y += 30
        if bl:
            im = self.text(self.f_help, bl, (255, 200, 110))
            s.blit(im, ((WIN_W - im.get_width()) / 2, y + 2))


# ===================================================================== main
def parse_args(argv):
    p = argparse.ArgumentParser(description="Haunted Mansion (working title)")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--character", choices=CHAR_ORDER, default="archie")
    p.add_argument("--room", default=None, help="debug: start in this room")
    p.add_argument("--scene", choices=("title", "room", "map", "win", "lose"), default=None,
                   help="debug: arrange a scene, draw one frame and quit (use with --screenshot)")
    p.add_argument("--screenshot", default=None)
    p.add_argument("--no-enemies", action="store_true")
    p.add_argument("--pos", default=None, help="debug: player position x,y in the room")
    p.add_argument("--facing", default=None, choices=("N", "E", "S", "W"))
    p.add_argument("--sim", type=float, default=1.2, help="debug: seconds to simulate before the screenshot")
    p.add_argument("--offline", action="store_true", help="no online high scores (local file only)")
    p.add_argument("--hidden-key", action="store_true",
                   help="hide the key inside, behind or under things (the harder game; off for now)")
    p.add_argument("--port", type=int, default=net.GAME_PORT, help="TCP port for hosting a two-player game")
    p.add_argument("--scores-file", default=None, help="debug: high score file instead of ~/.haunted_mansion/scores.json")
    p.add_argument("--show-top10", action="store_true", help="debug: keep the Top 10 on the title screen")
    p.add_argument("--score", type=int, default=None, help="debug: score for the scene (e.g. win/lose name entry)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pygame.mixer.pre_init(22050, -16, 2, 512)
    except Exception:
        pass
    pygame.init()
    pygame.display.set_caption(TITLE_NAME)
    headless = args.scene is not None
    flags = 0 if headless else (pygame.SCALED | pygame.RESIZABLE)
    try:
        window = pygame.display.set_mode((WIN_W, WIN_H), flags)
    except pygame.error:
        window = pygame.display.set_mode((WIN_W, WIN_H))
    game = Game(window, seed=args.seed, character=args.character, enemies=not args.no_enemies,
                save=not headless, title=args.scene in (None, "title") and args.room is None,
                online=not (headless or args.offline), scores_file=args.scores_file)
    game.show_top10 = args.show_top10
    game.net_port = args.port
    if args.hidden_key:
        game.key_hidden = True
        game.new_game(game.seed)
    if args.room:
        game.mode = "play"
        game.enter_room(args.room, None)
        game.sounds.loop("ambience")
    if args.pos:
        game.px, game.py = (float(v) for v in args.pos.split(","))
        game.entry = (game.px, game.py, game.facing)
    if args.facing:
        game.facing = args.facing
    if headless:
        if args.scene == "title":
            game.title_t = 2.0
        else:
            game.mode = "play"
            for _ in range(int(args.sim * 60)):
                game.update(1 / 60, auto=(0, 0))
            if args.scene == "map":
                for rid in list(game.house.rooms)[::2]:
                    game.visited.add(rid)
                game.show_map = True
            if args.score is not None:
                game.score = args.score
            if args.scene == "win":
                game.key_state = "carried"
                game.time = 263.0
                if args.score is not None:
                    game.score -= PTS_ESCAPE
                game.win()
                game.end_t = 2.0
            elif args.scene == "lose":
                game.lives = 0
                game.lose(Enemy("ghost", 1, 1, random.Random(1)))
                game.end_t = 2.0
        game.draw()
        if args.screenshot:
            pygame.image.save(window, args.screenshot)
        pygame.quit()
        return 0
    clock = pygame.time.Clock()
    running = True
    while running:
        dt = min(0.05, clock.tick(60) / 1000.0)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.TEXTINPUT:
                game.on_text(ev.text)
            elif ev.type == pygame.KEYDOWN:
                if game.entry_active:
                    game.entry_key(ev.key)
                elif ev.key == pygame.K_ESCAPE:
                    if game.mode == "lobby":
                        game.close_lobby()
                    elif game.mode == "title":
                        running = False
                    elif game.show_map:
                        game.show_map = False
                    else:
                        game.to_title()
                else:
                    game.on_key(ev.key)
        game.update(dt, keys=pygame.key.get_pressed())
        game.draw()
        pygame.display.flip()
    game.end_coop()       # tell the other player we've gone
    game.close_lobby()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
