#!/usr/bin/env python3
"""Synthesise Haunted Mansion's spooky sounds (22050 Hz, 16-bit mono WAV).

    python3 tools/make_sounds.py            # writes assets/sounds/*.wav
    python3 tools/make_sounds.py NAME ...   # just those (e.g. skel_clack1 skel_clack2 bat_flap)

Pure numpy, no samples. step1-3 and ow_archie/ow_holly are copied from
Daleks in Hedges and are not regenerated here.
"""
import os
import wave

import numpy as np

SR = 22050
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "sounds")
rng = np.random.default_rng(31)


def write(name, x, peak=0.8):
    x = np.asarray(x, np.float64)
    m = np.max(np.abs(x)) or 1.0
    x = x / m * peak
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"{name}.wav  {len(x) / SR:.2f}s")


def t_(d):
    return np.arange(int(d * SR)) / SR


def lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def lp_fast(x, fc):
    # FFT brick-ish low-pass (for long buffers)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / fc) ** 4)
    return np.fft.irfft(X, len(x))


def bp_fast(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= (1 / (1 + (f / hi) ** 4)) * (1 / (1 + (lo / np.maximum(f, 1)) ** 4))
    return np.fft.irfft(X, len(x))


def env(n, a=0.01, r=0.1):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def reverb(x, secs=1.6, wet=0.35):
    n = int(secs * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 4.0)
    ir = lp_fast(ir, 3000)
    y = np.convolve(x, ir)[: len(x) + n]
    y = y / (np.max(np.abs(y)) or 1)
    out = np.zeros(len(y))
    out[: len(x)] += x / (np.max(np.abs(x)) or 1) * (1 - wet)
    return out + y * wet


def loopable(x, fade=0.5):
    """Crossfade the tail into the head so it loops without a click."""
    n = int(fade * SR)
    head, tail = x[:n].copy(), x[-n:]
    w = np.linspace(0, 1, n)
    x = x[:-n].copy()
    x[:n] = head * w + tail * (1 - w)
    return x


def organ(f, d, partials=(1, 2, 3, 4, 6, 8), amps=(1, 0.6, 0.35, 0.3, 0.15, 0.1)):
    t = t_(d)
    vib = 1 + 0.003 * np.sin(2 * np.pi * 5.2 * t)
    return sum(a * np.sin(2 * np.pi * f * p * vib * t) for p, a in zip(partials, amps))


def make_title_theme():
    # D minor: slow organ chords with a creepy music-box melody on top, 16 s loop
    bpm_beat = 0.5
    chords = [(146.8, 174.6, 220.0), (116.5, 146.8, 174.6), (130.8, 164.8, 196.0), (110.0, 138.6, 164.8)]
    total = 16.5
    out = np.zeros(int(total * SR))
    for i, ch in enumerate(chords * 2):
        start = int(i * 2.0 * SR)
        d = 2.3
        s = sum(organ(f, d) for f in ch) * env(int(d * SR), 0.15, 0.6)
        out[start:start + len(s)] += s[: len(out) - start] * 0.35
        bass = organ(ch[0] / 2, d, (1, 2, 3), (1, 0.4, 0.2)) * env(int(d * SR), 0.05, 0.6)
        out[start:start + len(bass)] += bass[: len(out) - start] * 0.4
    mel = [587, 698, 659, 587, 554, 587, 440, 0, 523, 587, 523, 466, 440, 466, 554, 0,
           587, 698, 880, 784, 698, 659, 698, 0, 587, 554, 523, 466, 440, 554, 587, 0]
    for i, f in enumerate(mel):
        if not f:
            continue
        d = 0.9
        t = t_(d)
        s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 3 * t) + 0.12 * np.sin(2 * np.pi * f * 5.04 * t)) * np.exp(-t * 4)
        st = int(i * bpm_beat * SR)
        out[st:st + len(s)] += s[: len(out) - st] * 0.32
    wind = bp_fast(rng.standard_normal(len(out)), 200, 900) * (0.5 + 0.5 * np.sin(2 * np.pi * t_(total) / 8.0)) * 0.25
    out += wind[: len(out)] * np.max(np.abs(out)) / (np.max(np.abs(wind)) or 1) * 0.15
    out = reverb(out, 2.0, 0.35)[: len(out)]
    return loopable(out)


def make_ambience():
    d = 14.5
    t = t_(d)
    wind = bp_fast(rng.standard_normal(len(t)), 120, 700)
    wind *= 0.55 + 0.45 * np.sin(2 * np.pi * t / 7.25 + 1) ** 2
    howl = np.sin(2 * np.pi * (300 + 60 * np.sin(2 * np.pi * t / 3.6)) * t) * 0.04 * (np.sin(2 * np.pi * t / 14.5) ** 8)
    drone = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.4 * t) + 0.3 * np.sin(2 * np.pi * 58.3 * t)) * 0.12
    x = wind / np.max(np.abs(wind)) * 0.6 + drone + howl
    return loopable(x, 1.0)


def make_creak(seed, f0):
    r = np.random.default_rng(seed)
    d = 0.9
    t = t_(d)
    f = f0 * (1 + 0.25 * np.sin(2 * np.pi * 1.3 * t + r.random()))
    ph = np.cumsum(f) / SR
    # stick-slip: a pulse train with jitter through a resonance
    pulses = (np.sin(2 * np.pi * ph) > 0.97).astype(float) * (0.6 + 0.4 * r.random(len(t)))
    x = bp_fast(pulses, 300, 2200) + bp_fast(pulses, 900, 1300) * 0.6
    return reverb(x * env(len(t), 0.05, 0.3), 0.8, 0.25)


def make_door():
    x = make_creak(9, 22)
    t = t_(0.25)
    thud = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 18) + lp_fast(rng.standard_normal(len(t)), 400) * np.exp(-t * 25) * 0.5
    out = np.concatenate([x[: int(0.6 * SR)], thud])
    return out


def make_search():
    d = 0.55
    t = t_(d)
    x = bp_fast(rng.standard_normal(len(t)), 800, 5000)
    mod = (np.sin(2 * np.pi * 9 * t) > 0.2).astype(float) * 0.7 + 0.3
    return x * mod * env(len(t), 0.02, 0.2)


def make_key_found():
    out = np.zeros(int(1.4 * SR))
    for i, f in enumerate((1318.5, 1568, 1975.5, 2637)):
        t = t_(1.0)
        s = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t)) * np.exp(-t * 4)
        st = int(i * 0.09 * SR)
        out[st:st + len(s)] += s[: len(out) - st]
    return reverb(out, 1.2, 0.3)


def make_locked():
    out = np.zeros(int(0.5 * SR))
    for st in (0.0, 0.12, 0.22):
        t = t_(0.15)
        s = bp_fast(rng.standard_normal(len(t)), 1500, 6000) * np.exp(-t * 40) + np.sin(2 * np.pi * 180 * t) * np.exp(-t * 30) * 0.6
        i = int(st * SR)
        out[i:i + len(s)] += s
    return out


def make_unlock():
    a = make_locked()[: int(0.3 * SR)]
    t = t_(0.3)
    clunk = np.sin(2 * np.pi * 110 * t) * np.exp(-t * 14) + lp_fast(rng.standard_normal(len(t)), 600) * np.exp(-t * 20) * 0.5
    return np.concatenate([a, clunk, make_door() * 0.7])


def make_win():
    notes = [(293.7, 0.25), (349.2, 0.25), (440, 0.25), (587.3, 0.5), (523.3, 0.25), (587.3, 0.9)]
    out = []
    for f, d in notes:
        s = organ(f, d + 0.1) * env(int((d + 0.1) * SR), 0.02, 0.15)
        out.append(s[: int(d * SR)])
    return reverb(np.concatenate(out), 1.5, 0.3)


def make_gameover():
    notes = [(293.7, 0.45), (277.2, 0.45), (261.6, 0.45), (246.9, 1.4)]
    out = []
    for f, d in notes:
        s = (organ(f, d) + organ(f * 1.19, d) * 0.6 + organ(f / 2, d) * 0.7) * env(int(d * SR), 0.03, 0.1)
        out.append(s)
    return reverb(np.concatenate(out), 2.0, 0.4)


def make_push():
    d = 0.45
    t = t_(d)
    x = bp_fast(rng.standard_normal(len(t)), 80, 900) * (0.6 + 0.4 * np.sin(2 * np.pi * 23 * t))
    return x * env(len(t), 0.03, 0.15)


def make_ghost():
    d = 1.8
    t = t_(d)
    f = 330 + 120 * np.sin(np.pi * t / d) - 60 * t
    ph = np.cumsum(f) / SR
    x = np.sin(2 * np.pi * ph) + 0.3 * np.sin(4 * np.pi * ph)
    x *= 1 + 0.3 * np.sin(2 * np.pi * 6 * t)
    x = x * env(len(t), 0.4, 0.7) + bp_fast(rng.standard_normal(len(t)), 300, 1200) * 0.15 * env(len(t), 0.4, 0.7)
    return reverb(x, 1.6, 0.45)


def make_goblin():
    d = 0.6
    t = t_(d)
    f = 140 + 40 * np.sin(2 * np.pi * 7 * t)
    ph = np.cumsum(f) / SR
    saw = 2 * (ph % 1) - 1
    x = bp_fast(saw, 300, 2500) + bp_fast(rng.standard_normal(len(t)), 900, 2600) * 0.3
    return x * env(len(t), 0.03, 0.2) * (0.6 + 0.4 * np.sin(2 * np.pi * 11 * t))


def make_bat():
    out = np.zeros(int(0.5 * SR))
    for st in (0, 0.14, 0.26):
        t = t_(0.06)
        s = np.sin(2 * np.pi * (4200 - 18000 * t) * t) * np.exp(-t * 50)
        i = int(st * SR)
        out[i:i + len(s)] += s
    t = t_(0.5)
    flap = bp_fast(rng.standard_normal(len(t)), 100, 800) * (np.sin(2 * np.pi * 12 * t) > 0.6) * 0.4
    return out + flap


def make_spider():
    d = 0.5
    t = t_(d)
    clicks = (rng.random(len(t)) > 0.997).astype(float)
    x = bp_fast(clicks, 1500, 7000) * 3 + bp_fast(rng.standard_normal(len(t)), 3000, 8000) * 0.08 * env(len(t), 0.1, 0.3)
    return x


def make_skeleton():
    out = np.zeros(int(0.7 * SR))
    for k in range(9):
        t = t_(0.06)
        f = 900 + rng.random() * 900
        s = (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 2.3 * t)) * np.exp(-t * 70)
        i = int(rng.random() * 0.6 * SR)
        out[i:i + len(s)] += s
    return out


def make_monster():
    d = 1.3
    t = t_(d)
    f = 70 + 15 * np.sin(2 * np.pi * 1.5 * t)
    ph = np.cumsum(f) / SR
    saw = 2 * (ph % 1) - 1
    x = lp_fast(saw, 600) + lp_fast(rng.standard_normal(len(t)), 500) * 0.6
    x *= 1 + 0.5 * np.sin(2 * np.pi * 18 * t)
    return reverb(x * env(len(t), 0.15, 0.4), 1.0, 0.25)


def make_vampire():
    """A low, breathy hiss with a whispered rasp: noise through a slowly
    closing band (a long 'hhhsss'), soft attack, a long tail."""
    d = 1.4
    t = t_(d)
    n = rng.standard_normal(len(t))
    hiss = bp_fast(n, 2600, 7200) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.7 * t + 0.4))
    breath = bp_fast(rng.standard_normal(len(t)), 300, 1400) * 0.5
    rasp = bp_fast(n, 900, 2200) * (1 + np.sign(np.sin(2 * np.pi * 34 * t))) * 0.18
    x = (hiss + breath + rasp) * env(len(t), 0.25, 0.7)
    return reverb(x, 0.9, 0.3)


def make_stairs():
    steps = []
    for k in range(5):
        t = t_(0.13)
        s = lp_fast(rng.standard_normal(len(t)), 900) * np.exp(-t * 35) + np.sin(2 * np.pi * (120 + k * 8) * t) * np.exp(-t * 30) * 0.5
        steps.append(np.concatenate([s, np.zeros(int(0.06 * SR))]))
    return np.concatenate(steps)


def make_rug():
    d = 0.5
    t = t_(d)
    x = bp_fast(rng.standard_normal(len(t)), 300, 3000) * env(len(t), 0.15, 0.25)
    return x


def make_hurt_sting():
    d = 0.7
    t = t_(d)
    x = sum(np.sin(2 * np.pi * f * t) for f in (466, 494, 523)) * np.exp(-t * 4)
    return reverb(x, 0.8, 0.3)


def make_door_creak():
    """A big old front door swinging open (~2.2 s): stick-slip hinge pulses
    (a jittery pulse train whose rate sweeps up and down, so the groan
    changes pitch) through a bank of wood/door-panel resonances, a thin iron
    squeal on top, and a soft knock as the door comes to rest."""
    g = np.random.default_rng(1887)
    d = 2.3
    n = int(d * SR)
    t = np.arange(n) / SR

    def contour(points):
        xs, ys = zip(*points)
        return np.interp(t, xs, ys)

    # pulse rate (Hz) of the main groan: slow start, rising strain, sagging end
    rate = contour([(0, 38), (0.12, 55), (0.35, 120), (0.6, 190), (0.8, 150), (1.0, 230),
                    (1.25, 260), (1.45, 170), (1.65, 95), (1.8, 60), (2.3, 40)])
    rate *= 1 + 0.10 * np.sin(2 * np.pi * 3.1 * t) + 0.05 * np.sin(2 * np.pi * 7.3 * t + 1)
    amp = contour([(0, 0), (0.04, 0.5), (0.2, 0.35), (0.4, 0.9), (0.75, 0.7), (1.0, 1.0),
                   (1.3, 0.85), (1.6, 0.6), (1.8, 0.25), (1.95, 0.0), (2.3, 0.0)])
    amp *= 0.75 + 0.25 * np.abs(np.sin(2 * np.pi * 1.7 * t))   # it catches and slips
    exc = np.zeros(n)
    ph = 0.0
    for i in range(n):
        ph += rate[i] * (1 + g.normal(0, 0.06)) / SR
        if ph >= 1.0:
            ph -= 1.0
            exc[i] += amp[i] * (0.7 + 0.3 * g.random())
    click = np.exp(-np.arange(int(0.0012 * SR)) / (0.00025 * SR))
    exc = np.convolve(exc, click)[:n]
    # resonant bodies: the oak leaf, the frame, the iron hinge
    modes = [(96, 0.16, 1.0), (152, 0.12, 0.8), (231, 0.10, 0.9), (347, 0.08, 0.7), (512, 0.06, 0.55),
             (733, 0.05, 0.45), (1046, 0.04, 0.35), (1580, 0.03, 0.25), (2350, 0.02, 0.15)]
    ln = int(0.4 * SR)
    tt = np.arange(ln) / SR
    ir = np.zeros(ln)
    for f, dec, a in modes:
        f *= 1 + g.normal(0, 0.01)
        ir += a * np.sin(2 * np.pi * f * tt + g.random() * 6.28) * np.exp(-tt / dec)
    body = np.fft.irfft(np.fft.rfft(exc, n + ln) * np.fft.rfft(ir, n + ln), n + ln)[:n]
    # rasp: friction noise riding on the pulses
    noise = bp_fast(g.standard_normal(n), 900, 4200)
    rasp = noise * lp_fast(np.abs(exc), 60) * 6
    # a thin iron squeal near the end of the swing
    sq_f = contour([(0, 900), (0.95, 900), (1.05, 1180), (1.25, 1420), (1.4, 1260), (1.55, 980), (2.3, 980)])
    sq_f *= 1 + 0.015 * np.sin(2 * np.pi * 23 * t)
    sq_a = contour([(0, 0), (0.95, 0), (1.05, 0.25), (1.3, 0.35), (1.5, 0.12), (1.6, 0), (2.3, 0)])
    sq = np.sin(2 * np.pi * np.cumsum(sq_f) / SR) * sq_a
    sq += 0.3 * np.sin(2 * np.pi * 2 * np.cumsum(sq_f) / SR) * sq_a
    # the leaf settles open: a soft wooden knock
    knock = np.zeros(n)
    k0 = int(1.9 * SR)
    kt = np.arange(n - k0) / SR
    knock[k0:] = (np.sin(2 * np.pi * 82 * kt) * np.exp(-kt / 0.09) * 0.9
                  + np.sin(2 * np.pi * 171 * kt) * np.exp(-kt / 0.05) * 0.5
                  + lp_fast(g.standard_normal(n - k0), 700) * np.exp(-kt / 0.02) * 0.8)
    x = body / (np.max(np.abs(body)) or 1) + 0.18 * rasp + 0.22 * sq + 0.45 * knock
    # a big stone hall: a short dark reverb
    rl = int(1.1 * SR)
    rir = lp_fast(g.standard_normal(rl), 2200) * np.exp(-np.arange(rl) / SR * 4.5)
    rir[0] = 0
    wet = np.fft.irfft(np.fft.rfft(x, n + rl) * np.fft.rfft(rir, n + rl), n + rl)[:n + rl]
    out = np.concatenate([x, np.zeros(rl)]) + 0.28 * wet / (np.max(np.abs(wet)) or 1) * np.max(np.abs(x))
    out = out[:int(2.4 * SR)]
    out *= env(len(out), 0.005, 0.3)
    return out


def make_skel_clack(seed, f0):
    """One bony footfall (~0.25 s): a dry knock of inharmonic bone modes,
    the boot's dull thud under it and a short loose rattle after."""
    r = np.random.default_rng(seed)          # its own generator: the others' noise is unchanged
    out = np.zeros(int(0.26 * SR))
    t = t_(0.09)
    knock = sum(a * np.sin(2 * np.pi * f0 * m * t + r.random() * 6.28) * np.exp(-t * k)
                for m, a, k in ((1.0, 1.0, 55), (1.71, 0.6, 75), (2.93, 0.35, 110), (4.4, 0.2, 150)))
    out[:len(t)] += knock
    thud = np.sin(2 * np.pi * 120 * t * (1 - 0.6 * t)) * np.exp(-t * 45) * 0.7
    out[:len(t)] += thud
    for k in range(5):                        # the rattle: smaller, higher, tailing off
        tt = t_(0.035)
        f = f0 * r.uniform(1.4, 2.6)
        c = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 140) * (0.45 * 0.7 ** k)
        i = int((0.03 + 0.028 * k + r.uniform(0, 0.012)) * SR)
        out[i:i + len(c)] += c
    out += bp_fast(r.standard_normal(len(out)), 1500, 6000) * 0.06 * np.exp(-t_(0.26)[:len(out)] * 30)
    return out * env(len(out), 0.001, 0.05)


def make_bat_flap():
    """A soft leathery wing beat (~0.2 s): a swell of band-passed air with a
    little papery snap at the bottom of the stroke."""
    r = np.random.default_rng(77)
    n = int(0.2 * SR)
    t = t_(0.2)[:n]
    swell = np.clip(t / 0.05, 0, 1) ** 1.5 * np.exp(-np.clip(t - 0.05, 0, None) * 28)
    air = bp_fast(r.standard_normal(n), 220, 1600) * swell
    snap = bp_fast(r.standard_normal(n), 900, 4000) * np.exp(-np.abs(t - 0.055) * 160) * 0.5
    whomp = np.sin(2 * np.pi * 85 * t) * swell * 0.35
    return (air + snap + whomp) * env(n, 0.002, 0.04)


MAKERS = {
    "title_theme": (make_title_theme, 0.7), "ambience": (make_ambience, 0.7),
    "creak1": (lambda: make_creak(1, 18), 0.6), "creak2": (lambda: make_creak(2, 11), 0.6),
    "door": (make_door, 0.6), "search": (make_search, 0.5), "key_found": (make_key_found, 0.7),
    "locked": (make_locked, 0.7), "unlock": (make_unlock, 0.8), "win": (make_win, 0.8),
    "gameover": (make_gameover, 0.8), "push": (make_push, 0.6), "ghost": (make_ghost, 0.6),
    "goblin": (make_goblin, 0.6), "bat": (make_bat, 0.5), "spider": (make_spider, 0.5),
    "skeleton": (make_skeleton, 0.6), "monster": (make_monster, 0.75), "stairs": (make_stairs, 0.6),
    "rug": (make_rug, 0.5), "hurt": (make_hurt_sting, 0.6),
    "door_creak": (make_door_creak, 0.85),
    "skel_clack1": (lambda: make_skel_clack(5, 1250), 0.7), "skel_clack2": (lambda: make_skel_clack(9, 1080), 0.7),
    "bat_flap": (make_bat_flap, 0.6), "vampire": (make_vampire, 0.45),
}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    for n in names or MAKERS:
        fn, peak = MAKERS[n]
        write(n, fn(), peak)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
