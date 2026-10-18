"""Two players in one house over the network (see net.py for the wire).

The host owns the house: the seed (so both games build the same mansion and
hide the key in the same place), the key, furniture, enemies (in every room
a player is in), when the joiner is hurt, caught or escapes, and the end of
the game.
Each game moves its own player and sends its position 20 times a second;
the joining game asks the host before pushing, lifting, searching, picking
up the key or opening the front door, and the host checks each request.

Rules (documented in the README):
- Each player has their own COOP_LIVES hearts and their own score, by the
  single-player rules: their own walking seconds, 5 for each room THEY
  discover, 50 for whoever picks up the key, 200 for each player who escapes.
- The key is the team's: once either player has it, the front door is
  unlocked for both, but each player has to walk out through it themselves.
- A player who is out (caught for the last time, or escaped) watches the
  other one ("Watching Holly") and can't touch anything. The game ends when
  both are out; then each game shows its own end screen and Top 10 name entry.
- The host decides when the joiner is hurt, caught or escapes; each game
  keeps its own score.
- If the other game goes away, a player still in the house carries on alone
  (the joining game takes over its own copy of the house); a player who was
  watching goes to their end screen.
"""

import math
import random
import sys
import types

import mansion as M
import net
from objects import nice

COOP_LIVES = 5                 # each player's hearts: the same as one-player (game.LIVES)
HELLO_TIMEOUT_S = 5.0


class Partner:
    """The other player as this game sees them (smoothed for drawing)."""

    def __init__(self, char):
        self.char = char
        self.seen = False
        self.room = None
        self.tx = self.ty = 0.0      # latest reported position
        self.x = self.y = 0.0        # drawn position (eased towards tx, ty)
        self.facing = "N"
        self.moving = False
        self.fade = False
        self.walk_phase = 0.2
        self.invuln = 0.0
        self.grace = 0.0
        self.entry = (0.0, 0.0, "N")
        self.out = None              # what the other game says: None, "won" or "dead"
        self.killer = None

    def update(self, p, cycle_tiles):
        room = p.get("room")
        jump = room != self.room or not self.seen or math.hypot(p["x"] - self.tx, p["y"] - self.ty) > 2.0
        self.tx, self.ty = float(p["x"]), float(p["y"])
        self.facing = p.get("f", self.facing) if p.get("f") in ("N", "E", "S", "W") else self.facing
        self.moving = bool(p.get("m"))
        self.fade = bool(p.get("fade"))
        self.out = p.get("out") if p.get("out") in ("won", "dead") else None
        self.killer = p.get("k")
        if jump:
            self.x, self.y = self.tx, self.ty
        self.room = room
        self.seen = True

    def animate(self, dt, cycle_tiles):
        k = min(1.0, dt * 14.0)
        ox, oy = self.x, self.y
        self.x += (self.tx - self.x) * k
        self.y += (self.ty - self.y) * k
        d = math.hypot(self.x - ox, self.y - oy)
        if self.moving:
            self.walk_phase = (self.walk_phase + d / cycle_tiles) % 1.0
        else:
            self.walk_phase = 0.2
        self.invuln = max(0.0, self.invuln - dt)
        self.grace = max(0.0, self.grace - dt)


class Coop:
    def __init__(self, game, link, role, partner_char):
        self.g = game
        self.G = sys.modules[type(game).__module__]
        self.link = link
        self.role = role
        self.host = role == "host"
        self.client = not self.host
        self.partner = Partner(partner_char)
        self.partner_name = self.G.CHARACTERS[partner_char]
        self.other_enemies = None      # host: enemies in the partner's room when it isn't ours
        self.p_out = None              # host: the joiner's fate as the host decided it
        self.p_killer = None
        self.p_lives = COOP_LIVES      # host: the joiner's hearts
        self.pickup_cd = 0.0
        self.ended = False
        self.closed_reason = None
        self.cycle = game.chars[partner_char]["meta"]["cycle_tiles"]

    # ------------------------------------------------------------- helpers
    def send(self, t, **data):
        data["t"] = t
        self.link.send(data)

    def partner_out(self):
        """None while the other player is still in the house, else "won" / "dead"."""
        return self.p_out if self.host else self.partner.out

    def partner_killer(self):
        return self.p_killer if self.host else self.partner.killer

    def partner_here(self):
        p = self.partner
        return p.seen and p.room == self.g.room.id and not p.fade and self.partner_out() is None

    def room_objs(self, r):
        return {o.id: o for o in r.objs}

    def near(self, r, obj, reach=1.6):
        p = self.partner
        cx, cy = obj.x + obj.gx / 2.0, obj.y + obj.gy / 2.0
        return p.room == r.id and abs(p.tx - cx) <= obj.gx / 2.0 + reach and abs(p.ty - cy) <= obj.gy / 2.0 + reach

    # ------------------------------------------------------------- per frame
    def tick(self, dt):
        g = self.g
        for msg in self.link.poll():
            try:
                self.handle(msg)
            except (KeyError, TypeError, ValueError) as exc:   # a bad message never stops the game
                print("coop: ignored message", msg.get("t"), exc)
            if g.coop is not self:
                return
        if self.link.closed:
            self.lost(self.link.reason)
            return
        self.partner.animate(dt, self.cycle)
        if g.mode not in ("play", "watch"):
            return
        self.pickup_cd = max(0.0, self.pickup_cd - dt)
        if self.host:
            p = self.partner
            if p.seen and p.room != g.room.id and self.other_enemies and self.p_out is None:
                r = g.house.rooms[p.room]
                g.run_enemies(self.other_enemies, r, [self.partner_target()], p.grace, dt, audible=False)
        else:
            for e in g.enemies:
                k = min(1.0, dt * 12.0)
                e.x += (getattr(e, "tx", e.x) - e.x) * k
                e.y += (getattr(e, "ty", e.y) - e.y) * k
                e.phase += dt
        if self.link.state_due():
            self.send_state()

    def my_pose(self):
        g = self.g
        return {"room": g.room.id, "x": round(g.px, 3), "y": round(g.py, 3), "f": g.facing,
                "m": bool(g.moving) and g.out is None, "fade": bool(g.fade), "out": g.out, "k": g.killer if g.out == "dead" else None,
                "door": g.door_t is not None}

    def send_state(self):
        g = self.g
        if self.client:
            self.send("s", p=self.my_pose())
            return
        p = self.partner
        msg = {"p": self.my_pose(), "time": round(g.time, 2), "key": [g.key_state, g.key_pos]}
        # the room the joiner is looking at: their own, or ours while they watch us
        rid = p.room if self.p_out is None else g.room.id
        if p.seen and rid in g.house.rooms:
            r = g.house.rooms[rid]
            ens = g.enemies if rid == g.room.id else (self.other_enemies or [])
            msg["room"] = r.id
            msg["en"] = [[e.kind, round(e.x, 3), round(e.y, 3), bool(e.left), bool(e.chasing)] for e in ens]
            msg["ob"] = [[o.id, o.x, o.y, bool(o.lifted)] for o in r.objs if o.t.get("push") or o.t.get("lift")]
        self.send("s", **msg)

    # ------------------------------------------------------------- messages
    def handle(self, m):
        t = m.get("t")
        if t == "bye":
            self.lost("The other player left the game")
        elif t == "s":
            self.on_state(m)
        elif self.host:
            self.host_request(t, m)
        else:
            self.client_event(t, m)

    def on_state(self, m):
        g = self.g
        p = self.partner
        pose = m.get("p") or {}
        if pose.get("room") not in g.house.rooms:
            return
        old_room = p.room if p.seen else None
        p.update(pose, self.cycle)
        if pose.get("door") and g.door_t is None:
            g.open_front_door()               # the other game saw it open: so is ours (swinging if we're in the hall)
        if self.host:
            if p.room != old_room:
                self.partner_entered(p.room, old_room)
            return
        # ---- client: the host's world (the clock and the key; scores and hearts are our own)
        if g.out is None:
            g.time = float(m.get("time", g.time))
        ks, kp = m.get("key", [g.key_state, g.key_pos])
        g.key_state, g.key_pos = ks, (tuple(kp) if kp else None)
        if g.mode == "watch" and p.room != g.room.id:
            g.watch_room(p.room)
        if m.get("room") == g.room.id and not g.fade:
            self.apply_room(m.get("en", []), m.get("ob", []))

    def apply_room(self, ens, obs):
        g = self.g
        G = self.G
        kinds = [e[0] for e in ens]
        if [e.kind for e in g.enemies] != kinds:
            rng = random.Random(len(kinds))
            g.enemies = [G.Enemy(k, x, y, rng) for k, x, y, _l, _c in ens]
        for e, (k, x, y, left, chasing) in zip(g.enemies, ens):
            e.tx, e.ty, e.left = x, y, left
            if abs(e.x - x) + abs(e.y - y) > 2.0:
                e.x, e.y = x, y
            if chasing and not e.chasing:
                g.sounds.play(e.kind, 0.8)
            e.chasing = chasing
        objs = self.room_objs(g.room)
        for oid, x, y, lifted in obs:
            o = objs.get(oid)
            if o is None:
                continue
            if (o.x, o.y) != (x, y):
                d = (x - o.x, y - o.y)
                if abs(d[0]) + abs(d[1]) == 1:
                    o.dx, o.dy = -d[0], -d[1]
                    o.slide_t = G.SLIDE_TIME
                    g.sounds.play("push")
                o.x, o.y = x, y
            o.lifted = lifted

    # ---- host side: what the joining player asks for
    def partner_target(self):
        p = self.partner
        return types.SimpleNamespace(x=p.tx, y=p.ty, invuln=p.invuln, hit=self.partner_hurt)

    def partner_entered(self, rid, old):
        g = self.g
        p = self.partner
        r = g.house.rooms[rid]
        p.entry = (p.tx, p.ty, p.facing)
        p.grace = self.G.ENTRY_GRACE
        if rid == g.room.id:
            self.other_enemies = None          # we share our room's enemies
        else:
            r.reset_pushables()                # rooms tidy themselves when someone comes in
            for o in r.objs:
                o.slide_t = 0.0
            self.other_enemies = g.make_enemies(r, p.tx, p.ty)

    def partner_hurt(self, e):
        g = self.g
        p = self.partner
        if self.p_out is not None:
            return
        self.p_lives -= 1
        p.invuln = self.G.INVULN
        g.sounds.play("hurt", 0.4)
        if self.p_lives <= 0:
            self.p_out, self.p_killer = "dead", e.kind
            self.other_enemies = None
            self.send("dead", kind=e.kind)
            if g.out is None:
                g.say(f"The {e.kind} caught {self.partner_name}! You're on your own now.")
            self.check_end()
            return
        n = self.p_lives
        g.say(f"The {e.kind} got {self.partner_name}! {n} {'life' if n == 1 else 'lives'} left.")
        self.send("hurt", kind=e.kind, lives=n)
        if p.room != g.room.id:
            self.other_enemies = g.make_enemies(g.house.rooms[p.room], *p.entry[:2])
            p.grace = self.G.ENTRY_GRACE

    def host_request(self, t, m):
        g = self.g
        p = self.partner
        if g.mode not in ("play", "watch") or not p.seen or self.p_out is not None:
            return
        r = g.house.rooms.get(m.get("room", p.room))
        if r is None or r.id != p.room:
            return
        say = lambda text: self.send("say", text=text)   # noqa: E731
        if t == "push":
            o = self.room_objs(r).get(m.get("obj"))
            d = tuple(m.get("d", (0, 0)))
            if o is not None and o.t.get("push") and d in ((1, 0), (-1, 0), (0, 1), (0, -1)) and self.near(r, o):
                g.try_push(o, d, room=r, say=say, others=[(g.px, g.py)] if r is g.room and g.out is None else [])
        elif t == "lift":
            o = self.room_objs(r).get(m.get("obj"))
            if o is not None and o.t.get("lift") and self.near(r, o, 1.0):
                o.lifted = not o.lifted
                if o.lifted and g.key_state == "hidden" and g.key_place[:3] == (r.id, "rug", o.id):
                    g.key_state = "revealed"
                    g.key_pos = (o.x + o.gx - 0.5, o.y + o.gy - 0.5)
                    self.send("found", text="There's something under the rug!")
                elif o.lifted:
                    say("You lift the corner of the rug. Just dust.")
        elif t == "search":
            o = self.room_objs(r).get(m.get("obj"))
            if o is not None and self.near(r, o) and g.key_state == "hidden" and g.key_place[:3] == (r.id, "search", o.id):
                how = self.G.SEARCH_PHRASE[o.t["search"]].format(n=nice(o.type))
                self.key_taken(f"You found the front door key {how}!")
        elif t == "pickup":
            if g.key_state == "revealed" and g.key_place[0] == r.id and \
                    abs(p.tx - g.key_pos[0]) < 0.8 and abs(p.ty - g.key_pos[1]) < 0.8:
                self.key_taken("You picked up the front door key! Back to the Entrance Hall!")
        elif t == "escape":
            fd = r.front_door()
            if fd is not None and g.key_state == "carried" and p.ty < 1.2 and fd.index - 0.3 <= p.tx < fd.index + 2.3:
                self.p_out = "won"
                self.other_enemies = None
                self.send("escaped", pts=self.G.PTS_ESCAPE)
                g.sounds.play("unlock")
                if g.out is None:
                    g.say(f"{self.partner_name} escaped through the front door! Your turn!")
                self.check_end()

    def check_end(self):
        """Host: once both players are out, the game is over for both."""
        g = self.g
        if g.out is not None and self.p_out is not None and not self.ended:
            self.ended = True
            self.send("end", out=g.out, k=g.killer if g.out == "dead" else None)
            g.finish_end()

    def key_taken(self, text):
        g = self.g
        g.key_state = "carried"
        g.sounds.play("key_found")
        if g.out is None:
            g.say(f"{self.partner_name} found the front door key! Meet at the front door in the Entrance Hall!")
        self.send("key", text=text, pts=self.G.PTS_KEY)

    def announce_key(self):
        """Host found the key itself: tell the other player."""
        self.send("found", text=f"{self.G.CHARACTERS[self.g.character]} found the front door key! "
                                "Meet at the front door in the Entrance Hall!")

    # ---- client side: what the host tells us
    def client_event(self, t, m):
        g = self.g
        if t == "say":
            g.say(str(m.get("text", "")))
        elif t == "pop":
            g.popups.append([str(m.get("text", "")), g.px, g.py, 0.0])
        elif t in ("key", "found"):
            g.sounds.play("key_found")
            if g.out is None:
                g.say(str(m.get("text", "")))
            if t == "key":
                g.key_state = "carried"
                g.add_points(int(m.get("pts", self.G.PTS_KEY)))
        elif g.out is not None and t != "end":
            return                        # we're watching: nothing more can happen to us
        elif t == "hurt":
            g.client_hurt(str(m.get("kind", "ghost")), int(m.get("lives", g.lives)))
        elif t == "dead":
            g.lives = 0
            g.sounds.play(f"ow_{g.character}")
            g.go_out("dead", str(m.get("kind", "ghost")))
        elif t == "escaped":
            g.add_points(int(m.get("pts", self.G.PTS_ESCAPE)))
            g.go_out("won")
        elif t == "end":
            self.ended = True
            if m.get("out") in ("won", "dead"):          # how the host got out (it may not have said yet)
                self.partner.out, self.partner.killer = m["out"], m.get("k")
            g.finish_end()

    # ---- requests from this (client) game
    def request(self, t, **data):
        data["room"] = self.g.room.id
        self.send(t, **data)

    def want_pickup(self):
        if self.pickup_cd <= 0:
            self.pickup_cd = 0.4
            self.request("pickup")

    # ---- the end, and goodbyes
    def lost(self, reason):
        """The other game went away: carry on alone (or just stay on the end screen)."""
        g = self.g
        self.link.close(say_bye=False)
        g.coop = None
        if g.mode == "play":
            if self.client:
                g.spawn_enemies()           # our own copy of the house takes over
                g.grace = self.G.ENTRY_GRACE
            g.say(f"{self.partner_name} has gone ({reason.lower()}). Carrying on alone.")
        elif g.mode == "watch":             # nobody left to watch: that's the end
            g.net_note = f"{self.partner_name} has gone ({reason.lower()})."
            g.finish_end()

    def close(self):
        self.link.close()


# ===================================================================== lobbies
class HostLobby:
    """Waiting for the other player: open the port, say so on the LAN."""

    def __init__(self, game, port=net.GAME_PORT):
        self.g = game
        self.port = port
        self.server = net.Server(port)
        self.error = self.server.error
        self.ip = net.local_ip()
        self.beacon = None if self.error else net.Beacon(
            {"name": net.host_label(), "port": port, "ip": self.ip, "char": game.character})
        self.link = None
        self.hello_t = 0.0
        self.note = ""

    def update(self, dt):
        if self.error:
            return
        if self.beacon:
            self.beacon.tick()
        if self.link is None and self.server.link is not None:
            self.link, self.hello_t = self.server.link, 0.0
        if self.link is None:
            return
        self.hello_t += dt
        for msg in self.link.poll():
            if msg.get("t") == "hello":
                if msg.get("game") != net.GAME_ID or msg.get("v") != net.PROTOCOL:
                    self.link.send({"t": "refuse", "why": "That game is a different version."})
                    self.restart("A game of a different version tried to join.")
                    return
                G = sys.modules[type(self.g).__module__]
                mine = self.g.character
                theirs = next(c for c in G.CHAR_ORDER if c != mine)
                seed = self.g.coop_seed if self.g.coop_seed is not None else random.randrange(1_000_000)
                self.link.send({"t": "welcome", "v": net.PROTOCOL, "seed": seed, "host": mine, "you": theirs,
                                "name": net.host_label(), "hidden": bool(self.g.key_hidden)})
                self.close(keep_link=True)
                self.g.start_coop("host", self.link, seed, mine, theirs)
                return
        if self.link.closed or self.hello_t > HELLO_TIMEOUT_S:
            self.restart("Someone connected but didn't say hello. Still waiting.")

    def restart(self, why):
        if self.link:
            self.link.close(say_bye=False)
        self.link = None
        self.server = net.Server(self.port)
        self.error = self.server.error
        self.note = why

    def close(self, keep_link=False):
        if self.beacon:
            self.beacon.close()
            self.beacon = None
        self.server.stop()
        if self.link and not keep_link:
            self.link.close()

    def lines(self):
        G = sys.modules[type(self.g).__module__]
        if self.error:
            return ["Couldn't start a game", self.error, "Is another game already hosting on this computer?",
                    "Esc: back"]
        dots = "." * (1 + int(self.g.title_t * 2) % 3)
        return [f"Hosting as {G.CHARACTERS[self.g.character]}",
                f"Waiting for the other player to join{dots}",
                f"Your address: {self.ip}   (port {self.port})",
                "On the other computer choose Join a game: it should appear in the list,",
                "or type this address there.   Esc: cancel"] + ([self.note] if self.note else [])


class JoinLobby:
    """Find a host on the LAN (or type its address), connect and say hello."""

    def __init__(self, game):
        self.g = game
        self.scanner = net.Scanner()
        self.typed = ""
        self.pick = 0
        self.conn = None
        self.link = None
        self.status = ""
        self.wait_t = 0.0

    def hosts(self):
        return self.scanner.hosts()

    def on_text(self, text):
        for ch in text:
            if (ch.isascii() and (ch.isalnum() or ch in ".-:")) and len(self.typed) < 40:
                self.typed += ch

    def on_key(self, key, pg):
        if self.conn is not None or self.link is not None:
            return
        found = self.hosts()
        if key == pg.K_BACKSPACE:
            self.typed = self.typed[:-1]
        elif key in (pg.K_UP, pg.K_DOWN) and found:
            self.pick = (self.pick + (1 if key == pg.K_DOWN else -1)) % len(found)
        elif key in (pg.K_RETURN, pg.K_KP_ENTER):
            if self.typed.strip():
                try:
                    host, port = net.parse_hostport(self.typed)
                except ValueError:
                    self.status = "That address doesn't look right (for example 192.168.1.20)"
                    return
            elif found:
                host, port = found[min(self.pick, len(found) - 1)][0]
            else:
                self.status = "No games found yet. Type the host's address, or wait."
                return
            self.connect(host, port)

    def connect(self, host, port):
        self.conn = net.Connector(host, port)
        self.status = f"Connecting to {host}..."

    def update(self, dt):
        self.scanner.poll()
        if self.conn is not None and self.conn.done:
            if self.conn.link is None:
                self.status = self.conn.error or "Couldn't connect"
            else:
                self.link = self.conn.link
                self.link.send({"t": "hello", "game": net.GAME_ID, "v": net.PROTOCOL, "name": net.host_label()})
                self.wait_t = 0.0
                self.status = "Connected. Waiting for the host..."
            self.conn = None
        if self.link is None:
            return
        self.wait_t += dt
        for msg in self.link.poll():
            if msg.get("t") == "welcome" and msg.get("v") == net.PROTOCOL:
                self.close(keep_link=True)
                self.g.key_hidden = bool(msg.get("hidden", False))   # the host decides where keys go
                self.g.start_coop("client", self.link, int(msg["seed"]), msg["you"], msg["host"])
                return
            if msg.get("t") == "refuse":
                self.status = str(msg.get("why", "The host said no."))
                self.link.close(say_bye=False)
                self.link = None
                return
        if self.link.closed or self.wait_t > HELLO_TIMEOUT_S:
            self.status = "The host didn't answer. Is it still waiting for a player?"
            self.link.close(say_bye=False)
            self.link = None

    def close(self, keep_link=False):
        self.scanner.close()
        if self.link and not keep_link:
            self.link.close()

    def lines(self):
        G = sys.modules[type(self.g).__module__]
        out = ["Join a game"]
        if self.scanner.error:
            out.append(self.scanner.error)
        found = self.hosts()
        if found:
            out.append("Games on your network (Up / Down to choose):")
            for i, (addr, info) in enumerate(found[:5]):
                who = G.CHARACTERS.get(info.get("char"), "?")
                mark = "> " if i == self.pick and not self.typed else "   "
                out.append(f"{mark}{info.get('name', '?')} ({addr[0]}), hosting as {who}")
        else:
            dots = "." * (1 + int(self.g.title_t * 2) % 3)
            out.append(f"Looking for games on your network{dots}")
        caret = "_" if int(self.g.title_t * 2.5) % 2 == 0 else " "
        out.append(f"Or type the host's address: {self.typed}{caret}")
        out.append(self.status or "Enter: join      Esc: back")
        return out
