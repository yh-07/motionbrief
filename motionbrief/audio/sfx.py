# SPDX-License-Identifier: Apache-2.0
"""Procedural, original sound design (no third-party samples => no licensing risk).
All generators are deterministic (fixed seeds)."""
from __future__ import annotations

import numpy as np

SR = 48000


def _env(n: int, a: float, d: float) -> np.ndarray:
    t = np.arange(n) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    return att * np.exp(-np.maximum(t - a, 0) / max(d, 1e-4))


def _noise(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1, 1, n)


def _lp(x: np.ndarray, k: float) -> np.ndarray:
    """one-pole low-pass, k in (0,1] (smaller = darker)."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += k * (v - acc)
        y[i] = acc
    return y


def bass_hit() -> np.ndarray:
    n = int(SR * 0.9)
    t = np.arange(n) / SR
    f = 42 + 90 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * _env(n, 0.003, 0.32)
    click = _lp(_noise(n, 1), 0.3) * _env(n, 0.0005, 0.012)
    return 0.9 * body + 0.35 * click


def whoosh() -> np.ndarray:
    n = int(SR * 0.45)
    t = np.arange(n) / SR
    x = _noise(n, 2)
    k = 0.02 + 0.25 * np.sin(np.pi * t / t[-1]) ** 2
    y = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += k[i] * (x[i] - acc)
        y[i] = acc
    return 1.6 * y * np.sin(np.pi * t / t[-1]) ** 1.5


def ui_tick() -> np.ndarray:
    n = int(SR * 0.08)
    t = np.arange(n) / SR
    return 0.5 * np.sin(2 * np.pi * 2400 * t) * _env(n, 0.001, 0.015)


def digital_blip() -> np.ndarray:
    n = int(SR * 0.22)
    t = np.arange(n) / SR
    f = np.where(t < 0.07, 880, 1320)
    sq = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR))
    return 0.22 * sq * _env(n, 0.002, 0.08)


def riser() -> np.ndarray:
    n = int(SR * 1.6)
    t = np.arange(n) / SR
    f = 180 * (2 ** (t * 1.6))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    air = _lp(_noise(n, 3), 0.15)
    amp = (t / t[-1]) ** 2
    return amp * (0.35 * tone + 0.5 * air)


def shutter() -> np.ndarray:
    n = int(SR * 0.18)
    a = _lp(_noise(n, 4), 0.6) * _env(n, 0.0005, 0.01)
    b = np.zeros(n)
    off = int(SR * 0.06)
    b[off:] = (_lp(_noise(n - off, 5), 0.5) * _env(n - off, 0.0005, 0.015))
    return 0.9 * (a + b)


# ------------------------------------------------------------ tonal transition cues (in key with the bed)
# Transitions get *pitched* cues built from the chord playing at that moment instead of noise whooshes, which
# grow tiring when every cut has one (learned in other procedural-video work; see docs/BENCHMARK.md).
BED_BPM = 92.0
BED_GAIN = 4.0  # level of the bed, calibrated so its RMS matches the previous bed (see tests/test_music_bed.py)
BED_CHORDS = [  # I-V-vi-IV in C major, voiced 220-660 Hz
    (261.63, 329.63, 392.00),  # C
    (293.66, 392.00, 493.88),  # G (D4 G4 B4)
    (220.00, 261.63, 329.63),  # Am
    (261.63, 349.23, 440.00),  # F
]


def chord_at(t: float, bpm: float = BED_BPM) -> tuple[float, float, float]:
    """The music_bed chord sounding at time t (one chord per 4-beat bar)."""
    return BED_CHORDS[int(t / (4 * 60 / bpm)) % 4]


def glide(notes) -> np.ndarray:
    """Quiet triangle glide up a fifth (zoom-through)."""
    n = int(SR * 0.5)
    t = np.arange(n) / SR
    f = notes[0] * 2 * (1.5 ** (t / t[-1]))
    ph = np.cumsum(f) / SR
    tri = 2 * np.abs(2 * (ph % 1) - 1) - 1
    return 0.32 * tri * np.sin(np.pi * t / t[-1]) ** 1.2


def bloom(notes) -> np.ndarray:
    """Soft bell chord (mask / iris reveal)."""
    n = int(SR * 1.3)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, f in enumerate(notes):
        f = f * 4
        partials = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t * 6)
        out += partials * np.exp(-t * 3.2) * (1 - 0.15 * k)
    return 0.16 * out * np.clip(t / 0.004, 0, 1)


def swell(notes, seconds: float = 0.9) -> np.ndarray:
    """Reversed-pad swell that grows and stops dead on the cut (place it to *end* at the cut)."""
    n = int(SR * seconds)
    t = np.arange(n) / SR
    pad = sum(_pad_voice(f, t) for f in notes)
    env = (t / t[-1]) ** 2.2
    env[-int(0.004 * SR):] *= np.linspace(1, 0, int(0.004 * SR))
    return 0.13 * pad * env


def harp(notes, up: bool = True) -> np.ndarray:
    """Quick in-key pluck run."""
    seq = [f * m for m in (2, 4) for f in notes]
    seq = seq if up else seq[::-1]
    step = int(SR * 0.04)
    n = step * len(seq) + int(SR * 0.5)
    out = np.zeros(n)
    for k, f in enumerate(seq):
        m = n - k * step
        tt = np.arange(m) / SR
        out[k * step:] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 9)
    return 0.12 * out


def soft_impact() -> np.ndarray:
    """Short, dry tap for non-structural slams: a quick 240->160 Hz knock, no long low pitch drop (that read
    as a 'woo' under the narration)."""
    n = int(SR * 0.18)
    t = np.arange(n) / SR
    f = 160 + 80 * np.exp(-t * 40)
    return 0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.05)


TONAL = {"glide": glide, "bloom": bloom, "swell": swell, "harp": harp}


SFX = {
    "bass_hit": bass_hit,
    "soft_impact": soft_impact,
    "whoosh": whoosh,
    "ui_tick": ui_tick,
    "digital_blip": digital_blip,
    "riser": riser,
    "shutter": shutter,
}
# which stem each cue goes to (multitrack requirement)
STEM_OF = {
    "bass_hit": "impact",
    "soft_impact": "impact",
    "glide": "transition",
    "bloom": "transition",
    "swell": "transition",
    "harp": "transition",
    "whoosh": "transition",
    "riser": "transition",
    "ui_tick": "fx",
    "digital_blip": "fx",
    "shutter": "fx",
}


def reverb(x: np.ndarray, seconds: float = 1.6, wet: float = 0.22, seed: int = 9) -> np.ndarray:
    """Synthetic hall: exponentially decaying, low-passed stereo-ish noise IR (deterministic)."""
    from scipy.signal import fftconvolve
    n = int(SR * seconds)
    t = np.arange(n) / SR
    ir = np.random.default_rng(seed).normal(0, 1, n) * np.exp(-t * 6.9 / seconds)
    ir = np.convolve(ir, np.ones(6) / 6, mode="same")  # darken
    ir[: int(0.012 * SR)] = 0                           # pre-delay
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    y = fftconvolve(x, ir)[: len(x)]
    return (1 - wet) * x + wet * y * 0.9


def _pad_voice(f: float, t: np.ndarray, detune: float = 0.004) -> np.ndarray:
    """Warm 'saw' pad: a few harmonics (soft roll-off) x 3 detuned oscillators."""
    out = np.zeros_like(t)
    for d in (-detune, 0.0, detune):
        for h in range(1, 7):
            out += np.sin(2 * np.pi * f * (1 + d) * h * t + h) / (h ** 1.6)
    return out / 3


def _groove(t: np.ndarray, beat: float, seconds: float) -> np.ndarray:
    """Clean rhythm: closed shaker-like tick on every 8th (high-passed noise, 20 ms decay) and a soft
    60->45 Hz kick on beats 1 and 3. No snare. Deterministic (fixed seed)."""
    out = np.zeros_like(t)
    noise = np.random.default_rng(7).standard_normal(len(t))
    tick = np.diff(noise, prepend=0.0)  # first difference = crude high-pass
    for k in range(int(seconds / (beat / 2)) + 1):  # 8th-note ticks
        t0 = k * beat / 2
        m = (t >= t0) & (t < t0 + 0.04)
        out[m] += tick[m] * np.exp(-(t[m] - t0) * 50) * 0.022
    for b in range(0, int(seconds / beat) + 1, 2):  # kick on beats 1 and 3 of each bar
        t0 = b * beat
        m = (t >= t0) & (t < t0 + 0.12)
        dt = t[m] - t0
        out[m] += np.sin(2 * np.pi * (45 + 15 * np.exp(-dt * 40)) * dt) * np.exp(-dt * 20) * 0.12
    return out


def _strike(f: float, tt: np.ndarray, decay: float) -> np.ndarray:
    """Soft electric-piano / marimba tone: sine + 2nd and 3rd harmonic, 6 ms attack, exponential decay."""
    env = np.minimum(tt / 0.006, 1.0) * np.exp(-tt * decay)
    return (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt) + 0.1 * np.sin(6 * np.pi * f * tt)) * env


def music_bed(seconds: float, bpm: float = BED_BPM, groove: bool = False) -> np.ndarray:
    """Original, license-clean score bed in C major (I-V-vi-IV): soft chord stabs on beats 1 and 3, a light
    plucked 8th-note arpeggio an octave up, and a short small-hall reverb. No pads, no swells. groove=True adds
    a soft shaker tick and kick on the beats. Everything except the kick is high-passed at 120 Hz."""
    from scipy.signal import butter, sosfilt

    n = int(SR * seconds)
    t = np.arange(n) / SR
    beat = 60 / bpm
    bar = 4 * beat
    out = np.zeros(n)

    def add(t0: float, sig: np.ndarray) -> None:
        i0 = int(t0 * SR)
        if i0 < n:
            m = min(len(sig), n - i0)
            out[i0:i0 + m] += sig[:m]

    stab_len = int(1.1 * SR)
    stab_t = np.arange(stab_len) / SR
    pluck_len = int(0.4 * SR)
    pluck_t = np.arange(pluck_len) / SR
    arp_idx = (0, 1, 2, 1, 0, 2, 1, 2)  # 8th notes, chord tones one octave up
    for b in range(int(seconds / bar) + 1):
        ch = BED_CHORDS[b % 4]
        for pos, lvl in ((0, 1.0), (2, 0.8)):  # beats 1 and 3
            stab = sum(_strike(f, stab_t, 6.0) for f in ch)
            add(b * bar + pos * beat, 0.085 * lvl * stab)
        for k, idx in enumerate(arp_idx):
            pluck = np.sin(2 * np.pi * 2 * ch[idx] * pluck_t) + 0.2 * np.sin(4 * np.pi * 2 * ch[idx] * pluck_t)
            pluck *= np.minimum(pluck_t / 0.003, 1.0) * np.exp(-pluck_t * 12)
            add(b * bar + k * beat / 2, 0.04 * pluck)
    sos = butter(2, 120, btype="highpass", fs=SR, output="sos")
    tonal = sosfilt(sos, out)
    fade = np.clip(t / 1.2, 0, 1) * np.clip((seconds - t) / 2.5, 0, 1)
    bed = reverb(tonal * fade, 0.8, 0.13)
    if groove:  # rhythm stays dry, from the second bar on: the hall reverb would smear ticks and kicks
        bed = bed + _groove(t, beat, seconds) * (t > bar) * fade
    return _soft_limit(bed * BED_GAIN)


def _soft_limit(x: np.ndarray, knee: float = 0.4) -> np.ndarray:
    """Linear below `knee`, smooth tanh roll-off above it: keeps the bed body untouched and peaks below 1.0."""
    a = np.abs(x)
    over = np.maximum(a - knee, 0.0)
    return np.sign(x) * (np.minimum(a, knee) + (1 - knee) * np.tanh(over / (1 - knee)))
