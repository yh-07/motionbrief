# SPDX-License-Identifier: Apache-2.0
"""Explainer components, 16:9 (1920x1080 design space): CodeTerminal (code typed in a terminal, then its
output), Equation (a fraction or a product with a staged reveal) and TokenStream (decode: tokens fed one by
one by data packets; prefill: the whole prompt processed at once).

Layout is authored in a 1920x1080 design space and uniformly scaled and centred onto c.canvas. The scene
supplies the flat dark background; nothing here paints a full-screen backdrop, glow pool, particle or HUD.
Main visuals stay in x 120..1800, y 120..760.
"""
from __future__ import annotations

import math
import re

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.easing import clamp, ease_out_expo, lerp, progress
from motionbrief.render.svg_canvas.prims import back_out, body, ease_io, esc, fit_size, g, measure, mix, pill, text

BLUE, ORANGE, GREEN, YELLOW = "#3B82F6", "#F59E0B", "#22C55E", "#FACC15"
GREY, CHIP, PLATE, TERM = "#334155", "#1E2430", "#121620", "#0F1218"
TEXT, SUB, AMBER_INK = "#F8FAFC", "#94A3B8", "#3A2200"
KEYWORD, COMMENT = "#60A5FA", "#64748B"
MONO = "Consolas, 'Noto Sans Mono', monospace"
DESIGN_W, DESIGN_H = 1920, 1080
NBSP = "\u00a0"
PY_KEYWORDS = {"for", "in", "print", "def", "import", "return", "range", "if", "elif", "else", "while", "from",
               "as", "class", "with", "not", "and", "or", "True", "False", "None", "lambda", "pass", "break",
               "continue"}
DEFAULT_CODE = "import math\nvalues = [3, 1, 4, 1, 5]\nprint(math.sqrt(sum(values)))\n# done"
DECODE_TOKENS = ["因", "为", "大", "模", "型"]
PREFILL_PROMPT = "为什么天空是蓝色的？"
TOKEN_RE = re.compile(r"(#[^\n]*)|(\"[^\"\n]*\"|'[^'\n]*')|(\b\d[\d_]*(?:\.\d+)?\b)|([A-Za-z_]\w*)")


def _fit(c: Ctx, inner: str) -> str:
    """Uniform scale of the 1920x1080 design space onto the real canvas, centred."""
    k = min(c.canvas.w / DESIGN_W, c.canvas.h / DESIGN_H)
    return g(inner, tx=(c.canvas.w - DESIGN_W * k) / 2, ty=(c.canvas.h - DESIGN_H * k) / 2, s=k, ox=0, oy=0)


def _pop_scale(c: Ctx, delay: float) -> float:
    """Entrance pop that starts at 0.85, so the first frame already shows the static parts."""
    return 0.85 + 0.15 * c.pop(delay, 0.5)


def _at(c: Ctx, name: str, fallback: float) -> float:
    v = c.beats.at(name)
    return fallback if v is None else v


def _units(s: str) -> float:
    """Width of a monospace line in font-size units (CJK counts as a full em)."""
    return sum(1.0 if ord(ch) >= 0x2E80 else 0.6 for ch in s)


# ----------------------------------------------------------------- CodeTerminal
def _colours(code: str) -> list[str]:
    cols = [TEXT] * len(code)
    for m in TOKEN_RE.finditer(code):
        if m.group(1):
            col = COMMENT
        elif m.group(2):
            col = GREEN
        elif m.group(3):
            col = ORANGE
        else:
            col = KEYWORD if m.group(4) in PY_KEYWORDS else TEXT
        for i in range(m.start(), m.end()):
            cols[i] = col
    return cols


def _runs(line: str, cols: list[str], base: int, upto: int) -> list[tuple[str, str]]:
    runs: list[list[str]] = []
    for j in range(upto):
        ch = NBSP if line[j] == " " else line[j]
        col = cols[base + j]
        if runs and runs[-1][1] == col:
            runs[-1][0] += ch
        else:
            runs.append([ch, col])
    return [(s, col) for s, col in runs]


def _mono_line(x: float, yc: float, runs: list[tuple[str, str]], size: float, opacity: float = 1.0) -> str:
    spans = "".join(f'<tspan fill="{col}">{esc(s)}</tspan>' for s, col in runs)
    return (f'<text x="{x:.1f}" y="{yc + size * 0.36:.1f}" font-family="{MONO}" font-size="{size:.1f}" '
            f'font-weight="500" xml:space="preserve" opacity="{clamp(opacity):.3f}">{spans}</text>')


def CodeTerminal(c: Ctx) -> str:
    """mode: run (only mode). A terminal window: the code is typed from the entrance up to the reveal beat with
    a blinking cursor, then the output lines appear one per 0.25 s; the highlighted output line gets a yellow box
    that pops in at impact."""
    code_src = str(c.props.get("code", DEFAULT_CODE)).replace("\t", "    ")
    code = "\n".join(code_src.split("\n")[:12])
    out_text = str(c.props.get("output", ""))
    out_lines = out_text.split("\n")[:10] if out_text else []
    highlight = int(c.props.get("highlight", -1))
    title = str(c.props.get("title", "python"))
    code_lines = code.split("\n")
    n_c, n_o = len(code_lines), len(out_lines)

    # font size: fit the stacked rows into the panel height and the longest line into the width
    rows = n_c + max(1, n_o)
    size = min(34.0, 471.0 / (rows * 1.4))
    wu = max([_units(s) for s in code_lines + out_lines] + [1.0])
    size = max(22.0, min(size, 1520.0 / wu))
    lh = size * 1.4
    cw = size * 0.6

    ent = c.ent()
    rev = c.beats.at("reveal")
    type_end = rev if rev is not None else c.t0 + 0.45 * (c.t1 - c.t0)
    if type_end <= ent + 0.2:
        type_end = ent + 0.5
    k = int(len(code) * progress(c.t, ent, type_end - ent))
    out_start = type_end
    imp = _at(c, "impact", out_start + n_o * 0.25 + 0.3)

    code_top = 200.0
    div_y = code_top + max(n_c, 1) * lh + 22
    out_top = div_y + 24

    parts: list[str] = []
    cols = _colours(code)
    pos = 0
    for row, line in enumerate(code_lines):
        vis = min(len(line), max(0, k - pos))
        if vis > 0:
            parts.append(_mono_line(200, code_top + row * lh + lh / 2, _runs(line, cols, pos, vis), size))
        pos += len(line) + 1
    before = code[:k]
    crow = before.count("\n")
    ccol = len(before) - (before.rfind("\n") + 1)
    blink = 1.0 if int(c.t * 2.5) % 2 == 0 else 0.15
    parts.append(f'<rect x="{200 + ccol * cw:.1f}" y="{code_top + crow * lh + lh * 0.1:.1f}" width="{cw:.1f}" '
                 f'height="{lh * 0.8:.1f}" rx="2" fill="{TEXT}" fill-opacity="{blink:.2f}"/>')

    for i, line in enumerate(out_lines):
        s = out_start + i * 0.25
        if c.t < s:
            continue
        parts.append(_mono_line(200, out_top + i * lh + lh / 2, [(line.replace(" ", NBSP), GREEN)], size,
                                opacity=clamp((c.t - s) / 0.2)))

    if 0 <= highlight < n_o and c.t >= imp:
        hl_w = min(1544.0, _units(out_lines[highlight]) * size + 28)
        hl_y = out_top + highlight * lh + lh * 0.08
        box = (f'<rect x="188" y="{hl_y:.1f}" width="{hl_w:.1f}" height="{lh * 0.84:.1f}" rx="12" fill="none" '
               f'stroke="{YELLOW}" stroke-width="3"/>')
        parts.append(g(box, s=back_out(progress(c.t, imp, 0.35)), ox=188 + hl_w / 2, oy=hl_y + lh * 0.42))

    frame = (f'<defs><clipPath id="cterm_clip"><rect x="160" y="130" width="1600" height="630" rx="18"/>'
             f'</clipPath></defs>'
             f'<rect x="160" y="130" width="1600" height="630" rx="18" fill="{TERM}" stroke="{GREY}" '
             f'stroke-width="2"/>'
             f'<g clip-path="url(#cterm_clip)"><rect x="160" y="130" width="1600" height="48" fill="{CHIP}"/></g>'
             f'<circle cx="196" cy="154" r="7" fill="#9A4B4B"/>'
             f'<circle cx="224" cy="154" r="7" fill="#9A7433"/>'
             f'<circle cx="252" cy="154" r="7" fill="#3E7D59"/>'
             + text(296, 154, title, 26, 600, SUB, anchor="start")
             + f'<rect x="160" y="{div_y:.1f}" width="1600" height="2" fill="{GREY}"/>')
    return _fit(c, g(frame + "".join(parts), s=_pop_scale(c, 0.0), ox=960, oy=445))


# ----------------------------------------------------------------- Equation
def _result(c: Ctx, res: str, x: float, y: float, size: float, rev: float, imp: float) -> str:
    """Result text: pops in at the reveal, punches 1.0 -> 1.12 -> 1.0 at impact, with a yellow underline."""
    if c.t < rev:
        return ""
    pop = back_out(progress(c.t, rev, 0.45))
    punch = 1.0 + 0.12 * math.sin(math.pi * progress(c.t, imp, 0.5))
    sweep = ease_io(progress(c.t, imp, 0.35))
    line = ""
    if sweep > 0:
        w = measure(res, size, 900)
        line = (f'<rect x="{x:.1f}" y="{y + size * 0.5 + 14:.1f}" width="{w * sweep:.1f}" height="8" rx="4" '
                f'fill="{YELLOW}"/>')
    return g(text(x, y, res, size, 900, TEXT, anchor="start") + line, s=pop * punch, ox=x, oy=y)


def _fraction(c: Ctx, ent: float, num: str, den: str, res: str) -> str:
    a = c.t - ent
    rev = _at(c, "reveal", ent + 1.8)
    imp = _at(c, "impact", rev + 0.9)
    e1 = ease_out_expo(progress(a, 0.0, 0.6))
    e2 = ease_out_expo(progress(a, 0.6, 0.6))
    e3 = ease_io(progress(a, 1.0, 0.4))
    out = [text(700 - 260 * (1 - e1), 300 - 160 * (1 - e1), num, fit_size(num, 96, 900, 440), 900, ORANGE,
                opacity=0.35 + 0.65 * e1)]
    out.append(text(700, 470 + 90 * (1 - e2), den, fit_size(den, 96, 900, 440), 900, GREEN, opacity=e2))
    out.append(f'<rect x="460" y="376" width="{480 * e3:.1f}" height="8" rx="4" fill="{TEXT}"/>')
    if c.t >= rev:
        sign = "" if res.lstrip()[:1] in "≈=≤≥<>~" else "="  # the result may carry its own relation sign
        out.append(g(text(1030, 400, sign, 96, 900, TEXT), s=back_out(progress(c.t, rev, 0.45)), ox=1030, oy=400))
    out.append(_result(c, res, 1100, 400, fit_size(res, 104, 900, 690), rev, imp))
    return "".join(out)


def _product(c: Ctx, ent: float, a_txt: str, b_txt: str, res: str) -> str:
    a = c.t - ent
    rev = _at(c, "reveal", ent + 1.8)
    imp = _at(c, "impact", rev + 0.9)
    pieces = [(a_txt, 96.0, GREEN), ("×", 96.0, TEXT), (b_txt, 96.0, ORANGE), ("=", 96.0, TEXT),
              (res, 120.0, TEXT)]
    if res.lstrip()[:1] in "≈=≤≥<>~":  # the result carries its own relation sign
        pieces[3] = ("", 0.0, TEXT)
    gap = 34.0
    total = sum(measure(s, sz, 900) for s, sz, _ in pieces) + gap * (len(pieces) - 1)
    k = min(1.0, 1640.0 / total) if total > 0 else 1.0
    x = 960 - total * k / 2
    out = []
    for i, (s, sz, col) in enumerate(pieces):
        size = sz * k
        w = measure(s, size, 900)
        if i == 0:
            e = ease_out_expo(progress(a, 0.0, 0.6))
            out.append(text(x - 120 * (1 - e), 420, s, size, 900, col, anchor="start", opacity=0.35 + 0.65 * e))
        elif i in (1, 2):
            e = ease_out_expo(progress(a, 0.6, 0.6))
            p = back_out(progress(a, 0.6, 0.5))
            out.append(g(text(x, 420, s, size, 900, col, anchor="start"), s=0.8 + 0.2 * p, ox=x + w / 2, oy=420,
                         opacity=e))
        elif i == 3:
            if c.t >= rev:
                out.append(g(text(x, 420, s, size, 900, col, anchor="start"),
                             s=back_out(progress(c.t, rev, 0.45)), ox=x + w / 2, oy=420))
        else:
            out.append(_result(c, s, x, 420, size, rev, imp))
        x += w + gap * k
    return "".join(out)


def Equation(c: Ctx) -> str:
    """mode: fraction (num over den = result) | product (a x b = result). Parts fly or rise in, the '=' and the
    result pop in at the reveal, and at impact a yellow underline sweeps under the result which punches."""
    mode = str(c.props.get("mode", "fraction"))
    ent = c.ent()
    note = str(c.props.get("note", ""))
    if mode == "product":
        inner = _product(c, ent, str(c.props.get("a", "7B")), str(c.props.get("b", "2 Byte")),
                         str(c.props.get("result", "≈ 14 GB")))
        ox, oy = 960.0, 420.0
    else:
        inner = _fraction(c, ent, str(c.props.get("num", "60 GB/s")), str(c.props.get("den", "~4 GB")),
                          str(c.props.get("result", "≈ 15 token/s")))
        ox, oy = 700.0, 380.0
    if note:
        inner += text(1800, 150, note, 32, 500, SUB, anchor="end")
    breath = 1.0 + 0.01 * math.sin(2 * math.pi * (c.t - ent) / 3.0)
    return _fit(c, g(inner, s=breath, ox=ox, oy=oy))


# ----------------------------------------------------------------- TokenStream
PK_W, PK_H = 44, 30
LANE_Y = 360.0      # packets travel in the top lane of the bar
TOK_Y = 432.0       # tokens sit in the lower part of the bar


def _packet(cx: float, cy: float, opacity: float) -> str:
    if opacity <= 0.01:
        return ""
    x, y = cx - PK_W / 2, cy - PK_H / 2
    inner = (body(x, y, PK_W, PK_H, 9, GREEN, shine=0.3, shade=0.2, rim=False)
             + f'<rect x="{x + 8:.1f}" y="{y + 7:.1f}" width="12" height="5" rx="2.5" fill="#FFFFFF" fill-opacity="0.9"/>')
    return g(inner, opacity=opacity)


def _decode(c: Ctx) -> str:
    raw = c.props.get("tokens", DECODE_TOKENS)
    tokens = [str(t) for t in raw] if isinstance(raw, (list, tuple)) else [str(raw)]
    n = len(tokens)
    per = 1.0 / max(0.05, float(c.props.get("rate", 1.5)))
    label = str(c.props.get("label", ""))
    start = c.ent() + 0.4
    # each token gets its own measured width (multi-character tokens such as "edge" or "V12"), shrunk to fit
    fs, gap = 96.0, 28.0
    widths = [max(measure(t, fs, 900), fs * 0.6) for t in tokens]
    total = sum(widths) + gap * max(n - 1, 0)
    if total > 1440:
        k = 1440 / total
        fs, gap, widths = fs * k, gap * k, [w * k for w in widths]
        total = 1440.0
    centers, x = [], 960 - total / 2
    for w in widths:
        centers.append(x + w / 2)
        x += w + gap
    pitch = (widths[-1] + gap) if n else 120.0  # width of the pulse box on the last token

    def slot(i: int) -> float:
        return centers[i]

    parts = [f'<rect x="200" y="330" width="1520" height="180" rx="36" fill="{PLATE}" stroke="{GREY}" '
             f'stroke-width="2"/>']
    last_arrival = start + (n - 1) * per
    if n and c.t >= last_arrival:  # loop: soft pulse on the last slot once the stream has finished
        op = 0.10 + 0.12 * (0.5 + 0.5 * math.sin(2 * math.pi * c.t / 1.2))
        parts.append(f'<rect x="{slot(n - 1) - pitch / 2 + 6:.1f}" y="370" width="{pitch - 12:.1f}" height="124" '
                     f'rx="24" fill="{GREEN}" fill-opacity="{op:.3f}"/>')
    shown = 0
    for i, tok in enumerate(tokens):
        ai = start + i * per
        if c.t < ai:
            continue
        shown += 1
        p = progress(c.t, ai, 0.18)
        parts.append(g(text(slot(i), TOK_Y, tok, fs, 900, TEXT), s=0.7 + 0.3 * back_out(p), ox=slot(i), oy=TOK_Y,
                       opacity=clamp(p * 3)))

    arrivals = [(start + i * per, slot(i)) for i in range(n)]
    if n and c.t >= last_arrival:
        m0 = int((c.t - last_arrival) / per)
        arrivals += [(last_arrival + m * per, slot(n - 1)) for m in range(max(1, m0 - 1), m0 + 3)]
    for arr, sx in arrivals:
        s0 = arr - 0.5
        if c.t < s0 or c.t >= arr + 0.12:
            continue
        x = lerp(140, sx, ease_io(progress(c.t, s0, 0.5)))
        parts.append(_packet(x, LANE_Y, 1.0 - clamp((c.t - arr) / 0.12)))

    parts.append(text(200, 600, f"{shown} tokens", 40, 700, SUB, anchor="start"))
    if label:
        parts.append(text(1720, 600, label, 44, 800, ORANGE, anchor="end"))
    return _fit(c, "".join(parts))


def _prefill(c: Ctx) -> str:
    prompt = str(c.props.get("prompt", PREFILL_PROMPT))
    label = str(c.props.get("label", "PREFILL"))
    chars = [ch for ch in prompt if not ch.isspace()]
    n = len(chars)
    ent = c.ent()
    rev = _at(c, "reveal", ent + 1.2)
    gap = 12.0 if n <= 16 else 6.0
    cw = min(72.0, (1600.0 - gap * max(n - 1, 0)) / max(n, 1))
    fs = min(44.0, cw * 0.58)
    total = n * cw + max(n - 1, 0) * gap
    x0 = 960 - total / 2
    e = ease_out_expo(progress(c.t - ent, 0.0, 0.7))
    lit = progress(c.t, rev, 0.25)
    sweep_x = x0 - cw + (((c.t - rev) / 1.6) % 1.0) * (total + 2 * cw)

    row = []
    for i, ch in enumerate(chars):
        cx = x0 + i * (cw + gap) + cw / 2
        if c.t >= rev:
            glow = max(0.0, 1.0 - abs(cx - sweep_x) / (cw * 1.2))
            fill = mix(PLATE, mix(BLUE, "#FFFFFF", 0.35 * glow), lit)
            stroke_op = 1.0
        else:
            fill = PLATE
            stroke_op = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(2 * math.pi * c.t / 1.6 + i * 0.4))
        row.append(f'<rect x="{cx - cw / 2:.1f}" y="{400 - cw / 2:.1f}" width="{cw:.1f}" height="{cw:.1f}" '
                   f'rx="{cw * 0.18:.1f}" fill="{fill}" stroke="{BLUE}" stroke-width="3" '
                   f'stroke-opacity="{stroke_op:.3f}"/>')
        row.append(text(cx, 400, ch, fs, 900, TEXT))
    parts = [g("".join(row), tx=-300 * (1 - e), opacity=0.6 + 0.4 * e)]
    if label and c.t >= rev:
        p = back_out(progress(c.t, rev, 0.4))
        parts.append(g(pill(960, 250, label, 40, ORANGE, text_col=AMBER_INK), s=p, ox=960, oy=250))
    return _fit(c, "".join(parts))


def TokenStream(c: Ctx) -> str:
    """mode: decode (tokens appear one by one, each fed by a data packet) | prefill (whole prompt processed at
    once). decode: packets slide in on a lane and each token pops in when its packet arrives; after the last token
    a pulse keeps looping. prefill: the prompt chips slide in, then light up together with a label pill."""
    if str(c.props.get("mode", "decode")) == "prefill":
        return _prefill(c)
    return _decode(c)


for _fn in (CodeTerminal, Equation, TokenStream):
    _fn.native_landscape = True  # lays out the 16:9 canvas itself; scene.py skips the portrait slot scaling
    _fn.continuous_motion = True  # never sits still: blinking cursor, packets, breathing, shimmer


COMPONENTS = {"CodeTerminal": CodeTerminal, "Equation": Equation, "TokenStream": TokenStream}
