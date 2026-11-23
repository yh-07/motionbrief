# SPDX-License-Identifier: Apache-2.0
"""Chip-stage components: a phone that zooms into its SoC (PhoneSoc), matrix tiles for prefill and decode
(MatrixArray) and a model block that shrinks with quantisation (ModelShrink).

Layout is authored in a 1920x1080 design space (16:9) and uniformly scaled and centred onto c.canvas, so the
same numbers hold for any landscape canvas. The scene supplies the flat dark background; nothing here paints
a full-screen backdrop, glow pool, particle or HUD. Main visuals stay in x 80..1840, y 120..760.
"""
from __future__ import annotations

import math

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.easing import clamp, lerp, progress
from motionbrief.render.svg_canvas.prims import body, ease_io, g, mix, pill, text

BLUE, ORANGE, GREEN, RED = "#3B82F6", "#F59E0B", "#22C55E", "#EF4444"
GREY, CHIP, PLATE, CELL_DARK = "#334155", "#262D3B", "#121620", "#1E2430"
TEXT, SUB, AMBER_INK = "#F8FAFC", "#94A3B8", "#3A2200"
DESIGN_W, DESIGN_H = 1920, 1080
SAFE_X0, SAFE_Y0, SAFE_W, SAFE_H = 80, 120, 1760, 640


def _fit(c: Ctx, inner: str) -> str:
    """Uniform scale of the 1920x1080 design space onto the real canvas, centred."""
    k = min(c.canvas.w / DESIGN_W, c.canvas.h / DESIGN_H)
    return g(inner, tx=(c.canvas.w - DESIGN_W * k) / 2, ty=(c.canvas.h - DESIGN_H * k) / 2, s=k, ox=0, oy=0)


def _pop_scale(c: Ctx, delay: float) -> float:
    """Entrance pop that starts at 0.85, so the first frame already shows the static parts."""
    return 0.85 + 0.15 * c.pop(delay, 0.5)


def _packet(x: float, y: float, w: float = 40, h: float = 26, opacity: float = 1.0) -> str:
    """Green data packet with a small white highlight."""
    if opacity <= 0.01:
        return ""
    return g(body(x, y, w, h, 9, GREEN, shine=0.3, shade=0.2, rim=False)
             + f'<rect x="{x + 7:.1f}" y="{y + 6:.1f}" width="10" height="5" rx="2.5" fill="#FFFFFF" fill-opacity="0.9"/>',
             opacity=opacity, ox=x + w / 2, oy=y + h / 2)


def _clip(cid: str) -> str:
    """Clip rectangle for the safe main area (design units)."""
    return (f'<defs><clipPath id="{cid}"><rect x="{SAFE_X0}" y="{SAFE_Y0}" width="{SAFE_W}" height="{SAFE_H}"/>'
            f'</clipPath></defs>')


# ----------------------------------------------------------------- PhoneSoc
PH_X, PH_Y, PH_W, PH_H = 580, 230, 760, 420        # phone outline, centre (960, 440)
PH_CX, PH_CY = PH_X + PH_W / 2, PH_Y + PH_H / 2
SOC_X, SOC_Y, SOC_S = 840, 320, 240                 # square SoC package
NPU_X, NPU_Y, NPU_S = 885, 365, 150                 # NPU block inside the SoC
LP_X, LP_Y, LP_W, LP_H = 1160, 370, 140, 140        # LPDDR block outside the SoC
LINK_Y, LINK_H = PH_CY, 6                           # thin link between NPU and LPDDR


def PhoneSoc(c: Ctx) -> str:
    """mode: soc_zoom (only mode). A phone with a centred SoC; the NPU and LPDDR link inside. zoom 0 shows the
    whole phone, zoom 1 magnifies the SoC and NPU to fill the main area. Blue packets flow along the link."""
    zoom = clamp(float(c.props.get("zoom", 0.0)))
    rev = c.beats.at("reveal")
    if rev is not None:
        zoom = max(zoom, progress(c.t, rev, 1.0))
    zoom_eff = clamp(zoom)
    scale = 1.0 + 2.2 * zoom_eff

    # phone body, speaker slot
    phone = body(PH_X, PH_Y, PH_W, PH_H, 56, PLATE, shine=0.05, shade=0.15, rim=False)
    phone += (f'<rect x="{PH_X + 1.5}" y="{PH_Y + 1.5}" width="{PH_W - 3}" height="{PH_H - 3}" rx="55" fill="none" '
              f'stroke="{GREY}" stroke-width="3"/>')
    phone += f'<rect x="{PH_CX - 40}" y="{PH_Y + 22}" width="80" height="8" rx="4" fill="{GREY}"/>'

    # SoC package with its label
    soc = body(SOC_X, SOC_Y, SOC_S, SOC_S, 34, CHIP, shine=0.12, shade=0.2)
    soc += text(SOC_X + SOC_S / 2, SOC_Y + SOC_S + 40, "SoC", 34, 800, SUB)

    # NPU (blue) inside the SoC
    npu = body(NPU_X, NPU_Y, NPU_S, NPU_S, 26, BLUE, shine=0.25, shade=0.2)
    npu += text(NPU_X + NPU_S / 2, NPU_Y + NPU_S / 2, "NPU", 36, 800, TEXT)

    # LPDDR (orange) outside the SoC, with a thin link to the NPU
    lp = body(LP_X, LP_Y, LP_W, LP_H, 24, ORANGE, shine=0.25, shade=0.2)
    lp += text(LP_X + LP_W / 2, LP_Y + LP_H / 2, "LPDDR", 30, 800, AMBER_INK)
    link_x0, link_x1 = NPU_X + NPU_S, LP_X
    link = (f'<rect x="{link_x0:.1f}" y="{LINK_Y - LINK_H / 2:.1f}" width="{link_x1 - link_x0:.1f}" '
            f'height="{LINK_H}" rx="3" fill="{ORANGE}"/>')
    for k in range(2):  # two packets drift along the link, so the link is never still
        p = ((c.t - c.ent()) * 0.5 + k / 2) % 1.0
        link += (f'<circle cx="{lerp(link_x0, link_x1, p):.1f}" cy="{LINK_Y:.1f}" r="7" fill="{ORANGE}" '
                 f'fill-opacity="{clamp(min(p, 1 - p) * 8):.3f}"/>')

    inner = phone + soc + link + npu + lp
    pivot_x = (NPU_X + NPU_S / 2 + LP_X + LP_W / 2) / 2  # between NPU and LPDDR, so both stay in the safe area
    zoom_g = g(inner, s=scale, ox=pivot_x, oy=NPU_Y + NPU_S / 2)
    cid = "cs_PhoneSoc_clip"
    clipped = f'{_clip(cid)}<g clip-path="url(#{cid})">{zoom_g}</g>'
    return _fit(c, g(clipped, s=_pop_scale(c, 0.0), ox=PH_CX, oy=PH_CY))


# ----------------------------------------------------------------- MatrixArray
CELL, CELL_GAP = 26, 4
PITCH = CELL + CELL_GAP
PAD = 14
MAT_N = 8
MAT_SIDE = MAT_N * CELL + (MAT_N - 1) * CELL_GAP   # 236
PLATE_H = MAT_SIDE + 2 * PAD                        # 264
ARR_CY = 400                                        # centre y of the arrays


def _cell(x: float, y: float, fill: str) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{CELL}" height="{CELL}" rx="6" fill="{fill}"/>'


def _plate(x: float, w: float, y: float, h: float) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="24" fill="{PLATE}" '
            f'stroke="{GREY}" stroke-width="2"/>')


def _prefill(c: Ctx) -> str:
    """Two 8 x 8 blue matrices with x and =, a third matrix as the product; a wave sweeps across all three."""
    plate_w = MAT_SIDE + 2 * PAD                    # 264
    op_gap = 100
    total = 3 * plate_w + 2 * op_gap
    x0 = 960 - total / 2
    xs = [x0, x0 + plate_w + op_gap, x0 + 2 * (plate_w + op_gap)]
    top = ARR_CY - PLATE_H / 2
    out = []
    for b, px in enumerate(xs):
        out.append(_plate(px, plate_w, top, PLATE_H))
        for r in range(MAT_N):
            for k in range(MAT_N):
                col = b * MAT_N + k
                wave = 0.5 + 0.5 * math.sin(c.t * 3.2 - col * 0.38 - r * 0.42)
                out.append(_cell(px + PAD + k * PITCH, top + PAD + r * PITCH, mix(CELL_DARK, BLUE, 0.12 + 0.88 * wave)))
    out.append(text(xs[0] + plate_w + op_gap / 2, ARR_CY, "×", 64, 800, TEXT))
    out.append(text(xs[1] + plate_w + op_gap / 2, ARR_CY, "=", 64, 800, TEXT))
    out.append(text(960, 580, "Matrix × Matrix", 40, 800, TEXT))
    out.append(pill(960, 660, "COMPUTE", 30, BLUE))
    return "".join(out)


DEC_VEC_W = CELL + 2 * PAD          # 54: column vector plate, 1 cell wide
DEC_W_COLS = 40
DEC_W_W = DEC_W_COLS * CELL + (DEC_W_COLS - 1) * CELL_GAP + 2 * PAD  # 1224: wide weight plate
DEC_GAP = 200
DEC_PERIOD = 1.2


def _decode(c: Ctx) -> str:
    """One blue column vector times an 8 x 40 orange weight block; green packets stream from memory."""
    total = DEC_VEC_W + DEC_GAP + DEC_W_W
    vx = 960 - total / 2
    wx = vx + DEC_VEC_W + DEC_GAP
    top = ARR_CY - PLATE_H / 2
    out = [_plate(vx, DEC_VEC_W, top, PLATE_H), _plate(wx, DEC_W_W, top, PLATE_H)]
    for r in range(MAT_N):
        wave = 0.5 + 0.5 * math.sin(c.t * 3.2 - r * 0.6)
        out.append(_cell(vx + PAD, top + PAD + r * PITCH, mix(CELL_DARK, BLUE, 0.12 + 0.88 * wave)))
        for k in range(DEC_W_COLS):
            shimmer = 0.5 + 0.5 * math.sin(c.t * 2.0 - k * 0.3 - r * 0.2)
            out.append(_cell(wx + PAD + k * PITCH, top + PAD + r * PITCH, mix(CELL_DARK, ORANGE, 0.35 + 0.3 * shimmer)))

    # one packet at a time, leaving the weight block and sliding left into the vector, every 1.2 s
    p = (c.t % DEC_PERIOD) / DEC_PERIOD
    px_start = wx + 60
    px_end = vx + DEC_VEC_W + 6
    pkt_x = lerp(px_start, px_end, ease_io(p))
    pkt_y = ARR_CY - 13
    out.append(_packet(pkt_x, pkt_y, opacity=clamp(min(p, 1 - p) * 8)))

    out.append(text(960, 580, "Matrix × Vector", 40, 800, TEXT))
    out.append(pill(wx + DEC_W_W / 2, 660, "MEMORY", 30, ORANGE))
    return "".join(out)


def MatrixArray(c: Ctx) -> str:
    """mode: prefill | decode. prefill: 8x8 blue matrix times 8x8 matrix (COMPUTE, wave sweep). decode: one
    column vector times a wide weight block streamed from memory (MEMORY, green packets). Optional label above."""
    mode = str(c.props.get("mode", "prefill"))
    label = str(c.props.get("label", ""))[:12]
    scene = _decode(c) if mode == "decode" else _prefill(c)
    if label:
        scene += text(960, 220, label, 40, 800, TEXT)
    return _fit(c, g(scene, s=_pop_scale(c, 0.0), ox=960, oy=ARR_CY))


# ----------------------------------------------------------------- ModelShrink
TILE, TILE_GAP = 36, 4
TILE_PITCH = TILE + TILE_GAP
COLS = 12
BLOCK_W = COLS * TILE + (COLS - 1) * TILE_GAP       # 476
ROWS_BY_BITS = {16: 6, 8: 3, 4: 2}
SIZE_LABEL = {16: "FP16  14 GB", 8: "INT8  7 GB", 4: "INT4  3.5 GB"}
BLK_X = 960 - BLOCK_W / 2
BLK_TOP = 322
FRAME_PAD = 16
MAX_ROWS = 6
XFORM_DUR = 0.6


def _bits_key(bits) -> int:
    try:
        b = int(bits)
    except (TypeError, ValueError):
        return 16
    return min(ROWS_BY_BITS, key=lambda k: abs(k - b))


def ModelShrink(c: Ctx) -> str:
    """mode: shrink (only mode). A 7B green model block of parameter tiles; its height drops from 6 rows (16 bit)
    to 3 rows (8 bit) or 2 rows (4 bit) inside a fixed orange memory bar. Reveal eases the block to the bits value."""
    target = _bits_key(c.props.get("bits", 16))
    rev = c.beats.at("reveal")
    if rev is None:
        rows, shown = float(ROWS_BY_BITS[target]), target
    elif c.t < rev:
        rows, shown = float(MAX_ROWS), 16
    else:
        p = ease_io(progress(c.t, rev, XFORM_DUR))
        rows = lerp(MAX_ROWS, ROWS_BY_BITS[target], p)
        shown = target if p >= 0.5 else 16

    # fixed memory bar (6 rows) behind the block
    bar_x, bar_y = BLK_X - FRAME_PAD, BLK_TOP - FRAME_PAD
    bar_w, bar_h = BLOCK_W + 2 * FRAME_PAD, MAX_ROWS * TILE_PITCH - TILE_GAP + 2 * FRAME_PAD
    bar = (f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="26" fill="none" '
           f'stroke="{ORANGE}" stroke-opacity="0.45" stroke-width="3"/>')

    # tiles: a row stays while rows > its index; the row that is being dropped fades out
    tiles = []
    for r in range(MAX_ROWS):
        vis = clamp(rows - r)
        if vis <= 0.01:
            continue
        for k in range(COLS):
            wave = 0.5 + 0.5 * math.sin(c.t * 2.4 - k * 0.35 - r * 0.5)
            fill = mix(GREEN, "#FFFFFF", 0.1 * wave)
            tiles.append(f'<rect x="{BLK_X + k * TILE_PITCH:.1f}" y="{BLK_TOP + r * TILE_PITCH:.1f}" width="{TILE}" '
                         f'height="{TILE}" rx="7" fill="{fill}" fill-opacity="{vis:.3f}"/>')

    block_bottom = BLK_TOP + rows * TILE_PITCH - TILE_GAP
    labels = text(960, BLK_TOP - 36, "7B", 40, 800, TEXT)
    labels += text(960, block_bottom + 50, SIZE_LABEL[shown], 40, 800, TEXT)

    inner = bar + "".join(tiles) + labels
    return _fit(c, g(inner, s=_pop_scale(c, 0.0), ox=960, oy=BLK_TOP + 118))


for _fn in (PhoneSoc, MatrixArray, ModelShrink):
    _fn.native_landscape = True  # lays out the 16:9 canvas itself; scene.py skips the portrait slot scaling
    _fn.continuous_motion = True  # animates all the time: never a visual gap for the cadence checks


COMPONENTS = {"PhoneSoc": PhoneSoc, "MatrixArray": MatrixArray, "ModelShrink": ModelShrink}
