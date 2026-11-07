#!/usr/bin/env python3
"""Headless checks for the gamepad and for full screen on a television.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 tools/pad_test.py

Synthetic SDL controller events (no real pad), the keyboard left exactly as
it was, and the 1280x800 picture fitted to 1920x1080 and 3840x2160.
"""

import os
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# A leftover from a full-screen run must not change the other tools.
os.environ.pop("ZENSTATION", None)
os.environ.pop("SDL_RENDER_SCALE_QUALITY", None)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

import game as G  # noqa: E402
import pads  # noqa: E402
import screenfit  # noqa: E402

N_OK = 0
FAILS = []
ART = os.environ.get("PAD_ART", "/opt/cursor/artifacts")


def check(cond, msg):
    global N_OK
    if cond:
        N_OK += 1
        print(f"  ok  {msg}")
    else:
        FAILS.append(msg)
        print(f"  FAIL  {msg}")
    return cond


class Keys:
    """Stands in for pygame.key.get_pressed()."""

    def __init__(self, down=()):
        self.down = set(down)

    def __getitem__(self, k):
        return 1 if k in self.down else 0


def event_button(kind, iid, button):
    return pygame.event.Event(kind, {"instance_id": iid, "button": button})


def event_axis(iid, axis, value):
    return pygame.event.Event(pygame.CONTROLLERAXISMOTION, {"instance_id": iid, "axis": axis, "value": value})


def pump(box, events):
    """The main loop's pad order: events, then poll, then edges."""
    box.begin_frame()
    for ev in events:
        check(box.handle_event(ev), "controller event consumed")
    box.poll()
    box.finish()


def test_fit():
    print("letterbox")
    cases = {
        (1920, 1080): (96, 0, 1728, 1080),
        (3840, 2160): (192, 0, 3456, 2160),
        (1280, 800): (0, 0, 1280, 800),
        (1024, 768): (0, 64, 1024, 640),   # 4:3 is taller than 16:10, so the bars are above and below
    }
    for dst, want in cases.items():
        got = screenfit.fit_rect((1280, 800), dst)
        check(got == want, f"1280x800 on {dst[0]}x{dst[1]} -> {got}, want {want}")
        x, y, w, h = got
        check(x >= 0 and y >= 0 and x + w <= dst[0] and y + h <= dst[1], f"fitted rect inside {dst}")
        check(abs(w / h - 1280 / 800) < 0.01, f"aspect kept on {dst} ({w}x{h})")
        # Bars, when there are any, are equal on the two sides (within a pixel).
        check(abs(x - (dst[0] - (x + w))) <= 1 and abs(y - (dst[1] - (y + h))) <= 1, f"bars centred on {dst}")

    src = pygame.Surface((1280, 800))
    src.fill((200, 30, 40))
    for dw, dh in ((1920, 1080), (3840, 2160)):
        dst = pygame.Surface((dw, dh))
        dst.fill((1, 2, 3))
        t0 = time.perf_counter()
        rect = screenfit.letterbox_blit(src, dst)
        ms = (time.perf_counter() - t0) * 1000
        x, y, w, h = rect
        print(f"  software fit {dw}x{dh}: {ms:.2f} ms (one frame; not the path a Pi plays on)")
        check(dst.get_at((0, dh // 2))[:3] == (0, 0, 0), f"{dw}x{dh} left bar is black")
        check(dst.get_at((x - 1, dh // 2))[:3] == (0, 0, 0), f"{dw}x{dh} pixel before the picture is black")
        check(dst.get_at((x, dh // 2))[:3] == (200, 30, 40), f"{dw}x{dh} picture starts at the fitted edge")
        check(dst.get_at((x + w - 1, y + h // 2))[:3] == (200, 30, 40), f"{dw}x{dh} picture reaches the other edge")
        check(dst.get_at((x + w, dh // 2))[:3] == (0, 0, 0), f"{dw}x{dh} right bar is black")
        check(dst.get_at((x + w // 2, 0))[:3] == (200, 30, 40), f"{dw}x{dh} no bar across the top")
        check(dst.get_at((x + w // 2, dh - 1))[:3] == (200, 30, 40), f"{dw}x{dh} no bar across the bottom")
        check(dst.get_at((dw // 2, dh // 2))[:3] == (200, 30, 40), f"{dw}x{dh} centre is the picture")


def test_windows():
    print("display")
    check(screenfit.fullscreen_requested(False, "") is False, "no flag and no ZENSTATION: windowed")
    check(screenfit.fullscreen_requested(False, "0") is False, "ZENSTATION=0 stays windowed")
    check(screenfit.fullscreen_requested(False, "1") is True, "ZENSTATION=1 is full screen")
    check(screenfit.fullscreen_requested(True, "") is True, "--fullscreen is full screen")

    view = screenfit.open_display((G.WIN_W, G.WIN_H), fullscreen=False, headless=False)
    check(view.surface.get_size() == (1280, 800), f"windowed surface is 1280x800 ({view.surface.get_size()})")
    check(pygame.display.get_window_size() == (1280, 800), f"windowed window is 1280x800 ({pygame.display.get_window_size()})")
    check(pygame.mouse.get_visible() is True, "windowed: pointer shown")

    view = screenfit.open_display((G.WIN_W, G.WIN_H), fullscreen=True, headless=False)
    desk = pygame.display.get_desktop_sizes()[0]
    check(view.surface.get_size() == (1280, 800), f"full screen still draws at 1280x800 ({view.surface.get_size()})")
    check(tuple(pygame.display.get_window_size()) == tuple(desk),
          f"full screen window is the display's own size {desk}, got {pygame.display.get_window_size()}")
    check(pygame.mouse.get_visible() is False, "full screen: pointer hidden")
    view.present()
    check(pygame.mouse.get_visible() is False, "pointer stays hidden after a frame")

    for size in ((1920, 1080), (3840, 2160)):
        view = screenfit.open_display((G.WIN_W, G.WIN_H), fullscreen=True, headless=False, display_size=size)
        check(view.surface.get_size() == (1280, 800), f"simulated {size[0]}x{size[1]} still draws at 1280x800")
        check(tuple(view.window.get_size()) == size, f"simulated window is {size}, got {view.window.get_size()}")
        view.surface.fill((200, 30, 40))
        view.present()
        x, y, w, h = screenfit.fit_rect((1280, 800), size)
        pix = view.window.get_at
        check(pix((0, size[1] // 2))[:3] == (0, 0, 0), f"{size} window left bar is black")
        check(pix((x, size[1] // 2))[:3] == (200, 30, 40), f"{size} window picture starts after the bar")
        check(pix((x + w - 1, size[1] // 2))[:3] == (200, 30, 40), f"{size} window picture fills its height")
        check(pix((min(size[0] - 1, x + w), size[1] // 2))[:3] == (0, 0, 0), f"{size} window right bar is black")
        check(pygame.mouse.get_visible() is False, f"{size}: pointer hidden")


def test_pad_math():
    print("pad")
    check(pads.family_of("Xbox 360 Controller") == "xbox", "Xbox name")
    check(pads.family_of("Xbox Wireless Controller") == "xbox", "Xbox wireless name")
    check(pads.family_of("PS4 Controller") == "playstation", "PS4 wired name")
    check(pads.family_of("Wireless Controller") == "playstation", "DualShock 4 over Bluetooth")
    check(pads.family_of("Sony Interactive Entertainment DualSense") == "playstation", "DualSense")
    check(pads.family_of("Generic USB", "030000004c050000c405000000010000") == "playstation", "Sony GUID")
    check(pads.axis_unit(0.3) == 0.3 and abs(pads.axis_unit(32767) - 1) < 1e-3, "axis as a fraction or as SDL's raw value")
    check(pads.axis_unit(-32768) == -1.0, "full left is -1")

    box = pads.Pads()
    pad = box.attach_synthetic("Xbox 360 Controller")
    iid = pad.instance_id
    check(box.label("A") == "A" and box.label("BACK") == "Back" and box.label("START") == "Start", "Xbox hints")

    def move_axis(axis, value):
        pump(box, [event_axis(iid, axis, value)])
        return pad.digital_move()

    check(move_axis(pads.AXIS_LEFTX, 0.29) == (0, 0), "inside the 0.3 deadzone: no turn")
    check(move_axis(pads.AXIS_LEFTX, 0.30) == (1, 0), "on the 0.3 deadzone: turn right")
    check(move_axis(pads.AXIS_LEFTX, 0.25) == (1, 0), "eases back to 0.25: still held (hysteresis)")
    check(move_axis(pads.AXIS_LEFTX, 0.20) == (0, 0), "back to 0.20: released")
    check(move_axis(pads.AXIS_LEFTX, -32767) == (-1, 0), "raw SDL axis full left turns left")
    check(move_axis(pads.AXIS_LEFTX, 0.0) == (0, 0), "stick back to centre")
    check(move_axis(pads.AXIS_LEFTY, -0.8) == (0, 1), "stick up walks forwards")
    check(move_axis(pads.AXIS_LEFTY, 0.8) == (0, -1), "stick down walks backwards")
    check(move_axis(pads.AXIS_LEFTY, 0.0) == (0, 0), "stick back to centre again")
    check(move_axis(pads.AXIS_TRIGGERRIGHT, 1) == (0, 0), "a resting raw right trigger does not walk")
    check(move_axis(pads.AXIS_TRIGGERRIGHT, 32767) == (0, 1), "right trigger pulled walks forwards")
    check(move_axis(pads.AXIS_LEFTX, 0.8) == (1, 0), "a turn still wins over the trigger")
    move_axis(pads.AXIS_LEFTX, 0.0)
    check(move_axis(pads.AXIS_TRIGGERRIGHT, 0) == (0, 0), "trigger let go: stop")
    check(pads.Pads().label("RT") == "RT", "Xbox trigger hint")
    # Both axes out: the turn wins, as a held turn wins over a held step on the keyboard.
    pad.set_axis(pads.AXIS_LEFTX, 0.6)
    pad.set_axis(pads.AXIS_LEFTY, -0.9)
    check(pad.digital_move() == (1, 0), "diagonal stick turns rather than walks")
    pad.set_axis(pads.AXIS_LEFTX, 0.0)
    pad.set_axis(pads.AXIS_LEFTY, 0.0)

    pump(box, [event_button(pygame.CONTROLLERBUTTONDOWN, iid, pads.DPAD_LEFT)])
    check(pad.digital_move()[0] == -1, "D-pad left turns left")
    pad.set_axis(pads.AXIS_LEFTX, 1.0)   # stick says right; the D-pad is held
    check(pad.digital_move() == (-1, 0), "D-pad wins over the stick")
    pump(box, [event_button(pygame.CONTROLLERBUTTONUP, iid, pads.DPAD_LEFT)])
    pad.set_axis(pads.AXIS_LEFTX, 0.0)

    other = box.attach_synthetic("PS4 Controller")
    other.set_axis(pads.AXIS_LEFTX, 1.0)
    check(pads.axis_unit(1) == pads.axis_unit(-1) == 0.0 or abs(pads.axis_unit(1)) < 0.01, "a resting raw 1 is not a full tilt")
    other.set_button(pads.A, True)
    box.finish()
    check(pad.digital_move() == (0, 0), "the second pad does not move player 1")
    check(other.digital_move() == (1, 0) and other.family == "playstation", "second pad is its own PlayStation pad")
    check(box.player(0) is pad and box.player(1) is other, "pads stay in the order they were attached")
    check(pads.A not in pad.pressed and pads.A in other.pressed, "player 2's A is not player 1's A")

    # Hot-plug: a removed event drops that pad, and adding one does not crash with nothing plugged in.
    pump(box, [pygame.event.Event(pygame.CONTROLLERDEVICEREMOVED, {"instance_id": other.instance_id})])
    check(box.player(1) is None and box.player(0) is pad, "unplugging player 2 leaves player 1")
    pump(box, [pygame.event.Event(pygame.CONTROLLERDEVICEADDED, {"device_index": 0})])
    check(box.player(0) is pad, "a device-added scan keeps the synthetic pad")
    pump(box, [pygame.event.Event(pygame.CONTROLLERDEVICEREMOVED, {"instance_id": iid})])
    check(not box.connected, "unplugging the last pad clears the hints' pad")

    ps = pads.Pads()
    ps.attach_synthetic("Wireless Controller")
    check(ps.label("A") == "Cross" and ps.label("B") == "Circle" and ps.label("X") == "Square"
          and ps.label("Y") == "Triangle" and ps.label("START") == "Options" and ps.label("BACK") == "Share",
          "PlayStation hints, including the Bluetooth name")

    held = pads.Pads()
    q = held.attach_synthetic("Xbox One Controller")
    q.set_button(pads.BACK, True)
    check(held.consume_quit(0.6) is False, "Back held for 0.6s does not quit")
    q.set_button(pads.BACK, False)
    check(held.consume_quit(0.5) is False, "letting go resets the hold")
    q.set_button(pads.BACK, True)
    check(held.consume_quit(0.7) is False, "0.7s of a fresh hold does not quit")
    check(held.consume_quit(0.3) is True, "about a second of Back quits")
    # The other pad can quit too.
    q.set_button(pads.BACK, False)
    held.consume_quit(0.01)
    mate = held.attach_synthetic("PS4 Controller")
    mate.set_button(pads.BACK, True)
    check(held.consume_quit(1.0) is True, "player 2 holding Share also quits")


def test_game(screen):
    print("game")
    g = G.Game(screen, seed=3, enemies=False, save=False, title=True, online=False,
               scores_file=os.path.join(tempfile.mkdtemp(), "scores.json"))
    g.sounds.ok = False
    check(g.control_lines() == list(G.KEYBOARD_CONTROLS), "no pad: the title card is the keyboard one, word for word")
    check(g.name_hint() == f"Up to {__import__('scores').NAME_MAX} letters or numbers      Enter: send      Esc: skip",
          "no pad: the name hint is the keyboard one")
    check(g.pause_caption() == "Press P to carry on", "no pad: pause still says P")
    check(g.map_footer().endswith("Tab / M: close"), "no pad: the map still says Tab / M")

    # Keyboard tank controls, including a pad asking for the opposite.
    check(g.controls(Keys({pygame.K_LEFT})) == (-1, 0), "Left turns anticlockwise")
    check(g.controls(Keys({pygame.K_a})) == (-1, 0), "A turns anticlockwise")
    check(g.controls(Keys({pygame.K_RIGHT, pygame.K_UP})) == (1, 0), "a held turn still wins over a held step")
    check(g.controls(Keys({pygame.K_w})) == (0, 1), "W walks forwards")
    check(g.controls(Keys({pygame.K_s, pygame.K_DOWN})) == (0, -1), "S or Down walks backwards")
    g.mode = "play"
    g.facing = "N"
    g.turning = False
    g.turn_t = 0.0
    g.step_left = 0.0
    for _ in range(4):   # under TURN_S, so the held key starts one quarter turn and no more
        g.update(0.02, keys=Keys({pygame.K_LEFT}), pad_dir=(1, 0))
    check(g.facing == "W", f"keyboard Left wins over a pad pushing Right (facing {g.facing})")

    g.pads = pads.Pads()
    xbox = g.pads.attach_synthetic(pads.PAD_NAMES["xbox"])
    check(g.control_lines()[0].endswith("A: start"), "Xbox connected: the title card names A")
    check("Hold Back for a second: quit" in g.control_lines()[-1], "Xbox card mentions holding Back")
    check(all(len(ln) < 110 for ln in g.control_lines()), "title card stays one short line each")
    for ln in g.control_lines():
        w = g.f_help.size(ln)[0]
        check(w < 1240, f"title line fits the screen ({w}px): {ln}")
    check(g.btn("Y", "Tab") == "Y" and g.pause_caption() == "Press Start to carry on", "Xbox pause hint")

    # Title: stick and D-pad, then A.
    g.mode = "title"
    g.title_pick = 0
    g.title_opt = 0
    pump(g.pads, [event_axis(xbox.instance_id, pads.AXIS_LEFTX, 0.9)])
    g.apply_pad(1 / 60)
    check(g.title_pick == 1, "stick right chooses Holly")
    pump(g.pads, [event_axis(xbox.instance_id, pads.AXIS_LEFTX, 0.0)])
    g.title_opt = 0
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.A)])
    g.apply_pad(1 / 60)
    check(g.mode == "play", "A starts the game")
    g.to_title()
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.A)])
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.DPAD_UP)])
    g.apply_pad(1 / 60)
    check(g.title_opt == len(G.TITLE_OPTIONS) - 1, "D-pad up moves the title options")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.DPAD_UP)])

    # A second pad's A must not be a second press for this player. Back on the title first.
    g.to_title()
    ps = g.pads.attach_synthetic(pads.PAD_NAMES["ps4"])
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.A)])
    g.apply_pad(1 / 60)
    check(g.mode == "title", "player 2's Cross does not start player 1's game")
    g.pads.drop(ps.instance_id)

    # Walking and turning from the stick, and a tap of the D-pad taking a step.
    g.mode = "play"
    g.paused = False
    g.show_map = False
    g.facing = "N"
    g.turning = False
    g.turn_t = 0.0
    g.step_left = 0.0
    g._pad_dir = (0, 0)
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.DPAD_RIGHT)])
    g.apply_pad(1 / 60)
    check(g.turning or g.facing != "N", "D-pad right starts a turn")
    for _ in range(4):
        g.update(0.02, keys=Keys(), pad_dir=xbox.digital_move())
    check(g.facing == "E", f"held D-pad right is one quarter turn (facing {g.facing})")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.DPAD_RIGHT)])
    g.turning = False
    g.step_left = 0.0
    g._pad_dir = (0, 0)
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.DPAD_UP)])
    g.apply_pad(1 / 60)
    check(abs(g.step_left - G.STEP_MIN) < 1e-6, f"a tap of D-pad up owes a whole step ({g.step_left})")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.DPAD_UP)])

    # Map, pause, back.
    g._pad_ctx = None
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.Y)])
    g.apply_pad(1 / 60)
    check(g.show_map, "Y opens the map")
    check("Y: close" in g.map_footer() and "B: back" in g.map_footer(), "map footer names the pad")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.Y),
                  event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    check(not g.show_map and g.mode == "play", "B closes the map and stays in the game")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.B),
                  event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.START)])
    g.apply_pad(1 / 60)
    check(g.paused and g.pause_caption() == "Press Start to carry on", "Start pauses")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.START)])
    g.apply_pad(1 / 60)
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.START)])
    g.apply_pad(1 / 60)
    check(not g.paused, "Start again carries on")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, xbox.instance_id, pads.START),
                  event_button(pygame.CONTROLLERBUTTONDOWN, xbox.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    check(g.mode == "title", "B on the game returns to the title")

    # Host lobby, then the join list and a typed address.
    g.pads.drop(xbox.instance_id)
    ps = g.pads.attach_synthetic("Wireless Controller")
    check(g.btn("A", "Enter") == "Cross", "Bluetooth pad is named as PlayStation")
    g.title_pick = 0
    g.open_lobby("host")
    check(g.mode == "lobby", "host lobby opens")
    check(any(ln.endswith("Circle: cancel") for ln in g.lobby.lines()), "host lobby says Circle to cancel")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    check(g.mode == "title" and g.lobby is None, "Circle leaves the host lobby")

    g.open_lobby("join")
    lobby = g.lobby
    now = time.monotonic()
    lobby.scanner.found[("192.168.1.20", 50555)] = {
        "addr": ("192.168.1.20", 50555), "name": "Oak", "char": "holly", "seen": now}
    lobby.scanner.found[("192.168.1.21", 50555)] = {
        "addr": ("192.168.1.21", 50555), "name": "Elm", "char": "archie", "seen": now}
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.B),
                  event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.DPAD_DOWN)])
    g.apply_pad(1 / 60)
    check(lobby.pick == 1 and not lobby.edit, f"D-pad down picks the next game (pick {lobby.pick})")
    check(any("Cross: join" in ln and "Circle: back" in ln for ln in lobby.lines()), "join lobby names Cross and Circle")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.DPAD_DOWN),
                  event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.DPAD_RIGHT)])
    g.apply_pad(1 / 60)
    check(lobby.edit, "D-pad right edits the address")
    # Up cycles in a character. Release so the repeater notices the next press.
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.DPAD_RIGHT)])
    g._menu_repeat.reset()
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.DPAD_UP)])
    g.apply_pad(1 / 60)
    check(lobby.typed == "0", f"up on an empty address types 0 (got {lobby.typed!r})")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.DPAD_UP),
                  event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.X)])
    g.apply_pad(1 / 60)
    check(lobby.typed == "", "Square deletes that character")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.X),
                  event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    check(g.mode == "lobby" and not lobby.edit, "Circle leaves address editing and stays in the lobby")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    check(g.mode == "title", "Circle again leaves the lobby")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.B)])

    # High score name: up/down cycles, left/right moves, A accepts, and "archie" is saved as "Archie".
    g.mode = "end"
    g.end_t = 2.0
    g.score = 120
    g.entry_active = True
    g.entry_name = ""
    g.entry_cursor = 0
    g.entry_note = ""
    g._pad_ctx = None
    g._menu_repeat.reset()
    for ch in "archie":
        g.entry_cursor = len(g.entry_name)
        g._entry_cycle(1)   # the same step a pad's Up inserts
        guard = 0
        while g.entry_name[g.entry_cursor] != ch:
            g._entry_cycle(1)
            guard += 1
            if guard > 40:
                break
        check(g.entry_name[g.entry_cursor] == ch, f"cycled to {ch!r}")
    check(g.entry_name == "archie", f"pad spelt {g.entry_name!r}")
    # And the real events do one of those steps too.
    g.entry_name = ""
    g.entry_cursor = 0
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.DPAD_UP)])
    g.apply_pad(1 / 60)
    check(g.entry_name == "a", f"D-pad up on the name inserts a (got {g.entry_name!r})")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.DPAD_UP)])
    g._menu_repeat.reset()
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.DPAD_RIGHT)])
    g.apply_pad(1 / 60)
    check(g.entry_cursor == 1, "D-pad right moves along the name")
    g.entry_name = "archie"
    g.entry_cursor = 2
    hint = g.name_hint()
    check("Cross: send" in hint and "Circle: skip" in hint and "Square: delete" in hint, f"name hint: {hint}")
    check(g.f_small.size(hint)[0] < 1240, "name hint fits the screen")
    shown = g.entry_line()
    check("[c]" in shown or "c" in shown, f"the cursor sits on a letter ({shown!r})")
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.DPAD_RIGHT),
                  event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.A)])
    g.apply_pad(1 / 60)
    check(not g.entry_active and g.entry_note == "Archie", f"A sends 'archie' as 'Archie' (got {g.entry_note!r})")
    check(g.board.top() and g.board.top()[0][0] == "Archie", f"board has Archie ({g.board.top()[:1]})")

    # Skip, and the keyboard path still capitalises on its own.
    g.score = 130
    g.entry_active = True
    g.entry_name = "holly"
    g.entry_cursor = len(g.entry_name)
    g.entry_note = ""
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONUP, ps.instance_id, pads.A)])
    g.apply_pad(1 / 60)
    pump(g.pads, [event_button(pygame.CONTROLLERBUTTONDOWN, ps.instance_id, pads.B)])
    g.apply_pad(1 / 60)
    check(not g.entry_active and g.entry_note == "", "Circle skips the name")
    g.entry_active = True
    g.entry_name = ""
    g.entry_text("archie")
    g.entry_key(pygame.K_RETURN)
    check(g.entry_note == "Archie", "typing 'archie' and Enter is still saved as Archie")

    # Screenshots: title with an Xbox pad, name entry with a PlayStation pad.
    os.makedirs(ART, exist_ok=True)
    g.pads.drop(ps.instance_id)
    g.pads.attach_synthetic(pads.PAD_NAMES["xbox"])
    g.to_title()
    g.title_pick = 0
    g.title_opt = 0
    g.best = None
    g.best_score = 0
    g.board.local_best = 0
    g.board.entries = []
    g.board.pending = []
    g.title_t = 2.0
    g.show_top10 = False
    g.draw()
    title_path = os.path.join(ART, "title-pad-hints.png")
    pygame.image.save(g.screen, title_path)
    check(os.path.exists(title_path) and pygame.image.load(title_path).get_size() == (1280, 800),
          f"title screenshot {title_path}")

    g.pads.drop(g.pads.player(0).instance_id)
    g.pads.attach_synthetic(pads.PAD_NAMES["playstation"])
    g.mode = "end"
    g.end_t = 2.4          # blink on, so the pad's cursor is drawn, and the veil is solid
    g.won = True
    g.lost = False
    g.score = 140
    g.entry_active = True
    g.entry_name = "archie"
    g.entry_cursor = 2
    g.entry_note = ""
    g.msg_t = 0
    g.new_high = False
    g.best_score = 200
    g.killer = "ghost"
    g.time = 263
    g.best = 263
    g.new_best = False
    g.draw()
    name_path = os.path.join(ART, "name-entry-pad-hints.png")
    pygame.image.save(g.screen, name_path)
    check(pygame.image.load(name_path).get_size() == (1280, 800), f"name entry screenshot {name_path}")

    # The same title frame, letterboxed onto a 1080p and a 4K set.
    frame = g.screen.copy()
    # Redraw the title so the 1080p artifact is the title, not the name entry.
    g.to_title()
    g.pads.drop(g.pads.player(0).instance_id)
    g.pads.attach_synthetic(pads.PAD_NAMES["xbox"])
    g.title_t = 2.0
    g.draw()
    frame = g.screen.copy()
    for size, name in (((1920, 1080), "title-1080p-letterbox.png"), ((3840, 2160), "title-4k-letterbox.png")):
        tv = pygame.Surface(size)
        rect = screenfit.letterbox_blit(frame, tv)
        path = os.path.join(ART, name)
        pygame.image.save(tv, path)
        x, y, w, h = rect
        check(tv.get_at((0, size[1] // 2))[:3] == (0, 0, 0), f"{name}: side bar")
        check(tv.get_at((x + 8, size[1] // 2))[:3] != (0, 0, 0), f"{name}: picture inside the bars")
        check(tv.get_size() == size, f"{name} is {size}")
    g.close_lobby()
    return title_path, name_path


def test_cli():
    print("command line")
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.pop("ZENSTATION", None)
    title = os.path.join(ART, "title-pad-hints-cli.png")
    name = os.path.join(ART, "name-entry-pad-hints-cli.png")
    cmd = [sys.executable, os.path.join(ROOT, "game.py")]
    r = subprocess.run(cmd + ["--scene", "title", "--pad", "xbox", "--screenshot", title, "--offline"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    check(r.returncode == 0, f"--scene title exits 0 ({r.returncode})")
    if r.returncode != 0:
        print(r.stderr[-500:])
    check(os.path.exists(title) and pygame.image.load(title).get_size() == (1280, 800), "CLI title shot is 1280x800")
    env["ZENSTATION"] = "1"
    shot = os.path.join(tempfile.mkdtemp(), "zen.png")
    r = subprocess.run(cmd + ["--scene", "title", "--screenshot", shot, "--offline"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    check(r.returncode == 0 and pygame.image.load(shot).get_size() == (1280, 800),
          "ZENSTATION=1 does not change a screenshot scene: still 1280x800")
    env.pop("ZENSTATION", None)
    r = subprocess.run(cmd + ["--scene", "win", "--score", "400", "--pad", "ps4", "--screenshot", name, "--offline"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    check(r.returncode == 0, f"--scene win exits 0 ({r.returncode})")
    if r.returncode != 0:
        print(r.stderr[-800:])
    check(os.path.exists(name) and pygame.image.load(name).get_size() == (1280, 800), "CLI name entry shot is 1280x800")


def main():
    t0 = time.time()
    pygame.init()
    # A tiny window so surfaces can convert; the display tests then resize it.
    pygame.display.set_mode((16, 16))
    test_fit()
    test_windows()
    # Back to the size the game draws at, then the game itself.
    screen = pygame.display.set_mode((G.WIN_W, G.WIN_H))
    pygame.mouse.set_visible(True)
    test_pad_math()
    test_game(screen)
    test_cli()
    pygame.quit()
    print(f"\n{N_OK} checks passed, {len(FAILS)} failed, in {time.time() - t0:.1f}s")
    if FAILS:
        print("Failed:")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
