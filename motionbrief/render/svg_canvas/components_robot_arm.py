# SPDX-License-Identifier: Apache-2.0
"""RobotArm: a friendly side-view industrial arm on a table, handling a towel (robotics explainer prop).

Modes (props.mode): fail | compare | practice | reach | crash | success | idle.
Every frame is a pure function of c.t: gripper targets are keyframed (smoothstep between keys) and solved with a
two-link IK, so the joints move smoothly; the towel is a cloth strip hanging from the pinch point, then a heap
(failed), a folded stack (success / compare) or a flat slab.
"""
from __future__ import annotations

import math
import random

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.components_v3 import GREEN, RED, _k, _u, mark
from motionbrief.render.svg_canvas.easing import clamp, lerp
from motionbrief.render.svg_canvas.prims import (ball, body, contact_shadow, darken, ease_io, g, glow, lighten,
                                                 measure, pill)

BX = 360.0             # robot base x
L1, L2 = 230.0, 200.0  # upper arm / forearm
GL = 62.0              # wrist -> fingertip
TH = 38.0              # towel thickness (~40 px on screen)
K = 1.05               # global scale: table ~860 px, reach ~520 px
DEF_Y = 1180.0
TOWEL, STRIPE, SKIN = "#9BEFDF", "#23AE98", "#F2C6A8"
OBJ = {"sponge": (84.0, 60.0), "cup": (56.0, 72.0), "stone": (68.0, 48.0)}  # (w, h) of reach objects
PERIOD = 1.2           # practice cycle (s)


# ----------------------------------------------------------------- motion helpers
def _track(t: float, keys: list) -> tuple:
    """Piecewise smoothstep through (time, value-tuple) keys; holds the first/last value outside."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (ta, va), (tb, vb) in zip(keys, keys[1:]):
        if t <= tb:
            u = ease_io((t - ta) / (tb - ta)) if tb > ta else 1.0
            return tuple(lerp(a, b, u) for a, b in zip(va, vb))
    return keys[-1][1]


def _rp(px: float, py: float, dx: float, dy: float, deg: float) -> tuple[float, float]:
    """Point (dx, dy) relative to (px, py), rotated by deg (SVG convention: positive = clockwise on screen)."""
    a = math.radians(deg)
    return px + dx * math.cos(a) - dy * math.sin(a), py + dx * math.sin(a) + dy * math.cos(a)


def _rot(svg: str, p: tuple[float, float], deg: float) -> str:
    return g(svg, ox=p[0], oy=p[1], rot=deg)


def _beats(c: Ctx) -> tuple[float, float]:
    """(reveal, impact) with fallbacks; impact is at least 1.6 s after reveal so the choreography fits."""
    dur = c.t1 - c.t0
    rev = c.beats.at("reveal")
    if rev is None:
        rev = c.t0 + 0.4 * dur
    imp = c.beats.at("impact")
    if imp is None:
        imp = rev + max(1.6, 0.4 * dur)
    return rev, max(imp, rev + 1.6)


def _ik(s: tuple[float, float], w: tuple[float, float]):
    """Two-link IK: shoulder s, wrist target w (clamped to reach). Returns (a1, a2 deg, elbow, wrist)."""
    dx, dy = w[0] - s[0], w[1] - s[1]
    d = math.hypot(dx, dy)
    dmax = L1 + L2 - 3.0
    if d > dmax:
        dx, dy, d = dx * dmax / d, dy * dmax / d, dmax
    phi = math.atan2(dx, -dy)
    a1 = phi - math.acos(clamp((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d), -1.0, 1.0))
    e = (s[0] + L1 * math.sin(a1), s[1] - L1 * math.cos(a1))
    wc = (s[0] + dx, s[1] + dy)
    a2 = math.atan2(wc[0] - e[0], -(wc[1] - e[1]))
    return math.degrees(a1), math.degrees(a2), e, wc


# ----------------------------------------------------------------- robot
def _robot(c: Ctx, Y: float, tip: tuple[float, float], gdeg: float, o: float) -> tuple[str, tuple[float, float]]:
    """Arm with the fingertip at tip, gripper turned gdeg (0 = pointing down), opening o (0 closed .. 1 open).
    Returns (svg, effective fingertip after the reach clamp)."""
    s = (BX, Y - 120.0)
    gr = math.radians(gdeg)
    w = (tip[0] - GL * math.sin(gr), tip[1] - GL * math.cos(gr))
    a1, a2, e, wc = _ik(s, w)
    eff = (wc[0] + GL * math.sin(gr), wc[1] + GL * math.cos(gr))
    acc = c.accent
    out = [
        body(BX - 84, Y - 80, 168, 80, 34, darken(c.p1, 0.12)),
        ball(BX - 46, Y - 46, 9, acc),
        _rot(body(s[0] - 23, s[1] - L1, 46, L1, 23, lighten(c.p1, 0.12)), s, a1),
        _rot(body(e[0] - 18, e[1] - L2, 36, L2, 18, c.p1), e, a2),
        glow(s[0], s[1], 60, acc, 0.35),
        ball(s[0], s[1], 38, c.p2),
        ball(s[0], s[1], 10, acc),
        ball(e[0], e[1], 26, c.p2),
        ball(e[0], e[1], 8, acc),
        _rot(body(wc[0] - 32, wc[1] - 15, 64, 30, 15, c.p2), wc, -gdeg),
    ]
    for sg in (-1, 1):
        lat = sg * (10 + 18 * o)
        out.append(_rot(body(wc[0] + lat - 6, wc[1], 12, GL, 6, lighten(c.p2, 0.2)), wc, -gdeg))
    return "".join(out), eff


def _table(Y: float) -> str:
    legs = max(20.0, 1360.0 - (Y + 34.0))
    return (body(150, Y + 30, 26, legs, 8, "#2C2468", shine=0.1, shade=0.25)
            + body(844, Y + 30, 26, legs, 8, "#2C2468", shine=0.1, shade=0.25)
            + body(100, Y, 820, 34, 16, "#4A3AA0", shine=0.25, shade=0.2))


# ----------------------------------------------------------------- towel
def _drape(gp: tuple[float, float], ep: tuple[float, float], n: int = 16) -> list[tuple[float, float]]:
    """Centre line from the pinch point gp to the far end ep, sagging onto the table (quadratic curve)."""
    qx, qy = gp[0] + 0.2 * (ep[0] - gp[0]), ep[1] + 2.0
    pts = []
    for i in range(n + 1):
        u = i / n
        a, b, cc = (1 - u) ** 2, 2 * (1 - u) * u, u * u
        pts.append((a * gp[0] + b * qx + cc * ep[0], a * gp[1] + b * qy + cc * ep[1]))
    return pts


def _cloth(pts: list[tuple[float, float]]) -> str:
    """Soft cloth strip along a centre line: flat light-teal fill, a darker stripe down the middle, a light top edge."""
    n = len(pts)
    top, bot = [], []
    for i, (x, y) in enumerate(pts):
        x0, y0 = pts[max(i - 1, 0)]
        x1, y1 = pts[min(i + 1, n - 1)]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln * TH / 2, dx / ln * TH / 2
        top.append((x + nx, y + ny))
        bot.append((x - nx, y - ny))
    poly = top + bot[::-1]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in poly) + " Z"
    centre = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    edge = " ".join(f"{x:.1f},{y:.1f}" for x, y in top)
    return (f'<path d="{d}" fill="{TOWEL}" stroke="{TOWEL}" stroke-width="3" stroke-linejoin="round"/>'
            f'<polyline points="{centre}" fill="none" stroke="{STRIPE}" stroke-width="{TH * 0.26:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>'
            f'<polyline points="{edge}" fill="none" stroke="#FFFFFF" stroke-opacity="0.35" stroke-width="3" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def _heap(cx: float, cy: float, rx: float, ry: float, seed: int = 3) -> str:
    """A crumpled towel heap: a lumpy blob with dark crease lines."""
    rng = random.Random(seed)
    ph = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
    pts = []
    for i in range(24):
        a = 2 * math.pi * i / 24
        r = 1 + 0.09 * math.sin(3 * a + ph[0]) + 0.06 * math.sin(5 * a + ph[1]) + 0.04 * math.sin(8 * a + ph[2])
        pts.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
    creases = []
    for _ in range(3):
        x1 = cx + rng.uniform(-0.6, 0.6) * rx
        y1 = cy + rng.uniform(-0.4, 0.1) * ry
        x2 = x1 + rng.uniform(-0.35, 0.35) * rx
        y2 = y1 + rng.uniform(-0.2, 0.2) * ry
        qx = (x1 + x2) / 2 + rng.uniform(-0.2, 0.2) * rx
        qy = (y1 + y2) / 2 + rng.uniform(-0.2, 0.2) * ry
        creases.append(f'<path d="M{x1:.1f},{y1:.1f} Q{qx:.1f},{qy:.1f} {x2:.1f},{y2:.1f}" fill="none" '
                       f'stroke="{STRIPE}" stroke-opacity="0.7" stroke-width="5" stroke-linecap="round"/>')
    return (contact_shadow(cx, cy + ry * 0.7, rx * 1.15, ry * 0.45, 0.45)
            + f'<path d="{d}" fill="{TOWEL}" stroke="{TOWEL}" stroke-width="4" stroke-linejoin="round"/>'
            + glow(cx - rx * 0.3, cy - ry * 0.4, rx * 0.5, "#FFFFFF", 0.25)
            + "".join(creases))


def _slab(x0: float, x1: float, yt: float, h: float) -> str:
    """A flat folded layer (rectangle with a stripe)."""
    return (body(x0, yt, x1 - x0, h, 7, TOWEL, shine=0.25, shade=0.15)
            + f'<rect x="{x0 + 6:.1f}" y="{yt + h * 0.38:.1f}" width="{x1 - x0 - 12:.1f}" height="{h * 0.24:.1f}" '
              f'rx="2" fill="{STRIPE}"/>')


# ----------------------------------------------------------------- fail (and compare's left half)
def _fail_scene(c: Ctx, Y: float, R: float, imp: float) -> str:
    span = imp - R
    sl = R + 0.7 * span                     # the towel slips out of the gripper
    cc = (572.0, Y - TH / 2)                # pinch point on the towel corner
    ec = (cc[0] + 300.0, Y - TH / 2)        # far end of the 300 px towel
    gend = (cc[0] + 40.0, Y - TH / 2)       # where the slipping corner lands
    keys = [(c.t0, (470.0, Y - 400.0)), (R - 0.4, (cc[0], Y - 260.0)), (R, cc), (R + 0.3, cc),
            (sl - 0.1, (cc[0] - 60.0, Y - 480.0)), (sl + 0.3, (cc[0] + 60.0, Y - 400.0)),
            (c.t1 + 5.0, (cc[0] + 60.0, Y - 400.0))]
    okeys = [(c.t0, (1.0,)), (R, (1.0,)), (R + 0.12, (0.0,)), (sl, (0.0,)), (sl + 0.25, (1.0,)),
             (c.t1 + 5.0, (1.0,))]
    tip = _track(c.t, keys)
    o = _track(c.t, okeys)[0]
    if c.t < R + 0.05:
        gp = cc
    elif c.t < sl:
        gp = tip
    else:
        ts = _track(sl, keys)
        u = clamp((c.t - sl) / max(0.01, imp - sl)) ** 2
        gp = (lerp(ts[0], gend[0], u), lerp(ts[1], gend[1], u))
    if c.t < imp:
        towel = _cloth(_drape(gp, ec)) + contact_shadow((cc[0] + ec[0]) / 2, Y + 3, 150, 11, 0.35)
    else:
        towel = _heap(cc[0] + 150, Y - 30, 100, 30)
    arm, _ = _robot(c, Y, tip, 0.0, o)
    return towel + arm


def _fail(c: Ctx, Y: float) -> str:
    R, imp = _beats(c)
    return _fail_scene(c, Y, R, imp) + mark(860.0, Y - 260.0, False, _k(c, imp, 0.45), 66)


# ----------------------------------------------------------------- compare (robot left, human hand right)
def _hand(x: float, y: float) -> str:
    """Cartoon hand with its fingertips at (x, y), pointing down: rounded palm, four fingers, thumb."""
    parts = [body(-38, -120, 76, 84, 30, SKIN, shine=0.25, shade=0.12),
             body(-62, -92, 24, 52, 11, SKIN, shine=0.2, shade=0.12)]
    for dx in (-26, -8, 10, 28):
        parts.append(body(dx - 9, -66, 18, 66, 9, SKIN, shine=0.2, shade=0.12))
    return g("".join(parts), tx=x, ty=y, ox=0, oy=0)


def _fold_hand(c: Ctx, Y: float, R: float) -> str:
    xl, xm, xr = 620.0, 750.0, 880.0
    yt = Y - 22.0
    th = 180.0 * ease_io(clamp((c.t - R) / 0.9))
    towel = _slab(xl, xm, yt, TH) + g(_slab(xm, xr, yt, TH), rot=-th, ox=xm, oy=yt)
    if c.t < R:
        tip = _track(c.t, [(c.t0, (860.0, Y - 300.0)), (R - 0.4, (880.0, Y - 160.0)), (R, (xr, Y - TH / 2))])
    elif c.t < R + 0.9:
        tip = _rp(xm, yt, 150.0, TH / 2, -th)
    else:
        end = _rp(xm, yt, 150.0, TH / 2, -180.0)
        tip = _track(c.t, [(R + 0.9, end), (R + 1.6, (860.0, Y - 300.0)), (c.t1 + 5.0, (860.0, Y - 300.0))])
    return towel + contact_shadow(xm, Y + 3, 140, 10, 0.35) + _hand(tip[0], tip[1])


def _compare(c: Ctx, Y: float) -> str:
    R, imp = _beats(c)
    k = _k(c, imp, 0.45)
    left = g(_fail_scene(c, Y, R, imp), tx=-186.0, s=0.7, ox=276.0, oy=Y)
    divider = (f'<line x1="540" y1="560" x2="540" y2="{Y:.0f}" stroke="#FFFFFF" stroke-opacity="0.18" '
               f'stroke-width="3" stroke-dasharray="12 12"/>')
    return (divider + left + _fold_hand(c, Y, R)
            + mark(210.0, 700.0, False, k, 60) + mark(830.0, 700.0, True, k, 60))


# ----------------------------------------------------------------- practice (repeating grab-lift-drop)
def _practice(c: Ctx, Y: float) -> str:
    start = int(c.props.get("start", 1))
    ts = c.ent()
    el = max(0.0, c.t - ts)
    phi = (el / PERIOD) % 1.0
    cc = (560.0, Y - TH / 2)
    ec = (cc[0] + 300.0, Y - TH / 2)
    hp = (cc[0] + 10.0, Y - 300.0)
    lp = (cc[0] - 60.0, Y - 480.0)
    keys = [(0.0, hp), (0.25, cc), (0.35, cc), (0.65, lp), (0.72, lp), (1.0, hp)]
    okeys = [(0.0, (1.0,)), (0.22, (1.0,)), (0.3, (0.0,)), (0.62, (0.0,)), (0.68, (1.0,)), (1.0, (1.0,))]
    tip = _track(phi, keys)
    o = _track(phi, okeys)[0]
    if phi < 0.33:
        gp = cc
    elif phi < 0.66:
        gp = tip
    elif phi < 0.95:
        u = (phi - 0.66) / 0.29
        u2 = u * u
        gp = (lerp(lp[0], cc[0], u2), lerp(lp[1], cc[1], u2))
    else:
        gp = cc
    towel = _cloth(_drape(gp, ec)) + contact_shadow((cc[0] + ec[0]) / 2, Y + 3, 150, 11, 0.35)
    arm, _ = _robot(c, Y, tip, 0.0, o)
    count = start + int(el // PERIOD) // 2
    label = f"第 {count} 次"
    w = measure(label, 46, 800) + 46 * 1.4
    return towel + arm + pill(900 - w / 2, 560, label, 46, c.p1)


# ----------------------------------------------------------------- reach (stretch to a high shelf)
def _object(kind: str, x: float, y: float, c: Ctx) -> str:
    if kind == "cup":
        return (f'<path d="M{x + 26:.1f},{y - 18:.1f} q22,0 22,18 q0,20 -22,20" fill="none" stroke="#F4F2FF" '
                f'stroke-width="9" stroke-linecap="round"/>'
                + body(x - 28, y - 36, 56, 72, 14, "#F4F2FF", shine=0.3, shade=0.18)
                + body(x - 28, y + 6, 56, 10, 3, c.p1, shine=0.1, shade=0.1, rim=False))
    if kind == "stone":
        return g(ball(x, y, 34, "#9AA3B5"), sy=0.7, ox=x, oy=y)
    return (body(x - 42, y - 30, 84, 60, 12, "#FFD54A", shine=0.3, shade=0.2)
            + "".join(f'<rect x="{x + dx:.1f}" y="{y + dy:.1f}" width="12" height="8" rx="3" fill="#D9A22B" '
                      f'opacity="0.6"/>' for dx, dy in ((-26, -14), (4, -16), (-12, 4), (18, 6))))


def _reach(c: Ctx, Y: float) -> str:
    R, imp = _beats(c)
    kind = str(c.props.get("object", "sponge"))
    if kind not in OBJ:
        kind = "sponge"
    reachable = bool(c.props.get("reachable", False))
    w, h = OBJ[kind]
    ox = 680.0 if reachable else 860.0
    oy = 800.0 - h / 2                      # the shelf top is y 800
    tg = (ox - w / 2 - 4.0, oy)             # grasp point on the object's left face
    h0 = (430.0, Y - 400.0)
    appr = (tg[0] - 40.0, tg[1] - 10.0)
    if reachable:
        lift = (tg[0] - 40.0, tg[1] - 70.0)
        keys = [(c.t0, h0), (R, appr), (R + 0.45, tg), (R + 0.95, lift), (c.t1 + 5.0, lift)]
        okeys = [(c.t0, (1.0,)), (R + 0.3, (1.0,)), (R + 0.45, (0.0,)), (c.t1 + 5.0, (0.0,))]
    else:
        keys = [(c.t0, h0), (R, appr), (R + 0.45, tg), (c.t1 + 5.0, tg)]
        okeys = [(c.t0, (1.0,)), (c.t1 + 5.0, (1.0,))]
    tip = _track(c.t, keys)
    o = _track(c.t, okeys)[0]
    if not reachable:  # pushing against the limit: a small tremor
        tip = (tip[0], tip[1] + 2.5 * math.sin(c.t * 26.0) * _u(c, R + 0.45, 0.4))
    arm, eff = _robot(c, Y, tip, 80.0, o)
    shelf = (body(640, 800, 280, 28, 10, "#3D3190", shine=0.2, shade=0.2)
             + body(650, 828, 16, Y - 828, 6, "#2C2468", shine=0.05, shade=0.2)
             + body(884, 828, 16, Y - 828, 6, "#2C2468", shine=0.05, shade=0.2))
    if reachable and c.t >= R + 0.45:
        cx, cy = tip[0] + w / 2 + 4.0, tip[1]
    else:
        cx, cy = ox, oy
    gap = ""
    if not reachable and c.t >= R:
        op = _u(c, R, 0.35)
        gap = (f'<line x1="{eff[0]:.1f}" y1="{eff[1]:.1f}" x2="{tg[0]:.1f}" y2="{tg[1]:.1f}" stroke="#FFFFFF" '
               f'stroke-opacity="{0.85 * op:.2f}" stroke-width="5" stroke-dasharray="12 12" stroke-linecap="round"/>')
    return (shelf + _object(kind, cx, cy, c) + gap + arm
            + mark(840.0, 600.0, reachable, _k(c, imp, 0.45), 64))


# ----------------------------------------------------------------- crash (arm swings in, cup goes over)
def _crash(c: Ctx, Y: float) -> str:
    R, imp = _beats(c)
    px = 760.0
    keys = [(c.t0, (420.0, Y - 400.0)), (R - 0.5, (440.0, Y - 370.0)), (R, (672.0, Y - 100.0)),
            (R + 0.6, (590.0, Y - 300.0)), (c.t1 + 5.0, (590.0, Y - 300.0))]
    tip = _track(c.t, keys)
    arm, _ = _robot(c, Y, tip, 0.0, 1.0)
    u = clamp((c.t - R) / 0.6)
    cup_upright = (body(672, Y - 110, 88, 110, 16, "#F4F2FF", shine=0.3, shade=0.18)
                   + body(672, Y - 70, 88, 12, 0, c.p1, shine=0.1, shade=0.1, rim=False)
                   + f'<path d="M760,{Y - 88:.1f} H774 Q788,{Y - 88:.1f} 788,{Y - 66:.1f} V{Y - 62:.1f} '
                     f'Q788,{Y - 40:.1f} 774,{Y - 40:.1f} H760" fill="none" stroke="#F4F2FF" stroke-width="9"/>')
    cup = g(cup_upright, rot=90.0 * u * u, ox=px, oy=Y)
    sparks = []
    tau = c.t - R
    if 0.0 <= tau < 0.9:
        rng = random.Random(41)
        for i in range(14):
            vx = rng.uniform(-40.0, 220.0)
            vy = rng.uniform(-380.0, -110.0)
            x = 676.0 + vx * tau
            y = min(Y - 6.0, Y - 96.0 + vy * tau + 0.5 * 1500.0 * tau * tau)
            op = 1.0 - tau / 0.9
            if i % 3 < 2:
                sparks.append(glow(x, y, 26, c.accent, 0.5 * op) + ball(x, y, 6, lighten(c.accent, 0.3)))
            else:
                col = ("#7C5CFF", "#FFFFFF", "#22D3B6")[i % 3]
                sparks.append(f'<rect x="{x - 6:.1f}" y="{y - 4:.1f}" width="12" height="8" rx="2" fill="{col}" '
                              f'opacity="{op:.2f}" transform="rotate({tau * 400 + i * 40:.1f} {x:.1f} {y:.1f})"/>')
    sx, sy = 830.0, 570.0
    hand_ang = 1080.0 * max(0.0, c.t - c.t0)   # fast spin
    stopwatch = (ball(sx, sy, 44, "#F4F2FF")
                 + f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="44" fill="none" stroke="{c.p1}" stroke-width="10"/>'
                 + body(sx - 12, sy - 62, 24, 16, 6, c.p2, shine=0.2, shade=0.2)
                 + _rot(f'<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{sx:.0f}" y2="{sy - 32:.0f}" stroke="{RED}" '
                        f'stroke-width="6" stroke-linecap="round"/>', (sx, sy), hand_ang))
    return cup + "".join(sparks) + arm + stopwatch + mark(820.0, 880.0, False, _k(c, imp, 0.45), 64)


# ----------------------------------------------------------------- success (two folds, glow, check)
def _success(c: Ctx, Y: float) -> str:
    R, imp = _beats(c)
    f2 = max(R + 1.3, imp - 0.7)
    yt = Y - TH
    xl, xm, xr = 450.0, 600.0, 750.0
    mid = (xl + xm) / 2
    th1 = 180.0 * ease_io(clamp((c.t - R) / 0.9))
    th2 = 180.0 * ease_io(clamp((c.t - f2) / 0.6))
    if c.t < f2:
        towel = _slab(xl, xm, yt, TH) + g(_slab(xm, xr, yt, TH), rot=-th1, ox=xm, oy=yt)
    else:
        towel = (_slab(xl, mid, yt - TH, 2 * TH)
                 + g(_slab(mid, xm, yt - TH, 2 * TH), rot=-th2, ox=mid, oy=yt - TH))
    e1 = _rp(xm, yt, 150.0, TH / 2, -180.0)
    if c.t < R:
        tip = _track(c.t, [(c.t0, (470.0, Y - 400.0)), (R - 0.4, (xr, Y - 220.0)), (R, (xr, Y - TH / 2))])
    elif c.t < R + 0.9:
        tip = _rp(xm, yt, 150.0, TH / 2, -th1)
    elif c.t < f2 - 0.2:
        mt = ((R + 0.92) + (f2 - 0.2)) / 2
        tip = _track(c.t, [(R + 0.92, e1), (mt, (520.0, Y - 300.0)), (f2 - 0.2, (xm, yt))])
    elif c.t < f2 + 0.6:
        tip = _rp(mid, yt - TH, 75.0, TH, -th2)
    else:
        tip = _track(c.t, [(f2 + 0.6, _rp(mid, yt - TH, 75.0, TH, -180.0)), (f2 + 1.1, (520.0, Y - 340.0)),
                           (c.t1 + 5.0, (520.0, Y - 340.0))])
    okeys = [(c.t0, (1.0,)), (R, (1.0,)), (R + 0.15, (0.0,)), (R + 0.92, (0.0,)), (R + 1.05, (1.0,)),
             (f2 - 0.1, (1.0,)), (f2, (0.0,)), (f2 + 0.6, (0.0,)), (f2 + 0.72, (1.0,)), (c.t1 + 5.0, (1.0,))]
    o = _track(c.t, okeys)[0]
    arm, _ = _robot(c, Y, tip, 0.0, o)
    u = _u(c, imp, 0.6)
    halo = glow((xl + xm) / 2, Y - 1.5 * TH, 190.0, GREEN, 0.5 * u) if u > 0 else ""
    shadow = contact_shadow(540.0, Y + 3, 120, 12, 0.4)
    return (halo + shadow + towel + arm
            + mark(820.0, Y - 200.0, True, _k(c, imp, 0.45), 70))


# ----------------------------------------------------------------- idle (title background)
def _idle(c: Ctx, Y: float) -> str:
    tip = (470.0 + 10.0 * math.sin(2 * math.pi * c.t / 5.0), Y - 400.0)
    o = 0.5 + 0.5 * math.sin(2 * math.pi * c.t / 3.0)
    arm, _ = _robot(c, Y, tip, 0.0, o)
    cc, ec = (572.0, Y - TH / 2), (872.0, Y - TH / 2)
    return _cloth(_drape(cc, ec)) + contact_shadow(702, Y + 3, 150, 11, 0.35) + arm


_MODES = {"fail": _fail, "compare": _compare, "practice": _practice, "reach": _reach, "crash": _crash,
          "success": _success, "idle": _idle}


def robot_arm(c: Ctx) -> str:
    Y = float(c.props.get("y", DEF_Y))
    fn = _MODES.get(str(c.props.get("mode", "fail")), _fail)
    isx, isy = c.impact()
    return g(_table(Y) + fn(c, Y), s=K, sx=isx, sy=isy, ox=540.0, oy=Y)


COMPONENTS = {"RobotArm": robot_arm}
