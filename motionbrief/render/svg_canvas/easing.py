# SPDX-License-Identifier: Apache-2.0
"""Deterministic easing + beat helpers (mirror of motion/tokens.ts)."""
from __future__ import annotations

import math

from motionbrief.paths import load_tokens


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def ease_out_expo(t: float) -> float:
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_in_cubic(t: float) -> float:
    t = clamp(t)
    return t * t * t


def spring(t: float) -> float:
    t = clamp(t)
    return 1 - math.exp(-6 * t) * math.cos(10 * t)


def impact_pop(t: float) -> float:
    a, b, c = load_tokens()["impactPop"]
    if t <= 0:
        return a
    if t < 0.5:
        return a + (b - a) * (t / 0.5)
    if t < 1:
        return b + (c - b) * ((t - 0.5) / 0.5)
    return c


EASINGS = {
    "easeOutExpo": ease_out_expo,
    "easeInCubic": ease_in_cubic,
    "spring": spring,
    "linear": clamp,
}


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def progress(t: float, start: float, dur: float) -> float:
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


class Beats:
    """Motion beats for one target: query progress of entrance/reveal/impact/exit."""

    def __init__(self, beats: list[tuple[str, float]], scene_start: float):
        self.beats = beats
        self.scene_start = scene_start
        self.durs = load_tokens()["durations"]

    def at(self, grammar: str) -> float | None:
        for g, a in self.beats:
            if g == grammar:
                return a
        return None

    def p(self, grammar: str, t: float, ease: str = "easeOutExpo", default_at: float | None = None) -> float:
        a = self.at(grammar)
        if a is None:
            a = default_at if default_at is not None else self.scene_start
        return EASINGS[ease](progress(t, a, self.durs.get(grammar, 0.4)))

    def impact_scale(self, t: float) -> float:
        a = self.at("impact")
        if a is None or t < a:
            return 1.0
        return impact_pop(progress(t, a, self.durs["impact"]))

    def since(self, grammar: str, t: float) -> float:
        a = self.at(grammar)
        return -1.0 if a is None else t - a
