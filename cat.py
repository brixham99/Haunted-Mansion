"""The black cat.

It is nowhere to be seen until someone goes down into the Coal Cellar,
where it lies curled up asleep. It wakes, stretches, gives a little "mrrp"
and from then on follows whoever found it, a short way behind, from room
to room. When both players end up in the same room it goes over to the one
it wasn't following (once per meeting: not again until they have been
apart). It is harmless, can't be hurt, the baddies ignore it and it isn't
solid.

Its secret: the first time it follows someone into the Lumber Room it
arches its back and hisses at the mummy. After that it leads that player,
room by room along the shortest way through the doors, stairs and ladders,
to the room with the key and then to the key's spot, and sits there until
the key is picked up. If the player lags (doesn't come through the door
It never goes ahead: in each room on the route it goes to the way out it
wants, sits beside it inside the room facing the doorway and waits; only
when its player has gone through (that way or any other) does it follow,
just behind, and lead on from the room they are in.
Once the key is found it goes back to simply following.

One player: the game runs it. Two players: the host runs it and sends
state() with every update; the joiner draws what it is sent (eased).
"""
import math
import types

import mansion as M

CAT_ROOM = "coal_cellar"        # where it is found
MUMMY_ROOM = "lumber_room"      # where it hisses (and the mummy lives)
CAT_BED = (1.5, 3.5)            # curled up by the coal heap (the nearest free tile)
FOLLOW_D = 1.15                 # tiles behind the player it settles
FOLLOW_SPEED = 3.6              # tiles/s catching up (the player walks 3.0)
LEAD_SPEED = 2.4                # tiles/s leading: a little slower than the player
CROSS_S = 6.0                   # s at most to get to a door when following (then it slips through)
WAKE_S = (0.9, 1.0, 0.5)        # curled up, stretching, sitting: then off it goes
HISS_S = 2.2
WALK_FRAMES = 6                 # tools/cat_walk.py: one stride (both diagonal pairs) in six frames
WALK_FRAME_D = 0.5 / WALK_FRAMES   # tiles per frame: cat_walk.CYCLE_TILES a cycle, so planted paws don't skate
SIT_FLICK_S = 3.0               # sitting from behind: the tail flicks every so often

# eight screen directions -> (frame set, mirrored); 0 = screen right, clockwise
VIEWS = (("cat_e", False), ("cat_se", False), ("cat_s", False), ("cat_se", True),
         ("cat_e", True), ("cat_ne", True), ("cat_n", False), ("cat_ne", False))


def screen_dir(vx, vy):
    """World vector -> (screen x, screen y): world N is up-right on screen."""
    return vx - vy, (vx + vy) / 2.0


def view_for(vx, vy):
    sx, sy = screen_dir(vx, vy)
    k = int(round(math.atan2(sy, sx) / (math.pi / 4))) % 8
    return VIEWS[k]


def way(house, a, b):
    """How to get from room a to its neighbour b: (point to walk to in a,
    point it arrives at in b, world direction out through it) or None."""
    ra, rb = house.rooms[a], house.rooms[b]
    for side, d in ra.doors.items():
        if d["to"] == b and M.OPPOSITE[side] in rb.doors:
            out = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}[side]
            return ra.door_entry(side), rb.door_entry(M.OPPOSITE[side]), out
    for o in ra.objs:
        if o.type in M.LINK_TYPES and o.link == b:
            back = next((o2 for o2 in rb.objs if o2.type in M.LINK_TYPES and o2.link == a), None)
            if back is None:
                continue
            ex, ey = o.exit_pos()
            cx, cy = o.x + o.gx / 2.0, o.y + o.gy / 2.0
            return (ex, ey), back.exit_pos(), (cx - ex, cy - ey)
    return None


def key_spot(g):
    """Where to sit to show the key: the key itself if it lies in the open,
    else the reachable tile nearest the thing it is in, under or behind."""
    rid, how, what = g.key_place
    room = g.house.rooms[rid]
    if g.key_state == "revealed" and g.key_pos:
        return rid, tuple(g.key_pos), None
    if how == "open":
        return rid, (what[0] + 0.5, what[1] + 0.5), None
    o = g.house.find_obj(room, what)
    reach = g.house.room_reach(room)
    if o.side == "N":
        cx, cy = o.index + o.gx / 2.0, 0.0
    elif o.side == "W":
        cx, cy = 0.0, o.index + o.gy / 2.0
    else:
        cx, cy = o.x + o.gx / 2.0, o.y + o.gy / 2.0
    cells = sorted(reach, key=lambda c: (c[0] + 0.5 - cx) ** 2 + (c[1] + 0.5 - cy) ** 2)
    c = cells[0] if cells else (int(cx), int(cy))
    return rid, (c[0] + 0.5, c[1] + 0.5), (cx, cy)


class Cat:
    def __init__(self, house):
        r = house.rooms[CAT_ROOM]
        reach = house.room_reach(r)
        free = [c for c in r.free_floor() if c in reach] or sorted(reach)
        c = min(free, key=lambda c: (c[0] + 0.5 - CAT_BED[0]) ** 2 + (c[1] + 0.5 - CAT_BED[1]) ** 2)
        self.room = CAT_ROOM
        self.x, self.y = c[0] + 0.5, c[1] + 0.5
        self.tx, self.ty = self.x, self.y      # (the joiner: where the host says it is)
        self.state = "asleep"   # asleep | wake | follow | hiss | lead | wait | atkey
        self.follows = None     # "host" | "client"
        self.hissed = False
        self.met = False        # the players are together (switched for this meeting)
        self.set, self.left, self.frame = "cat_poses", False, 2      # curled up
        self.look = (1.0, 0.0)
        self.t = 0.0            # time in this state
        self.walk_d = 0.0
        self.path = []
        self.path_goal = None
        self.path_t = 0.0
        self.cross_t = 0.0
        self.heard = "asleep"   # the last state sounds were played for (both sides)
        self.mummy_xy = None

    # ------------------------------------------------------------ who is where
    @staticmethod
    def players(g):
        out = []
        me = g.my_role()
        if g.room is not None:
            out.append(types.SimpleNamespace(role=me, room=g.room.id, x=g.px, y=g.py,
                                             active=g.out is None and g.mode == "play"))
        cp = g.coop
        if cp is not None:
            p = cp.partner
            out.append(types.SimpleNamespace(role="client" if me == "host" else "host", room=p.room, x=p.tx, y=p.ty,
                                             active=p.seen and cp.partner_out() is None))
        return out

    def visible_in(self, rid):
        return self.room == rid

    # ------------------------------------------------------------ the host runs it
    def update(self, g, dt):
        ps = [p for p in self.players(g) if p.active]
        self.t += dt
        together = len(ps) == 2 and ps[0].room == ps[1].room
        if self.state == "asleep":
            self.met = together
            finder = next((p for p in ps if p.room == CAT_ROOM), None)
            if finder is not None:
                self.follows = finder.role
                self.set_state("wake")
                self.look = (finder.x - self.x, finder.y - self.y)
            self.pose()
            return
        if together and not self.met and self.state != "wake":
            other = next((p for p in ps if p.role != self.follows), None)
            if other is not None:
                self.follows = other.role
                self.path = []
        self.met = together
        tgt = next((p for p in ps if p.role == self.follows), None)
        if tgt is None and ps:                 # whoever we followed is out of the house
            tgt = ps[0]
            self.follows = tgt.role
        if self.state == "wake":
            if self.t >= sum(WAKE_S):
                self.set_state("follow")
            self.pose()
            return
        if tgt is None:
            self.sit_toward(self.look)
            return
        if self.state == "hiss":
            if self.mummy_xy:
                self.look = (self.mummy_xy[0] - self.x, self.mummy_xy[1] - self.y)
            if self.t >= HISS_S:
                self.set_state("lead" if g.key_state != "carried" else "follow")
            self.pose()
            return
        if not self.hissed and self.room == MUMMY_ROOM and tgt.room == MUMMY_ROOM and self.t > 0.3 \
                and self.state in ("follow", "lead", "wait"):
            m = self.find_mummy(g)
            self.mummy_xy = (m.x, m.y) if m is not None else (self.x + 1.0, self.y + 1.0)
            self.hissed = True
            self.set_state("hiss")
            self.look = (self.mummy_xy[0] - self.x, self.mummy_xy[1] - self.y)
            self.pose()
            return
        if self.state in ("lead", "wait", "atkey"):
            if g.key_state == "carried":
                self.set_state("follow")
            else:
                self.lead(g, tgt, dt)
                return
        self.follow(g, tgt, dt)

    def set_state(self, s):
        if s != self.state:
            self.state = s
            self.t = 0.0

    def find_mummy(self, g):
        ens = g.enemies if g.room is not None and g.room.id == MUMMY_ROOM else \
            (g.coop.other_enemies if g.coop is not None and g.coop.other_enemies else [])
        return next((e for e in ens if e.kind == "mummy"), None)

    # ------------------------------------------------------------ following
    def follow(self, g, tgt, dt):
        if self.state not in ("follow",):
            self.set_state("follow")
        if tgt.room == self.room:
            self.cross_t = 0.0
            d = math.hypot(tgt.x - self.x, tgt.y - self.y)
            if d > FOLLOW_D + 0.25:
                self.walk_to(g, tgt.x, tgt.y, FOLLOW_SPEED if d > 2.0 else LEAD_SPEED, dt, stop=FOLLOW_D)
            else:
                self.sit_toward((tgt.x - self.x, tgt.y - self.y))
            return
        self.go_toward_room(g, tgt.room, FOLLOW_SPEED, dt)

    def go_toward_room(self, g, rid, speed, dt):
        """Walk to the way out towards room rid and slip through it."""
        nxt = g.house.route(self.room, rid)
        if len(nxt) < 2:
            return
        w = way(g.house, self.room, nxt[1])
        if w is None:
            return
        self.cross_t += dt
        (hx, hy), arrive, _out = w
        if self.walk_to(g, hx, hy, speed, dt) or self.cross_t > CROSS_S:
            self.cross(nxt[1], arrive)

    def cross(self, rid, arrive):
        self.room = rid
        self.x, self.y = arrive
        self.path = []
        self.cross_t = 0.0
        self.t = 0.0 if self.state != "follow" else self.t
        self.came_t = 0.0

    # ------------------------------------------------------------ leading
    def lead(self, g, tgt, dt):
        """Show the way, one room at a time, never going ahead: in each room
        on the route it goes to the way out it wants, sits beside it inside
        the room facing the doorway, and waits. Only once its player has
        gone through (that way, or any other) does it follow, just behind,
        and in the new room it heads for the next way out. In the key's room
        it goes to the key's spot and sits."""
        key_room, spot, obj = key_spot(g)
        if tgt.room != self.room:                     # they've gone through: after them
            self.set_state("lead")
            self.go_toward_room(g, tgt.room, FOLLOW_SPEED, dt)
            return
        self.cross_t = 0.0
        if self.room == key_room:
            if self.walk_to(g, spot[0], spot[1], LEAD_SPEED, dt, stop=0.05):
                self.set_state("atkey")
                look = (obj[0] - self.x, obj[1] - self.y) if obj else (tgt.x - self.x, tgt.y - self.y)
                self.sit_toward(look, state="atkey")
            else:
                self.set_state("lead")
            return
        r = g.house.route(self.room, key_room)
        w = way(g.house, self.room, r[1])
        if w is None:
            self.sit_toward(self.look)
            return
        (hx, hy), _arrive, out = w
        sx, sy = self.beside(g, hx, hy, out)
        if self.walk_to(g, sx, sy, LEAD_SPEED, dt, stop=0.06):
            self.set_state("wait")                    # sitting by the way out, waiting for them
            self.sit_toward(out, state="wait")
        else:
            self.set_state("lead")

    def exit_seat(self, g):
        """Leading: (room, seat point, way out direction, next room) where it waits now, or None."""
        key_room = key_spot(g)[0]
        if self.room == key_room:
            return None
        r = g.house.route(self.room, key_room)
        w = way(g.house, self.room, r[1])
        if w is None:
            return None
        (hx, hy), _a, out = w
        return self.room, self.beside(g, hx, hy, out), out, r[1]

    def beside(self, g, hx, hy, out):
        """A seat just inside the room next to the way out (hx, hy): half a
        tile further in and a tile to one side, so the doorway stays clear;
        the doorway point itself if neither side is free floor."""
        r = g.house.rooms[self.room]
        ox, oy = out
        n = math.hypot(ox, oy) or 1.0
        ox, oy = ox / n, oy / n
        solid = r.solid_cells()
        for side in (1.0, -1.0):
            px, py = -oy * side, ox * side
            x, y = hx - ox * 0.5 + px * 1.0, hy - oy * 0.5 + py * 1.0
            c = (int(x), int(y))
            if 0.3 <= x <= r.w - 0.3 and 0.3 <= y <= r.d - 0.3 and r.inside(c) and c not in solid:
                return x, y
        return hx - ox * 0.4, hy - oy * 0.4

    # ------------------------------------------------------------ moving and posing
    def walk_to(self, g, gx, gy, speed, dt, stop=0.08):
        """One step towards (gx, gy) round the furniture; True when there."""
        r = g.house.rooms[self.room]
        d = math.hypot(gx - self.x, gy - self.y)
        if d <= stop:
            return True
        goal = (int(gx), int(gy))
        self.path_t -= dt
        if self.path_goal != goal or self.path_t <= 0:
            p = r.path((int(self.x), int(self.y)), goal, r.solid_cells())
            self.path = (p or [])[1:]
            self.path_goal = goal
            self.path_t = 0.5
        if self.path:
            wx, wy = self.path[0][0] + 0.5, self.path[0][1] + 0.5
            if len(self.path) == 1:
                wx, wy = gx, gy
        else:
            wx, wy = gx, gy
        vx, vy = wx - self.x, wy - self.y
        n = math.hypot(vx, vy)
        step = speed * dt
        if n < 1e-6:
            if self.path:
                self.path.pop(0)
            return d <= stop + 0.02
        if n <= step:
            self.x, self.y = wx, wy
            if self.path:
                self.path.pop(0)
        else:
            self.x += vx / n * step
            self.y += vy / n * step
            if not self.path and stop > 0.1 and math.hypot(gx - self.x, gy - self.y) < stop:
                pass
        self.walk_d += min(step, n)
        self.set, self.left = view_for(vx, vy)
        self.frame = int(self.walk_d / WALK_FRAME_D) % WALK_FRAMES
        self.look = (vx, vy)
        return math.hypot(gx - self.x, gy - self.y) <= stop

    def sit_toward(self, look, state=None):
        if look and math.hypot(*look) > 1e-6:
            self.look = look
        sx, sy = screen_dir(*self.look)
        self.left = sx < 0
        if sy < 0:
            self.set = "cat_poses_back"
            self.frame = 1 if (self.t % SIT_FLICK_S) > SIT_FLICK_S - 0.5 else 0
        else:
            self.set, self.frame = "cat_poses", 0

    def pose(self):
        """The poses of the still states: asleep, waking, hissing."""
        sx, sy = screen_dir(*self.look)
        self.left = sx < 0
        if self.state == "asleep":
            self.set, self.frame = "cat_poses", 2
        elif self.state == "wake":
            a, b, _c = WAKE_S
            self.set, self.frame = "cat_poses", (2 if self.t < a else (3 if self.t < a + b else 0))
        elif self.state == "hiss":
            if sy < 0:
                self.set, self.frame = "cat_poses_back", 2 + int(self.t * 5) % 2
            else:
                self.set, self.frame = "cat_poses", 1

    # ------------------------------------------------------------ the network
    def state_msg(self):
        return [self.room, round(self.x, 3), round(self.y, 3), self.state, self.set, self.frame,
                bool(self.left), self.follows, bool(self.hissed)]

    def apply(self, m):
        """The joiner: what the host says."""
        room, x, y, state, set_, frame, left, follows, hissed = m
        jump = room != self.room or math.hypot(x - self.x, y - self.y) > 2.0
        self.room, self.tx, self.ty = room, float(x), float(y)
        if jump:
            self.x, self.y = self.tx, self.ty
        if state != self.state:
            self.state, self.t = state, 0.0
        self.set, self.frame, self.left = set_, int(frame), bool(left)
        self.follows, self.hissed = follows, bool(hissed)

    def ease(self, dt):
        k = min(1.0, dt * 12.0)
        self.x += (self.tx - self.x) * k
        self.y += (self.ty - self.y) * k
        self.t += dt

    # ------------------------------------------------------------ sounds (both sides)
    def sounds(self, g):
        if self.state == self.heard:
            return
        prev, self.heard = self.heard, self.state
        if g.room is None or g.room.id != self.room or g.mode not in ("play", "watch"):
            return
        d = math.hypot(g.px - self.x, g.py - self.y)
        vol = max(0.25, 1.0 - d / 10.0)
        if self.state == "hiss":
            g.sounds.play("cat_hiss", vol)
        elif self.state == "wake" and prev == "asleep":
            g.sounds.play("cat_mew", vol)
