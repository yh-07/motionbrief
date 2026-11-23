# SPDX-License-Identifier: Apache-2.0
"""Phone-interior components: a memory-bus bottleneck (BusCongestion) and a busy NPU array (NpuArray).

Layout is authored in a 1920x1080 design space (16:9) and uniformly scaled and centred onto c.canvas, so the
same numbers hold for any landscape canvas. The scene supplies the flat dark background; nothing here paints
a full-screen backdrop, glow pool, particle or HUD.
"""
from __future__ import annotations

import math
import random

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.easing import clamp, lerp
from motionbrief.render.svg_canvas.prims import body, g, mix, text, wobble

BLUE, ORANGE, GREEN, RED = "#3B82F6", "#F59E0B", "#22C55E", "#EF4444"
GREY, IDLE_BLUE, CHIP = "#334155", "#1E3A8A", "#262D3B"
TEXT, SUB, AMBER_INK = "#F8FAFC", "#94A3B8", "#3A2200"
DESIGN_W, DESIGN_H = 1920, 1080

# ----------------------------------------------------------------- shared bits
PACKET_W, PACKET_H = 40, 28


def _fit(c: Ctx, inner: str) -> str:
    """Uniform scale of the 1920x1080 design space onto the real canvas, centred."""
    k = min(c.canvas.w / DESIGN_W, c.canvas.h / DESIGN_H)
    return g(inner, tx=(c.canvas.w - DESIGN_W * k) / 2, ty=(c.canvas.h - DESIGN_H * k) / 2, s=k, ox=0, oy=0)


def _pop_scale(c: Ctx, delay: float) -> float:
    """Entrance pop that starts at 0.85, so the first frame already shows the static parts."""
    return 0.85 + 0.15 * c.pop(delay, 0.5)


def _packet(x: float, y: float, opacity: float = 1.0) -> str:
    """Green data packet (40 x 28) with a small white highlight."""
    if opacity <= 0.01:
        return ""
    return g(body(x, y, PACKET_W, PACKET_H, 9, GREEN, shine=0.3, shade=0.2, rim=False)
             + f'<rect x="{x + 7:.1f}" y="{y + 6:.1f}" width="10" height="5" rx="2.5" fill="#FFFFFF" fill-opacity="0.9"/>',
             opacity=opacity, ox=x + PACKET_W / 2, oy=y + PACKET_H / 2)


# ----------------------------------------------------------------- BusCongestion
LP_X, LP_Y, LP_W, LP_H = 140, 300, 240, 220         # LPDDR block
BUS_X, BUS_Y, BUS_W, BUS_H = 380, 397, 800, 26      # narrow bus tube, centre y 410
BUS_CY = BUS_Y + BUS_H / 2
NPU_X, NPU_Y, NPU_W, NPU_H = 1180, 200, 600, 480    # NPU block
CELL, CELL_GAP = 70, 14
CELL_X0, CELL_Y0 = NPU_X + (NPU_W - (6 * CELL + 5 * CELL_GAP)) / 2, NPU_Y + (NPU_H - (4 * CELL + 3 * CELL_GAP)) / 2
Q_CX = 412              # queue column centre, stacked above the bus entrance
Q_BOTTOM = 386          # bottom edge of the lowest queued packet
Q_STEP = 32
Q_MAX, FLOW_MAX_PACKETS = 8, 8


def BusCongestion(c: Ctx) -> str:
    """mode: congestion (only mode). LPDDR feeds a narrow bus into a large NPU; packets queue at the entrance;
    only a fraction of NPU cells are fed, and the idle ones flash red on impact."""
    flow = clamp(float(c.props.get("flow", 0.25)))
    queue = max(0, min(Q_MAX, int(c.props.get("queue", 6))))
    label = str(c.props.get("label", ""))[:10]
    ent, rev = c.ent(), c.beats.at("reveal")

    if rev is None:
        shown_q = queue
    elif c.t >= rev:
        shown_q = round(queue * clamp((c.t - rev) / 1.2))
    else:
        shown_q = 0

    # LPDDR block (amber) with its label and bandwidth line
    lp = body(LP_X, LP_Y, LP_W, LP_H, 36, ORANGE, shine=0.25, shade=0.2)
    lp += text(LP_X + LP_W / 2, 392, "LPDDR", 40, 800, AMBER_INK)
    lp += text(LP_X + LP_W / 2, 548, "60 GB/s", 34, 700, SUB)
    if label:
        lp += text(LP_X + LP_W / 2, 258, label, 40, 800, TEXT)
    lp_g = g(lp, s=_pop_scale(c, 0.0), ox=LP_X + LP_W / 2, oy=LP_Y + LP_H / 2)

    # memory bus: grey tube with a thin amber core
    bus = (f'<rect x="{BUS_X}" y="{BUS_Y}" width="{BUS_W}" height="{BUS_H}" rx="{BUS_H / 2}" fill="{GREY}"/>'
           f'<rect x="{BUS_X + 14}" y="{BUS_CY - 3:.1f}" width="{BUS_W - 28}" height="6" rx="3" '
           f'fill="{ORANGE}" fill-opacity="0.9"/>')
    bus_g = g(bus, s=_pop_scale(c, 0.1), ox=BUS_X + BUS_W / 2, oy=BUS_CY)

    # NPU block (blue rim) with a 6 x 4 grid of compute cells and its label
    npu = body(NPU_X, NPU_Y, NPU_W, NPU_H, 40, CHIP, shine=0.05, shade=0.25, rim=False)
    npu += (f'<rect x="{NPU_X + 2}" y="{NPU_Y + 2}" width="{NPU_W - 4}" height="{NPU_H - 4}" rx="38" fill="none" '
            f'stroke="{BLUE}" stroke-opacity="0.6" stroke-width="4"/>')
    n_cells = 24
    order = list(range(n_cells))
    random.Random(5).shuffle(order)
    lit = set(order[:round(flow * n_cells)])
    since_imp = c.beats.since("impact", c.t)
    for i in range(n_cells):
        x = CELL_X0 + (i % 6) * (CELL + CELL_GAP)
        y = CELL_Y0 + (i // 6) * (CELL + CELL_GAP)
        if i in lit:
            pulse = 0.5 + 0.5 * math.sin(c.t * 2.2 + i * 0.9)
            fill = mix(BLUE, "#FFFFFF", 0.22 * pulse)
        elif 0 <= since_imp < 0.3:  # idle cells flash red once on impact, then fade back to grey
            fill = mix(RED, GREY, since_imp / 0.3)
        else:
            fill = GREY
        npu += f'<rect x="{x:.1f}" y="{y:.1f}" width="{CELL}" height="{CELL}" rx="12" fill="{fill}"/>'
    npu += text(NPU_X + NPU_W / 2, 160, "NPU", 40, 800, TEXT)
    npu_g = g(npu, s=_pop_scale(c, 0.2), ox=NPU_X + NPU_W / 2, oy=NPU_Y + NPU_H / 2)

    # queue of packets piled up above the bus entrance
    queued = [_packet(Q_CX - PACKET_W / 2, Q_BOTTOM - PACKET_H - i * Q_STEP + wobble(c.t, 0.4, 1.5, i * 0.9))
              for i in range(shown_q)]

    # packets flowing along the bus at constant speed; more flow means more packets in transit
    n_moving = min(FLOW_MAX_PACKETS, 2 + round(flow * 6))
    moving = []
    for k in range(n_moving):
        p = ((c.t - ent) * 0.32 + k / n_moving) % 1.0
        x = lerp(BUS_X + 6, NPU_X - 60, p)
        moving.append(_packet(x, BUS_CY - PACKET_H / 2, opacity=clamp((1 - p) * 6)))

    inner = bus_g + lp_g + npu_g + "".join(queued) + "".join(moving)
    return _fit(c, inner)


# ----------------------------------------------------------------- NpuArray
BLK_X, BLK_Y, BLK_W, BLK_H = 360, 200, 1200, 520
NCOLS, NROWS, NCELL, NGAP = 16, 8, 52, 10
GRID_X = BLK_X + (BLK_W - (NCOLS * NCELL + (NCOLS - 1) * NGAP)) / 2
GRID_Y = BLK_Y + (BLK_H - (NROWS * NCELL + (NROWS - 1) * NGAP)) / 2


def NpuArray(c: Ctx) -> str:
    """mode: array (only mode). A large NPU compute array (16 x 8 cells) with rows of cells lighting in a wave;
    'load' sets the active fraction, the label pops on impact."""
    load = clamp(float(c.props.get("load", 1.0)))
    label = str(c.props.get("label", "100 TOPS"))
    total = NCOLS * NROWS
    order = list(range(total))
    random.Random(7).shuffle(order)
    active = set(order[:round(load * total)])

    cells = []
    for i in range(total):
        col, row = i % NCOLS, i // NCOLS
        x = GRID_X + col * (NCELL + NGAP)
        y = GRID_Y + row * (NCELL + NGAP)
        if i in active:  # sinusoidal wave, phase by column, rows light in turn
            wave = 0.5 + 0.5 * math.sin(c.t * 3.0 - col * 0.45 - row * 0.3)
            fill = mix(IDLE_BLUE, BLUE, 0.35 + 0.65 * wave)
        else:
            fill = IDLE_BLUE
        cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{NCELL}" height="{NCELL}" rx="10" fill="{fill}"/>')

    block = body(BLK_X, BLK_Y, BLK_W, BLK_H, 40, CHIP, shine=0.05, shade=0.25, rim=False)
    block += (f'<rect x="{BLK_X + 2}" y="{BLK_Y + 2}" width="{BLK_W - 4}" height="{BLK_H - 4}" rx="38" fill="none" '
              f'stroke="{BLUE}" stroke-opacity="0.5" stroke-width="4"/>')
    block_g = g(block + "".join(cells), s=_pop_scale(c, 0.0), ox=BLK_X + BLK_W / 2, oy=BLK_Y + BLK_H / 2)

    isx, isy = c.impact()
    label_g = g(text(960, 146, label, 64, 900, TEXT), s=_pop_scale(c, 0.3), sx=isx, sy=isy, ox=960, oy=146)
    return _fit(c, block_g + label_g)


for _fn in (BusCongestion, NpuArray):
    _fn.native_landscape = True  # lays out the 16:9 canvas itself; scene.py skips the portrait slot scaling
    _fn.continuous_motion = True  # animates all the time: never a visual gap for the cadence checks


COMPONENTS = {"BusCongestion": BusCongestion, "NpuArray": NpuArray}
