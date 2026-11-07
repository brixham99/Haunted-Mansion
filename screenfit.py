"""Put the 1280x800 picture on a television without stretching it.

The game is drawn at its own resolution either way. In full screen, SDL's
SCALED flag keeps that surface and asks the display's renderer to scale it
to the TV's current mode, preserving the aspect ratio (black bars at the
sides of a 16:9 set). The CPU still fills 1280x800 pixels a frame; the scale
is the GPU's, the same one the resizable window already uses.

If a renderer cannot do that, or a caller names an exact display size (the
headless checks at 1920x1080 and 3840x2160), the frame is letterboxed in
software with the same fit. That path is the fallback, not the one a Pi uses
while playing.
"""

from __future__ import annotations

import os

import pygame


def fullscreen_requested(flag: bool = False, env=None) -> bool:
    """True for --fullscreen, or for the environment variable ZENSTATION=1."""
    if flag:
        return True
    if env is None:
        env = os.environ.get("ZENSTATION", "")
    return str(env).strip() == "1"


def fit_rect(src_size, dst_size):
    """(x, y, w, h) of src fitted inside dst, centred, aspect kept.

    The limiting axis is filled exactly, so a 16:10 picture on a 16:9 TV
    gets equal black bars on the left and right and none above or below.
    """
    sw, sh = int(src_size[0]), int(src_size[1])
    dw, dh = int(dst_size[0]), int(dst_size[1])
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        return 0, 0, max(dw, 0), max(dh, 0)
    # dw/sw ? dh/sh, compared as integers so 1280x800 on 1920x1080 is exact.
    if dw * sh >= dh * sw:
        th = dh
        tw = (sw * dh + sh // 2) // sh
    else:
        tw = dw
        th = (sh * dw + sw // 2) // sw
    tw = max(1, min(dw, tw))
    th = max(1, min(dh, th))
    x = (dw - tw) // 2
    y = (dh - th) // 2
    return x, y, tw, th


def letterbox_blit(src, dst, bg=(0, 0, 0)):
    """Draw src onto dst, centred, with black bars. Returns the fitted rect."""
    dst.fill(bg)
    x, y, w, h = fit_rect(src.get_size(), dst.get_size())
    if (w, h) == src.get_size():
        dst.blit(src, (x, y))
    else:
        dst.blit(pygame.transform.scale(src, (w, h)), (x, y))
    return x, y, w, h


def desktop_size():
    """The display's current mode, or None if SDL cannot say."""
    try:
        sizes = pygame.display.get_desktop_sizes()
    except Exception:
        sizes = []
    if sizes and sizes[0][0] > 1 and sizes[0][1] > 1:
        return int(sizes[0][0]), int(sizes[0][1])
    try:
        info = pygame.display.Info()
        if info.current_w > 1 and info.current_h > 1:
            return int(info.current_w), int(info.current_h)
    except Exception:
        pass
    return None


class _View:
    """The surface the game draws on, and how that reaches the window."""

    def __init__(self, surface, fullscreen: bool):
        self.surface = surface
        self.fullscreen = fullscreen

    def present(self):
        if self.fullscreen:
            pygame.mouse.set_visible(False)
        pygame.display.flip()


class _Letterboxed(_View):
    def __init__(self, draw, window):
        super().__init__(draw, True)
        self.window = window

    def present(self):
        pygame.mouse.set_visible(False)
        letterbox_blit(self.surface, self.window)
        pygame.display.flip()


def _letterbox_window(logical, display_size):
    """A borderless window at display_size. The game is drawn at `logical` and fitted in."""
    display_size = (int(display_size[0]), int(display_size[1]))
    try:
        window = pygame.display.set_mode(display_size, pygame.FULLSCREEN | pygame.NOFRAME)
    except pygame.error:
        window = pygame.display.set_mode(display_size, pygame.NOFRAME)
    draw = pygame.Surface(logical).convert()
    pygame.mouse.set_visible(False)
    return _Letterboxed(draw, window)


def open_display(logical, *, fullscreen: bool, headless: bool, display_size=None):
    """Open the window. The returned surface is always `logical` (1280x800).

    display_size forces a borderless window of that exact size and a software
    letterbox. The headless TV checks pass 1920x1080 and 3840x2160. Playing
    on a set does not: full screen uses SDL SCALED at the display's own mode.
    """
    logical = (int(logical[0]), int(logical[1]))
    if headless or not fullscreen:
        flags = 0 if headless else (pygame.SCALED | pygame.RESIZABLE)
        try:
            surf = pygame.display.set_mode(logical, flags)
        except pygame.error:
            surf = pygame.display.set_mode(logical)
        if not headless:
            pygame.mouse.set_visible(True)
        return _View(surf, False)

    pygame.mouse.set_visible(False)
    if display_size:
        return _letterbox_window(logical, (int(display_size[0]), int(display_size[1])))

    # Linear filtering on the way to the TV. Set before the renderer exists,
    # and only for full screen, so a resizable window scales as it does now.
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")
    try:
        surf = pygame.display.set_mode(logical, pygame.FULLSCREEN | pygame.SCALED | pygame.NOFRAME)
    except pygame.error:
        surf = None
    if surf is not None and surf.get_size() == logical:
        return _View(surf, True)
    native = desktop_size() or logical
    return _letterbox_window(logical, native)
