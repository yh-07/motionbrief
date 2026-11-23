# SPDX-License-Identifier: Apache-2.0
"""16:9 comparison components: SplitCompare (narrow vs wide memory pipe, or two value panels), HBars (horizontal
bar chart with a highlighted row) and ChipTags (labels attached to anchor points around a chip die).

Layout is authored in a 1920x1080 design space (16:9) and uniformly scaled and centred onto c.canvas, so the same
numbers hold for any landscape canvas. The scene supplies the flat dark background; nothing here paints a
full-screen backdrop, glow pool, particle or HUD. Main visuals stay in x 120..1800, y 120..760.
"""
from __future__ import annotations

import math

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.easing import clamp, ease_out_expo, lerp, progress
from motionbrief.render.svg_canvas.prims import back_out, body, ease_io, fit_size, g, lin, measure, mix, text

BLUE, ORANGE, GREEN, RED = "#3B82F6", "#F59E0B", "#22C55E", "#EF4444"
YELLOW, GREY, CHIP, PANEL, PANEL2 = "#FACC15", "#334155", "#262D3B", "#121620", "#1E2430"
TEXT, SUB, AMBER_INK, STONE = "#F8FAFC", "#94A3B8", "#3A2200", "#475569"
GRAY_NAME = "#64748B"
COLOR_NAMES = {"blue": BLUE, "orange": ORANGE, "green": GREEN, "red": RED, "gray": GRAY_NAME}
DESIGN_W, DESIGN_H = 1920, 1080


# ----------------------------------------------------------------- shared bits
def _fit(c: Ctx, inner: str) -> str:
    """Uniform scale of the 1920x1080 design space onto the real canvas, centred."""
    k = min(c.canvas.w / DESIGN_W, c.canvas.h / DESIGN_H)
    return g(inner, tx=(c.canvas.w - DESIGN_W * k) / 2, ty=(c.canvas.h - DESIGN_H * k) / 2, s=k, ox=0, oy=0)


def _pop_scale(c: Ctx, delay: float) -> float:
    """Entrance pop that starts at 0.85, so the first frame already shows the static parts."""
    return 0.85 + 0.15 * c.pop(delay, 0.5)


def _packet(x: float, y: float, w: float, h: float, opacity: float = 1.0) -> str:
    """Green data packet with a small white highlight (same style as the chip-stage packet)."""
    if opacity <= 0.01:
        return ""
    inner = (body(x, y, w, h, min(h / 2, 9), GREEN, shine=0.3, shade=0.2, rim=False)
             + f'<rect x="{x + w * 0.2:.1f}" y="{y + h * 0.22:.1f}" width="{w * 0.3:.1f}" height="{h * 0.2:.1f}" '
               f'rx="{h * 0.1:.1f}" fill="#FFFFFF" fill-opacity="0.9"/>')
    return g(inner, opacity=opacity, ox=x + w / 2, oy=y + h / 2)


def _col(name, default: str) -> str:
    if isinstance(name, str):
        if name in COLOR_NAMES:
            return COLOR_NAMES[name]
        if name.startswith("#") and len(name) == 7:
            return name
    return COLOR_NAMES[default]


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _num(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _rev(c: Ctx) -> float:
    r = c.beats.at("reveal")
    return c.t0 + 2.0 if r is None else r


def _imp(c: Ctx) -> float:
    i = c.beats.at("impact")
    return c.t0 + 3.0 if i is None else i


def _fs(s, size: float, weight: int, max_w: float) -> float:
    return fit_size(str(s), size, weight, max_w)


def _impact_pop(c: Ctx, inner: str, cx: float, cy: float) -> str:
    """Single 0.5 s pulse (scale 1 -> 1.12 -> 1) on the impact beat."""
    u = clamp((c.t - _imp(c)) / 0.5)
    return g(inner, s=1.0 + 0.12 * math.sin(math.pi * u), ox=cx, oy=cy)


# ----------------------------------------------------------------- SplitCompare
PANEL_Y, PANEL_W, PANEL_H = 140, 780, 620
LEFT_X, RIGHT_X = 140, 1000
PIPE_CAP, LANE_PITCH = 232.0, 14.0
PERIOD_QUEUED, PERIOD_FREE = 2.4, 0.9
LEFT_DEF = {"title": "PHONE", "value": "LPDDR", "sub": "几十 GB/s", "color": "orange"}
RIGHT_DEF = {"title": "SERVER GPU", "value": "HBM", "sub": "TB/s class", "color": "orange"}


def _side(c: Ctx, key: str, default: dict) -> tuple[str, str, str, str]:
    d = {**default, **_d(c.props.get(key))}
    return str(d.get("title", "")), str(d.get("value", "")), str(d.get("sub", "")), _col(d.get("color"), "orange")


def _frame(px: float, py: float, border: str) -> str:
    return (f'<rect x="{px}" y="{py}" width="{PANEL_W}" height="{PANEL_H}" rx="20" fill="{PANEL}" '
            f'stroke="{border}" stroke-width="3"/>')


def _pipe_panel(c: Ctx, px: float, title: str, value: str, sub: str, col: str, border: str, n_lanes: int,
                pitch: float, queued: bool, e: float) -> str:
    py = PANEL_Y
    cy = py + 330
    h_pipe = n_lanes * pitch
    x0, x1 = px + 200, px + 580
    out = [_frame(px, py, border),
           text(px + PANEL_W / 2, py + 60, title, _fs(title, 44, 800, 680), 800, SUB),
           text(px + PANEL_W / 2, py + 150, value, _fs(value, 72, 900, 700), 900, col),
           f'<rect x="{x0 - 4}" y="{cy - h_pipe / 2 - 8:.1f}" width="{x1 - x0 + 8}" height="{h_pipe + 16:.1f}" '
           f'rx="12" fill="{PANEL2}" stroke="{GREY}" stroke-width="2"/>']
    pw = 30.0
    travel = x1 - x0 - pw - 8
    for k in range(n_lanes):
        ly = cy - h_pipe / 2 + k * pitch
        out.append(f'<rect x="{x0}" y="{ly + 1:.1f}" width="{x1 - x0}" height="{pitch - 2:.1f}" '
                   f'rx="{(pitch - 2) / 2:.1f}" fill="{CHIP}"/>')
        n_pk = 3 if queued else 2
        for j in range(n_pk):
            if queued:
                # slow lane: packets decelerate toward the compute entrance and bunch up there
                pos = ((c.t - e) / PERIOD_QUEUED + j / n_pk + k * 0.13) % 1.0
                x = x0 + 4 + travel * (1 - (1 - pos) ** 3)
                op = clamp(pos * 10)
            else:
                # free lane: constant speed, faded at both ends
                pos = ((c.t - e) / PERIOD_FREE + j / n_pk + k * 0.37) % 1.0
                x = x0 + 4 + travel * pos
                op = clamp(min(pos, 1 - pos) * 8)
            out.append(_packet(x, ly + 2, pw, pitch - 4, op))
    out.append(body(px + 40, cy - 100, 160, 200, 28, ORANGE, shine=0.25, shade=0.2))
    out.append(text(px + 120, cy, "内存", 36, 800, AMBER_INK))
    out.append(body(px + 580, cy - 100, 160, 200, 28, BLUE, shine=0.25, shade=0.2))
    out.append(text(px + 660, cy, "计算", 36, 800, TEXT))
    out.append(text(px + PANEL_W / 2, py + 520, sub, _fs(sub, 36, 700, 700), 700, TEXT))
    return "".join(out)


def _panel_card(c: Ctx, px: float, side: int, title: str, value: str, sub: str, col: str, border: str,
                e: float, scale: float) -> str:
    py = PANEL_Y
    cid = f"cmp_sheen_{side}"
    sx = px - 260 + (((c.t - e) * 0.18) % 1.0) * (PANEL_W + 260)
    sd, su = lin([(0, "#FFFFFF", 0.0), (0.5, "#FFFFFF", 0.09), (1, "#FFFFFF", 0.0)], 0, 0, 1, 0)
    sheen = (f'<defs><clipPath id="{cid}"><rect x="{px}" y="{py}" width="{PANEL_W}" height="{PANEL_H}" rx="20"/>'
             f'</clipPath></defs><g clip-path="url(#{cid})">{sd}'
             f'<rect x="{sx:.1f}" y="{py}" width="260" height="{PANEL_H}" fill="{su}"/></g>')
    cx = px + PANEL_W / 2
    value_svg = _impact_pop(c, text(cx, py + 300, value, _fs(value, 96, 900, 700), 900, col), cx, py + 300)
    inner = (_frame(px, py, border) + sheen
             + text(cx, py + 90, title, _fs(title, 44, 800, 680), 800, SUB)
             + value_svg
             + text(cx, py + 430, sub, _fs(sub, 36, 700, 700), 700, TEXT))
    if scale != 1.0:
        inner = g(inner, s=scale, ox=px + PANEL_W / 2, oy=py + PANEL_H / 2)
    return inner


def SplitCompare(c: Ctx) -> str:
    """mode: pipes | panels. pipes: a 2-lane memory pipe (left) versus a wide pipe with ratio x as many lanes
    (right), green packets queue on the left and flow freely on the right. panels: two value panels with a
    big value each. Reveal highlights the right side (yellow border; panels also scale it up 4 %)."""
    mode = str(c.props.get("mode", "pipes"))
    lt, lv, ls, lc = _side(c, "left", LEFT_DEF)
    rt, rv, rs, rc = _side(c, "right", RIGHT_DEF)
    rev, e = _rev(c), c.ent()
    border_r = mix(GREY, YELLOW, progress(c.t, rev, 0.35))
    if mode == "panels":
        scale = 1.0 + 0.04 * ease_io(progress(c.t, rev, 0.5))
        inner = (_panel_card(c, LEFT_X, 0, lt, lv, ls, lc, GREY, e, 1.0)
                 + _panel_card(c, RIGHT_X, 1, rt, rv, rs, rc, border_r, e, scale))
    else:
        n_r = max(1, min(24, int(round(2 * _num(c.props.get("ratio", 8), 8.0)))))
        pitch = min(LANE_PITCH, PIPE_CAP / n_r)
        inner = (_pipe_panel(c, LEFT_X, lt, lv, ls, lc, GREY, 2, pitch, True, e)
                 + _pipe_panel(c, RIGHT_X, rt, rv, rs, rc, border_r, n_r, pitch, False, e))
    inner += f'<rect x="958.5" y="180" width="3" height="540" fill="{GREY}"/>'
    return _fit(c, g(inner, s=_pop_scale(c, 0.0), ox=960, oy=540))


# ----------------------------------------------------------------- HBars
BAR_X, BAR_MAX, BAR_H = 470.0, 1150.0, 64.0
ROW_TOP, ROW_BOT = 170.0, 720.0
DEF_ITEMS = [
    {"label": "FP16", "value": 14, "text": "14 GB", "color": "green"},
    {"label": "INT8", "value": 7, "text": "7 GB", "color": "green"},
    {"label": "INT4", "value": 3.5, "text": "3.5 GB", "color": "green"},
    {"label": "INT2", "value": 1.75, "text": "1.75 GB", "color": "green"},
]


def _bar_text(it: dict, unit: str) -> str:
    if it.get("text") not in (None, ""):
        return str(it["text"])
    s = f"{_num(it.get('value'), 0.0):g}"
    return f"{s} {unit}" if unit else s


def HBars(c: Ctx) -> str:
    """mode: bars (only mode). Up to 6 horizontal bars, one row each, growing in turn. items: [{label, value,
    text, color}]. highlight (index) gets a yellow outline on reveal, the others dim; it pulses on impact and a
    sheen keeps sliding along it. Default: FP16 14 / INT8 7 / INT4 3.5 / INT2 1.75 GB, highlight 2."""
    raw = c.props.get("items")
    given = [it for it in raw if isinstance(it, dict)][:6] if isinstance(raw, list) else []
    items = given or DEF_ITEMS
    hl = int(_num(c.props.get("highlight", 2 if not given else -1), -1))
    unit = str(c.props.get("unit", "") or "")
    note = str(c.props.get("note", "") or "")
    rev, imp, e = _rev(c), _imp(c), c.ent()
    n = len(items)
    vals = [max(0.0, _num(it.get("value"), 0.0)) for it in items]
    vmax = max(vals + [1e-9])
    labels = [str(it.get("label", "")) for it in items]
    labels_sz = [_fs(s, 40, 800, 320) for s in labels]
    tvals = [_bar_text(it, unit) for it in items]
    tsz = [_fs(s, 44, 800, 300) for s in tvals]
    tw = max(measure(s, sz, 800) for s, sz in zip(tvals, tsz))
    bar_max = max(400.0, min(BAR_MAX, 1300.0 - tw))
    slot = (ROW_BOT - ROW_TOP) / n

    out = []
    for i, it in enumerate(items):
        cy = ROW_TOP + (i + 0.5) * slot
        bar_y = cy - BAR_H / 2
        col = _col(it.get("color"), "green")
        grow = ease_out_expo(progress(c.t, e + 0.25 * i, 0.6))
        bw = bar_max * vals[i] / vmax * grow
        bar = body(BAR_X, bar_y, bw, BAR_H, BAR_H / 2, col, shine=0.25, shade=0.2, rim=False) if bw > 1 else ""
        if i == hl:
            if bw > 40:
                sw = min(120.0, bw * 0.5)
                sx = BAR_X + (bw - sw) * ((c.t * 0.2) % 1.0)
                sd, su = lin([(0, "#FFFFFF", 0.0), (0.5, "#FFFFFF", 0.35), (1, "#FFFFFF", 0.0)], 0, 0, 1, 0)
                bar += (f'{sd}<rect x="{sx:.1f}" y="{bar_y + 8:.1f}" width="{sw:.1f}" height="{BAR_H - 16:.1f}" '
                        f'rx="24" fill="{su}"/>')
            ol = progress(c.t, rev, 0.3)
            bar += (f'<rect x="{BAR_X - 5}" y="{bar_y - 5:.1f}" width="{bw + 10:.1f}" height="{BAR_H + 10:.1f}" '
                    f'rx="{BAR_H / 2 + 5:.1f}" fill="none" stroke="{YELLOW}" stroke-width="6" '
                    f'stroke-opacity="{ol:.3f}"/>')
            u = clamp((c.t - imp) / 0.5)
            bar = g(bar, sy=1.0 + 0.15 * math.sin(math.pi * u), ox=BAR_X + bw / 2, oy=cy)
        row_op = lerp(1.0, 0.45, progress(c.t, rev, 0.4)) if (hl >= 0 and i != hl) else 1.0
        row = (bar
               + text(440, cy, labels[i], labels_sz[i], 800, TEXT, "end")
               + text(BAR_X + bw + 20, cy, tvals[i], tsz[i], 800, TEXT, "start", opacity=grow))
        out.append(g(row, opacity=row_op))
    if note:
        out.append(text(1800, 150, note, _fs(note, 30, 700, 900), 700, SUB, "end"))
    return _fit(c, g("".join(out), s=_pop_scale(c, 0.0), ox=960, oy=540))


# ----------------------------------------------------------------- ChipTags
DIE_X, DIE_Y, DIE_W, DIE_H = 620, 200, 680, 460
BUS_Y = 530
DEF_TAGS = ["KV Cache", "Cache 命中率", "Runtime", "Kernel", "功耗", "散热"]
# (anchor on the die, tag centre) per tag slot, in appearance order
SLOTS = [((620, 260), (330, 260)), ((1300, 260), (1600, 260)), ((800, 200), (800, 150)),
         ((800, 660), (800, 720)), ((620, 540), (330, 540)), ((1300, 400), (1600, 400)),
         ((1120, 200), (1120, 150)), ((1120, 660), (1120, 720))]


def _chip_blocks(c: Ctx, e: float) -> str:
    out = [f'<rect x="{DIE_X}" y="{DIE_Y}" width="{DIE_W}" height="{DIE_H}" rx="40" fill="{PANEL2}" '
           f'stroke="{GREY}" stroke-width="3"/>',
           f'<rect x="880" y="327" width="40" height="6" rx="3" fill="{GREY}"/>',
           f'<rect x="880" y="527" width="40" height="6" rx="3" fill="{GREY}"/>',
           body(660, 260, 220, 340, 26, BLUE, shine=0.25, shade=0.2),
           text(770, 430, "NPU", 40, 800, TEXT),
           body(920, 260, 340, 140, 24, STONE, shine=0.15, shade=0.2),
           text(1090, 330, "Cache", 36, 800, TEXT),
           body(920, 460, 340, 140, 24, STONE, shine=0.15, shade=0.2),
           text(1090, 530, "MC", 36, 800, TEXT),
           body(1340, 440, 120, 180, 22, ORANGE, shine=0.25, shade=0.2),
           text(1400, 530, "LPDDR", fit_size("LPDDR", 30, 800, 104), 800, AMBER_INK)]
    # soft data flow on the orange bus between the memory controller and LPDDR
    out.append(f'<rect x="1260" y="{BUS_Y - 3}" width="80" height="6" rx="3" fill="{ORANGE}"/>')
    for j in range(2):
        pos = ((c.t - e) * 0.7 + j / 2) % 1.0
        out.append(f'<circle cx="{1270 + 60 * pos:.1f}" cy="{BUS_Y}" r="7" fill="{ORANGE}" '
                   f'fill-opacity="{clamp(min(pos, 1 - pos) * 8):.3f}"/>')
    return "".join(out)


def ChipTags(c: Ctx) -> str:
    """mode: tags (only mode). A chip die with an NPU, Cache and MC block and an orange LPDDR block on its right
    edge. Tags are pill labels outside the die, each attached by a leader line to its own point on the die; they
    appear one at a time from the reveal beat (or 0.6 s after entrance). emphasis (index) gets a yellow border
    on impact."""
    raw = c.props.get("tags")
    tags = [str(x) for x in raw][:len(SLOTS)] if isinstance(raw, list) and raw else DEF_TAGS
    emph = int(_num(c.props.get("emphasis", -1), -1))
    e = c.ent()
    base = c.beats.at("reveal")
    base = e + 0.6 if base is None else base
    imp = _imp(c)
    out = [_chip_blocks(c, e)]
    for k, label in enumerate(tags):
        (ax, ay), (tx, ty) = SLOTS[k]
        start = base + 0.45 * k
        if c.t < start:
            continue
        pop = max(0.01, back_out(progress(c.t, start, 0.45)))
        border = mix(SUB, YELLOW, progress(c.t, imp, 0.3)) if k == emph else SUB
        size = fit_size(label, 34, 800, 260)
        w = measure(label, size, 800) + size * 1.4
        h = size * 1.75
        tag = (f'<rect x="{tx - w / 2:.1f}" y="{ty - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" '
               f'fill="{CHIP}" stroke="{border}" stroke-width="3"/>' + text(tx, ty, label, size, 800, TEXT))
        leader = (f'<line x1="{ax}" y1="{ay}" x2="{tx}" y2="{ty}" stroke="{SUB}" stroke-width="3" '
                  f'stroke-opacity="0.85"/><circle cx="{ax}" cy="{ay}" r="8" fill="{SUB}"/>')
        out.append(g(leader + tag, s=pop, ox=tx, oy=ty))
    return _fit(c, g("".join(out), s=_pop_scale(c, 0.0), ox=960, oy=540))


for _fn in (SplitCompare, HBars, ChipTags):
    _fn.native_landscape = True  # lays out the 16:9 canvas itself; scene.py skips the portrait slot scaling
    _fn.continuous_motion = True  # something moves on every frame; never still for long


COMPONENTS = {"SplitCompare": SplitCompare, "HBars": HBars, "ChipTags": ChipTags}
