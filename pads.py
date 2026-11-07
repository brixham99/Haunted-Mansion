"""Gamepads through SDL's GameController API.

Xbox and PlayStation pads share one layout: A/Cross confirms, B/Circle goes
back, X/Square and Y/Triangle are the other actions, Start/Options pauses,
and holding Back/Share quits. The keyboard is never read here.

This game has one local player, so pad 0 drives them. A second pad is kept
as player 2 for a local two-player game; there isn't one (two-player is over
the network, one pad per computer).
"""

from __future__ import annotations

import pygame

# SDL GameController buttons and axes. The same numbers on every pad.
A = pygame.CONTROLLER_BUTTON_A
B = pygame.CONTROLLER_BUTTON_B
X = pygame.CONTROLLER_BUTTON_X
Y = pygame.CONTROLLER_BUTTON_Y
BACK = pygame.CONTROLLER_BUTTON_BACK
GUIDE = pygame.CONTROLLER_BUTTON_GUIDE
START = pygame.CONTROLLER_BUTTON_START
LEFTSHOULDER = pygame.CONTROLLER_BUTTON_LEFTSHOULDER
RIGHTSHOULDER = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER
DPAD_UP = pygame.CONTROLLER_BUTTON_DPAD_UP
DPAD_DOWN = pygame.CONTROLLER_BUTTON_DPAD_DOWN
DPAD_LEFT = pygame.CONTROLLER_BUTTON_DPAD_LEFT
DPAD_RIGHT = pygame.CONTROLLER_BUTTON_DPAD_RIGHT

AXIS_LEFTX = pygame.CONTROLLER_AXIS_LEFTX
AXIS_LEFTY = pygame.CONTROLLER_AXIS_LEFTY
AXIS_RIGHTX = pygame.CONTROLLER_AXIS_RIGHTX
AXIS_RIGHTY = pygame.CONTROLLER_AXIS_RIGHTY
AXIS_TRIGGERLEFT = pygame.CONTROLLER_AXIS_TRIGGERLEFT
AXIS_TRIGGERRIGHT = pygame.CONTROLLER_AXIS_TRIGGERRIGHT

BUTTONS = (A, B, X, Y, BACK, GUIDE, START,
           pygame.CONTROLLER_BUTTON_LEFTSTICK, pygame.CONTROLLER_BUTTON_RIGHTSTICK,
           LEFTSHOULDER, RIGHTSHOULDER, DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT)
AXES = (AXIS_LEFTX, AXIS_LEFTY, AXIS_RIGHTX, AXIS_RIGHTY, AXIS_TRIGGERLEFT, AXIS_TRIGGERRIGHT)

DEADZONE = 0.30
RELEASE_ZONE = 0.24          # a little under the deadzone, so the edge doesn't chatter
QUIT_HOLD_S = 1.0

# British names for the on-screen hints. SDL's logical buttons match Xbox;
# a PlayStation pad is the same buttons with its own names.
LABELS = {
    "xbox": {"A": "A", "B": "B", "X": "X", "Y": "Y", "START": "Start", "BACK": "Back", "RT": "RT"},
    "playstation": {"A": "Cross", "B": "Circle", "X": "Square", "Y": "Triangle",
                    "START": "Options", "BACK": "Share", "RT": "R2"},
}

# --pad on the command line, and the name a real pad of that sort reports.
PAD_NAMES = {
    "xbox": "Xbox 360 Controller",
    "ps4": "PS4 Controller",
    "playstation": "Wireless Controller",   # a DualShock 4 over Bluetooth
}


def axis_unit(value) -> float:
    """SDL hands axes back as -32768..32767, or already as -1..1.

    Controller.get_axis gives whole numbers (-32768..32767); Joystick.get_axis
    gives floats (-1..1). Tell them apart by type, not size: a resting stick can
    read a raw 1 or -1, which must not count as a full tilt."""
    if isinstance(value, int) and not isinstance(value, bool):
        v = value / 32767.0
    else:
        v = float(value)
        if abs(v) > 1.5:
            v /= 32767.0
    if v < -1.0:
        return -1.0
    if v > 1.0:
        return 1.0
    return v


def family_of(name: str, guid: str = "") -> str:
    """'playstation' or 'xbox' (the default: SDL's own button names).

    A DualShock 4 on Bluetooth often introduces itself only as
    "Wireless Controller". Sony's USB id is 0x054c, which an SDL joystick
    GUID stores little-endian as "4c05". Xbox is matched first so that
    "Xbox Wireless Controller" is not read as that PlayStation name.
    """
    n = (name or "").lower().strip()
    g = (guid or "").lower()
    if any(s in n for s in ("xbox", "x-box", "xinput")):
        return "xbox"
    if "4c05" in g or any(s in n for s in (
            "playstation", "dualshock", "dual shock", "dualsense", "sony",
            "ps3", "ps4", "ps5")):
        return "playstation"
    if n == "wireless controller":
        return "playstation"
    return "xbox"


def _controller_module():
    try:
        import pygame._sdl2.controller as ctrl
        return ctrl
    except Exception:
        return None


class MenuRepeat:
    """One pulse as a direction is pressed, then a steady repeat while held.

    Menus and the high-score name use this. Walking does not: a held stick
    is read every frame, the same way a held key is.
    """

    def __init__(self, delay: float = 0.32, rate: float = 0.12):
        self.delay = delay
        self.rate = rate
        self.cur = (0, 0)
        self.acc = 0.0
        self.repeating = False

    def reset(self):
        self.cur = (0, 0)
        self.acc = 0.0
        self.repeating = False

    def pulses(self, direction, dt: float):
        d = (int(direction[0]), int(direction[1]))
        if d == (0, 0):
            self.reset()
            return []
        if d != self.cur:
            self.cur = d
            self.acc = 0.0
            self.repeating = False
            return [d]
        self.acc += dt
        need = self.rate if self.repeating else self.delay
        out = []
        while self.acc >= need and len(out) < 4:
            self.acc -= need
            self.repeating = True
            need = self.rate
            out.append(d)
        return out


class Pad:
    """One controller, real or synthetic. Buttons and axes are the SDL layout."""

    def __init__(self, instance_id, name, family, controller=None, joystick=None, synthetic=False):
        self.instance_id = instance_id
        self.name = name or "Controller"
        self.family = family
        self.controller = controller
        self.joystick = joystick
        self.synthetic = synthetic
        self.buttons = {b: False for b in BUTTONS}
        self.prev_buttons = dict(self.buttons)
        self.pressed = set()
        self.axes = {a: 0.0 for a in AXES}
        self._axis_dir = {AXIS_LEFTX: 0, AXIS_LEFTY: 0}
        self._rt_on = False         # right trigger pulled: walk forwards
        self.back_held = 0.0

    def set_button(self, button, down: bool):
        if button in self.buttons:
            self.buttons[button] = bool(down)

    def set_axis(self, axis, value):
        if axis not in self.axes:
            return
        v = axis_unit(value)
        self.axes[axis] = v
        if axis in self._axis_dir:
            self._axis_dir[axis] = self._hysteresis(axis, v)
        elif axis == AXIS_TRIGGERRIGHT:
            self._rt_on = v >= RELEASE_ZONE if self._rt_on else v >= DEADZONE

    def _hysteresis(self, axis, value: float) -> int:
        cur = self._axis_dir[axis]
        if cur == 0:
            if value <= -DEADZONE:
                return -1
            if value >= DEADZONE:
                return 1
            return 0
        if cur < 0:
            if value <= -RELEASE_ZONE:
                return -1
            if value >= DEADZONE:
                return 1
            return 0
        if value >= RELEASE_ZONE:
            return 1
        if value <= -DEADZONE:
            return -1
        return 0

    def raw_xy(self):
        """(x, y) with x positive right and y positive down. The D-pad wins
        over the stick on any axis it is holding."""
        lx = self._axis_dir[AXIS_LEFTX]
        ly = self._axis_dir[AXIS_LEFTY]
        left, right = self.buttons[DPAD_LEFT], self.buttons[DPAD_RIGHT]
        up, down = self.buttons[DPAD_UP], self.buttons[DPAD_DOWN]
        x = (-1 if left else 0) + (1 if right else 0)
        y = (-1 if up else 0) + (1 if down else 0)
        if not x:
            x = lx
        if not y:
            y = ly
        return x, y

    def digital_move(self):
        """Tank controls: (turn, walk). Turn is +1 clockwise. Walk is +1
        forwards. A turn wins over a step, as it does on the keyboard, and
        the D-pad wins over the stick."""
        x, y = self.raw_xy()
        if x:
            return x, 0
        if y:
            return 0, -y          # stick / D-pad up is forwards
        if self._rt_on:
            return 0, 1           # right trigger walks forwards (A is the action button)
        return 0, 0

    def menu_vector(self):
        """One axis at a time for menus: (x, y), y positive down."""
        x, y = self.raw_xy()
        if x and y:
            ax = abs(self.axes[AXIS_LEFTX])
            ay = abs(self.axes[AXIS_LEFTY])
            dpad = self.buttons[DPAD_LEFT] or self.buttons[DPAD_RIGHT] or self.buttons[DPAD_UP] or self.buttons[DPAD_DOWN]
            if dpad or ay > ax:
                x = 0
            else:
                y = 0
        return x, y

    def poll(self):
        if self.synthetic:
            return
        if self.controller is not None:
            self._poll_controller()
        elif self.joystick is not None:
            self._poll_joystick()

    def _poll_controller(self):
        c = self.controller
        try:
            if not c.attached():
                return
        except Exception:
            return
        for b in BUTTONS:
            try:
                self.buttons[b] = bool(c.get_button(b))
            except Exception:
                pass
        for a in AXES:
            try:
                self.set_axis(a, c.get_axis(a))
            except Exception:
                pass

    def _poll_joystick(self):
        """A pad SDL does not know as a game controller. Xbox-style buttons,
        or the Linux DualShock 4 order when the name says PlayStation."""
        js = self.joystick
        try:
            nbtn = js.get_numbuttons()
        except Exception:
            return

        def btn(i):
            try:
                return 0 <= i < nbtn and bool(js.get_button(i))
            except Exception:
                return False

        if self.family == "playstation":
            # Linux js mapping for a DualShock 4: Cross, Circle, Triangle, Square.
            mapping = {A: 0, B: 1, Y: 2, X: 3, LEFTSHOULDER: 4, RIGHTSHOULDER: 5, BACK: 8, START: 9}
        else:
            mapping = {A: 0, B: 1, X: 2, Y: 3, LEFTSHOULDER: 4, RIGHTSHOULDER: 5, BACK: 6, START: 7}
        for b in BUTTONS:
            self.buttons[b] = False
        for b, i in mapping.items():
            self.buttons[b] = btn(i)
        hat = (0, 0)
        try:
            if js.get_numhats():
                hat = js.get_hat(0)
        except Exception:
            hat = (0, 0)
        self.buttons[DPAD_LEFT] = hat[0] < 0
        self.buttons[DPAD_RIGHT] = hat[0] > 0
        self.buttons[DPAD_UP] = hat[1] > 0
        self.buttons[DPAD_DOWN] = hat[1] < 0
        if hat == (0, 0) and nbtn >= 15 and self.family != "playstation":
            # Some Xbox drivers report the D-pad as buttons 11..14 instead of a hat.
            self.buttons[DPAD_UP] = btn(11)
            self.buttons[DPAD_DOWN] = btn(12)
            self.buttons[DPAD_LEFT] = btn(13)
            self.buttons[DPAD_RIGHT] = btn(14)
        try:
            naxis = js.get_numaxes()
        except Exception:
            naxis = 0
        for i, axis in enumerate((AXIS_LEFTX, AXIS_LEFTY)):
            if i < naxis:
                try:
                    self.set_axis(axis, js.get_axis(i))
                except Exception:
                    pass

    def finish(self):
        self.pressed = {b for b, down in self.buttons.items() if down and not self.prev_buttons[b]}
        self.prev_buttons = dict(self.buttons)

    def close(self):
        for obj in (self.controller, self.joystick):
            if obj is None:
                continue
            try:
                obj.quit()
            except Exception:
                pass
        self.controller = None
        self.joystick = None


class Pads:
    """The pads currently plugged in, in the order they were found."""

    def __init__(self):
        self.by_id = {}
        self.order = []
        self._next_syn = -1
        self._ready = False

    def _init_backend(self):
        if self._ready:
            return
        self._ready = True
        try:
            pygame.joystick.init()
        except Exception:
            pass
        ctrl = _controller_module()
        if ctrl is not None and not ctrl.get_init():
            try:
                ctrl.init()
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return bool(self.order)

    def player(self, index: int):
        """The pad for local player index (0 is the only player this game moves)."""
        if 0 <= index < len(self.order):
            return self.order[index]
        return None

    def label(self, key: str) -> str:
        fam = self.player(0).family if self.player(0) is not None else "xbox"
        return LABELS.get(fam, LABELS["xbox"]).get(key, key)

    def attach_synthetic(self, name: str):
        """A pad with no hardware behind it, driven by events or set_button."""
        iid = self._next_syn
        self._next_syn -= 1
        pad = Pad(iid, name, family_of(name), synthetic=True)
        self.by_id[iid] = pad
        self.order.append(pad)
        return pad

    def drop(self, instance_id):
        pad = self.by_id.pop(instance_id, None)
        if pad is None:
            return
        if pad in self.order:
            self.order.remove(pad)
        pad.close()

    def scan(self):
        """Open whatever is plugged in. Safe to call often; already-open pads stay."""
        self._init_backend()
        ctrl = _controller_module()
        try:
            n = pygame.joystick.get_count()
        except Exception:
            n = 0
        alive = set()
        for i in range(n):
            opened = self._open_index(i, ctrl)
            if opened is not None:
                alive.add(opened)
        for pad in list(self.order):
            if pad.synthetic:
                continue
            if pad.instance_id not in alive:
                self.drop(pad.instance_id)

    def _open_index(self, index, ctrl):
        try:
            if ctrl is not None and ctrl.is_controller(index):
                return self._open_controller(index, ctrl)
            return self._open_joystick(index)
        except Exception:
            return None

    def _open_controller(self, index, ctrl):
        # Know the instance id before opening a Controller, so a later scan
        # does not open the same pad twice (quitting that second open can
        # drop the first).
        joy = pygame.joystick.Joystick(index)
        try:
            joy.init()
        except Exception:
            pass
        iid = joy.get_instance_id()
        if iid in self.by_id:
            return iid
        c = ctrl.Controller(index)
        name = ""
        try:
            name = c.name or ""
        except Exception:
            name = ""
        if not name:
            try:
                name = ctrl.name_forindex(index) or joy.get_name()
            except Exception:
                name = joy.get_name()
        guid = ""
        try:
            guid = joy.get_guid()
        except Exception:
            pass
        pad = Pad(iid, name, family_of(name, guid), controller=c, joystick=joy)
        self.by_id[iid] = pad
        self.order.append(pad)
        return iid

    def _open_joystick(self, index):
        joy = pygame.joystick.Joystick(index)
        try:
            joy.init()
        except Exception:
            pass
        iid = joy.get_instance_id()
        if iid in self.by_id:
            return iid
        name = joy.get_name()
        guid = ""
        try:
            guid = joy.get_guid()
        except Exception:
            pass
        pad = Pad(iid, name, family_of(name, guid), joystick=joy)
        self.by_id[iid] = pad
        self.order.append(pad)
        return iid

    def handle_event(self, ev) -> bool:
        """True if ev was a controller event. Synthetic pads take button and
        axis events; real pads are polled, so their events are only consumed."""
        t = ev.type
        if t in (pygame.CONTROLLERDEVICEADDED, pygame.JOYDEVICEADDED, pygame.CONTROLLERDEVICEREMAPPED):
            self.scan()
            return True
        if t in (pygame.CONTROLLERDEVICEREMOVED, pygame.JOYDEVICEREMOVED):
            iid = getattr(ev, "instance_id", getattr(ev, "which", None))
            self.drop(iid)
            return True
        if t in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
            pad = self.by_id.get(getattr(ev, "instance_id", None))
            if pad is not None and pad.synthetic:
                pad.set_button(ev.button, t == pygame.CONTROLLERBUTTONDOWN)
            return True
        if t == pygame.CONTROLLERAXISMOTION:
            pad = self.by_id.get(getattr(ev, "instance_id", None))
            if pad is not None and pad.synthetic:
                pad.set_axis(ev.axis, ev.value)
            return True
        if t in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYAXISMOTION, pygame.JOYHATMOTION, pygame.JOYBALLMOTION):
            return True
        return False

    def begin_frame(self):
        for pad in self.order:
            pad.pressed = set()

    def poll(self):
        self._init_backend()
        for pad in self.order:
            pad.poll()

    def finish(self):
        for pad in self.order:
            pad.finish()

    def consume_quit(self, dt: float) -> bool:
        """True once any pad has held Back/Share for about a second."""
        quit_now = False
        for pad in self.order:
            if pad.buttons[BACK]:
                pad.back_held += dt
                if pad.back_held >= QUIT_HOLD_S:
                    quit_now = True
            else:
                pad.back_held = 0.0
        return quit_now
