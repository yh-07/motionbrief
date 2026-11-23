# SPDX-License-Identifier: Apache-2.0
"""Cartoon Tech v2 components (REVIEW R-27/R-28).

Every component is a pure function Ctx -> SVG fragment (frame N is always identical).
Motion follows classic animation principles: anticipation + overshoot on entrances
(back_out), squash & stretch on impacts and fast moves, follow-through/stagger, idle secondary
motion (bob, blink, shimmer) so nothing on screen is ever fully static.
"""
from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable

from motionbrief.render.svg_canvas.canvas import Canvas
from motionbrief.render.svg_canvas.easing import Beats, clamp, ease_out_expo, lerp, progress
from motionbrief.render.svg_canvas.prims import (back_out, ball, body, contact_shadow, darken, ease_io, fit_size, g,
                                                  glow, lighten, lin, measure, mix, pill, rad, shadow_text, text,
                                                  wobble)


@dataclass
class Ctx:
    t: float
    t0: float
    t1: float
    frame: int
    props: dict[str, Any]
    beats: Beats
    palette: dict[str, Any]
    tokens: dict[str, Any]
    canvas: Canvas
    obj_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def local(self) -> float:
        return self.t - self.t0

    @property
    def p1(self) -> str:
        return self.palette["primary"][0]

    @property
    def p2(self) -> str:
        pr = self.palette["primary"]
        return pr[1] if len(pr) > 1 else pr[0]

    @property
    def accent(self) -> str:
        return self.palette["accent"]

    def ent(self) -> float:
        return self.beats.at("entrance") or self.t0

    def pop(self, delay: float = 0.0, dur: float = 0.55) -> float:
        """0..~1.1..1 overshoot entrance."""
        return back_out(progress(self.t, self.ent() + delay, dur)) if self.t >= self.ent() + delay else 0.0

    def impact(self) -> tuple[float, float]:
        """Squash & stretch on the impact beat -> (sx, sy)."""
        since = self.beats.since("impact", self.t)
        if since < 0 or since > 0.45:
            return 1.0, 1.0
        u = since / 0.45
        k = math.sin(u * math.pi * 2.2) * (1 - u) * 0.12
        return 1 + k, 1 - k


def text_width(s: str, size: float) -> float:  # used by G1 safe-area checks
    return measure(s, size, 900)


SKY_TOP, SKY_MID, SKY_LOW, HILL = "#FF7A59", "#FFB547", "#FFD7A1", "#22B8A0"


def scene_color(u: float, v: float) -> str:
    """A tiny sunset 'photo' used by the pixel components. u,v in [0,1]."""
    if v > 0.64 + 0.1 * math.sin(u * 3.0 + 0.6):
        return mix(HILL, "#0F5E57", (v - 0.62) / 0.38)
    if math.hypot(u - 0.68, v - 0.42) < 0.13:
        return "#FFF3C4"
    return mix(mix("#6D4AFF", SKY_TOP, v / 0.4), SKY_LOW, clamp((v - 0.35) / 0.3))


# =============================================================== mascot "小光"
def _interp_keys(keys: list, t: float, canvas: Canvas) -> tuple[float, float, float, float, float]:
    """keys: [[t, x, y, s], ...] (absolute s). Returns x, y, s, vx, vy (ease-in-out between keys)."""
    if not keys:
        return canvas.cx, canvas.cy, 1.0, 0.0, 0.0
    if t <= keys[0][0]:
        k = keys[0]
        return k[1], k[2], k[3] if len(k) > 3 else 1.0, 0.0, 0.0
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            span = max(b[0] - a[0], 1e-3)
            u = (t - a[0]) / span
            e = ease_io(u)
            de = 6 * u * (1 - u) / span
            sa = a[3] if len(a) > 3 else 1.0
            sb = b[3] if len(b) > 3 else 1.0
            return (lerp(a[1], b[1], e), lerp(a[2], b[2], e), lerp(sa, sb, e),
                    (b[1] - a[1]) * de, (b[2] - a[2]) * de)
    k = keys[-1]
    return k[1], k[2], k[3] if len(k) > 3 else 1.0, 0.0, 0.0


def _mood(c: Ctx) -> str:
    m = "happy"
    for at, mood in c.props.get("moods", []):
        if c.t >= at:
            m = mood
    return m


def photon_guide(c: Ctx) -> str:
    """The narrator-companion: a photon with big eyes. Blinks, bobs, squashes along velocity,
    looks where it is going, leaves a sparkle trail when moving fast."""
    x, y, s, vx, vy = _interp_keys(c.props.get("keys", []), c.t, c.canvas)
    appear = back_out(progress(c.t, c.ent(), 0.6)) if c.t >= c.ent() else 0.0
    if appear <= 0.001:
        return ""
    speed = math.hypot(vx, vy)
    bob = wobble(c.t, 0.55, 10) if speed < 60 else 0
    y += bob
    R = 62 * s
    # squash & stretch along motion
    st = clamp(speed / 2600, 0, 0.28)
    ang = math.degrees(math.atan2(vy, vx)) if speed > 1 else 0
    sx, sy = 1 + st, 1 - st * 0.6
    isx, isy = c.impact()
    out = []
    # trail
    if speed > 300:
        rng = random.Random(c.frame)
        for i in range(9):
            back = (i + 1) * 0.022
            tx, ty, _, _, _ = _interp_keys(c.props.get("keys", []), c.t - back, c.canvas)
            out.append(glow(tx + rng.uniform(-8, 8), ty + rng.uniform(-8, 8), R * (0.55 - i * 0.045),
                            c.accent, 0.35 * (1 - i / 9)))
    out.append(glow(x, y, R * 3.4, c.accent, 0.42))
    core = [ball(x, y, R, "#FFC94D", "#FFF7D6")]
    mood = _mood(c)
    # look direction
    lx = clamp(vx / 900, -1, 1) * R * 0.12
    ly = clamp(vy / 900, -1, 1) * R * 0.10
    look = c.props.get("look")
    if look and speed < 60:
        lx, ly = look[0] * R * 0.12, look[1] * R * 0.1
    # blink: every ~3.1 s, 0.14 s long (deterministic, per-object phase)
    ph = (c.t + (zlib.crc32(c.obj_id.encode("utf-8")) % 97) / 31) % 3.1
    lid = 1.0 if ph > 0.14 else abs(ph - 0.07) / 0.07
    eye_h = R * 0.30 * (1.25 if mood == "surprised" else 1.0) * max(lid, 0.08)
    for side in (-1, 1):
        ex, ey = x + side * R * 0.33, y - R * 0.08
        core.append(f'<ellipse cx="{ex:.1f}" cy="{ey:.1f}" rx="{R * 0.17:.1f}" ry="{eye_h:.1f}" fill="#FFFFFF"/>')
        if lid > 0.3:
            core.append(f'<circle cx="{ex + lx:.1f}" cy="{ey + ly + R * 0.03:.1f}" r="{R * 0.10:.1f}" fill="#2A1B5C"/>')
            core.append(f'<circle cx="{ex + lx - R * 0.04:.1f}" cy="{ey + ly - R * 0.03:.1f}" r="{R * 0.035:.1f}" '
                        f'fill="#FFFFFF"/>')
    # cheeks + mouth
    for side in (-1, 1):
        core.append(f'<ellipse cx="{x + side * R * 0.55:.1f}" cy="{y + R * 0.22:.1f}" rx="{R * 0.13:.1f}" '
                    f'ry="{R * 0.08:.1f}" fill="#FF7A8A" opacity="0.55"/>')
    my = y + R * 0.30
    if mood == "surprised":
        core.append(f'<ellipse cx="{x:.1f}" cy="{my + R * 0.04:.1f}" rx="{R * 0.09:.1f}" ry="{R * 0.12:.1f}" fill="#7A2E2E"/>')
    elif mood == "worried":
        core.append(f'<path d="M{x - R * 0.16:.1f},{my + R * 0.08:.1f} Q{x:.1f},{my - R * 0.06:.1f} '
                    f'{x + R * 0.16:.1f},{my + R * 0.08:.1f}" stroke="#7A2E2E" stroke-width="{R * 0.06:.1f}" '
                    f'fill="none" stroke-linecap="round"/>')
    else:
        core.append(f'<path d="M{x - R * 0.18:.1f},{my - R * 0.02:.1f} Q{x:.1f},{my + R * 0.2:.1f} '
                    f'{x + R * 0.18:.1f},{my - R * 0.02:.1f}" stroke="#7A2E2E" stroke-width="{R * 0.06:.1f}" '
                    f'fill="none" stroke-linecap="round"/>')
    tr = (f"translate({x:.1f},{y:.1f}) rotate({ang:.1f}) scale({sx * isx * appear:.4f},{sy * isy * appear:.4f}) "
          f"rotate({-ang:.1f}) translate({-x:.1f},{-y:.1f})")
    out.append(f'<g transform="{tr}">{"".join(core)}</g>')
    return "".join(out)


# =============================================================== phone + lenses
def lens_array(c: Ctx) -> str:
    n = int(c.props.get("count", 4))
    cols = 2
    rows = math.ceil(n / cols)
    r, gap = 118, 290
    bw, bh = cols * gap + 70, rows * gap + 70
    oy = float(c.props.get("y", c.canvas.cy))
    pe = c.pop(0, 0.6)
    out = [contact_shadow(c.canvas.cx, oy + bh / 2 + 40, bw * 0.6, 44, 0.5),
           body(c.canvas.cx - bw / 2, oy - bh / 2, bw, bh, 120, "#3B2F7A", shine=0.18, shade=0.35)]
    rev = c.beats.since("reveal", c.t)
    for i in range(n):
        col, row = i % cols, i // cols
        x = c.canvas.cx + (col - (cols - 1) / 2) * gap
        y = oy + (row - (rows - 1) / 2) * gap
        k = back_out(progress(c.t, c.ent() + 0.1 + 0.11 * i, 0.55)) if c.t >= c.ent() + 0.1 + 0.11 * i else 0
        tint = c.p1 if i % 2 == 0 else c.p2
        d1, ring = lin([(0, "#E8E6F5", 1), (0.5, "#8C86B0", 1), (1, "#3A3560", 1)], 0, 0, 1, 1)
        d2, glass = rad([(0, lighten(tint, 0.3), 1), (0.45, darken(tint, 0.45), 1), (1, "#0A0820", 1)],
                        fx=0.38, fy=0.32, r=0.62)
        L = [d1, d2, f'<circle cx="{x}" cy="{y}" r="{r}" fill="{ring}"/>',
             f'<circle cx="{x}" cy="{y}" r="{r * 0.86}" fill="#141032"/>',
             f'<circle cx="{x}" cy="{y}" r="{r * 0.78}" fill="{glass}"/>',
             f'<circle cx="{x}" cy="{y}" r="{r * 0.36}" fill="#07051A" opacity="0.85"/>',
             f'<circle cx="{x}" cy="{y}" r="{r * 0.55}" fill="none" stroke="{lighten(tint, 0.4)}" '
             f'stroke-opacity="0.35" stroke-width="3"/>',
             f'<ellipse cx="{x - r * 0.32:.1f}" cy="{y - r * 0.36:.1f}" rx="{r * 0.2:.1f}" ry="{r * 0.11:.1f}" '
             f'fill="#FFFFFF" opacity="0.75" transform="rotate(-35 {x - r * 0.32:.1f} {y - r * 0.36:.1f})"/>',
             f'<circle cx="{x + r * 0.28:.1f}" cy="{y + r * 0.3:.1f}" r="{r * 0.06:.1f}" fill="#FFFFFF" opacity="0.5"/>']
        if rev >= 0:  # glint sweeps across lenses in sequence
            a = clamp(1 - abs(rev - 0.12 * i - 0.25) / 0.25)
            if a > 0:
                L.append(glow(x - r * 0.2, y - r * 0.25, r * 0.9, "#FFFFFF", 0.55 * a))
        off = c.beats.since("exit", c.t)
        if off >= 0:  # "none of them can take a photo": lenses go dark together, then a red cross pops per lens
            L.append(f'<circle cx="{x}" cy="{y}" r="{r * 0.8:.1f}" fill="#05041A" '
                     f'opacity="{0.72 * ease_out_expo(clamp(off / 0.25)):.3f}"/>')
            kx = back_out(clamp((off - 0.12 - 0.06 * i) / 0.3), 1.6) if off > 0.12 + 0.06 * i else 0
            if kx > 0:
                arm = r * 0.5
                xs = "".join(f'<line x1="{x - arm}" y1="{y + sgn * arm}" x2="{x + arm}" y2="{y - sgn * arm}" '
                             f'stroke="#FF4D6A" stroke-width="22" stroke-linecap="round"/>' for sgn in (-1, 1))
                L.append(glow(x, y, r * 0.9, "#FF4D6A", 0.35) + g(xs, s=max(kx, 1e-3), ox=x, oy=y))
        out.append(g("".join(L), s=max(k, 1e-3), ox=x, oy=y))
    # flash LED
    out.append(ball(c.canvas.cx + bw / 2 - 60, oy - bh / 2 + 60, 18, "#FFE9B0"))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3) * (1 + wobble(c.t, 0.25, 0.006)), sx=isx, sy=isy, oy=oy,
             ty=wobble(c.t, 0.3, 6))


# =============================================================== pixel plate
BAYER = {"R": "#FF5A6E", "G": "#3EE08F", "B": "#4D8DFF"}


def _bayer(i: int, j: int) -> str:
    return ("R" if j % 2 == 0 else "G") if i % 2 == 0 else ("G" if j % 2 == 0 else "B")


GREEN_ON = "#3EE08F"


def raw_frame_plate(c: Ctx) -> str:
    """modes: photo | guess | mono | raw (ISP switch flips off, photo fades to raw) | bayer | demosaic"""
    n = int(c.props.get("cells", 8))
    mode = c.props.get("mode", "bayer")
    size = 92
    gap = 8
    W = n * size
    x0, y0 = c.canvas.cx - W / 2, float(c.props.get("y", c.canvas.cy - 60)) - W / 2
    ent = c.ent()
    rev = c.beats.at("reveal")
    out = [contact_shadow(c.canvas.cx, y0 + W + 50, W * 0.55, 40, 0.5),
           body(x0 - 26, y0 - 26, W + 52, W + 52, 44, "#2A2160", shine=0.12, shade=0.3)]
    for i in range(n):
        for j in range(n):
            ch = _bayer(i, j)
            u, v = (j + 0.5) / n, (i + 0.5) / n
            photo = scene_color(u, v)
            delay = (i + j) * 0.018
            pk = back_out(progress(c.t, ent + delay, 0.42)) if c.t >= ent + delay else 0.0
            if pk <= 0.001:
                continue
            flip = 1.0
            if mode == "photo":
                col = photo
            elif mode == "guess":
                w = clamp(((c.t - rev) / 1.2 * (n + 3) - (i + j) / 2)) if rev is not None and c.t >= rev else 0.0
                flip = abs(math.cos(w * math.pi))  # card flip: photo -> single colour tile
                col = photo if w < 0.5 else mix(BAYER[ch], "#1A1440", 0.15)
            elif mode == "mono":
                lum_ = lum(photo)
                fill = clamp(((c.t - (rev or ent)) / 1.6 * (n + 3) - (n - i)) / 2) if c.t >= (rev or ent) else 0
                col = mix("#1D1846", mix("#2B2560", "#E8E6F5", lum_), fill)
            elif mode == "raw":  # ISP switched off: the photo fades to the dark, grey, greenish raw read-out
                f = ease_io(progress(c.t, rev, 1.0)) if rev is not None and c.t >= rev else 0.0
                col = mix(photo, mix("#1B2A22", "#7E9C82", lum(photo) * 0.8), f)
            elif mode == "bayer":
                lum_ = lum(photo)
                col = mix(mix("#2B2560", "#E8E6F5", lum_), BAYER[ch], 0.75)
            else:  # demosaic
                base = mix(BAYER[ch], "#1A1440", 0.15)
                w = clamp((c.t - rev) / 1.5 * (n + 3) - j) if rev is not None and c.t >= rev else 0.0
                col = mix(base, photo, ease_out_expo(w))
            x, y = x0 + j * size, y0 + i * size
            cell = body(x + gap / 2, y + gap / 2, size - gap, size - gap, 16, col, shine=0.16, shade=0.18, rim=False)
            if mode == "guess" and rev is not None and c.t >= rev + 0.6:
                a = clamp((c.t - rev - 0.6 - (i * 7 + j * 3) % 11 * 0.03) / 0.3)
                if (i * 5 + j * 3) % 3 != 0:
                    cell += text(x + size / 2, y + size / 2, "?", 40, 900, "#FFFFFF", opacity=0.85 * a)
            out.append(g(cell, s=pk, sx=flip, ox=x + size / 2, oy=y + size / 2))
    # bayer legend: RGGB block highlight + G is half
    if mode == "bayer" and rev is not None and c.t >= rev:
        pr = ease_out_expo(progress(c.t, rev, 0.5))
        bx, by = x0 + 2 * size, y0 + 2 * size
        out.append(f'<rect x="{bx - 4}" y="{by - 4}" width="{2 * size + 8}" height="{2 * size + 8}" rx="22" '
                   f'fill="none" stroke="#FFFFFF" stroke-width="7" opacity="{pr:.3f}"/>')
        out.append(glow(bx + size, by + size, size * 1.6, "#FFFFFF", 0.18 * pr))
        ly = y0 + W + 120
        for k, ch in enumerate("RGGB"):
            lx = c.canvas.cx + (k - 1.5) * 128
            kk = back_out(progress(c.t, rev + 0.1 * k, 0.45)) if c.t >= rev + 0.1 * k else 0
            out.append(g(ball(lx, ly, 48, BAYER[ch]) + text(lx, ly, ch, 46, 900, "#FFFFFF"), s=max(kk, 1e-3),
                         ox=lx, oy=ly))
    if mode == "raw":  # the ISP switch on the plate's corner flips off on reveal
        off = ease_io(progress(c.t, rev, 0.3)) if rev is not None and c.t >= rev else 0.0
        sx_, sy_ = x0 + W - 90, y0 - 80
        out.append(body(sx_ - 70, sy_ - 34, 140, 68, 34, mix(GREEN_ON, "#4A4470", off), shine=0.25, shade=0.2)
                   + ball(lerp(sx_ + 36, sx_ - 36, off), sy_, 28, "#FFFFFF")
                   + text(sx_ - 120, sy_, "ISP", 40, 900, "#FFFFFF", "end"))
    if mode == "demosaic" and rev is not None:
        # neighbour arrows into a target pixel (shows interpolation)
        a = clamp((c.t - rev + 0.9) / 0.4) * clamp((rev + 0.2 - c.t) / 0.3 + 1)
        ti, tj = 3, 4
        tx, ty = x0 + tj * size + size / 2, y0 + ti * size + size / 2
        if a > 0.01:
            out.append(f'<rect x="{tx - size / 2 - 2}" y="{ty - size / 2 - 2}" width="{size + 4}" height="{size + 4}" '
                       f'rx="18" fill="none" stroke="#FFFFFF" stroke-width="6" opacity="{a:.3f}"/>')
            for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                sx_, sy_ = tx + dj * size, ty + di * size
                out.append(f'<line x1="{sx_:.1f}" y1="{sy_:.1f}" x2="{lerp(sx_, tx, 0.62):.1f}" y2="{lerp(sy_, ty, 0.62):.1f}" '
                           f'stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" opacity="{a:.3f}"/>')
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=y0 + W / 2, ty=wobble(c.t, 0.25, 5))


def lum(col: str) -> float:
    col = col.lstrip("#")
    r, gg, b = int(col[0:2], 16) / 255, int(col[2:4], 16) / 255, int(col[4:6], 16) / 255
    return 0.2126 * r + 0.7152 * gg + 0.0722 * b


# =============================================================== particles
def particle_stream(c: Ctx) -> str:
    mode = c.props.get("mode", "photons")
    if mode == "denoise":
        return denoise_card(c)
    n = int(c.props.get("count", 60))
    rng = random.Random(int(c.props.get("seed", 0)))
    pe = clamp(progress(c.t, c.ent(), 0.6))
    lt = c.local
    cols = [c.accent, lighten(c.accent, 0.4), c.p2, c.p1]
    out = []
    for k in range(n):
        speed = rng.uniform(0.18, 0.5)
        phase = rng.random()
        r = rng.uniform(5, 12)
        col = cols[k % len(cols)]
        if mode == "photons":
            x = rng.uniform(40, 1040) + wobble(lt, 0.2, 20, k)
            u = (phase + lt * speed) % 1.0
            y = lerp(-80, 2000, u)
            px, py = x - 30 * speed, y - 260 * speed
        else:  # converge
            ang = rng.uniform(0, 2 * math.pi)
            u = (phase + lt * speed * 0.8) % 1.0
            rr = lerp(950, 140, ease_out_expo(u))
            x, y = c.canvas.cx + math.cos(ang) * rr, c.canvas.cy + math.sin(ang) * rr
            rr2 = rr + 200 * (1 - u)
            px, py = c.canvas.cx + math.cos(ang) * rr2, c.canvas.cy + math.sin(ang) * rr2
        d, u_ = lin([(0, col, 0), (1, col, 0.55)], 0, 0, 1, 1) if px <= x else lin([(0, col, 0.55), (1, col, 0)], 0, 0, 1, 1)
        out.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{col}" '
                   f'stroke-opacity="0.28" stroke-width="{r * 0.9:.1f}" stroke-linecap="round"/>')
        tw = 0.6 + 0.4 * math.sin(lt * 6 + k)
        out.append(glow(x, y, r * 3.2, col, 0.35 * tw))
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.7:.1f}" fill="{lighten(col, 0.6)}"/>')
    return g("".join(out), opacity=pe)


def denoise_card(c: Ctx) -> str:
    W, H = 780, 900
    x0, y0 = c.canvas.cx - W / 2, c.canvas.cy - H / 2 - 40
    pe = c.pop(0, 0.6)
    rev = c.beats.at("reveal") or (c.t0 + 2)
    clean = ease_io(progress(c.t, rev, 1.8))
    sweep_x = x0 + W * clean
    rng = random.Random(7)
    out = [contact_shadow(c.canvas.cx, y0 + H + 40, W * 0.55, 40, 0.5)]
    d, sky = lin([(0, "#0E1240", 1), (1, "#3B2A7A", 1)])
    out.append(f'{d}<clipPath id="dnc"><rect x="{x0}" y="{y0}" width="{W}" height="{H}" rx="46"/></clipPath>'
               f'<g clip-path="url(#dnc)"><rect x="{x0}" y="{y0}" width="{W}" height="{H}" fill="{sky}"/>')
    out.append(glow(x0 + W * 0.72, y0 + H * 0.2, 150, "#FFF2C4", 0.6))
    out.append(ball(x0 + W * 0.72, y0 + H * 0.2, 54, "#FFF2C4"))
    for k in range(28):  # stars
        sx_, sy_ = x0 + rng.random() * W, y0 + rng.random() * H * 0.45
        out.append(f'<circle cx="{sx_:.1f}" cy="{sy_:.1f}" r="{rng.uniform(1.5, 3.5):.1f}" fill="#FFFFFF" '
                   f'opacity="{0.4 + 0.5 * abs(math.sin(c.t * 2 + k)):.2f}"/>')
    # city skyline with lit windows
    bx = x0
    while bx < x0 + W:
        bw = rng.uniform(80, 150)
        bh = rng.uniform(220, 420)
        by = y0 + H - bh
        out.append(body(bx + 4, by, bw - 8, bh + 40, 14, rng.choice(["#2A2160", "#312770", "#241C55"]),
                        shine=0.08, shade=0.2, rim=False))
        for wy in range(int(by + 30), int(y0 + H - 20), 46):
            for wx in range(int(bx + 22), int(bx + bw - 30), 34):
                if rng.random() < 0.55:
                    out.append(f'<rect x="{wx}" y="{wy}" width="16" height="22" rx="4" fill="#FFC94D" '
                               f'opacity="{rng.uniform(0.5, 0.95):.2f}"/>')
        bx += bw
    # noise: frame-varying RGB speckles, only right of the sweep
    fr = random.Random(c.frame * 7919 + 13)
    for k in range(int(c.props.get("count", 160))):
        x = x0 + rng.random() * W
        y = y0 + rng.random() * H
        if x < sweep_x:
            continue
        col = fr.choice(["#FFFFFF", "#FF5A6E", "#3EE08F", "#4D8DFF"])
        out.append(f'<rect x="{x + fr.uniform(-10, 10):.1f}" y="{y + fr.uniform(-10, 10):.1f}" width="12" height="12" '
                   f'rx="3" fill="{col}" opacity="{fr.uniform(0.35, 0.8):.2f}"/>')
    out.append("</g>")
    out.append(f'<rect x="{x0}" y="{y0}" width="{W}" height="{H}" rx="46" fill="none" stroke="#FFFFFF" '
               f'stroke-opacity="0.18" stroke-width="3"/>')
    if 0.01 < clean < 0.99:  # glowing squeegee
        out.append(glow(sweep_x, y0 + H / 2, 260, c.p2, 0.35))
        out.append(body(sweep_x - 9, y0 - 30, 18, H + 60, 9, lighten(c.p2, 0.3), shine=0.4, shade=0.1, rim=False))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 5))


# =============================================================== white balance
def color_sweep(c: Ctx) -> str:
    cast = c.props.get("from", "#FF9A3C")
    W, H = 560, 640
    x0, y0 = c.canvas.cx - W / 2 + 30, c.canvas.cy - H / 2 + 90
    pe = c.pop(0, 0.6)
    rev = c.beats.at("reveal") or (c.t0 + 2)
    k = ease_io(progress(c.t, rev, 1.4))
    paper = mix(mix("#FFFFFF", cast, 0.5), "#FFFFFF", k)
    out = [contact_shadow(c.canvas.cx, y0 + H + 30, W * 0.55, 40, 0.5),
           glow(c.canvas.cx, y0 + H * 0.4, 520, mix(cast, "#BFD7FF", k), 0.28),
           g(body(x0, y0, W, H, 30, paper, shine=0.0, shade=0.12), rot=-3, oy=y0 + H / 2)]
    for i in range(6):
        y = y0 + 140 + i * 88
        out.append(g(f'<rect x="{x0 + 70}" y="{y}" width="{W - 140 - (i % 2) * 120}" height="16" rx="8" '
                     f'fill="{darken(paper, 0.22, "#6B6480")}"/>', rot=-3, oy=y0 + H / 2))
    # colour-temperature slider
    sy = 560
    d, u = lin([(0, "#FF8A2A", 1), (0.5, "#FFFFFF", 1), (1, "#7FB2FF", 1)], 0, 0, 1, 0)
    out.append(f'{d}<rect x="{c.canvas.cx - 330}" y="{sy - 18}" width="660" height="36" rx="18" fill="{u}"/>')
    kx = lerp(c.canvas.cx - 300, c.canvas.cx, k)
    out.append(glow(kx, sy, 90, mix(cast, "#FFFFFF", k), 0.5))
    out.append(ball(kx, sy, 34, mix(cast, "#FFFFFF", k)))
    out.append(text(c.canvas.cx - 330, sy + 70, "烛光", 38, 700, "#FFD2A8", "start"))
    out.append(text(c.canvas.cx + 330, sy + 70, "阴天", 38, 700, "#BFD7FF", "end"))
    # lamp flame on the left that flickers
    fx, fy = 190, y0 + 120
    fl = 1 + wobble(c.t, 3.1, 0.06) + wobble(c.t, 7.3, 0.03)
    out.append(glow(fx, fy, 160 * fl, "#FF9A3C", 0.45 * (1 - 0.6 * k)))
    candle = (body(fx - 26, fy + 34, 52, 150, 12, "#F2E6D8", shine=0.3, shade=0.25)
              + f'<line x1="{fx}" y1="{fy + 34}" x2="{fx}" y2="{fy + 18}" stroke="#3A2A20" stroke-width="5"/>')
    flame = (f'<path d="M{fx},{fy - 60} Q{fx + 34},{fy - 4} {fx},{fy + 24} Q{fx - 34},{fy - 4} {fx},{fy - 60} Z" fill="#FFB547"/>'
             f'<path d="M{fx},{fy - 26} Q{fx + 14},{fy + 2} {fx},{fy + 16} Q{fx - 14},{fy + 2} {fx},{fy - 26} Z" fill="#FFF2C4"/>')
    out.append(g(candle + g(flame, sx=fl, sy=1 + (fl - 1) * 1.6, ox=fx, oy=fy + 20), opacity=1 - 0.5 * k))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy)


# =============================================================== HDR merge
def _scene_card(x: float, y: float, w: float, h: float, kind: str, cid: str) -> str:
    sky = {"short": "#4B3A9A", "long": "#FFFFFF", "merged": "#FF9A6E"}[kind]
    sky2 = {"short": "#2A1F66", "long": "#FFF1E0", "merged": "#7C5CFF"}[kind]
    ground = {"short": "#0C0A22", "long": "#3EE0B8", "merged": "#22B8A0"}[kind]
    house = {"short": "#151030", "long": "#FFE0A0", "merged": "#FFB547"}[kind]
    d, u = lin([(0, sky2, 1), (1, sky, 1)])
    s = [contact_shadow(x + w / 2, y + h + 26, w * 0.5, 30, 0.45), d,
         f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="34"/></clipPath>',
         f'<g clip-path="url(#{cid})"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{u}"/>']
    if kind != "long":
        s.append(glow(x + w * 0.72, y + h * 0.26, w * 0.35, "#FFF2C4", 0.6))
        s.append(ball(x + w * 0.72, y + h * 0.26, w * 0.1, "#FFF2C4"))
    s.append(f'<path d="M{x},{y + h * 0.66} Q{x + w * 0.5},{y + h * 0.56} {x + w},{y + h * 0.64} L{x + w},{y + h} '
             f'L{x},{y + h} Z" fill="{ground}"/>')
    s.append(body(x + w * 0.2, y + h * 0.46, w * 0.3, h * 0.2, 6, house, shine=0.1, shade=0.2, rim=False))
    s.append(f'<path d="M{x + w * 0.16},{y + h * 0.47} L{x + w * 0.35},{y + h * 0.34} L{x + w * 0.54},{y + h * 0.47} Z" '
             f'fill="{darken(house, 0.2)}"/>')
    s.append("</g>")
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="34" fill="none" stroke="#FFFFFF" '
             f'stroke-opacity="0.25" stroke-width="3"/>')
    return "".join(s)


def exposure_merge(c: Ctx) -> str:
    pe = c.pop(0, 0.6)
    rev = c.beats.at("reveal") or (c.t0 + 2)
    m = ease_io(progress(c.t, rev, 1.0))
    w, h = 410, 540
    y = c.canvas.cy - h / 2 - 40
    xl = lerp(c.canvas.cx - w - 34, c.canvas.cx - w / 2, m)
    xr = lerp(c.canvas.cx + 34, c.canvas.cx - w / 2, m)
    out = []
    if m < 0.98:
        out.append(g(_scene_card(xl, y, w, h, "short", "ems"), opacity=1 - m * 0.6, rot=lerp(-4, 0, m),
                     ox=xl + w / 2, oy=y + h / 2))
        out.append(g(_scene_card(xr, y, w, h, "long", "eml"), opacity=1 - m * 0.6, rot=lerp(4, 0, m),
                     ox=xr + w / 2, oy=y + h / 2))
        # the two labels converge with their cards: gone before they would overlap the merged label
        out.append(text(xl + w / 2, y + h + 80, "暗处看不清", 40, 800, "#C9C3F0", opacity=clamp(1 - 2.5 * m)))
        out.append(text(xr + w / 2, y + h + 80, "天空过曝", 40, 800, "#C9C3F0", opacity=clamp(1 - 2.5 * m)))
    if m > 0.25:
        k = back_out(progress(c.t, rev + 0.15, 0.55)) if c.t >= rev + 0.15 else 0
        out.append(glow(c.canvas.cx, y + h / 2, 480, c.accent, 0.25 * k))
        out.append(g(_scene_card(c.canvas.cx - w / 2, y, w, h, "merged", "emm"), s=max(k, 1e-3), oy=y + h / 2))
        out.append(text(c.canvas.cx, y + h + 80, "亮暗都看得清", 44, 900, c.accent, opacity=clamp(k) * clamp((m - 0.45) / 0.3)))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 5))


# =============================================================== pipeline
ICONS = {
    "去马赛克": "grid", "降噪": "sparkle", "白平衡": "sun", "色调映射": "contrast", "JPEG": "file",
}


def _icon(kind: str, x: float, y: float, col: str) -> str:
    if kind == "grid":
        return "".join(f'<rect x="{x - 22 + (k % 2) * 24}" y="{y - 22 + (k // 2) * 24}" width="20" height="20" rx="5" '
                       f'fill="{col}"/>' for k in range(4))
    if kind == "sparkle":
        return (f'<path d="M{x},{y - 26} Q{x + 4},{y - 4} {x + 26},{y} Q{x + 4},{y + 4} {x},{y + 26} '
                f'Q{x - 4},{y + 4} {x - 26},{y} Q{x - 4},{y - 4} {x},{y - 26} Z" fill="{col}"/>')
    if kind == "sun":
        rays = "".join(f'<line x1="{x + 18 * math.cos(a):.1f}" y1="{y + 18 * math.sin(a):.1f}" '
                       f'x2="{x + 28 * math.cos(a):.1f}" y2="{y + 28 * math.sin(a):.1f}" stroke="{col}" '
                       f'stroke-width="5" stroke-linecap="round"/>' for a in [i * math.pi / 4 for i in range(8)])
        return rays + f'<circle cx="{x}" cy="{y}" r="12" fill="{col}"/>'
    if kind == "contrast":
        return (f'<circle cx="{x}" cy="{y}" r="24" fill="none" stroke="{col}" stroke-width="5"/>'
                f'<path d="M{x},{y - 24} A24,24 0 0,1 {x},{y + 24} Z" fill="{col}"/>')
    return (f'<path d="M{x - 18},{y - 26} L{x + 8},{y - 26} L{x + 20},{y - 14} L{x + 20},{y + 26} L{x - 18},{y + 26} Z" '
            f'fill="{col}"/>')


def pipeline_flythrough(c: Ctx) -> str:
    stages = c.props.get("stages", ["A", "B", "C", "D"])
    focus = int(c.props.get("focus", -1))
    n = len(stages)
    bw, bh, gap = 640, 140, 190
    top = float(c.props.get("top", 360))
    ent = c.ent()
    imp = c.beats.at("impact")
    # stages are on screen from the entrance; runDelay only postpones lighting them (no empty opening frame)
    run_t0 = ent + 0.5 + float(c.props.get("runDelay", 0.0))
    per = float(c.props.get("perStage", 0.45))
    out = []
    # conveyor rail
    out.append(f'<rect x="{c.canvas.cx - 6}" y="{top}" width="12" height="{(n - 1) * gap}" rx="6" fill="#FFFFFF" opacity="0.12"/>')
    u_tok = clamp((c.t - run_t0) / (per * n)) if focus < 0 else (1.0 if imp and c.t >= imp else clamp((c.t - run_t0) / (per * n)))
    for i, name in enumerate(stages):
        y = top + i * gap
        pk = back_out(progress(c.t, ent + 0.08 * i, 0.5)) if c.t >= ent + 0.08 * i else 0
        lit_t = run_t0 + i * per
        lit = (focus < 0 and c.t >= lit_t) or (focus >= 0 and i == focus and imp is not None and c.t >= imp)
        base = c.accent if lit else (c.p1 if i % 2 == 0 else darken(c.p2, 0.15))
        box = (contact_shadow(c.canvas.cx, y + bh / 2 + 16, bw * 0.48, 22, 0.4)
               + (glow(c.canvas.cx, y, bw * 0.7, c.accent, 0.3) if lit else "")
               + body(c.canvas.cx - bw / 2, y - bh / 2, bw, bh, bh / 2, base, shine=0.24, shade=0.22)
               + (_icon(ICONS[name], c.canvas.cx - bw / 2 + 80, y, "#FFFFFF" if not lit else "#3A2200") if name in ICONS
                  else text(c.canvas.cx - bw / 2 + 80, y, str(i + 1), 52, 900, "#FFFFFF" if not lit else "#3A2200"))
               + text(c.canvas.cx + 30, y, name, 56, 900, "#FFFFFF" if not lit else "#3A2200"))
        pop = 1.0
        if lit:
            since = c.t - (lit_t if focus < 0 else imp)
            pop = 1 + 0.06 * math.sin(clamp(since / 0.3) * math.pi)
        out.append(g(box, s=max(pk, 1e-3) * pop, oy=y))
    if c.props.get("error"):  # a red error blob grows at every stage it passes (s15: errors compound)
        lit_n = sum(c.t >= run_t0 + i * per for i in range(n))
        if lit_n:
            ey = top + (lit_n - 1) * gap
            r = 22 * 1.45 ** lit_n
            out.append(glow(c.canvas.cx - bw / 2 - 60, ey, r * 2.2, "#FF4D6A", 0.4) + ball(c.canvas.cx - bw / 2 - 60, ey, r, "#FF4D6A"))
        if imp is not None and c.t >= imp:
            k = back_out(progress(c.t, imp, 0.45))
            yb = top + (n - 1) * gap + 210
            out.append(g(glow(c.canvas.cx, yb, 220, "#FF4D6A", 0.45) + ball(c.canvas.cx, yb, 110, "#FF4D6A")
                         + text(c.canvas.cx, yb, "!", 150, 900, "#FFFFFF"), s=max(k, 1e-3), oy=yb))
    # travelling photo token (camera pipelines; elsewhere only when asked for)
    if 0 < u_tok < 1 and c.props.get("token", any(st in ICONS for st in stages)):
        ty = top + u_tok * (n - 1) * gap
        tx = c.canvas.cx + bw / 2 + 70
        out.append(glow(tx, ty, 120, "#FFFFFF", 0.3))
        out.append(g(body(tx - 46, ty - 46, 92, 92, 18, "#FFF2C4", shine=0.3, shade=0.1)
                     + f'<path d="M{tx - 36},{ty + 26} L{tx - 8},{ty - 6} L{tx + 10},{ty + 12} L{tx + 22},{ty} '
                       f'L{tx + 36},{ty + 26} Z" fill="#22B8A0"/>'
                     + f'<circle cx="{tx + 18}" cy="{ty - 20}" r="9" fill="#FF9A3C"/>', rot=8 + wobble(c.t, 1.2, 4),
                     ox=tx, oy=ty))
    if focus < 0 and c.props.get("budget", True):
        by = top + (n - 1) * gap + 150
        out.append(body(c.canvas.cx - bw / 2, by, bw, 34, 17, "#241C55", shine=0.0, shade=0.2))
        fillw = max(34, bw * clamp((c.t - run_t0) / (per * n)))
        out.append(body(c.canvas.cx - bw / 2, by, fillw, 34, 17, c.accent, shine=0.3, shade=0.1, rim=False))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 4))


# =============================================================== hero chip
def chip_state(c: Ctx) -> dict:
    """Per-frame state for the Layer B (three.js) chip body; same beats as the 2.5D version."""
    since = c.beats.since("impact", c.t)
    return {"u": c.t - c.ent(), "flash": clamp(1 - since / 0.8) if since >= 0 else 0.0}


def chip_reveal(c: Ctx) -> str:
    """2.5D hero chip (also the WebGL fallback for the Layer B ChipReveal). With c.extra["layerB"] (a PNG data
    URI of the GPU-rendered toon body) only the body is swapped; rays/glow/shadow/shockwave stay SVG."""
    S = 460
    ent = c.ent()
    drop = back_out(progress(c.t, ent, 0.75), 1.2) if c.t >= ent else 0
    y_off = lerp(-900, 0, drop)
    bob = wobble(c.t - ent, 0.35, 10)
    x0, y0 = c.canvas.cx - S / 2, c.canvas.cy - S / 2
    base = c.p1
    out = []
    since = c.beats.since("impact", c.t)
    # light rays behind (rotate slowly, flare on impact)
    rays_a = 0.05 + (0.14 * clamp(1 - since / 1.2) if since >= 0 else 0)
    if c.t >= ent + 0.3:
        rot = (c.t - ent) * 8
        d, u = lin([(0, c.accent, rays_a), (1, c.accent, 0)], 0.5, 0, 0.5, 1)
        rays = "".join(f'<path d="M{c.canvas.cx},{c.canvas.cy} L{c.canvas.cx - 34},{c.canvas.cy - 820} L{c.canvas.cx + 34},{c.canvas.cy - 820} Z" fill="{u}" '
                       f'transform="rotate({rot + k * 30:.1f} {c.canvas.cx} {c.canvas.cy})"/>' for k in range(12))
        out.append(d + rays)
    out.append(glow(c.canvas.cx, c.canvas.cy, 620, base, 0.45))
    if since >= 0:
        out.append(glow(c.canvas.cx, c.canvas.cy, 700, c.accent, 0.5 * clamp(1 - since / 0.8)))
    chip = []
    dp, pin = lin([(0, "#F4F2FF", 1), (1, "#8C86B0", 1)])
    chip.append(dp)
    for k in range(8):
        off = -S / 2 + 46 + k * (S - 92) / 7
        for (px, py, w, h) in ((c.canvas.cx + off - 11, y0 - 40, 22, 52), (c.canvas.cx + off - 11, y0 + S - 12, 22, 52),
                               (x0 - 40, c.canvas.cy + off - 11, 52, 22), (x0 + S - 12, c.canvas.cy + off - 11, 52, 22)):
            chip.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{w}" height="{h}" rx="7" fill="{pin}"/>')
    chip.append(body(x0 + 14, y0 + 30, S, S, 56, darken(base, 0.55), shine=0, shade=0, rim=False))  # extrusion
    chip.append(body(x0, y0, S, S, 56, base, shine=0.3, shade=0.3))
    d = S * 0.6
    dx, dy = c.canvas.cx - d / 2, c.canvas.cy - d / 2
    chip.append(body(dx, dy, d, d, 26, "#120E33", shine=0.06, shade=0.1, rim=False))
    pulse = 0.35 + 0.35 * (0.5 + 0.5 * math.sin((c.t - ent) * 4))
    for k in range(1, 5):
        chip.append(f'<line x1="{dx + k * d / 5:.1f}" y1="{dy + 18}" x2="{dx + k * d / 5:.1f}" y2="{dy + d - 18}" '
                    f'stroke="{c.p2}" stroke-width="4" opacity="{pulse:.2f}"/>')
        chip.append(f'<line x1="{dx + 18}" y1="{dy + k * d / 5:.1f}" x2="{dx + d - 18}" y2="{dy + k * d / 5:.1f}" '
                    f'stroke="{c.p2}" stroke-width="4" opacity="{pulse:.2f}"/>')
    # signal dots running along traces
    for k in range(6):
        u = ((c.t - ent) * 0.7 + k / 6) % 1
        lane = 1 + k % 4
        if k % 2:
            px, py = dx + 18 + u * (d - 36), dy + lane * d / 5
        else:
            px, py = dx + lane * d / 5, dy + 18 + u * (d - 36)
        chip.append(glow(px, py, 26, c.p2, 0.7) + f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#E9FFFA"/>')
    label = c.props.get("label", "")
    if label:
        chip.append(shadow_text(c.canvas.cx, c.canvas.cy, label, 120, 900, "#FFFFFF"))
    isx, isy = c.impact()
    out.append(contact_shadow(c.canvas.cx, c.canvas.cy + S * 0.78, S * 0.6 * (0.5 + 0.5 * drop), 40, 0.55 * drop))
    if c.extra.get("layerB"):
        half = 450  # toon.ToonRenderer default size / 2, centred on the chip
        chip = [f'<image x="{c.canvas.cx - half}" y="{c.canvas.cy - half}" width="{2 * half}" height="{2 * half}" '
                f'href="{c.extra["layerB"]}"/>'] + ([shadow_text(c.canvas.cx, c.canvas.cy, label, 120, 900, "#FFFFFF")] if label else [])
    out.append(g("".join(chip), ty=y_off + bob, sx=isx, sy=isy))
    if 0 <= since <= 0.9:  # shockwave
        u = since / 0.9
        out.append(f'<circle cx="{c.canvas.cx}" cy="{c.canvas.cy}" r="{lerp(S * 0.55, S * 1.6, ease_out_expo(u)):.1f}" fill="none" '
                   f'stroke="{lighten(c.accent, 0.3)}" stroke-width="{lerp(22, 1, u):.1f}" opacity="{1 - u:.3f}"/>')
    return "".join(out)


# =============================================================== title + eye
def title_card(c: Ctx) -> str:
    st = c.tokens["typography"]["styles"][c.props.get("style", "headline")]
    y = c.tokens["typography"]["anchors"][c.props.get("anchor", "center")]
    s = c.props.get("text", "")
    k = c.pop(0, 0.6)
    size = fit_size(s, st["size"], st["weight"])  # long words shrink to fit instead of being cut
    w = measure(s, size, st["weight"])
    sweep = ease_out_expo(progress(c.t, c.ent() + 0.3, 0.6))
    sub = c.props.get("sub", "")
    body_ = (glow(c.canvas.cx, y, w * 0.8, c.accent, 0.25) + shadow_text(c.canvas.cx, y, s, size, st["weight"], st["color"])
             + body(c.canvas.cx - w / 2, y + size * 0.78, max(w * sweep, 1), 14, 7, c.accent, shine=0.3, shade=0, rim=False))
    if sub:
        body_ += text(c.canvas.cx, y + size * 1.5, sub, 44, 700, "#C9C3F0", opacity=clamp((c.t - c.ent() - 0.5) / 0.4))
    isx, isy = c.impact()
    return g(body_, s=max(k, 1e-3), sx=isx, sy=isy, oy=y)


def eye_blink_frames(c: Ctx) -> str:
    """Payoff visual: one human blink vs. the number of 33 ms frames that fit inside it."""
    ent = c.ent()
    pe = c.pop(0, 0.6)
    ex, ey = c.canvas.cx, c.canvas.cy - 260
    rev = c.beats.at("reveal") or (ent + 1.5)
    # slow blink during [rev, rev+1.2]
    u = clamp((c.t - rev) / 1.2)
    lid = math.sin(u * math.pi) if 0 < u < 1 else 0
    out = [glow(ex, ey, 360, c.p2, 0.25)]
    d, u_ = rad([(0, "#FFFFFF", 1), (1, "#D9D4F5", 1)], fx=0.4, fy=0.35)
    out.append(f'{d}<ellipse cx="{ex}" cy="{ey}" rx="260" ry="{150 * (1 - lid) + 4:.1f}" fill="{u_}"/>')
    if lid < 0.85:
        out.append(f'<clipPath id="eyec"><ellipse cx="{ex}" cy="{ey}" rx="260" ry="{150 * (1 - lid) + 4:.1f}"/></clipPath>'
                   f'<g clip-path="url(#eyec)">{ball(ex + wobble(c.t, 0.4, 20), ey, 100, c.p2)}'
                   f'<circle cx="{ex + wobble(c.t, 0.4, 20):.1f}" cy="{ey}" r="48" fill="#0B1033"/>'
                   f'<circle cx="{ex + wobble(c.t, 0.4, 20) - 22:.1f}" cy="{ey - 24}" r="16" fill="#FFFFFF"/></g>')
    out.append(f'<path d="M{ex - 280},{ey} Q{ex},{ey - 190 - 30 * (1 - lid)} {ex + 280},{ey}" stroke="#E9E6FF" '
               f'stroke-width="12" fill="none" stroke-linecap="round" opacity="0.8"/>')
    # frames popping in during the blink
    nmax = int(c.props.get("frames", 12))
    cols = 6
    for k in range(nmax):
        at = rev + 0.1 * k
        kk = back_out(progress(c.t, at, 0.35)) if c.t >= at else 0
        if kk <= 0:
            continue
        fx = c.canvas.cx + (k % cols - (cols - 1) / 2) * 140
        fy = c.canvas.cy + 160 + (k // cols) * 170
        col = c.accent if k < 3 else c.p1
        out.append(g(body(fx - 55, fy - 70, 110, 140, 18, col, shine=0.3, shade=0.2)
                     + text(fx, fy, f"{k + 1}", 50, 900, "#FFFFFF"), s=kk, ox=fx, oy=fy))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy)


COMPONENTS: dict[str, Callable[[Ctx], str]] = {
    "TitleCard": title_card,
    "LensArray": lens_array,
    "RawFramePlate": raw_frame_plate,
    "ParticleStream": particle_stream,
    "ColorSweep": color_sweep,
    "ExposureMerge": exposure_merge,
    "PipelineFlythrough": pipeline_flythrough,
    "ChipReveal": chip_reveal,
    "PhotonGuide": photon_guide,
    "EyeBlinkFrames": eye_blink_frames,
}

from motionbrief.render.svg_canvas import components_v3 as _v3  # noqa: E402  (needs the helpers above)

COMPONENTS.update(_v3.COMPONENTS)
from motionbrief.render.svg_canvas import components_generic as _gen  # noqa: E402

COMPONENTS.update(_gen.COMPONENTS)
for _mod in ("components_robot_arm", "components_concepts", "components_embodied", "components_phone_interior", "components_chip_stage",
             "components_explainer", "components_compare"):  # topic packs
    COMPONENTS.update(__import__(f"motionbrief.render.svg_canvas.{_mod}", fromlist=["COMPONENTS"]).COMPONENTS)

# components with a Layer B (GPU) body: per-frame state for the three.js page
LAYER_B_STATE = {"ChipReveal": chip_state}
