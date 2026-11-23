# SPDX-License-Identifier: Apache-2.0
"""Topic-agnostic concept components for explainers (every label comes from props).

Cartoon Tech v2 look, same helpers as components_v3:
  balance_scale  a cartoon balance: which side is heavier (comparison, trade-off, weight of evidence)
  timeline       a long time bar with coloured bands, start/end labels and an optional marker
  loop_cycle     3-5 stages on a ring with a token that keeps travelling round (process, feedback loop)
  chat_window    a phone-style chat with bubbles, optional code lines and numbered plan rows
Every component is a pure function of (Ctx, t).
"""
from __future__ import annotations

import math

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.components_v3 import _clip, _k, _u
from motionbrief.render.svg_canvas.easing import clamp, progress
from motionbrief.render.svg_canvas.prims import (back_out, ball, body, contact_shadow, darken, ease_io, esc,
                                                 g, glow, measure, pill, text, wobble)

WHITE = "#FFFFFF"
DIM = "#C9C3F0"
MONO = "Consolas, 'Courier New', monospace"


# ----------------------------------------------------------------- shared bits
def _pop(c: Ctx, at: float | None, dur: float = 0.5) -> float:
    """Entrance scale 0.6 -> ~1 (back-out): parts are visible on the first frame and pop to full size."""
    return 0.6 + 0.4 * _k(c, at, dur)


def _fit(s: str, size: float, max_w: float, weight: int = 800, pad: float = 0.0, lo: float = 18.0) -> float:
    """Largest font size (step 2, <= size, >= lo) so that measure(s) + pad*size fits max_w."""
    while size > lo and measure(s, size, weight) + pad * size > max_w:
        size -= 2
    return size


def _wrap(s: str, size: float, max_w: float, weight: int = 800) -> list[str]:
    """Greedy character wrap (CJK-safe)."""
    lines: list[str] = []
    cur = ""
    for ch in s:
        if cur and measure(cur + ch, size, weight) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


# ----------------------------------------------------------------- 1. BalanceScale
BEAM_L = 336.0  # pivot -> hang point (beam ~720 px wide)
PAN_DROP = 195.0  # hang point -> pan rim
PAN_W, PAN_H = 260.0, 83.0
TILT = 14.0
LABEL_PX = 40.0


def _tag(cx: float, top: float, label: str, base: str, max_w: float = 230.0) -> tuple[str, float]:
    """Pill-like label under a pan: up to two lines at LABEL_PX. Returns (svg, height)."""
    size = LABEL_PX
    lines = _wrap(label, size, max_w)
    lh = size * 1.3
    w = max(measure(s, size, 800) for s in lines) + size * 0.9
    h = len(lines) * lh + size * 0.5
    parts = [body(cx - w / 2, top, w, h, min(h / 2, 28.0), base, shine=0.25, shade=0.2)]
    for k, s in enumerate(lines):
        parts.append(text(cx, top + size * 0.25 + lh * (k + 0.5), s, size, 800, WHITE))
    return "".join(parts), h


def balance_scale(c: Ctx) -> str:
    """Props: left, right (labels, <=8 chars), heavy ("left" | "right" | "none", default "right"), y (default 980).
    Entrance: post, base and beam, pans pop in with their labels. Reveal: the beam tilts 14 deg with a back-out
    bounce so the heavy side drops and the light pan lifts; labels move with the pans. Impact: dust puff under the
    heavy pan. heavy="none" keeps the beam level and only breathes."""
    y = float(c.props.get("y", 980))
    heavy = str(c.props.get("heavy", "right"))
    labels = {"left": str(c.props.get("left", "左")), "right": str(c.props.get("right", "右"))}
    piv = y - 200.0
    floor_y = y + 280.0
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")

    target = TILT if heavy == "right" else -TILT if heavy == "left" else 0.0
    settle = progress(c.t, rev, 0.7) if rev is not None else 0.0
    ang = target * back_out(settle) + wobble(c.t, 0.35, 0.6 if target else 1.2) * settle
    th = math.radians(ang)
    ddx, ddy = BEAM_L * math.cos(th), BEAM_L * math.sin(th)
    ends = {"right": (c.canvas.cx + ddx, piv + ddy), "left": (c.canvas.cx - ddx, piv - ddy)}

    out = [contact_shadow(c.canvas.cx, floor_y + 90, 300, 22, 0.45),
           body(c.canvas.cx - 17, piv, 34, floor_y - piv + 6, 16, "#6B64A0", shine=0.2, shade=0.3, rim=False),
           body(c.canvas.cx - 260, floor_y, 520, 78, 39, "#3A3560", shine=0.2, shade=0.25),
           g(body(c.canvas.cx - BEAM_L - 24, piv - 18, 2 * BEAM_L + 48, 36, 18, "#A99CFF", shine=0.35, shade=0.15),
             s=_pop(c, ent, 0.5), rot=ang, ox=c.canvas.cx, oy=piv)]

    bottoms: dict[str, float] = {}
    for i, side in enumerate(("left", "right")):
        ex, ey = ends[side]
        top = ey + PAN_DROP
        base = c.p1 if side == "left" else darken(c.p2, 0.25)
        tag, th_ = _tag(ex, top + PAN_H + 8, labels[side], base)
        bottoms[side] = top + PAN_H + 8 + th_
        strings = "".join(
            f'<line x1="{ex:.1f}" y1="{ey:.1f}" x2="{ex + dx:.1f}" y2="{top:.1f}" stroke="{DIM}" stroke-width="6" '
            f'stroke-linecap="round"/>' for dx in (-150, 150))
        pan = body(ex - PAN_W / 2, top, PAN_W, PAN_H, 40, "#EDE9FF", shine=0.3, shade=0.22) + tag
        out.append(strings)
        out.append(g(pan, s=_pop(c, ent + 0.25 + 0.15 * i, 0.5), ox=ex, oy=top + PAN_H / 2))

    out.append(ball(c.canvas.cx, piv, 28, WHITE))

    if heavy in ends and imp is not None and c.t >= imp:  # dust puff under the heavy pan
        hx, hy = ends[heavy][0], bottoms[heavy]
        u = clamp((c.t - imp) / 0.8)
        for k, dx in enumerate((-90, -45, 0, 45, 90)):
            rr = 14 + 40 * u + 6 * (k % 2)
            px, py = hx + dx, hy - 6 * u + 10
            out.append(glow(px, py, rr * 1.6, "#DDE7FF", 0.6 * (1 - u))
                       + f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rr:.1f}" fill="#DDE7FF" opacity="{0.5 * (1 - u):.3f}"/>')

    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=piv)


# ----------------------------------------------------------------- 2. Timeline
TL_X0, TL_X1 = 110.0, 970.0
TL_Y, TL_H = 960.0, 56.0
LABEL_Y, TIER_H = 900.0, 64.0
LABEL_PX, EDGE_PX = 40.0, 38.0


def _tlx(f: float) -> float:
    return TL_X0 + clamp(f) * (TL_X1 - TL_X0)


def _band_col(c: Ctx, col, i: int) -> str:
    if col in (None, ""):
        return (c.p1, c.p2)[i % 2]
    if col == "accent":
        return c.accent
    if col == "p1":
        return c.p1
    if col == "p2":
        return c.p2
    return str(col)


def timeline(c: Ctx) -> str:
    """Props: bands [{label, from, to, color?}] (fractions 0..1 of the bar; color "accent"|"p1"|"p2"|hex),
    start, end (end labels), marker {at, label} (optional), focus (band index, optional).
    Entrance: the bar draws left to right over ~1.2 s, bands show as ghosts. Reveal: bands fill in, with
    labels above (stacked when they collide). Impact: the focus band glows and a pill label pops with a pointer.
    A light sweeps along the bar once revealed; a slim 'now' tick sits at the right end."""
    bands = list(c.props.get("bands") or [])
    start, end = str(c.props.get("start", "")), str(c.props.get("end", ""))
    marker = c.props.get("marker")
    focus = c.props.get("focus")
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    rev_t = rev if rev is not None else ent + 1.2
    bar_top = TL_Y - TL_H / 2

    draw = ease_io(progress(c.t, ent, 1.2))
    track_w = (TL_X1 - TL_X0) * draw
    out = []
    if track_w >= 2:
        out.append(body(TL_X0, bar_top, track_w, TL_H, min(TL_H / 2, track_w / 2), "#241C55", shine=0.0, shade=0.2,
                        rim=False))

    placed: list[tuple[float, float, int]] = []
    for i, b in enumerate(bands):
        f0, f1 = float(b.get("from", 0.0)), float(b.get("to", 1.0))
        label = str(b.get("label", ""))
        col = _band_col(c, b.get("color"), i)
        x0, x1 = _tlx(f0), _tlx(f1)
        wfull = max(x1 - x0, 1.0)
        r = min(TL_H / 2, wfull / 2)
        u = ease_io(_u(c, rev_t + 0.12 * i, 0.5))
        kf = _k(c, imp, 0.45) if focus == i else 0.0

        if kf > 0:
            out.append(glow(x0 + wfull / 2, TL_Y, wfull / 2 + 70, col, 0.6 * kf))
        out.append(g(body(x0, bar_top, wfull, TL_H, r, col, shine=0.0, shade=0.0, rim=False), opacity=0.22))
        if u > 0.01:
            wu = max(wfull * u, 2.0)
            out.append(body(x0, bar_top, wu, TL_H, min(r, wu / 2), col, shine=0.3, shade=0.18, rim=False))
        if kf > 0:
            out.append(f'<rect x="{x0:.1f}" y="{bar_top:.1f}" width="{wfull:.1f}" height="{TL_H:.1f}" rx="{r:.1f}" '
                       f'fill="#FFFFFF" opacity="{0.35 * clamp(kf):.3f}"/>')

        if not label:
            continue
        s = _fit(label, LABEL_PX, 300, lo=LABEL_PX)
        wl = measure(label, s, 800)
        mid = _tlx((f0 + f1) / 2)
        cx = clamp(mid, TL_X0 + wl / 2 + 4, TL_X1 - wl / 2 - 4)
        tier = 0
        while any(t == tier and not (hi < cx - wl / 2 - 10 or lo > cx + wl / 2 + 10) for lo, hi, t in placed):
            tier += 1
        placed.append((cx - wl / 2, cx + wl / 2, tier))
        ly = LABEL_Y - tier * TIER_H

        if kf > 0:  # focus: the plain label fades out and a pill with a pointer pops in its place
            py_ = ly - 56
            pb = py_ + s * 0.875
            pointer = (f'<path d="M{cx - 12:.1f},{pb - 2:.1f} L{cx + 12:.1f},{pb - 2:.1f} '
                       f'L{mid:.1f},{bar_top - 4:.1f} Z" fill="{col}"/>')
            tc = "#1B1148" if col in (c.accent, c.p2) else WHITE
            out.append(g(pill(cx, py_, label, s, col, text_col=tc) + pointer, s=max(kf, 1e-3), oy=py_ + s))
            out.append(text(cx, ly, label, s, 800, WHITE, opacity=1 - clamp(kf)))
        else:
            if abs(cx - mid) > 2 or tier:
                out.append(f'<line x1="{mid:.1f}" y1="{bar_top - 4:.1f}" x2="{mid:.1f}" y2="{ly + s * 0.6:.1f}" '
                           f'stroke="{col}" stroke-width="4" stroke-linecap="round"/>')
            out.append(text(cx, ly, label, s, 800, WHITE))

    if start:
        out.append(text(TL_X0, TL_Y + 72, start, _fit(start, EDGE_PX, 260, lo=EDGE_PX), 800, DIM, "start"))
    if end:
        out.append(text(TL_X1, TL_Y + 72, end, _fit(end, EDGE_PX, 260, lo=EDGE_PX), 800, DIM, "end"))

    out.append(f'<rect x="{TL_X1 - 2:.1f}" y="{bar_top - 2:.1f}" width="4" height="{TL_H + 24:.1f}" rx="2" '
               f'fill="#FFFFFF" opacity="{0.9 * draw:.3f}"/>')

    if isinstance(marker, dict):
        mx = _tlx(float(marker.get("at", 0.5)))
        ml = str(marker.get("label", ""))
        s = _fit(ml, LABEL_PX, 300, lo=LABEL_PX)
        wm = measure(ml, s, 800) + s * 1.4
        mcx = clamp(mx, TL_X0 + wm / 2, TL_X1 - wm / 2)
        my = TL_Y + 140
        mk = _k(c, rev_t + 0.3, 0.45)
        mg = (f'<line x1="{mx:.1f}" y1="{bar_top - 14:.1f}" x2="{mx:.1f}" y2="{TL_Y + TL_H / 2 + 14:.1f}" '
              f'stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>'
              f'<line x1="{mx:.1f}" y1="{TL_Y + TL_H / 2 + 14:.1f}" x2="{mcx:.1f}" y2="{my - s * 0.875:.1f}" '
              f'stroke="#FFFFFF" stroke-opacity="0.6" stroke-width="3"/>'
              + ball(mx, TL_Y, 11, WHITE) + pill(mcx, my, ml, s, c.p1))
        out.append(g(mg, s=max(mk, 1e-3), oy=TL_Y))

    if c.t >= rev_t + 1.2:  # a light sweeps along the bar, forever
        sxp = TL_X0 + (TL_X1 - TL_X0) * (((c.t - rev_t) / 2.4) % 1.0)
        out.append(glow(sxp, TL_Y, 46, WHITE, 0.4) + ball(sxp, TL_Y, 7, WHITE))

    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=TL_Y)


# ----------------------------------------------------------------- 3. LoopCycle
LOOP_R, LOOP_NODE = 285.0, 92.0
LOOP_PERIOD = 2.4


def loop_cycle(c: Ctx) -> str:
    """Props: stages (list, 3-5 labels of <=4 chars), centre (optional label for the middle).
    Entrance: nodes pop in on the ring, arrows follow. Reveal: a glowing token starts travelling the loop
    (period 2.4 s, endless) and each node lights as it passes. Impact: the whole ring pulses."""
    stages = [str(s) for s in (c.props.get("stages") or [])][:5] or ["输入", "处理", "输出"]
    centre = c.props.get("centre")
    n = len(stages)
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    phase = ((c.t - rev) / LOOP_PERIOD) % 1.0 if rev is not None and c.t >= rev else None
    angs = [-90.0 + 360.0 * i / n for i in range(n)]

    def at(deg: float) -> tuple[float, float]:
        th = math.radians(deg)
        return c.canvas.cx + LOOP_R * math.cos(th), c.canvas.cy + LOOP_R * math.sin(th)

    pulse = 0.0
    if imp is not None and c.t >= imp:
        u = clamp((c.t - imp) / 0.9)
        pulse = math.sin(u * math.pi * 3) * (1 - u)

    out = []
    delta = (LOOP_NODE + 20) / LOOP_R  # angular half-gap so arrows start/stop outside the nodes
    for i in range(n):
        a0 = math.radians(angs[i]) + delta
        a1 = math.radians(angs[(i + 1) % n] + (360.0 if i == n - 1 else 0.0)) - delta
        x0, y0 = c.canvas.cx + LOOP_R * math.cos(a0), c.canvas.cy + LOOP_R * math.sin(a0)
        x1, y1 = c.canvas.cx + LOOP_R * math.cos(a1), c.canvas.cy + LOOP_R * math.sin(a1)
        dx, dy = -math.sin(a1), math.cos(a1)
        nx, ny = math.cos(a1), math.sin(a1)
        tip = (x1 + dx * 12, y1 + dy * 12)
        bx, by = x1 - dx * 18, y1 - dy * 18
        head = (f'<path d="M{tip[0]:.1f},{tip[1]:.1f} L{bx + nx * 13:.1f},{by + ny * 13:.1f} '
                f'L{bx - nx * 13:.1f},{by - ny * 13:.1f} Z" fill="#FFFFFF" fill-opacity="0.75"/>')
        arc = (f'<path d="M{x0:.1f},{y0:.1f} A{LOOP_R:.1f},{LOOP_R:.1f} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" '
               f'stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="8" stroke-linecap="round"/>')
        op = ease_io(progress(c.t, ent + 0.1 * i + 0.3, 0.3))
        out.append(g(arc + head, opacity=op))

    for i, stage in enumerate(stages):
        x, y = at(angs[i])
        col = c.p1 if i % 2 == 0 else darken(c.p2, 0.25)
        lit = 0.0
        if phase is not None:
            d = abs(phase - i / n)
            d = min(d, 1 - d)
            lit = clamp(1 - d / 0.12)
        s_lab = _fit(stage, 40, 2 * LOOP_NODE - 40, lo=40)
        inner = (glow(x, y, LOOP_NODE * 1.45, c.accent, 0.55 * lit)
                 + ball(x, y, LOOP_NODE, col)
                 + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{LOOP_NODE:.1f}" fill="#FFFFFF" opacity="{0.3 * lit:.3f}"/>'
                 + text(x, y, stage, s_lab, 900, WHITE))
        out.append(g(inner, s=_pop(c, ent + 0.1 * i, 0.5), ox=x, oy=y))

    if phase is not None:  # token with a short trail
        for k in range(7):
            pk = (phase - k * 0.02) % 1.0
            tx, ty = at(-90.0 + 360.0 * pk)
            rr = 16 - 1.6 * k
            out.append(g(ball(tx, ty, rr, c.accent), opacity=1 - k / 7))
        hx, hy = at(-90.0 + 360.0 * phase)
        out.append(glow(hx, hy, 80, c.accent, 0.75) + ball(hx, hy, 20, c.accent))

    hub = [ball(c.canvas.cx, c.canvas.cy, 118, "#2E2770")]
    if centre:
        lines = _wrap(str(centre), 48, 190)
        fs = min(_fit(s, 48, 190) for s in lines)
        for k, s in enumerate(lines):
            hub.append(text(c.canvas.cx, c.canvas.cy + (k - (len(lines) - 1) / 2) * fs * 1.2, s, fs, 900, WHITE))
    out.append(g("".join(hub), s=_pop(c, ent + 0.3, 0.5), oy=c.canvas.cy))

    isx, isy = c.impact()
    return g("".join(out), s=1 + 0.06 * pulse, sx=isx, sy=isy, oy=c.canvas.cy)


# ----------------------------------------------------------------- 4. ChatWindow
CARD_X, CARD_Y, CARD_W, CARD_H = 160.0, 520.0, 760.0, 820.0
MSG_GAP = 0.45  # seconds between bubbles
BUBBLE_FS, BUBBLE_MAX_W, BUBBLE_TEXT_W = 36.0, 680.0, 620.0
ROW_GAP = 10.0
CODE_LH, CODE_H = 36.0, 160.0
CODE_LINES = ["def solve(x):", "    return x**3 / 3", "∫ x² dx = x³ / 3", "+ C", "d/dx (x³/3) = x²"]


def _chat_rows(msgs: list[dict], c: Ctx, code: bool, code_lines: list[str], plan: bool) -> list[dict]:
    fs = BUBBLE_FS
    lh, px, py = fs * 1.3, 28.0, 14.0
    x0, x1 = CARD_X + 40, CARD_X + CARD_W - 40
    ent = c.ent()
    last_ai = max((i for i, m in enumerate(msgs) if m.get("role") != "user"), default=-1)
    rows: list[dict] = []
    y, num = CARD_Y + 100.0, 0
    for i, m in enumerate(msgs):
        user = m.get("role") == "user"
        has_code = code and i == last_ai
        txt = str(m.get("text", ""))
        e = {"role": "user" if user else "ai", "T": ent + 0.15 + MSG_GAP * i, "fs": fs, "lh": lh, "py": py,
             "code": has_code, "plan": (not user) and plan, "code_lines": code_lines}
        if user:
            lines = _wrap(txt, fs, BUBBLE_TEXT_W)
            w = min(max(measure(s, fs, 800) for s in lines) + 2 * px, BUBBLE_MAX_W)
            x, tb = x1 - w, len(lines) * lh
            e.update(code_x=0.0, code_w=0.0, num=0)
        elif plan:
            num += 1
            lines = _wrap(txt, fs, (x1 - x0) - 84 - 28)
            w, x = x1 - x0, x0
            tb = max(len(lines) * lh, 52.0)
            e.update(code_x=x + 84, code_w=w - 84 - 28, num=num)
        else:
            lines = _wrap(txt, fs, BUBBLE_TEXT_W)
            lw = max(measure(s, fs, 800) for s in lines)
            w = min(max(lw + 2 * px, 480.0 if has_code else 0.0), BUBBLE_MAX_W)
            x, tb = x0, len(lines) * lh
            e.update(code_x=x + px, code_w=w - 2 * px, num=0)
        h = tb + 2 * py + ((12 + CODE_H) if has_code else 0)
        e.update(x=x, y=y, w=w, h=h, lines=lines, tb=tb)
        rows.append(e)
        y += h + ROW_GAP
    return rows


def _mono(x: float, y: float, s: str, size: float, fill: str) -> str:
    return (f'<text x="{x:.1f}" y="{y + size * 0.36:.1f}" font-family="{MONO}" font-size="{size}" font-weight="700" '
            f'fill="{fill}" text-anchor="start">{esc(s)}</text>')


def _code_box(c: Ctx, e: dict, i: int) -> str:
    """Scrolling monospace lines inside a clipped dark box (one line per 1.1 s, looping)."""
    lines = e["code_lines"]
    x, w = e["code_x"], e["code_w"]
    y = e["y"] + e["py"] + e["tb"] + 12
    off = max(0.0, c.t - e["T"]) / 1.1
    k0 = math.floor(off)
    fr = off - k0
    rows = []
    for j in range(-1, 5):
        yc = y + 8 + CODE_LH / 2 + (j - fr) * CODE_LH
        rows.append(_mono(x + 16, yc, lines[(k0 + j) % len(lines)], 28, "#E9E6FF"))
    bg = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{CODE_H:.1f}" fill="#070620" opacity="0.92"/>'
    return _clip(f"chc{i}", x, y, w, CODE_H, 16, bg + "".join(rows))


def _typing(c: Ctx, e: dict) -> str:
    x, y = e["x"], e["y"]
    parts = [body(x, y, 124, 62, 31, darken(c.p2, 0.3), shine=0.2, shade=0.25)]
    for k in range(3):
        dy = -6 * abs(math.sin(c.t * 7 - k * 0.9))
        parts.append(ball(x + 38 + 24 * k, y + 31 + dy, 9, WHITE))
    return "".join(parts)


def _message(c: Ctx, e: dict, i: int, lit: bool) -> str:
    x, y, w, h = e["x"], e["y"], e["w"], e["h"]
    fs, lh, py = e["fs"], e["lh"], e["py"]
    if e["role"] == "user":
        base = c.p1
        parts = [body(x, y, w, h, 30, base, shine=0.25, shade=0.2)]
        for k, s in enumerate(e["lines"]):
            parts.append(text(x + w / 2, y + py + lh * (k + 0.5), s, fs, 800, WHITE))
    elif e["plan"]:
        base = "#2B2470"
        parts = [body(x, y, w, h, 28, base, shine=0.1, shade=0.2)]
        bc = y + py + lh / 2
        parts.append(ball(x + 44, bc, 24, darken(c.p2, 0.2)) + text(x + 44, bc, str(e["num"]), 30, 900, WHITE))
        for k, s in enumerate(e["lines"]):
            parts.append(text(x + 84, y + py + lh * (k + 0.5), s, fs, 800, WHITE, "start"))
    else:
        base = darken(c.p2, 0.3)
        parts = [body(x, y, w, h, 30, base, shine=0.2, shade=0.25)]
        for k, s in enumerate(e["lines"]):
            parts.append(text(x + w / 2, y + py + lh * (k + 0.5), s, fs, 800, WHITE))
    if e["code"]:
        parts.append(_code_box(c, e, i))
    if lit:  # the latest bubble glows after the reveal
        cx, cy = x + w / 2, y + h / 2
        parts.insert(0, glow(cx, cy, max(w, h) * 0.8, base, 0.4 + 0.15 * math.sin(c.t * 3)))
    return "".join(parts)


def chat_window(c: Ctx) -> str:
    """Props: messages [{role: "user"|"ai", text (<=24 chars)}]; code (false | true | list of strings: when true or a
    non-empty list, the last AI bubble shows 3-5 scrolling monospace code/formula lines; a list overrides the
    default lines); plan (bool: AI messages render as numbered plan rows "1 xxx").
    Entrance: the card is up at once; bubbles appear one by one every 0.45 s (typing dots before each AI bubble).
    Reveal: the latest bubble glows. Impact: the last bubble pops."""
    msgs = [m for m in (c.props.get("messages") or []) if isinstance(m, dict)]
    raw_code = c.props.get("code", False)
    code = bool(raw_code)
    code_lines = [str(s) for s in raw_code] if isinstance(raw_code, list) and raw_code else CODE_LINES
    plan = bool(c.props.get("plan", False))
    rev, imp = c.beats.at("reveal"), c.beats.at("impact")
    rows = _chat_rows(msgs, c, code, code_lines, plan)

    parts = [body(CARD_X, CARD_Y, CARD_W, CARD_H, 56, "#1B1648", shine=0.06, shade=0.3)]
    parts += [ball(CARD_X + 50 + 24 * k, CARD_Y + 46, 8, "#FFFFFF") for k in range(3)]
    parts.append(f'<rect x="{CARD_X + 30}" y="{CARD_Y + 84}" width="{CARD_W - 60}" height="2" fill="#FFFFFF" '
                 f'opacity="0.12"/>')

    last = len(rows) - 1
    for i, e in enumerate(rows):
        T = e["T"]
        if c.t < T:
            if e["role"] == "ai" and c.t >= T - 0.24:
                parts.append(_typing(c, e))
            continue
        s = _pop(c, T, 0.35)
        if i == last and imp is not None and c.t >= imp:
            s *= 1 + 0.12 * math.sin(math.pi * clamp((c.t - imp) / 0.5))
        op = clamp(progress(c.t, T, 0.18))
        cx, cy = e["x"] + e["w"] / 2, e["y"] + e["h"] / 2
        lit = i == last and rev is not None and c.t >= rev
        parts.append(g(_message(c, e, i, lit), s=s, ox=cx, oy=cy, opacity=op))
    return "".join(parts)


COMPONENTS = {
    "BalanceScale": balance_scale,
    "Timeline": timeline,
    "LoopCycle": loop_cycle,
    "ChatWindow": chat_window,
}
