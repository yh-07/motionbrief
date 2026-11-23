# SPDX-License-Identifier: Apache-2.0
"""Cartoon Tech v2 components for the ISP v3 full cut (48 shots).

Every component is a pure function of (Ctx, t): entrance/reveal/impact beats drive the story beat of the shot
(problem -> method -> failure -> fix). Modes select the shot variant; see motion/registry.json for props.
"""
from __future__ import annotations

import math
import random

from motionbrief.render.svg_canvas.components import BAYER, Ctx, scene_color
from motionbrief.render.svg_canvas.easing import clamp, ease_out_expo, lerp, progress
from motionbrief.render.svg_canvas.prims import (back_out, ball, body, contact_shadow, darken, ease_io, g,
                                                 glow, lighten, lin, mix, pill, text, wobble)

RED, GREEN, CYAN = "#FF4D6A", "#3EE08F", "#22D3B6"
RGB = [BAYER["R"], BAYER["G"], BAYER["B"]]


# ----------------------------------------------------------------- shared bits
def _k(c: Ctx, at: float | None, dur: float = 0.45) -> float:
    """back-out pop progress from `at` (0 before)."""
    return back_out(progress(c.t, at, dur)) if at is not None and c.t >= at else 0.0


def _u(c: Ctx, at: float | None, dur: float) -> float:
    return clamp((c.t - at) / dur) if at is not None and c.t >= at else 0.0


def mark(x: float, y: float, ok: bool, k: float, r: float = 64) -> str:
    """Round badge with a check (ok) or a cross, popping with k."""
    if k <= 0.001:
        return ""
    col = GREEN if ok else RED
    if ok:
        ink = (f'<path d="M{x - r * 0.45:.1f},{y + r * 0.02:.1f} L{x - r * 0.1:.1f},{y + r * 0.36:.1f} '
               f'L{x + r * 0.5:.1f},{y - r * 0.34:.1f}" fill="none" stroke="#FFFFFF" stroke-width="{r * 0.22:.1f}" '
               f'stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        a = r * 0.36
        ink = "".join(f'<line x1="{x - a:.1f}" y1="{y + s * a:.1f}" x2="{x + a:.1f}" y2="{y - s * a:.1f}" '
                      f'stroke="#FFFFFF" stroke-width="{r * 0.22:.1f}" stroke-linecap="round"/>' for s in (-1, 1))
    return g(glow(x, y, r * 1.6, col, 0.35) + ball(x, y, r, col) + ink, s=max(k, 1e-3), ox=x, oy=y)


def _clip(cid: str, x: float, y: float, w: float, h: float, r: float, inner: str) -> str:
    return (f'<clipPath id="{cid}"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}"/></clipPath>'
            f'<g clip-path="url(#{cid})">{inner}</g>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="none" stroke="#FFFFFF" '
            f'stroke-opacity="0.22" stroke-width="3"/>')


def _sunset(x: float, y: float, w: float, h: float, n: int = 10) -> str:
    """The recurring sunset photo, as soft blocks (same palette as RawFramePlate)."""
    cw, ch = w / n, h / n
    return "".join(f'<rect x="{x + j * cw:.1f}" y="{y + i * ch:.1f}" width="{cw + 1:.1f}" height="{ch + 1:.1f}" '
                   f'fill="{scene_color((j + 0.5) / n, (i + 0.5) / n)}"/>' for i in range(n) for j in range(n))


def _night_city(x: float, y: float, w: float, h: float, noise: float, frame: int, seed: int = 7,
                blur: float = 0.0, sweep: float | None = None) -> str:
    """Night skyline. noise 0..1 = RGB speckle density; blur 0..1 melts the windows into glows (lost detail).
    sweep (x) limits noise/blur to the right/left of a vertical squeegee position."""
    rng = random.Random(seed)
    d, sky = lin([(0, "#0E1240", 1), (1, "#3B2A7A", 1)])
    s = [d, f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{sky}"/>',
         glow(x + w * 0.74, y + h * 0.18, w * 0.2, "#FFF2C4", 0.55), ball(x + w * 0.74, y + h * 0.18, w * 0.06, "#FFF2C4")]
    bx = x
    while bx < x + w:
        bw, bh = rng.uniform(w * 0.11, w * 0.19), rng.uniform(h * 0.25, h * 0.5)
        by = y + h - bh
        s.append(body(bx + 4, by, bw - 8, bh + 40, 12, rng.choice(["#2A2160", "#312770", "#241C55"]),
                      shine=0.08, shade=0.2, rim=False))
        for wy in range(int(by + 26), int(y + h - 18), 42):
            for wx in range(int(bx + 18), int(bx + bw - 26), 30):
                if rng.random() < 0.55:
                    melted = blur > 0 and (sweep is None or wx < sweep)
                    if melted:
                        s.append(glow(wx + 7, wy + 10, 34, "#FFC94D", 0.22 * blur + 0.05))
                    else:
                        s.append(f'<rect x="{wx}" y="{wy}" width="14" height="20" rx="4" fill="#FFC94D" '
                                 f'opacity="{rng.uniform(0.5, 0.95):.2f}"/>')
        bx += bw
    fr = random.Random(frame * 7919 + seed)
    for _ in range(int(220 * noise)):
        px, py = x + fr.random() * w, y + fr.random() * h
        if sweep is not None and px < sweep:
            continue
        s.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="11" height="11" rx="3" '
                 f'fill="{fr.choice(["#FFFFFF", *RGB])}" opacity="{fr.uniform(0.35, 0.85):.2f}"/>')
    return "".join(s)


def _noise_bar(cx: float, y: float, w: float, level: float, col: str, marks: list[tuple[float, str, bool]] = ()) -> str:
    """Horizontal 'noise' meter: length = level (0..1); marks = (level, label, reached)."""
    s = [body(cx - w / 2, y - 18, w, 36, 18, "#241C55", shine=0.0, shade=0.2),
         body(cx - w / 2, y - 18, max(36, w * level), 36, 18, col, shine=0.3, shade=0.1, rim=False),
         text(cx - w / 2 - 20, y, "噪点", 34, 800, "#C9C3F0", "end")]
    for lv, lab, on in marks:
        mx = cx - w / 2 + w * lv
        s.append(f'<line x1="{mx:.1f}" y1="{y - 40}" x2="{mx:.1f}" y2="{y + 40}" stroke="{"#FFFFFF" if on else "#6B64A0"}" '
                 f'stroke-width="5" stroke-linecap="round"/>')
        if lab:
            s.append(text(mx, y + 74, lab, 36, 900, "#FFFFFF" if on else "#8C86B0"))
    return "".join(s)


# ----------------------------------------------------------------- s07–s09 pixel wells
def photon_well(c: Ctx) -> str:
    """modes: count (photons land, charge rises, counter ticks) | gray (photons lose colour, '?' over wells)
    | filter (R/G/G/B caps drop on; wrong-colour photons bounce, liquid takes the cap colour)."""
    mode = c.props.get("mode", "count")
    n, ww, wh, gap = 4, 170, 330, 60
    y_top = float(c.props.get("y", 900))
    x0 = c.canvas.cx - (n * ww + (n - 1) * gap) / 2
    ent, rev, _imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    caps = ["R", "G", "G", "B"]
    out = []
    for i in range(n):
        x = x0 + i * (ww + gap)
        pk = _k(c, ent + 0.07 * i, 0.5)
        cap = caps[i] if mode == "filter" and rev is not None and c.t >= rev else None
        landed = 0
        drops = []
        for k in range(14):
            t0 = ent + 0.35 + k * 0.32 + i * 0.09
            colr = RGB[(k * 5 + i * 2) % 3]
            u = (c.t - t0) / 0.55
            if u < 0:
                continue
            ch = colr
            bounce = cap is not None and t0 > rev and colr != BAYER[cap]
            if u >= 1:
                if bounce:
                    continue
                landed += 1
                continue
            py = lerp(y_top - 520, y_top + wh - 30 - landed * 18, ease_io(u))
            if bounce and py > y_top - 10:  # ricochet off the filter cap
                b = (py - (y_top - 10)) / 200
                py = y_top - 10 - 220 * b
                ch = mix(colr, "#FFFFFF", 0.3)
                drops.append(g(glow(x + ww / 2 + 60 * b, py, 30, ch, 0.4) + ball(x + ww / 2 + 60 * b, py, 13, ch),
                               opacity=clamp(1 - b)))
                continue
            if mode == "gray" and py > y_top:
                ch = mix(colr, "#B8B4CC", clamp((py - y_top) / 80))
            drops.append(glow(x + ww / 2, py, 34, ch, 0.45) + ball(x + ww / 2, py, 14, ch))
        level = min(wh - 40, landed * 18)
        liquid = BAYER[cap] if cap else (mix("#8C86B0", "#B8B4CC", 0.4) if mode == "gray" else c.p2)
        w = [contact_shadow(x + ww / 2, y_top + wh + 30, ww * 0.55, 22, 0.45),
             body(x, y_top, ww, wh, 34, "#1B1648", shine=0.06, shade=0.25)]
        if level > 0:
            w.append(body(x + 14, y_top + wh - 14 - level, ww - 28, level, 20, liquid, shine=0.3, shade=0.15, rim=False))
        w.append(body(x + 8, y_top + 8, 28, wh - 16, 14, "#FFFFFF", shine=0, shade=0, rim=False)
                 .replace('fill="#FFFFFF"', 'fill="#FFFFFF" fill-opacity="0.10"', 1))
        if cap:
            kc = _k(c, rev + 0.08 * i, 0.4)
            w.append(g(body(x - 12, y_top - 34, ww + 24, 40, 18, BAYER[cap], shine=0.35, shade=0.15)
                       + text(x + ww / 2, y_top - 14, cap, 30, 900, "#FFFFFF"), s=max(kc, 1e-3), ty=-160 * (1 - kc),
                       ox=x + ww / 2, oy=y_top - 14))
        if mode == "count":
            w.append(text(x + ww / 2, y_top + wh + 80, str(landed), 54, 900, "#FFFFFF"))
        if mode == "gray" and rev is not None and c.t >= rev + 0.08 * i:
            kq = _k(c, rev + 0.08 * i, 0.4)
            w.append(g(ball(x + ww / 2, y_top - 90, 46, "#FFFFFF") + text(x + ww / 2, y_top - 90, "?", 56, 900, c.p1),
                       s=max(kq, 1e-3), ox=x + ww / 2, oy=y_top - 90))
        out.append(g("".join(w), s=max(pk, 1e-3), ox=x + ww / 2, oy=y_top + wh) + "".join(drops))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=y_top + wh / 2, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s16–s17 neighbours
def neighbor_grid(c: Ctx) -> str:
    """modes: ask (red centre pixel blinks 'G? B?') | average (four green neighbours pass 120/128/124/132 in,
    the centre turns green, the formula lands on impact)."""
    mode = c.props.get("mode", "ask")
    sz, yc = 210, float(c.props.get("y", 960))
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    vals = {(-1, 0): 120, (1, 0): 128, (0, -1): 124, (0, 1): 132}
    out = []
    centre_g = ease_out_expo(_u(c, imp if mode == "average" else None, 0.5))
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            x, y = c.canvas.cx + dj * sz, yc + di * sz
            ch = "R" if (di, dj) == (0, 0) else "G" if di == 0 or dj == 0 else "B"
            pk = _k(c, ent + 0.04 * (abs(di) + abs(dj)), 0.45)
            col = BAYER[ch] if ch != "R" else mix(BAYER["R"], BAYER["G"], 0.5 * centre_g)
            cell = body(x - sz / 2 + 8, y - sz / 2 + 8, sz - 16, sz - 16, 34, col, shine=0.22, shade=0.2)
            cell += text(x, y - (30 if (di, dj) in vals and mode == "average" else 0), ch, 64, 900, "#FFFFFF")
            if mode == "average" and (di, dj) in vals:
                cell += text(x, y + 42, str(vals[(di, dj)]), 44, 900, "#0B2A1C")
            out.append(g(cell, s=max(pk, 1e-3), ox=x, oy=y))
    if mode == "ask":
        bl = 0.5 + 0.5 * math.sin((c.t - ent) * 7)
        out.append(f'<rect x="{c.canvas.cx - sz / 2 + 2}" y="{yc - sz / 2 + 2}" width="{sz - 4}" height="{sz - 4}" rx="38" '
                   f'fill="none" stroke="#FFFFFF" stroke-width="9" opacity="{0.4 + 0.6 * bl:.3f}"/>')
        kq = _k(c, rev, 0.45)
        out.append(g(pill(c.canvas.cx - 90, yc - sz - 150, "G?", 48, BAYER["G"]) + pill(c.canvas.cx + 90, yc - sz - 150, "B?", 48, BAYER["B"]),
                     s=max(kq, 1e-3), oy=yc - sz - 150))
    else:
        for (di, dj), v in vals.items():  # value chips fly to the centre between reveal and impact
            u = ease_io(_u(c, rev, max(0.3, (imp or (rev or 0) + 1) - (rev or 0))))
            if 0 < u < 1:
                x, y = lerp(c.canvas.cx + dj * sz, c.canvas.cx, u), lerp(yc + di * sz + 42, yc, u)
                out.append(pill(x, y, str(v), 34, "#1E7F55"))
        kf = _k(c, imp, 0.5)
        out.append(g(pill(c.canvas.cx, yc + sz * 1.5 + 90, "(120+128+124+132) ÷ 4 = 126", 40, "#241C55"), s=max(kf, 1e-3),
                     oy=yc + sz * 1.5 + 90))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=yc, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s19–s20 moiré fence
def moire_fence(c: Ctx) -> str:
    """modes: artifact (rainbow false colour blooms on the fine fence, red cross) | fix (a cyan arrow sweeps
    along the wires, erasing the rainbow, green check)."""
    mode = c.props.get("mode", "artifact")
    W, H = 820, 1020
    x0, y0 = c.canvas.cx - W / 2, float(c.props.get("y", 900)) - H / 2
    _ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    pe = c.pop(0, 0.55)
    inner = [_sunset(x0, y0, W, H)]
    for k in range(-40, 40):  # fence: two families of thin diagonal wires
        a = x0 + k * 26
        inner.append(f'<line x1="{a}" y1="{y0}" x2="{a + H}" y2="{y0 + H}" stroke="#1A1440" stroke-width="5" opacity="0.8"/>')
        inner.append(f'<line x1="{a + H}" y1="{y0}" x2="{a}" y2="{y0 + H}" stroke="#1A1440" stroke-width="5" opacity="0.8"/>')
    amt = _u(c, rev, 0.9) if mode == "artifact" else 1.0
    sweep = ease_io(_u(c, rev, max(0.4, (imp or (rev or 0) + 1.5) - (rev or 0) - 0.2))) if mode == "fix" else 0.0
    if amt > 0:
        bands = []
        for k in range(18):  # low-frequency false-colour bands = the aliasing pattern
            off = k * 120 - 600 + 40 * math.sin(k * 1.7)
            col = ["#FF3B6B", "#29E3E3", "#FFE14D"][k % 3]
            bands.append(f'<path d="M{x0 + off},{y0} q{180},{H / 2} 0,{H} l70,0 q{180},{-H / 2} 0,{-H} Z" fill="{col}" '
                         f'opacity="{0.42 * amt:.3f}"/>')
        mask = ""
        if mode == "fix":  # erased region grows along the diagonal from the top-left
            r = sweep * (W + H)
            mask = (f'<clipPath id="mfk"><path d="M{x0 + r},{y0 - 10} L{x0 + W + 900},{y0 - 10} L{x0 + W + 900},{y0 + H + 10} '
                    f'L{x0 + r - H - 20},{y0 + H + 10} Z"/></clipPath>')
            inner.append(mask + f'<g clip-path="url(#mfk)">{"".join(bands)}</g>')
        else:
            inner.append("".join(bands))
    out = [contact_shadow(c.canvas.cx, y0 + H + 40, W * 0.55, 40, 0.5), _clip("mfc", x0, y0, W, H, 40, "".join(inner))]
    if mode == "fix" and 0 < sweep < 1:
        r = sweep * (W + H)
        ax, ay = x0 + r * 0.5, y0 + r * 0.5
        out.append(glow(ax, ay, 160, CYAN, 0.5))
        out.append(g(f'<path d="M-70,-26 L30,-26 L30,-60 L90,0 L30,60 L30,26 L-70,26 Z" fill="{CYAN}"/>',
                     tx=ax, ty=ay, ox=0, oy=0, rot=45))
    out.append(mark(x0 + W - 40, y0 + 40, mode == "fix", _k(c, imp, 0.45), 70))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy, oy=y0 + H / 2, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s21–s23 photon bars
def photon_bars(c: Ctx) -> str:
    """modes: stream (a continuous beam breaks into random grains on reveal) | day (dense grains, six columns
    almost equal) | night (sparse grains, columns jump; on impact cut to a noisy night city)."""
    mode = c.props.get("mode", "stream")
    n, cw, gap, base = 6, 120, 34, float(c.props.get("y", 1280))
    x0 = c.canvas.cx - (n * cw + (n - 1) * gap) / 2
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    rng = random.Random(21)
    out = []
    city = ease_out_expo(_u(c, imp, 0.5)) if mode == "night" else 0.0
    beam = mode == "stream" and (rev is None or c.t < rev)
    rate = {"stream": 6.0, "day": 22.0, "night": 2.2}[mode]
    for i in range(n):
        x = x0 + i * (cw + gap)
        if mode == "day":
            target = 640 + rng.uniform(-12, 12)
            count = f"{1000 + int(target - 640) + 20 * i % 37}"
        elif mode == "night":
            target = rng.choice([60, 140, 30, 230, 90, 180])
            count = str(int(target / 30))
        else:
            target = 300 + rng.uniform(-60, 60)
            count = ""
        h = target * ease_out_expo(_u(c, ent + 0.3, 2.4 if mode != "night" else 1.6))
        col = mix(c.p1, c.p2, i / (n - 1))
        out.append(body(x, base - 8, cw, 30, 12, "#241C55", shine=0, shade=0.2))
        if h > 2:
            out.append(body(x + 10, base - h, cw - 20, h, 22, col, shine=0.3, shade=0.18, rim=False))
        if count:
            out.append(text(x + cw / 2, base + 70, count, 40, 900, "#FFFFFF", opacity=clamp(h / 60)))
        if beam:
            d, u = lin([(0, c.accent, 0), (1, c.accent, 0.8)])
            out.append(f'{d}<rect x="{x + cw / 2 - 14}" y="{base - 1100}" width="28" height="{1100 - h:.1f}" rx="14" fill="{u}"/>')
        else:
            t_start = rev if mode == "stream" else ent
            for k in range(int(rate * 6)):  # falling grains
                tk = t_start + (k + (i * 0.37) % 1) / rate
                u = (c.t - tk) / 0.7
                if 0 <= u < 1:
                    py = lerp(base - 1150, base - h - 10, u ** 1.4)
                    gx = x + cw / 2 + 26 * math.sin(k * 2.3 + i)
                    out.append(glow(gx, py, 26, c.accent, 0.5) + ball(gx, py, 10, lighten(c.accent, 0.3)))
    bars = g("".join(out), opacity=1 - city)
    res = [bars]
    if city > 0:
        W, H = 820, 1000
        cx0, cy0 = c.canvas.cx - W / 2, c.canvas.cy - H / 2 - 20
        res.append(g(contact_shadow(c.canvas.cx, cy0 + H + 40, W * 0.55, 40, 0.5)
                     + _clip("pbc", cx0, cy0, W, H, 44, _night_city(cx0, cy0, W, H, 1.0, c.frame)),
                     s=lerp(0.85, 1, city), opacity=city))
    isx, isy = c.impact()
    return g("".join(res), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s24–s28 burst stacking
def burst_stack(c: Ctx) -> str:
    """modes: smear (pink squeegee wipes: noise gone, windows melt, red cross) | align (offset night frames slide
    into register, ×1→×6) | stack (×6→×12, noise keeps falling) | milestones (×1→×16 with 1/2 and 1/4 marks)
    | shutter (shutter ring fills 1/16→16/16, '稳住', check). Noise ∝ 1/√N (shot noise)."""
    mode = c.props.get("mode", "align")
    W, H = 780, 820
    x0, y0 = c.canvas.cx - W / 2, float(c.props.get("y", 860)) - H / 2
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    end = imp if imp is not None else c.t1 - 0.4
    pe = c.pop(0, 0.55)
    n0, n1 = {"align": (1, 6), "stack": (6, 12), "milestones": (1, 16), "shutter": (1, 16)}.get(mode, (1, 1))
    run0 = rev if rev is not None else ent + 0.4
    u = ease_io(clamp((c.t - run0) / max(0.3, end - run0)))
    nn = max(1, round(lerp(n0, n1, u))) if mode != "smear" else 1
    noise = 1 / math.sqrt(nn)
    out = [contact_shadow(c.canvas.cx, y0 + H + 40, W * 0.55, 40, 0.5)]
    if mode == "smear":
        sw = ease_io(_u(c, rev, max(0.3, (imp or c.t1) - (rev or ent) - 0.15)))
        sx = x0 + W * sw
        city = _night_city(x0, y0, W, H, 1.0, c.frame, blur=1.0 if sw > 0 else 0.0, sweep=sx)
        out.append(_clip("bsm", x0, y0, W, H, 44, city))
        if 0.01 < sw < 0.99:
            out.append(glow(sx, y0 + H / 2, 240, "#FF7AC8", 0.35)
                       + body(sx - 10, y0 - 34, 20, H + 68, 10, "#FF8AD0", shine=0.4, shade=0.1, rim=False))
        out.append(mark(x0 + W - 40, y0 + 40, False, _k(c, imp, 0.45), 70))
    else:
        if mode == "align":  # ghost frames converge into register
            for k in range(5, 0, -1):
                off = (1 - u) * 46 * k
                rk = (1 - u) * (6 - 2.4 * k % 7)
                out.append(g(_clip(f"bsg{k}", x0, y0, W, H, 44, _night_city(x0, y0, W, H, 0.6, c.frame + k * 31, seed=7)),
                             tx=off * (1 if k % 2 else -1), ty=-off * 0.5, rot=rk, opacity=0.18 + 0.05 * (5 - k)))
        out.append(_clip("bsc", x0, y0, W, H, 44, _night_city(x0, y0, W, H, noise, c.frame)))
        out.append(pill(x0 + W - 90, y0 + H - 60, f"×{nn}", 46, c.p1))
        if mode != "shutter":
            marks = [(0.5, "4 张 → 1/2", nn >= 4), (0.25, "16 张 → 1/4", nn >= 16)] if mode == "milestones" else []
            out.append(_noise_bar(c.canvas.cx + 40, y0 + H + 130, W - 120, noise, RED, marks))
        else:
            sy, r = y0 + H + 240, 110
            ring = 2 * math.pi * r
            done = nn / 16
            out.append(f'<circle cx="{c.canvas.cx}" cy="{sy}" r="{r}" fill="none" stroke="#241C55" stroke-width="26"/>')
            out.append(f'<circle cx="{c.canvas.cx}" cy="{sy}" r="{r}" fill="none" stroke="{c.accent}" stroke-width="26" '
                       f'stroke-linecap="round" stroke-dasharray="{ring * done:.1f} {ring:.1f}" '
                       f'transform="rotate(-90 {c.canvas.cx} {sy})"/>')
            out.append(ball(c.canvas.cx, sy, r - 34, "#F4F2FF") + text(c.canvas.cx, sy, f"{nn}/16", 44, 900, "#241C55"))
            out.append(text(c.canvas.cx + r + 70, sy, "稳住", 52, 900, "#FFFFFF", "start",
                            opacity=0.55 + 0.45 * math.sin(c.t * 6) ** 2 if nn < 16 else 0.0))
            out.append(mark(c.canvas.cx + r * 0.8, sy - r * 0.8, True, _k(c, imp, 0.45), 52))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy, oy=y0 + H / 2, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s29–s33 white balance
ORANGE, BLUE = "#FFB070", "#9CC4FF"


def _paper(x: float, y: float, w: float, h: float, col: str, rot: float = 0) -> str:
    lines = "".join(f'<rect x="{x + w * 0.15:.1f}" y="{y + h * (0.22 + 0.14 * i):.1f}" width="{w * (0.7 - 0.15 * (i % 2)):.1f}" '
                    f'height="{h * 0.04:.1f}" rx="{h * 0.02:.1f}" fill="{darken(col, 0.25, "#6B6480")}"/>' for i in range(5))
    return g(contact_shadow(x + w / 2, y + h + 18, w * 0.5, 18, 0.4) + body(x, y, w, h, 20, col, shine=0.05, shade=0.12)
             + lines, rot=rot, ox=x + w / 2, oy=y + h / 2)


def _candle(x: float, y: float, t: float, a: float = 1.0) -> str:
    fl = 1 + wobble(t, 3.1, 0.06)
    return g(glow(x, y, 140 * fl, "#FF9A3C", 0.45) + body(x - 22, y + 30, 44, 120, 10, "#F2E6D8", shine=0.3, shade=0.25)
             + g(f'<path d="M{x},{y - 50} Q{x + 28},{y} {x},{y + 22} Q{x - 28},{y} {x},{y - 50} Z" fill="#FFB547"/>',
                 sy=fl, ox=x, oy=y + 20), opacity=a)


def _cloud(x: float, y: float, s: float = 1.0) -> str:
    return "".join(ball(x + dx * s, y + dy * s, r * s, "#DDE7FF") for dx, dy, r in ((-50, 10, 46), (0, -12, 60), (55, 8, 44)))


def wb_compare(c: Ctx) -> str:
    """modes: temps (candle-orange vs cloudy-blue paper, '=') | brain (brain row turns both white, sensor row stays
    tinted + cross) | wrong (face drifts yellow, snow drifts blue, crosses) | night (three coloured street lamps,
    a small network lights up, the paper turns white, check)."""
    mode = c.props.get("mode", "temps")
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    pe = c.pop(0, 0.55)
    yc = float(c.props.get("y", 980))
    out = []
    if mode == "temps":
        for side, (col, lab) in enumerate(((ORANGE, "≈1900K"), (BLUE, "≈6500K"))):
            x = c.canvas.cx + (-1 if side == 0 else 1) * 230
            k = _k(c, ent + 0.12 * side, 0.5)
            icon = _candle(x, yc - 300, c.t) if side == 0 else _cloud(x, yc - 300, 1.2)
            out.append(g(icon + _paper(x - 150, yc - 160, 300, 380, col, -3 if side == 0 else 3)
                         + text(x, yc + 300, lab, 46, 900, col), s=max(k, 1e-3), ox=x, oy=yc))
        out.append(g(text(c.canvas.cx, yc + 30, "=", 120, 900, "#FFFFFF"), s=max(_k(c, rev, 0.4), 1e-3), oy=yc + 30))
    elif mode == "brain":
        fix = ease_io(_u(c, rev, 1.0))
        for row, (y, lab) in enumerate(((yc - 330, "大脑"), (yc + 230, "传感器"))):
            k = _k(c, ent + 0.15 * row, 0.5)
            icon = (ball(c.canvas.cx - 360, y, 70, "#FF9AB8") + text(c.canvas.cx - 360, y, "脑", 56, 900, "#7A2140")
                    if row == 0 else body(c.canvas.cx - 430, y - 66, 140, 132, 26, c.p1, shine=0.3, shade=0.2)
                    + "".join(f'<rect x="{c.canvas.cx - 412 + 26 * q}" y="{y - 84}" width="10" height="20" rx="4" fill="#C9C3F0"/>'
                              for q in range(4)))
            cols = [mix(ORANGE, "#FFFFFF", fix), mix(BLUE, "#FFFFFF", fix)] if row == 0 else [ORANGE, BLUE]
            papers = "".join(_paper(c.canvas.cx - 180 + 260 * q, y - 150, 220, 300, cols[q]) for q in range(2))
            out.append(g(icon + text(c.canvas.cx - 360, y + 120, lab, 38, 800, "#C9C3F0") + papers, s=max(k, 1e-3), oy=y))
        out.append(mark(c.canvas.cx + 420, yc + 100, False, _k(c, imp, 0.45), 60))
    elif mode == "wrong":
        drift = ease_io(_u(c, rev, 1.2))
        for side in range(2):
            x = c.canvas.cx + (-1 if side == 0 else 1) * 230
            k = _k(c, ent + 0.12 * side, 0.5)
            w, h = 400, 560
            bx, by = x - w / 2, yc - h / 2
            if side == 0:  # portrait
                skin = mix("#F2C6A8", "#E8C640", 0.75 * drift)
                bg = mix("#5A4DB0", "#8A7A30", 0.5 * drift)
                inner = (f'<rect x="{bx}" y="{by}" width="{w}" height="{h}" fill="{bg}"/>'
                         + ball(x, by + h * 0.42, 110, skin) + body(x - 150, by + h * 0.66, 300, 260, 120, mix("#3EE0B8", "#C9C040", drift)))
            else:  # snow mountain
                snow = mix("#F4F6FF", "#7FA8FF", 0.75 * drift)
                inner = (f'<rect x="{bx}" y="{by}" width="{w}" height="{h}" fill="{mix("#8EC5FF", "#3A5ACF", drift)}"/>'
                         + f'<path d="M{bx},{by + h} L{x - 20},{by + h * 0.3} L{bx + w},{by + h} Z" fill="{mix("#6A6FA8", "#2A3A8A", drift)}"/>'
                         + f'<path d="M{x - 92},{by + h * 0.55} L{x - 20},{by + h * 0.3} L{x + 60},{by + h * 0.5} '
                           f'L{x + 10},{by + h * 0.46} L{x - 30},{by + h * 0.56} Z" fill="{snow}"/>'
                         + f'<rect x="{bx}" y="{by + h * 0.82}" width="{w}" height="{h * 0.2}" fill="{snow}"/>')
            out.append(g(contact_shadow(x, by + h + 30, w * 0.5, 26, 0.45) + _clip(f"wbw{side}", bx, by, w, h, 34, inner)
                         + mark(bx + w - 30, by + 30, False, _k(c, imp, 0.45), 52), s=max(k, 1e-3), ox=x, oy=yc))
    else:  # night: three lamps on one paper
        fixk = ease_io(_u(c, imp - 0.6 if imp else rev, 0.6))
        lamps = [("#FF8A2A", -300), ("#3EE08F", 0), ("#FF5AC8", 300)]
        for k_, (col, dx) in enumerate(lamps):
            lx, ly = c.canvas.cx + dx, yc - 420
            kk = _k(c, ent + 0.1 * k_, 0.45)
            out.append(g(body(lx - 8, ly, 16, 260, 8, "#3A3560", shine=0, shade=0.2) + glow(lx, ly, 220, col, 0.4 * (1 - 0.6 * fixk))
                         + ball(lx, ly, 30, lighten(col, 0.3)), s=max(kk, 1e-3), ox=lx, oy=ly))
        d, rainbow = lin([(0, "#FFB070", 1), (0.5, "#B6FFD0", 1), (1, "#FFB0E8", 1)], 0, 0, 1, 0)
        out.append(d + _paper(c.canvas.cx - 170, yc - 120, 340, 420, "#FFFFFF")
                   + g(f'<rect x="{c.canvas.cx - 170}" y="{yc - 120}" width="340" height="420" rx="20" fill="{rainbow}"/>', opacity=1 - fixk))
        kn = _k(c, rev, 0.45)
        nx, ny = c.canvas.cx + 330, yc - 60
        nodes = [(nx - 60, ny - 50), (nx - 60, ny + 50), (nx, ny - 70), (nx, ny), (nx, ny + 70), (nx + 60, ny)]
        net = "".join(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{CYAN}" stroke-width="4" opacity="0.7"/>'
                      for a in nodes[:2] for b in nodes[2:5]) + "".join(
            f'<line x1="{a[0]}" y1="{a[1]}" x2="{nodes[5][0]}" y2="{nodes[5][1]}" stroke="{CYAN}" stroke-width="4" opacity="0.7"/>'
            for a in nodes[2:5])
        out.append(g(glow(nx, ny, 140, CYAN, 0.35) + net + "".join(ball(x, y, 14, "#E9FFFA") for x, y in nodes),
                     s=max(kn, 1e-3), ox=nx, oy=ny))
        out.append(mark(c.canvas.cx + 150, yc - 110, True, _k(c, imp, 0.45), 54))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy, oy=yc, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s34, s36 tone ladder
def tone_ladder(c: Ctx) -> str:
    """modes: squeeze (a tall many-rung ladder is squashed into a 256-rung box; '怎么压？' on impact)
    | spacing (two columns: even rungs vs rungs bunched toward the dark end, as the eye wants)."""
    mode = c.props.get("mode", "squeeze")
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    out = []
    if mode == "squeeze":
        sq = ease_io(_u(c, rev, 1.1))
        top, bot = lerp(330, 860, sq), lerp(1420, 1180, sq)
        lx = lerp(c.canvas.cx - 230, c.canvas.cx + 230, sq)
        rungs = 64
        for i in range(rungs):
            v = i / (rungs - 1)
            y = lerp(bot, top, v)
            k = _k(c, ent + 0.01 * i, 0.3)
            out.append(f'<rect x="{lx - 110}" y="{y:.1f}" width="220" height="{max(2.0, (bot - top) / rungs - 2):.1f}" '
                       f'fill="{mix("#05041A", "#FFFFFF", v)}" opacity="{k:.3f}"/>')
        out.append(text(lerp(c.canvas.cx - 230, c.canvas.cx + 230, sq), lerp(270, 800, sq), "几千级", 44, 900, "#FFFFFF", opacity=1 - sq))
        bx, by, bw, bh = c.canvas.cx + 110, 850, 240, 340
        kb = _k(c, ent + 0.3, 0.5)
        out.append(g(body(bx, by, bw, bh, 28, "#241C55", shine=0.05, shade=0.25)
                     + f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="28" fill="none" stroke="{c.accent}" stroke-width="6"/>'
                     + text(bx + bw / 2, by + bh + 60, "JPEG：256 级", 40, 900, c.accent), s=max(kb, 1e-3),
                     ox=bx + bw / 2, oy=by + bh / 2))
        out.append(g(pill(bx + bw / 2, by - 90, "怎么压？", 48, RED), s=max(_k(c, imp, 0.45), 1e-3), ox=bx + bw / 2, oy=by - 90))
    else:
        for side, (lab, gam) in enumerate((("平均分", 1.0), ("按人眼分", 2.2))):
            x = c.canvas.cx + (-1 if side == 0 else 1) * 220
            k = _k(c, ent + 0.15 * side, 0.5)
            col = [body(x - 120, 420, 240, 1000, 30, "#241C55", shine=0.05, shade=0.25)]
            d, ramp = lin([(0, "#FFFFFF", 1), (1, "#05041A", 1)])
            col.append(d + f'<rect x="{x - 100}" y="440" width="200" height="960" rx="20" fill="{ramp}"/>')
            shown = _u(c, rev, 1.2) if side == 1 else _u(c, ent + 0.4, 1.2)
            for i in range(1, 16):
                if i / 16 > shown:
                    break
                v = (i / 16) ** gam  # fraction from the dark (bottom) end
                y = 1400 - 960 * v
                col.append(f'<line x1="{x - 130}" y1="{y:.1f}" x2="{x + 130}" y2="{y:.1f}" stroke="{c.accent}" '
                           f'stroke-width="6" stroke-linecap="round"/>')
            col.append(text(x, 1490, lab, 46, 900, "#FFFFFF"))
            out.append(g("".join(col), s=max(k, 1e-3), ox=x, oy=920))
        out.append(g(text(c.canvas.cx + 220, 330, "暗部台阶多", 40, 900, c.accent), s=max(_k(c, imp, 0.45), 1e-3), ox=c.canvas.cx + 220, oy=330))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s35, s37 tone card
def _landscape(x: float, y: float, w: float, h: float, sky_k: float, dark_k: float) -> str:
    """sky_k: 0 = blown white sky .. 1 = sky with clouds; dark_k: 0 = crushed black shadows .. 1 = readable."""
    sky_top = mix("#FFFFFF", "#5A7BFF", sky_k)
    sky_low = mix("#FFFFFF", "#FFC6A0", sky_k)
    d, sky = lin([(0, sky_top, 1), (1, sky_low, 1)])
    house = mix("#000000", "#C96A4A", dark_k)
    roof = mix("#000000", "#7A3A30", dark_k)
    ground = mix("#000000", "#2F8A6A", dark_k)
    skin = mix("#000000", "#F2C6A8", dark_k)
    s = [d, f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{sky}"/>']
    if sky_k > 0.05:
        s.append(g(_cloud(x + w * 0.3, y + h * 0.18, 1.1) + _cloud(x + w * 0.72, y + h * 0.28, 0.8), opacity=sky_k))
    s.append(f'<path d="M{x},{y + h * 0.66} Q{x + w * 0.5},{y + h * 0.58} {x + w},{y + h * 0.65} L{x + w},{y + h} L{x},{y + h} Z" fill="{ground}"/>')
    s.append(body(x + w * 0.16, y + h * 0.46, w * 0.34, h * 0.24, 6, house, shine=0.06 * dark_k, shade=0.2, rim=False))
    s.append(f'<path d="M{x + w * 0.12},{y + h * 0.47} L{x + w * 0.33},{y + h * 0.33} L{x + w * 0.54},{y + h * 0.47} Z" fill="{roof}"/>')
    s.append(ball(x + w * 0.72, y + h * 0.56, w * 0.06, skin)
             + body(x + w * 0.66, y + h * 0.62, w * 0.12, h * 0.16, 30, mix("#000000", "#3EA0E0", dark_k), shine=0.1, shade=0.2, rim=False))
    return "".join(s)


def tone_card(c: Ctx) -> str:
    """modes: crush (even compression: sky turns pure white, house & person pure black; labels) | lift
    (shoot dark to keep the sky ①, then lift the shadows ②, check)."""
    mode = c.props.get("mode", "crush")
    _ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    W, H = 780, 780
    x0, y0 = c.canvas.cx - W / 2, 540  # below the headline band, above the subtitles
    pe = c.pop(0, 0.55)
    if mode == "crush":
        k = ease_io(_u(c, rev, 0.9))
        sky_k, dark_k = 1 - k, 1 - k
    else:
        k = ease_io(_u(c, rev, 1.1))
        sky_k, dark_k = 1.0, lerp(0.18, 1.0, k)
    inner = _landscape(x0, y0, W, H, sky_k, dark_k)
    if mode == "lift":
        inner += f'<rect x="{x0}" y="{y0}" width="{W}" height="{H}" fill="#05041A" opacity="{0.35 * (1 - k):.3f}"/>'
    out = [contact_shadow(c.canvas.cx, y0 + H + 40, W * 0.55, 40, 0.5), _clip(f"tc{mode}", x0, y0, W, H, 44, inner)]
    if mode == "crush":
        ki = _k(c, imp, 0.45)
        out.append(g(pill(x0 + W * 0.5, y0 + H * 0.16, "死白", 46, RED) + pill(x0 + W * 0.33, y0 + H * 0.82, "死黑", 46, RED),
                     s=max(ki, 1e-3), oy=y0 + H / 2))
    else:
        out.append(g(pill(c.canvas.cx, y0 + H - 160, "① 拍暗 · 保住天空", 40, c.p1), opacity=1 - k * 0.6))
        out.append(g(pill(c.canvas.cx, y0 + H - 60, "② 提亮暗处", 40, c.p2), s=max(_k(c, rev, 0.45), 1e-3), oy=y0 + H - 60))
        out.append(mark(x0 + W - 40, y0 + 40, True, _k(c, imp, 0.45), 64))
    isx, isy = c.impact()
    return g("".join(out), s=max(pe, 1e-3), sx=isx, sy=isy, oy=y0 + H / 2, ty=wobble(c.t, 0.25, 4))


# ----------------------------------------------------------------- s40–s42 multi-camera
TINTS = [("#FF9A3C", "超广角"), (None, "主摄"), ("#4D8DFF", "长焦"), ("#3EE08F", "微距")]


def _lighthouse(x: float, y: float, w: float, h: float, tint: str | None, t: float, zoom: float = 1.0) -> str:
    cx, base = x + w / 2, y + h * 0.72
    inner = []
    d, sky = lin([(0, "#2A2F8A", 1), (1, "#FF9A6E", 1)])
    inner.append(d + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{sky}"/>')
    sc = zoom
    tower = (f'<path d="M{cx - 34},{base} L{cx - 22},{base - 300} L{cx + 22},{base - 300} L{cx + 34},{base} Z" fill="#F4F2FF"/>'
             + "".join(f'<rect x="{cx - 40}" y="{base - 60 - 80 * k}" width="80" height="26" fill="#FF4D6A"/>' for k in range(3))
             + body(cx - 34, base - 352, 68, 54, 12, "#FFE9B0", shine=0.3, shade=0.1)
             + f'<path d="M{cx - 40},{base - 350} L{cx},{base - 390} L{cx + 40},{base - 350} Z" fill="#3A3560"/>')
    beam_a = 0.25 + 0.15 * math.sin(t * 2)
    beam = f'<path d="M{cx},{base - 325} L{cx + 520},{base - 420} L{cx + 520},{base - 230} Z" fill="#FFF2C4" opacity="{beam_a:.3f}"/>'
    inner.append(g(beam + tower, s=sc, ox=cx, oy=base))
    inner.append(f'<path d="M{x},{base} Q{cx},{base - 16} {x + w},{base} L{x + w},{y + h} L{x},{y + h} Z" fill="#1E5A8A"/>')
    if tint:
        inner.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{tint}" opacity="0.28"/>')
    return "".join(inner)


def zoom_switch(c: Ctx) -> str:
    """modes: grid (same lighthouse through four lenses, each with its own colour bias) | zoom (slider 0.6×→5×;
    each lens hand-over flashes '颜色跳了！' and the tint jumps)."""
    mode = c.props.get("mode", "grid")
    ent, _rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    out = []
    if mode == "grid":
        w, h, gp = 400, 470, 30
        for i, (tint, lab) in enumerate(TINTS):
            x = c.canvas.cx - w - gp / 2 + (i % 2) * (w + gp)
            y = 470 + (i // 2) * (h + 110)
            k = _k(c, ent + 0.1 * i, 0.5)
            out.append(g(contact_shadow(x + w / 2, y + h + 20, w * 0.5, 20, 0.4)
                         + _clip(f"zs{i}", x, y, w, h, 30, _lighthouse(x, y, w, h, tint, c.t))
                         + text(x + w / 2, y + h + 52, lab, 38, 800, "#C9C3F0"), s=max(k, 1e-3), ox=x + w / 2, oy=y + h / 2))
    else:
        u = ease_io(_u(c, ent + 0.3, max(0.5, (imp or c.t1) - ent - 0.3)))
        zf = lerp(0.6, 5.0, u)
        lens = 0 if zf < 1.0 else 1 if zf < 3.0 else 2
        tint = [TINTS[0][0], None, TINTS[2][0]][lens]
        W, H = 800, 980
        x0, y0 = c.canvas.cx - W / 2, 330
        out.append(contact_shadow(c.canvas.cx, y0 + H + 30, W * 0.55, 36, 0.5)
                   + _clip("zsz", x0, y0, W, H, 40, _lighthouse(x0, y0, W, H, tint, c.t, zoom=lerp(0.7, 2.4, u))))
        for thr, t_lab in ((1.0, "主摄"), (3.0, "长焦")):  # flash at each hand-over
            tt = ent + 0.3 + _cross_time(thr, max(0.5, (imp or c.t1) - ent - 0.3))
            if 0 <= c.t - tt <= 0.9:
                kk = back_out(clamp((c.t - tt) / 0.3))
                out.append(f'<rect x="{x0}" y="{y0}" width="{W}" height="{H}" rx="40" fill="#FFFFFF" '
                           f'opacity="{0.35 * clamp(1 - (c.t - tt) / 0.25):.3f}"/>')
                out.append(g(pill(c.canvas.cx, y0 + 120, "颜色跳了！", 50, RED), s=max(kk, 1e-3), oy=y0 + 120))
        sy = y0 + H + 130
        out.append(body(c.canvas.cx - 360, sy - 14, 720, 28, 14, "#241C55", shine=0, shade=0.2))
        kx = c.canvas.cx - 360 + 720 * u
        out.append(ball(kx, sy, 34, c.accent) + text(kx, sy + 72, f"{zf:.1f}×", 40, 900, "#FFFFFF"))
        out.append(text(c.canvas.cx - 360, sy + 72, "0.6×", 34, 700, "#8C86B0", "start", opacity=clamp((kx - c.canvas.cx + 260) / 80)))
        out.append(text(c.canvas.cx + 360, sy + 72, "5×", 34, 700, "#8C86B0", "end", opacity=clamp((c.canvas.cx + 260 - kx) / 80)))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 4))


def _cross_time(thr: float, span: float) -> float:
    """Seconds into the slide at which the zoom factor 0.6→5 (eased over `span`) crosses `thr`."""
    lo, hi = 0.0, 1.0
    target = (thr - 0.6) / 4.4
    for _ in range(30):  # invert ease_io by bisection (monotone)
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ease_io(mid) < target else (lo, mid)
    return lo * span


def triple_isp(c: Ctx) -> str:
    """Three always-on lanes: lens -> ISP n -> preview; data dots flow, the active lane follows the zoom; check."""
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    out = []
    active = int(((c.t - (rev or ent)) / 0.9) % 3) if rev is not None and c.t >= rev else 1
    for i in range(3):
        y = 560 + i * 300
        k = _k(c, ent + 0.12 * i, 0.5)
        on = i == active
        col = c.accent if on else c.p1
        dots = []
        for q in range(4):  # data flows along the lane, under the boxes
            u = ((c.t - ent) * 0.9 + q / 4 + i * 0.13) % 1
            px = lerp(c.canvas.cx - 290, c.canvas.cx + 240, u)
            dots.append(glow(px, y, 22, CYAN, 0.5) + ball(px, y, 9, "#E9FFFA"))
        lane = [f'<rect x="{c.canvas.cx - 380}" y="{y - 6}" width="760" height="12" rx="6" fill="#FFFFFF" opacity="0.12"/>',
                "".join(dots),
                ball(c.canvas.cx - 360, y, 64, "#3A3560") + ball(c.canvas.cx - 360, y, 40, darken(c.p2, 0.3)) + ball(c.canvas.cx - 372, y - 12, 12, "#FFFFFF"),
                (glow(c.canvas.cx, y, 200, c.accent, 0.3) if on else "")
                + body(c.canvas.cx - 120, y - 64, 240, 128, 30, col, shine=0.28, shade=0.2)
                + text(c.canvas.cx, y, f"ISP {i + 1}", 48, 900, "#3A2200" if on else "#FFFFFF"),
                body(c.canvas.cx + 250, y - 70, 140, 140, 20, "#F4F2FF", shine=0.2, shade=0.15)
                + _clip(f"tip{i}", c.canvas.cx + 262, y - 58, 116, 116, 12,
                        _lighthouse(c.canvas.cx + 262, y - 58, 116, 116, [TINTS[0][0], None, TINTS[2][0]][i], c.t))]
        out.append(g("".join(lane), s=max(k, 1e-3), oy=y))
    out.append(g(pill(c.canvas.cx, 1460, "后台待命 · 一拉就切", 44, "#241C55"), s=max(_k(c, rev, 0.45), 1e-3), oy=1460))
    out.append(mark(c.canvas.cx + 330, 400, True, _k(c, imp, 0.45), 56))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, ty=wobble(c.t, 0.25, 4))


COMPONENTS = {
    "PhotonWell": photon_well,
    "NeighborGrid": neighbor_grid,
    "MoireFence": moire_fence,
    "PhotonBars": photon_bars,
    "BurstStack": burst_stack,
    "WBCompare": wb_compare,
    "ToneLadder": tone_ladder,
    "ToneCard": tone_card,
    "ZoomSwitch": zoom_switch,
    "TripleISP": triple_isp,
}
