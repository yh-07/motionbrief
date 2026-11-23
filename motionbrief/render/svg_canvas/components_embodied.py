# SPDX-License-Identifier: Apache-2.0
"""Embodied-AI explainer components (Cartoon Tech v2): RobotBody, Sim2Real, DataScale.

Pure functions of (Ctx, t): no wall clock, randomness only via random.Random(fixed seed).
Content band: x 110-970, y 480-1400. Every mode has a populated first frame and animates on beats.
"""
from __future__ import annotations

import math
import random

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.components_v3 import GREEN, RED, _clip, _k, _u, mark
from motionbrief.render.svg_canvas.easing import clamp, ease_out_expo, lerp, progress
from motionbrief.render.svg_canvas.prims import (ball, body, contact_shadow, darken, ease_io, g, glow,
                                                 lighten, lin, mix, pill, rad, text, wobble)

PI2 = 2 * math.pi
INK = "#0B1033"
PINK = "#F0A8FF"
WHITE = "#FFFFFF"
SKIN = "#F2C6A8"
WATER = "#3D8BFF"
FOOT_Y = 1350  # design-space feet; the robot transform lifts them to y 1380
HEAD_CY = 735
ROBOT_S = 1.17  # single-robot modes are authored in design space and scaled about the feet
GRID = "#22D3B6"
SIM_WALLS = ["#2A1F7A", "#1D3A6E", "#3B2A8F", "#16556B"]
SIM_TABLES = ["#7C5CFF", "#22D3B6", "#4B7BFF", "#B49BFF"]
REAL_WALL, REAL_TABLE, REAL_CUBE = "#F2D6A8", "#8B4F2B", "#E8703A"
# continent blobs (cx, cy, rx, ry) as fractions of the map box
MAP_CONT = [(0.17, 0.34, 0.11, 0.10), (0.12, 0.22, 0.07, 0.05), (0.20, 0.46, 0.06, 0.07),
            (0.26, 0.70, 0.06, 0.14), (0.50, 0.35, 0.07, 0.08), (0.49, 0.56, 0.09, 0.13),
            (0.52, 0.72, 0.05, 0.07), (0.68, 0.30, 0.14, 0.13), (0.76, 0.52, 0.06, 0.07),
            (0.84, 0.74, 0.07, 0.06)]


def _beat(c: Ctx, name: str, off: float) -> float:
    """Beat time, or entrance + off when the storyboard gives none."""
    v = c.beats.at(name)
    return v if v is not None else c.ent() + off


def _limb(x0: float, y0: float, length: float, ang: float, w: float, col: str) -> str:
    """Rounded limb hung from (x0, y0); positive ang swings the tip toward -x."""
    return (f'<g transform="translate({x0:.1f},{y0:.1f}) rotate({ang:.2f})">'
            + body(-w / 2, 0, w, length, w / 2, col, shine=0.2, shade=0.25, rim=False)
            + ball(0, length, w * 0.62, lighten(col, 0.12))
            + "</g>")


def _arm_pts(bx: float, by: float, l1: float, l2: float, a1: float, a2: float):
    """Two-link arm: a1 from vertical (deg), a2 relative to the upper link. Returns (elbow, tip)."""
    e = (bx + l1 * math.sin(math.radians(a1)), by - l1 * math.cos(math.radians(a1)))
    a = math.radians(a1 + a2)
    return e, (e[0] + l2 * math.sin(a), e[1] - l2 * math.cos(a))


# ================================================================ RobotBody
def _robot(c: Ctx, arm_l: float, arm_r: float, head_glow: float, visor: float) -> str:
    """Friendly humanoid in design space (feet at FOOT_Y, centred on CX, 700 px tall)."""
    p1, p2 = c.p1, c.p2
    out = [contact_shadow(c.canvas.cx, FOOT_Y + 12, 190, 28, 0.45), glow(c.canvas.cx, HEAD_CY, 230, PINK, head_glow)]
    for side in (-1, 1):
        lx = c.canvas.cx + side * 72
        out.append(body(lx - 40, 1130, 80, 200, 36, p2, shine=0.2, shade=0.25))
        out.append(body(lx - 52, 1316, 104, 34, 17, p1, shine=0.25, shade=0.2))
    out.append(ball(c.canvas.cx - 160, 872, 34, p1))
    out.append(ball(c.canvas.cx + 160, 872, 34, p1))
    out.append(_limb(c.canvas.cx - 160, 872, 236, arm_l, 58, p2))
    out.append(_limb(c.canvas.cx + 160, 872, 236, -arm_r, 58, p2))
    out.append(body(c.canvas.cx - 26, 812, 52, 46, 12, p2, shine=0.1, shade=0.2, rim=False))
    out.append(body(c.canvas.cx - 150, 846, 300, 300, 72, p1))
    out.append(body(c.canvas.cx - 70, 880, 140, 120, 28, darken(p1, 0.2), shine=0.1, shade=0.1, rim=False))
    out.append(ball(c.canvas.cx, 940, 26, p2))
    out.append(ball(c.canvas.cx - 118, 736, 18, p2))
    out.append(ball(c.canvas.cx + 118, 736, 18, p2))
    out.append(body(c.canvas.cx - 110, 650, 220, 170, 78, p1))
    out.append(f'<rect x="{c.canvas.cx - 82}" y="690" width="164" height="92" rx="44" '
               f'fill="{mix(INK, p2, 0.15 + 0.55 * visor)}"/>')
    for side in (-1, 1):
        ex = c.canvas.cx + side * 38
        out.append(glow(ex, 736, 46, p2, 0.6 * visor))
        out.append(ball(ex, 736, 15, p2))
    return "".join(out)


def _brain(cx: float, cy: float, r: float, col: str) -> str:
    """Lumpy pink-violet brain with two fold strokes."""
    n = 48
    pts = []
    for i in range(n):
        a = PI2 * i / n
        rr = r * (1 + 0.07 * math.sin(5 * a + 0.4) + 0.05 * math.sin(9 * a + 1.0))
        pts.append(f"{cx + rr * math.cos(a) * 1.12:.1f},{cy + rr * math.sin(a) * 0.9:.1f}")
    d, u = rad([(0, "#FFE3FA", 1), (0.5, col, 1), (1, darken(col, 0.3), 1)], cx=0.5, cy=0.5, r=0.6, fx=0.35, fy=0.3)
    fold = darken(col, 0.4)
    folds = (f'<path d="M{cx - r * 0.55:.1f},{cy - r * 0.05:.1f} '
             f'q{r * 0.3:.1f},{-r * 0.35:.1f} {r * 0.55:.1f},{-r * 0.05:.1f} '
             f'M{cx - r * 0.2:.1f},{cy + r * 0.3:.1f} q{r * 0.3:.1f},{-r * 0.3:.1f} {r * 0.6:.1f},{-r * 0.05:.1f}" '
             f'fill="none" stroke="{fold}" stroke-width="{r * 0.09:.1f}" stroke-linecap="round" opacity="0.7"/>')
    return d + f'<path d="M{" L".join(pts)} Z" fill="{u}"/>' + folds


def _brain_drop(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    imp = max(_beat(c, "impact", 1.7), rev + 0.05)
    if c.t < rev:
        by = 600 + 8 * wobble(c.t, 0.6, 1.0)
    else:
        f = clamp((c.t - rev) / (imp - rev))
        by = lerp(600, HEAD_CY, f * f)  # gravity: accelerate into the head
    sink = _u(c, imp, 0.35)
    out = [_robot(c, 6 * wobble(c.t, 0.5, 1.0), -6 * wobble(c.t, 0.5, 1.0), 0.2 + 0.5 * sink,
                  0.25 + 0.75 * _u(c, imp, 0.3))]
    alpha = 1 - sink
    if alpha > 0.01:
        out.append(glow(c.canvas.cx, by, 130, PINK, 0.5 * alpha))
        out.append(g(_brain(c.canvas.cx, by, 62, "#F07BE0"), s=1 - 0.75 * sink, ox=c.canvas.cx, oy=by, opacity=alpha))
    return "".join(out)


def _lag(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    imp = max(_beat(c, "impact", rev + 0.5), rev + 0.05)
    lean = -7 * ease_io(_u(c, rev, 0.6))
    tremble = 2.2 * math.sin(PI2 * 13 * c.t)  # stiff, fast jitter
    lit = _u(c, rev, 0.4)
    out = [g(_robot(c, 16 + tremble, 16 + 0.8 * tremble, 0.4 + 0.45 * lit, 0.35 + 0.6 * lit),
             rot=lean, ox=c.canvas.cx, oy=FOOT_Y)]
    if c.t >= rev:
        rise = ease_out_expo(progress(c.t, rev, imp - rev))
        off = (1 - rise) * 460
        walls = list(c.props.get("walls", ["数据", "动作", "练习"]))[:3]
        cols = [c.p1, c.p2, c.accent]
        for i, label in enumerate(walls):
            wx = c.canvas.cx + (i - 1) * 220
            out.append(g(body(wx - 95, 1000, 190, 350, 34, cols[i], shine=0.22, shade=0.25)
                         + text(wx, 1062, str(label), 46, 900, WHITE), ty=off))
    return "".join(out)


def _piece(x: float, y: float, label: str, col: str) -> str:
    """Jigsaw-like piece: rounded square with a knob on top."""
    return (ball(x, y - 50, 18, col) + body(x - 50, y - 50, 100, 100, 22, col, shine=0.25, shade=0.2)
            + text(x, y, label, 36, 900, WHITE))


def _puzzle(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    imp = max(_beat(c, "impact", rev + 0.5), rev + 0.05)
    lock = _k(c, imp, 0.45)
    items = list(c.props.get("items", ["常识", "手感", "练习"]))[:3]
    finals = [(c.canvas.cx - 108, 985), (c.canvas.cx, 985), (c.canvas.cx + 108, 985)]
    starts = [(245, 985), (c.canvas.cx, 1270), (835, 985)]
    cols = [c.p1, c.p2, c.accent]
    out = [_robot(c, 10, 10, 0.2 + 0.35 * lock, 0.2 + 0.6 * lock)]
    if lock > 0.001:
        out.append(glow(c.canvas.cx, 985, 230, c.p2, 0.35 * lock))
    for i, label in enumerate(items):
        fx, fy = finals[i]
        sx, sy = starts[i]
        f = clamp((c.t - (rev + 0.12 * i)) / 0.5) if c.t >= rev else 0.0
        e = ease_out_expo(f)
        out.append(_piece(lerp(sx, fx, e), lerp(sy, fy, e), str(label), cols[i]))
    out.append(mark(c.canvas.cx + 200, 830, True, _k(c, imp, 0.45), 52))
    return "".join(out)


def _cards(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    items = list(c.props.get("items", ["杯子", "毛巾", "门把手"]))[:5]
    starts = [(245, 990), (835, 990), (245, 1200), (835, 1200), (c.canvas.cx, 1290)]
    gap, dur = 0.45, 0.8
    arrived = 0.0
    cards = []
    for i, label in enumerate(items):
        sx, sy = starts[i]
        t0 = rev + gap * i
        f = clamp((c.t - t0) / dur) if c.t >= rev else 0.0
        e = ease_io(f)
        x = lerp(sx, c.canvas.cx, e)
        y = lerp(sy, HEAD_CY, e) - 90 * math.sin(math.pi * e)
        s = lerp(1.0, 0.25, e)
        op = 1 - clamp((e - 0.7) / 0.3)
        if c.t >= rev:
            arrived += clamp((c.t - (t0 + dur)) / 0.2)
        if op <= 0.01:
            continue
        col = c.p1 if i % 2 == 0 else c.p2
        card = body(-70, -48, 140, 96, 26, col, shine=0.25, shade=0.2) + text(0, 0, str(label), 38, 900, WHITE)
        cards.append(g(card, tx=x, ty=y, s=s, ox=0, oy=0, opacity=op))
    out = [_robot(c, 8 * wobble(c.t, 0.4, 1.0), -8 * wobble(c.t, 0.4, 1.0), 0.3 + 0.16 * arrived,
                  min(1.0, 0.2 + 0.2 * arrived))]
    return "".join(out + cards)


def _mini(c: Ctx, x: float, y: float, s: float, kind: int, ph: float) -> str:
    """Small robot at feet (x, y): 0 single arm, 1 dual arm, 2 four-legged dog."""
    p1, p2 = c.p1, c.p2
    a = 20 * math.sin(PI2 * 0.5 * c.t + ph)
    out = [contact_shadow(x, y + 4 * s, 110 * s, 12 * s, 0.4)]
    if kind == 2:
        for dx in (-70, -36, 36, 70):
            out.append(body(x + (dx - 10) * s, y - 70 * s, 20 * s, 74 * s, 8 * s, p1, shine=0.1, shade=0.2, rim=False))
        out.append(body(x - 95 * s, y - 150 * s, 190 * s, 92 * s, 40 * s, p2))
        out.append(body(x + 60 * s, y - 222 * s, 80 * s, 72 * s, 30 * s, p1))
        out.append(ball(x + 100 * s, y - 196 * s, 9 * s, INK))
        return "".join(out)
    arms = [(46, -a)] if kind == 0 else [(46, -a), (-46, a)]
    for dx, ang in arms:
        out.append(_limb(x + dx * s, y - 222 * s, 150 * s, ang, 22 * s, p2))
    out.append(body(x - 46 * s, y - 232 * s, 92 * s, 212 * s, 30 * s, p1, shine=0.2, shade=0.25))
    out.append(body(x - 38 * s, y - 304 * s, 76 * s, 70 * s, 26 * s, p2, shine=0.25, shade=0.2))
    out.append(body(x - 28 * s, y - 292 * s, 56 * s, 24 * s, 10 * s, INK, shine=0, shade=0, rim=False))
    return "".join(out)


SKILL = [0.92, 0.74, 0.85, 0.6, 0.8]


def _robot_fleet(c: Ctx) -> str:
    """Fleet in final coordinates (no design transform): robots ~1.6x the previous size."""
    rev = _beat(c, "reveal", 1.2)
    n = max(2, min(5, int(c.props.get("count", 3))))
    slot = 860.0 / n
    base_y = 1100.0
    s = min(1.5, slot / 200)
    xs = [110 + slot * (i + 0.5) for i in range(n)]
    lit = _u(c, rev, 0.6)
    out = []
    for i in range(n - 1):
        y = base_y - 200 * s
        x1, x2 = xs[i] + 70 * s, xs[i + 1] - 70 * s
        out.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{c.p2}" stroke-width="6" '
                   f'stroke-linecap="round" stroke-dasharray="14 12" stroke-dashoffset="{-c.t * 60:.1f}" '
                   f'opacity="{0.25 + 0.7 * lit:.2f}"/>')
    for i, x in enumerate(xs):
        out.append(_mini(c, x, base_y, s, i % 3, i * 1.3))
        bw = slot * 0.62
        lvl = SKILL[i % len(SKILL)] * ease_io(_u(c, rev + 0.15 * i, 0.7))
        out.append(f'<rect x="{x - bw / 2:.1f}" y="1240" width="{bw:.1f}" height="26" rx="13" fill="#241C55"/>')
        if lvl > 0.01:
            col = c.p2 if i % 2 == 0 else c.accent
            out.append(f'<rect x="{x - bw / 2:.1f}" y="1240" width="{max(26.0, bw * lvl):.1f}" height="26" rx="13" '
                       f'fill="{col}"/>')
    return "".join(out)


def robot_body(c: Ctx) -> str:
    mode = str(c.props.get("mode", "brain_drop"))
    isx, isy = c.impact()
    if mode == "fleet":
        return g(_robot_fleet(c), sx=isx, sy=isy, oy=c.canvas.cy)
    fn = {"brain_drop": _brain_drop, "lag": _lag, "cards": _cards, "puzzle": _puzzle}.get(mode, _brain_drop)
    # design space -> final: scale about the feet, lift so feet land at y 1380
    return g(g(fn(c), s=ROBOT_S, ox=c.canvas.cx, oy=FOOT_Y, ty=30), sx=isx, sy=isy, oy=c.canvas.cy)


# ================================================================ Sim2Real
def _surf(x: float, y: float, w: float, h: float, col: str, sim: bool, r: float = 6.0) -> str:
    if sim:
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" fill="{col}" '
                f'stroke="{GRID}" stroke-opacity="0.85" stroke-width="2"/>')
    return body(x, y, w, h, r, col, shine=0.25, shade=0.2, rim=False)


def _poly(pts: list[tuple[float, float]], col: str, stroke: str | None = None) -> str:
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
    st = f' stroke="{stroke}" stroke-width="2" stroke-linejoin="round"' if stroke else ""
    return f'<path d="{d}" fill="{col}"{st}/>'


def _cube_geo(x0: float, y0: float, W: float, H: float):
    cs = W * 0.13
    return x0 + W * 0.40, y0 + H * 0.58, cs, cs * 0.35  # px, table-top y, cube size, depth


def _cube_box(x0: float, y0: float, W: float, H: float, pad: float = 14.0):
    px, ty, cs, d = _cube_geo(x0, y0, W, H)
    side = cs + d + 2 * pad
    return px - pad, ty - cs - d - pad, side, side


def _room(x0: float, y0: float, W: float, H: float, sim: bool, table: str, wall: str, cube: str,
          lamp: float) -> str:
    """Room in absolute coords: back wall, floor, table with a cube, and a lamp.
    sim = flat cyan-violet with a grid floor; real = warm colours, soft shadows and light."""
    px, ty, cs, d = _cube_geo(x0, y0, W, H)
    fy = y0 + H * 0.62
    floor_h = y0 + H - fy
    out = []
    if sim:
        out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{W:.1f}" height="{H:.1f}" fill="{wall}"/>')
        out.append(f'<rect x="{x0:.1f}" y="{fy:.1f}" width="{W:.1f}" height="{floor_h:.1f}" fill="#1A1452"/>')
        seg = [f"M{x0:.1f},{fy:.1f} H{x0 + W:.1f}"]
        for k in range(1, 5):
            seg.append(f"M{x0:.1f},{fy + floor_h * k / 5:.1f} H{x0 + W:.1f}")
        for k in range(7):
            xx = x0 + W * k / 6
            seg.append(f"M{xx:.1f},{fy:.1f} V{y0 + H:.1f}")
        out.append(f'<path d="{" ".join(seg)}" stroke="{GRID}" stroke-opacity="0.5" stroke-width="2" fill="none"/>')
    else:
        dw, uw = lin([(0, lighten(wall, 0.2), 1), (1, wall, 1)], 0, 0, 0, 1)
        df, uf = lin([(0, "#D9A46B", 1), (1, "#B8733F", 1)], 0, 0, 0, 1)
        out.append(f'{dw}<rect x="{x0:.1f}" y="{y0:.1f}" width="{W:.1f}" height="{fy - y0:.1f}" fill="{uw}"/>')
        out.append(f'{df}<rect x="{x0:.1f}" y="{fy:.1f}" width="{W:.1f}" height="{floor_h:.1f}" fill="{uf}"/>')
    tx, tw, th = x0 + W * 0.20, W * 0.56, H * 0.05
    leg_bot = y0 + H * 0.9
    for lx in (tx + tw * 0.08, tx + tw * 0.84):
        out.append(_surf(lx, ty + th, W * 0.035, leg_bot - ty - th, table, sim, 3))
    out.append(_surf(tx, ty, tw, th, table, sim))
    out.append(_poly([(px, ty - cs), (px + d, ty - cs - d), (px + cs + d, ty - cs - d), (px + cs, ty - cs)],
                     lighten(cube, 0.3), GRID if sim else None))
    out.append(_poly([(px + cs, ty - cs), (px + cs + d, ty - cs - d), (px + cs + d, ty - d), (px + cs, ty)],
                     darken(cube, 0.3), GRID if sim else None))
    out.append(f'<rect x="{px:.1f}" y="{ty - cs:.1f}" width="{cs:.1f}" height="{cs:.1f}" fill="{cube}"'
               + (f' stroke="{GRID}" stroke-width="2"' if sim else "") + "/>")
    if not sim:
        out.append(contact_shadow(tx + tw / 2, leg_bot, tw * 0.6, H * 0.035, 0.5))
        out.append(contact_shadow(px + cs * 0.6, ty + 2, cs * 0.9, cs * 0.16, 0.6))
    lx = x0 + W * 0.86
    ly = y0 + H * 0.14
    out.append(f'<rect x="{lx - 3:.1f}" y="{ly:.1f}" width="6" height="{fy - ly:.1f}" '
               f'fill="{"#9B8CFF" if sim else "#5A3A22"}"/>')
    inner = (f'<path d="M{lx - 22:.1f},{ly:.1f} L{lx + 22:.1f},{ly:.1f} L{lx + 46:.1f},{ly + 50:.1f} '
             f'L{lx - 46:.1f},{ly + 50:.1f} Z" fill="{"#B49BFF" if sim else "#FFC36B"}"/>')
    if not sim:
        inner = glow(lx, ly + 60, 120, "#FFD27A", 0.5) + inner
    out.append(g(inner, rot=lamp, ox=lx, oy=ly))
    return "".join(out)


def _card(cid: str, x0: float, y0: float, W: float, H: float, sim: bool, table: str, wall: str,
          lamp: float = 0.0, tilt: float = 0.0) -> str:
    room = _room(x0, y0, W, H, sim, table, wall, GRID if sim else REAL_CUBE, lamp)
    return _clip(cid, x0, y0, W, H, 26, g(room, rot=tilt, ox=x0 + W / 2, oy=y0 + H / 2))


def _sim_flicker(c: Ctx, x0: float, y0: float, W: float, H: float) -> str:
    """One SIM room whose table/wall/lamp/tilt jump every 0.35 s (seeded per step)."""
    step = int(max(0.0, c.t - c.ent()) / 0.35)
    rng = random.Random(7300 + step)
    table = rng.choice(SIM_TABLES)
    wall = rng.choice(SIM_WALLS)
    lamp = rng.uniform(-38, 38)
    tilt = rng.uniform(-6, 6)
    return _card("sim_flk", x0, y0, W, H, True, table, wall, lamp, tilt)


def _mini_room(c: Ctx, x: float, y: float, w: float, h: float, ph: float) -> str:
    """Tiny SIM room with a tiny arm (for the grid cells)."""
    fy = y + h * 0.62
    out = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="#1B1660"/>',
           f'<rect x="{x:.1f}" y="{fy:.1f}" width="{w:.1f}" height="{y + h - fy:.1f}" rx="6" fill="#1A1452"/>']
    seg = [f"M{x:.1f},{fy + (y + h - fy) * 0.5:.1f} H{x + w:.1f}"]
    for k in range(5):
        xx = x + w * k / 4
        seg.append(f"M{xx:.1f},{fy:.1f} V{y + h:.1f}")
    out.append(f'<path d="{" ".join(seg)}" stroke="{GRID}" stroke-opacity="0.5" stroke-width="1.5" fill="none"/>')
    out.append(f'<rect x="{x + w * 0.15:.1f}" y="{y + h * 0.5:.1f}" width="{w * 0.7:.1f}" height="{h * 0.07:.1f}" '
               f'rx="3" fill="#7C5CFF"/>')
    out.append(f'<rect x="{x + w * 0.44:.1f}" y="{y + h * 0.5 - w * 0.16:.1f}" width="{w * 0.16:.1f}" '
               f'height="{w * 0.16:.1f}" fill="{GRID}"/>')
    out.append(f'<circle cx="{x + w * 0.86:.1f}" cy="{y + h * 0.2:.1f}" r="{w * 0.05:.1f}" fill="#B49BFF"/>')
    base = (x + w * 0.1, y + h * 0.94)
    a1 = 35 + 15 * math.sin(PI2 * 0.7 * c.t + ph)
    a2 = -25 + 20 * math.sin(PI2 * 0.7 * c.t + ph + 1.1)
    e, tip = _arm_pts(base[0], base[1], h * 0.42, h * 0.36, a1, a2)
    out.append(f'<path d="M{base[0]:.1f},{base[1]:.1f} L{e[0]:.1f},{e[1]:.1f} L{tip[0]:.1f},{tip[1]:.1f}" '
               f'fill="none" stroke="{GRID}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    out.append(f'<circle cx="{tip[0]:.1f}" cy="{tip[1]:.1f}" r="5" fill="#FFB547"/>')
    return "".join(out)


def _grid(c: Ctx) -> str:
    ent = c.ent()
    cw, ch, gap = 164.0, 120.0, 8.0
    x0 = c.canvas.cx - (5 * cw + 4 * gap) / 2
    y0 = 540.0
    out = []
    for i in range(30):
        r, col = divmod(i, 5)
        x = x0 + col * (cw + gap)
        y = y0 + r * (ch + gap)
        k = _k(c, ent + 0.02 * i, 0.3)
        if k <= 0.001:
            continue
        out.append(g(_mini_room(c, x, y, cw, ch, i * 0.9), s=max(k, 1e-3), ox=x + cw / 2, oy=y + ch / 2))
    return "".join(out)


GAP_W, GAP_H, GAP_Y = 400.0, 420.0, 700.0


def _gap(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    k = ease_io(_u(c, rev, 0.6))
    W, H, y0 = GAP_W, GAP_H, GAP_Y
    xl, xr = 110.0, 560.0
    out = [_card("gap_sim", xl - 20 * k, y0, W, H, True, SIM_TABLES[0], SIM_WALLS[0], -20),
           _card("gap_real", xr + 20 * k, y0, W, H, False, REAL_TABLE, REAL_WALL, 15)]
    mid = 535.0
    rng = random.Random(4242)
    pts = [(mid + rng.uniform(-14, 14), y0 - 20 + i * (H + 40) / 10) for i in range(11)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    if k > 0.001:
        out.append(f'<path d="{d}" fill="none" stroke="#05071A" stroke-width="{4 + 26 * k:.1f}" stroke-linejoin="round"/>')
        out.append(f'<path d="{d}" fill="none" stroke="{RED}" stroke-width="{2 + 3 * k:.1f}" '
                   f'stroke-opacity="{0.4 + 0.6 * k:.2f}" stroke-linejoin="round"/>')
    else:
        out.append(f'<line x1="{mid}" y1="{y0}" x2="{mid}" y2="{y0 + H}" stroke="#FFFFFF" stroke-opacity="0.35" '
                   f'stroke-width="3" stroke-dasharray="10 10"/>')
    out.append(text(xl + W / 2, y0 + H + 40, "仿真", 40, 900, "#C9C3F0"))
    out.append(text(xr + W / 2, y0 + H + 40, "现实", 40, 900, "#FFE2B0"))
    out.append(pill(c.canvas.cx, y0 + H + 150, "现实差距", 46, RED, opacity=_u(c, rev + 0.3, 0.4)))
    return "".join(out)


def _randomize(c: Ctx) -> str:
    W, H = 560.0, 500.0
    step = int(max(0.0, c.t - c.ent()) / 0.35)
    return (_sim_flicker(c, c.canvas.cx - W / 2, 560, W, H)
            + pill(c.canvas.cx, 1240, f"花样 ×{step + 1}", 50, c.p1))


def _transfer(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    imp = max(_beat(c, "impact", rev + 0.5), rev + 0.05)
    W, H, y0 = GAP_W, GAP_H, GAP_Y
    k = ease_io(_u(c, rev, 0.6))
    out = [_sim_flicker(c, lerp(c.canvas.cx - W / 2, 110, k), y0, W, H)]
    if c.t >= rev:
        rx = lerp(1050, 560, ease_out_expo(_u(c, rev, 0.5)))
        out.append(_card("tr_real", rx, y0, W, H, False, REAL_TABLE, REAL_WALL, 12))
        if c.t >= imp:
            bx, by, bw, bh = _cube_box(rx, y0, W, H)
            sc = lerp(1.5, 1.0, ease_out_expo(_u(c, imp, 0.15)))
            out.append(g(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="8" fill="none" '
                         f'stroke="{GREEN}" stroke-width="7"/>', s=sc, ox=bx + bw / 2, oy=by + bh / 2))
            out.append(mark(bx + bw, by, True, _k(c, imp, 0.45), 46))
            err = str(c.props.get("error", "1.5 cm"))
            if err:
                op = _u(c, imp, 0.3)
                cxr = rx + W / 2
                ry = y0 + H + 30  # ruler under the card, clear of the table
                ticks = " ".join(f"M{cxr - 150 + 300 * j / 10:.1f},{ry + 2:.1f} v10" for j in range(11))
                out.append(body(cxr - 150, ry, 300, 22, 6, "#FFB547", shine=0.2, shade=0.2, rim=False))
                out.append(f'<path d="{ticks}" stroke="#FFFFFF" stroke-width="2" fill="none"/>')
                out.append(pill(cxr, ry + 80, err, 40, "#241C55", opacity=op))
    return "".join(out)


def _door(x: float, top: float, w: float, h: float, col: str) -> str:
    return (body(x - w / 2, top, w, h, 20, col, shine=0.2, shade=0.2)
            + body(x - w / 2 + 14, top + 18, w - 28, h - 18, 14, darken(col, 0.25), shine=0, shade=0.1, rim=False)
            + ball(x + w * 0.3, top + h * 0.55, 10, "#FFE9A8"))


def _cook(c: Ctx, x: float, feet: float, s: float) -> str:
    ph = c.t * 7.0
    sw = math.sin(ph)
    yb = feet - abs(math.cos(ph)) * 7 * s
    out = [contact_shadow(x, feet + 4, 46 * s, 9 * s, 0.4),
           _limb(x - 14 * s, yb - 96 * s, 96 * s, 22 * sw, 28 * s, "#2A1F7A"),
           _limb(x + 14 * s, yb - 96 * s, 96 * s, -22 * sw, 28 * s, "#2A1F7A"),
           body(x - 44 * s, yb - 200 * s, 88 * s, 124 * s, 30 * s, WHITE, shine=0.15, shade=0.12),
           _limb(x - 44 * s, yb - 190 * s, 92 * s, 20 * sw, 22 * s, WHITE),
           _limb(x + 44 * s, yb - 190 * s, 92 * s, -20 * sw, 22 * s, WHITE),
           ball(x, yb - 236 * s, 38 * s, "#FFD2A0"),
           body(x - 36 * s, yb - 312 * s, 72 * s, 60 * s, 22 * s, WHITE, shine=0.2, shade=0.1),
           ball(x, yb - 318 * s, 26 * s, WHITE)]
    return "".join(out)


def _kitchen(x: float, y: float, w: float, h: float) -> str:
    out = [body(x, y, w, h, 30, "#F5E2C4", shine=0.1, shade=0.1, rim=False)]
    cab_w = (w - 60) / 4
    for i in range(4):
        cx0 = x + 30 + i * cab_w
        out.append(body(cx0 + 6, y + 28, cab_w - 12, 112, 14, "#C48A55", shine=0.15, shade=0.2, rim=False))
        out.append(f'<rect x="{cx0 + cab_w / 2 - 16:.1f}" y="{y + 60:.1f}" width="32" height="8" rx="4" fill="#FFF2D8"/>')
    out.append(body(x + w * 0.56, y + 104, 120, 66, 22, "#5B4B8A", shine=0.2, shade=0.2, rim=False))
    out.append(body(x, y + 170, w, 34, 10, REAL_TABLE, shine=0.2, shade=0.2, rim=False))
    out.append(text(x + w / 2, y + h - 36, "家里的厨房", 40, 900, "#5A3A22"))
    return "".join(out)


def _doors(c: Ctx) -> str:
    ent = c.ent()
    imp = max(_beat(c, "impact", 3.0), ent + 0.1)
    f = clamp((c.t - ent) / (imp - ent))
    x = lerp(130, 800, f)
    out = []
    for i, col in enumerate([c.p1, c.p2, c.accent, "#FF6B9A"]):
        out.append(_door(230 + i * 170, 620, 130, 300, col))
    out.append('<rect x="110" y="960" width="860" height="3" fill="#FFFFFF" opacity="0.25"/>')
    out.append(_cook(c, x, 960, 0.78))
    k = _k(c, imp, 0.5)
    if k > 0.001:
        out.append(g(_kitchen(110, 1040, 800, 300), s=k, ox=c.canvas.cx, oy=1190))
    return "".join(out)


def sim_to_real(c: Ctx) -> str:
    fn = {"grid": _grid, "gap": _gap, "randomize": _randomize, "transfer": _transfer,
          "doors": _doors}.get(str(c.props.get("mode", "gap")), _gap)
    isx, isy = c.impact()
    return g(fn(c), sx=isx, sy=isy, oy=c.canvas.cy)


# ================================================================ DataScale
def _mountain(c: Ctx) -> str:
    ent = c.ent()
    imp = max(_beat(c, "impact", 2.2), ent + 0.1)
    palette = [c.p1, c.p2, "#A9B8FF", "#7FE8D6"]
    rng = random.Random(911)
    base, rows, rh = 1380.0, 24, 27.0
    out = []
    idx = 0
    for r in range(rows):
        rw = 820.0 * (1 - 0.82 * r / (rows - 1))
        n = max(2, int(rw / 68))
        y_target = base - r * rh - 16
        for i in range(n):
            bw = rng.uniform(46, 96)
            x = c.canvas.cx - rw / 2 + (i + 0.5) * rw / n + rng.uniform(-8, 8)
            col = palette[rng.randrange(len(palette))]
            t0 = ent + 0.012 * idx
            idx += 1
            f = ease_io(clamp((c.t - t0) / 0.5))
            if f <= 0:
                continue
            y = lerp(y_target - 420, y_target, f)
            out.append(f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="16" rx="8" fill="{col}" '
                       f'opacity="0.9"/>')
    label = str(c.props.get("label", "15T+"))
    out.append(g(text(c.canvas.cx, 640, label, 72, 900, c.accent), s=max(_k(c, imp, 0.45), 1e-3), oy=640))
    return "".join(out)


def _ocean(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    imp = max(_beat(c, "impact", rev + 0.6), rev + 0.05)
    x0, x1 = 110.0, 730.0
    out = []
    bands = [(c.p2, 26, 1060, 1.0, 0.0, 0.9), (c.p1, 30, 1130, 0.8, 1.7, 0.8),
             (lighten(c.p1, 0.2), 26, 1210, 1.2, 3.1, 0.75), (c.p2, 22, 1300, 0.9, 4.2, 0.7)]
    for j, (col, amp, by, sp, ph, op) in enumerate(bands):
        pts = []
        for k in range(int((x1 - x0) / 16) + 1):
            x = x0 + k * 16
            pts.append((x, by + amp * math.sin(PI2 * (x - x0) / 240 + sp * c.t * 2.2 + ph)))
        line = " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        out.append(f'<path d="M{line} L{x1:.1f},1400 L{x0:.1f},1400 Z" fill="{col}" opacity="{op}"/>')
        if j == 0:
            out.append(f'<path d="M{line}" fill="none" stroke="{WHITE}" stroke-opacity="0.6" stroke-width="4"/>')
    out.append(g(text(420, 920, str(c.props.get("label", "15 万亿")), 72, 900, c.accent),
                 s=max(_k(c, imp, 0.45), 1e-3), oy=920))
    k_rev = _u(c, rev, 0.4)
    # open cupped hand, side view: palm curve, four finger bumps, thumb; water blob in the cup
    out.append(glow(858, 1180, 170, c.p2, 0.45 * k_rev))
    fingers = [((790, 1160), (742, 1124)), ((788, 1178), (738, 1146)),
               ((788, 1196), (740, 1170)), ((792, 1212), (748, 1196))]
    for (bx, by), (tx, ty) in fingers:
        out.append(f'<path d="M{bx},{by} L{tx},{ty}" stroke="{SKIN}" stroke-width="26" stroke-linecap="round"/>')
    out.append(f'<path d="M934,1170 L956,1128" stroke="{SKIN}" stroke-width="28" stroke-linecap="round"/>')
    out.append(f'<path d="M770,1150 C776,1232 826,1262 862,1262 C902,1262 948,1232 952,1150 '
               f'C928,1180 892,1196 860,1196 C826,1196 794,1182 770,1150 Z" fill="{SKIN}"/>')
    out.append('<path d="M800,1222 C830,1248 892,1248 920,1222" fill="none" stroke="#D9A07E" '
               'stroke-width="5" stroke-linecap="round" opacity="0.6"/>')
    bob = 2 * wobble(c.t, 0.5, 1.0)
    out.append(f'<ellipse cx="860" cy="{1170 + bob:.1f}" rx="58" ry="22" fill="{WATER}"/>')
    out.append(f'<ellipse cx="842" cy="{1160 + bob:.1f}" rx="16" ry="6" fill="#BFE0FF" opacity="0.8"/>')
    out.append(text(860, 1300, str(c.props.get("small", "机器人数据")), 40, 800, WHITE))
    return "".join(out)


def _arm_bot(c: Ctx, x: float, y: float, s: float, j: int) -> str:
    a1 = 22 * math.sin(PI2 * 0.25 * c.t + j * 0.9)
    a2 = -40 + 22 * math.sin(PI2 * 0.25 * c.t + j * 0.9 + 1.0)
    bx, by = x, y - 18 * s
    e, tip = _arm_pts(bx, by, 54 * s, 44 * s, a1, a2)
    return (body(x - 24 * s, y - 18 * s, 48 * s, 18 * s, 6 * s, "#241C55", shine=0, shade=0.2, rim=False)
            + f'<path d="M{bx:.1f},{by:.1f} L{e[0]:.1f},{e[1]:.1f} L{tip[0]:.1f},{tip[1]:.1f}" fill="none" '
              f'stroke="{c.p2}" stroke-width="{9 * s:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
            + ball(e[0], e[1], 7 * s, c.p1) + ball(tip[0], tip[1], 9 * s, c.accent))


def _fleet(c: Ctx) -> str:
    rev = _beat(c, "reveal", 0.8)
    imp = max(_beat(c, "impact", rev + 1.5), rev + 0.05)
    n = max(2, min(30, int(c.props.get("count", 13))))
    months = max(2, int(c.props.get("months", 17)))
    nrows = 3 if n > 8 else 2
    counts = [n // nrows + (1 if i < n % nrows else 0) for i in range(nrows)]
    bases = [700.0, 900.0, 1100.0] if nrows == 3 else [760.0, 990.0]
    s = min(1.6, 860.0 / max(counts) / 105)
    out = []
    idx = 0
    for cnt, base_y in zip(counts, bases):
        slot = 860.0 / cnt
        for j in range(cnt):
            out.append(_arm_bot(c, 110 + slot * (j + 0.5), base_y, s, idx))
            idx += 1
    # calendar: pages flip from month 1 up to `months` between reveal and impact
    prog = clamp((c.t - rev) / (imp - rev)) if c.t >= rev else 0.0
    pos = prog * (months - 1)
    m = int(pos)
    frac = pos - m
    shown = 1 + m
    px0, py0, pw, ph = 300.0, 1150.0, 480.0, 150.0
    page = (body(px0, py0, pw, ph, 28, "#F4F1FF", shine=0.2, shade=0.1, rim=False)
            + body(px0, py0, pw, 60, 28, c.p1, shine=0.25, shade=0.1, rim=False)
            + text(c.canvas.cx, py0 + 30, "累计月份", 40, 900, WHITE))
    out.append(page)
    out.append(ball(px0 + 80, py0 + 4, 12, WHITE) + ball(px0 + pw - 80, py0 + 4, 12, WHITE))
    out.append(text(c.canvas.cx, py0 + 102, str(shown), 72, 900, INK))
    if m >= 1 and frac < 0.3 and prog < 1.0:
        f = frac / 0.3
        old = body(px0, py0, pw, ph, 28, "#F4F1FF", shine=0.2, shade=0.1, rim=False) \
            + text(c.canvas.cx, py0 + 102, str(shown - 1), 72, 900, INK)
        out.append(g(old, sy=max(0.02, math.cos(math.pi / 2 * f)), ox=c.canvas.cx, oy=py0 + ph / 2))
    out.append(pill(c.canvas.cx, 1345, f"{n} 台 · {months} 个月", 44, c.p1))
    return "".join(out)


def _map(c: Ctx) -> str:
    rev = _beat(c, "reveal", 1.2)
    imp = max(_beat(c, "impact", rev + 0.6), rev + 0.05)
    x0, y0, W, H = 110.0, 500.0, 860.0, 480.0
    out = []
    for ux, uy, rx, ry in MAP_CONT:
        out.append(f'<ellipse cx="{x0 + W * ux:.1f}" cy="{y0 + H * uy:.1f}" rx="{W * rx:.1f}" ry="{H * ry:.1f}" '
                   f'fill="{c.p1}" fill-opacity="0.38" stroke="{lighten(c.p1, 0.3)}" stroke-opacity="0.35" '
                   f'stroke-width="3"/>')
    rng = random.Random(55)
    k_rev = _u(c, rev, 0.6)
    out.append(glow(c.canvas.cx, 900, 220, c.p2, 0.3 * k_rev))
    for i in range(40):
        ux, uy, rx, ry = MAP_CONT[rng.randrange(len(MAP_CONT))]
        ang = rng.uniform(0, PI2)
        rr = math.sqrt(rng.random()) * 0.8
        sx = x0 + W * ux + W * rx * rr * math.cos(ang)
        sy = y0 + H * uy + H * ry * rr * math.sin(ang)
        tx, ty = c.canvas.cx - 91 + 26 * (i % 8), 960 - 26 * (i // 8)
        f = ease_io(clamp((c.t - (rev + 0.02 * i)) / 0.7)) if c.t >= rev else 0.0
        x = lerp(sx, tx, f) + (1 - f) * 3 * math.sin(c.t * 3 + i)
        y = lerp(sy, ty, f) + (1 - f) * 3 * math.cos(c.t * 3 + i)
        out.append(glow(x, y, 16, c.p2, 0.45))
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{c.p2}"/>')
    out.append(g(text(c.canvas.cx, 1120, str(c.props.get("label", "100 万+ 条 · 22 种")), 44, 900, c.accent),
                 s=max(_k(c, imp, 0.45), 1e-3), oy=1120))
    return "".join(out)


def _counter(c: Ctx) -> str:
    ent = c.ent()
    el = max(0.0, c.t - ent)
    ph = PI2 * el / 1.6
    grip = 0.5 + 0.5 * math.sin(ph)
    base = (240.0, 1330.0)
    e, tip = _arm_pts(base[0], base[1], 300, 250, 22 + 10 * math.sin(ph), -62 + 16 * math.sin(ph + 0.9))
    out = [contact_shadow(base[0], 1362, 110, 16, 0.4),
           body(base[0] - 60, 1330, 120, 30, 12, "#241C55", shine=0, shade=0.2, rim=False),
           f'<path d="M{base[0]:.1f},{base[1]:.1f} L{e[0]:.1f},{e[1]:.1f} L{tip[0]:.1f},{tip[1]:.1f}" fill="none" '
           f'stroke="{c.p2}" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>',
           ball(e[0], e[1], 20, c.p1),
           body(tip[0] - 30, tip[1] - 30, 60, 60, 10, c.accent, shine=0.2, shade=0.2, rim=False),
           ball(tip[0], tip[1], 16 * lerp(1.0, 0.7, grip), c.p1)]
    n = int(c.props.get("start", 0)) + int(el / 0.8)
    since = el % 0.8
    pulse = 1 + 0.12 * max(0.0, 1 - since / 0.25)
    out.append(body(480, 1000, 470, 290, 44, c.p1, shine=0.15, shade=0.2))
    out.append(g(text(715, 1120, f"+{n}", 96, 900, c.accent), s=pulse, ox=715, oy=1120))
    out.append(text(715, 1240, str(c.props.get("label", "网上搜不到")), 44, 800, WHITE))
    return "".join(out)


def data_scale(c: Ctx) -> str:
    fn = {"mountain": _mountain, "ocean": _ocean, "fleet": _fleet, "map": _map,
          "counter": _counter}.get(str(c.props.get("mode", "mountain")), _mountain)
    isx, isy = c.impact()
    return g(fn(c), sx=isx, sy=isy, oy=c.canvas.cy)


COMPONENTS = {
    "RobotBody": robot_body,
    "Sim2Real": sim_to_real,
    "DataScale": data_scale,
}
