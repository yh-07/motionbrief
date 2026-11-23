# SPDX-License-Identifier: Apache-2.0
"""Generic, parameterised diagram components (plan A): any explainer beat the topic library lacks can be told
with cards and bars. Same Cartoon Tech v2 look and beat semantics as the topic components:
entrance = items pop in one by one, reveal = items light / values fill, impact = highlight + marks land.
"""
from __future__ import annotations

from motionbrief.render.svg_canvas.components import Ctx
from motionbrief.render.svg_canvas.components_v3 import GREEN, RED, _k, mark
from motionbrief.render.svg_canvas.easing import clamp, ease_out_expo, progress
from motionbrief.render.svg_canvas.prims import (body, contact_shadow, darken, glow, g, measure, text, wobble)


def _col(c: Ctx, name: str | None, i: int) -> str:
    return {"p1": c.p1, "p2": c.p2, "accent": c.accent, "red": RED, "green": GREEN}.get(
        name or "", c.p1 if i % 2 == 0 else darken(c.p2, 0.15))


def _fit(s: str, size: float, w: float) -> float:
    """Shrink a label until it fits width w."""
    while size > 22 and measure(s, size, 900) > w:
        size -= 2
    return size


def info_cards(c: Ctx) -> str:
    """items: [{title, value?, mark?: ok|bad, color?: p1|p2|accent|red|green}] (1-6);
    layout: column | row | grid; highlight: index lit on impact (-1 none); y: centre."""
    items = c.props.get("items", [])[:6]
    layout = c.props.get("layout", "column" if len(items) > 3 else "row")
    hi = int(c.props.get("highlight", -1))
    yc = float(c.props.get("y", 960))
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    n = max(1, len(items))
    if layout == "row":
        cols, w, h = n, min(300, (900 - 30 * (n - 1)) / n), 360
    elif layout == "grid":
        cols, w, h = 2, 420, 300
    else:
        cols, w, h = 1, 760, 150 if n > 4 else 180
    rows = (n + cols - 1) // cols
    gap = 30
    x0 = c.canvas.cx - (cols * w + (cols - 1) * gap) / 2
    y0 = yc - (rows * h + (rows - 1) * gap) / 2
    lit_k = ease_out_expo(progress(c.t, rev, 0.5)) if rev is not None and c.t >= rev else 0.0
    out = []
    for i, it in enumerate(items):
        x, y = x0 + (i % cols) * (w + gap), y0 + (i // cols) * (h + gap)
        k = _k(c, ent + 0.12 * i, 0.5)
        on = i == hi and imp is not None and c.t >= imp
        base = c.accent if on else _col(c, it.get("color"), i)
        ink = "#3A2200" if on else "#FFFFFF"
        title, value = str(it.get("title", "")), str(it.get("value", ""))
        card = [contact_shadow(x + w / 2, y + h + 14, w * 0.48, 18, 0.4),
                glow(x + w / 2, y + h / 2, w * 0.7, c.accent, 0.3) if on else "",
                body(x, y, w, h, min(40, h / 2), base, shine=0.24, shade=0.22)]
        if value:
            vs = _fit(value, 72 if layout != "column" else 60, w * (0.85 if layout != "column" else 0.4))
            ts = _fit(title, 40, w * (0.85 if layout != "column" else 0.5))
            if layout == "column":
                card.append(text(x + 40, y + h / 2, title, ts, 900, ink, "start"))
                card.append(text(x + w - 40, y + h / 2, value, vs, 900, ink, "end", opacity=0.4 + 0.6 * lit_k))
            else:
                card.append(text(x + w / 2, y + h * 0.36, value, vs, 900, ink, opacity=0.4 + 0.6 * lit_k))
                card.append(text(x + w / 2, y + h * 0.74, title, ts, 800, ink))
        else:
            card.append(text(x + w / 2, y + h / 2, title, _fit(title, 52, w * 0.85), 900, ink))
        if it.get("mark") in ("ok", "bad"):
            card.append(mark(x + w - 24, y + 24, it["mark"] == "ok", _k(c, imp if imp is not None else rev, 0.45), 40))
        pop = 1 + (0.05 if on else 0) * clamp(1 - (c.t - (imp or 0)) / 0.4)
        out.append(g("".join(card), s=max(k, 1e-3) * pop, ox=x + w / 2, oy=y + h / 2))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=yc, ty=wobble(c.t, 0.25, 4))


def stat_bars(c: Ctx) -> str:
    """bars: [{label, value (number), display?: text shown, color?}] (2-6); unit: suffix; highlight: index;
    scale: max value (default = largest). Bars grow on reveal (or entrance); the highlight pops on impact."""
    bars = c.props.get("bars", [])[:6]
    unit = str(c.props.get("unit", ""))
    hi = int(c.props.get("highlight", -1))
    top_v = float(c.props.get("scale", max([float(b.get("value", 0)) for b in bars] + [1e-9])))
    ent, rev, imp = c.ent(), c.beats.at("reveal"), c.beats.at("impact")
    n = max(1, len(bars))
    gap, bh_max, base = 28, 760, float(c.props.get("y", 1340))
    w = min(150, (860 - gap * (n - 1)) / n)
    x0 = c.canvas.cx - (n * w + (n - 1) * gap) / 2
    grow = ease_out_expo(progress(c.t, rev if rev is not None else ent + 0.3, 1.0))
    out = [f'<rect x="{x0 - 30:.1f}" y="{base:.1f}" width="{n * w + (n - 1) * gap + 60:.1f}" height="6" rx="3" '
           f'fill="#FFFFFF" opacity="0.25"/>']
    for i, b in enumerate(bars):
        x = x0 + i * (w + gap)
        k = _k(c, ent + 0.08 * i, 0.45)
        on = i == hi and imp is not None and c.t >= imp
        col = c.accent if on else _col(c, b.get("color"), i)
        v = float(b.get("value", 0))
        h = max(8.0, bh_max * clamp(v / top_v) * grow)
        shown = b.get("display") or (f"{v * grow:.0f}" if v >= 10 else f"{v * grow:.1f}") + unit
        bar = [glow(x + w / 2, base - h / 2, w * 1.2, c.accent, 0.3) if on else "",
               body(x, base - h, w, h, min(24, w / 2), col, shine=0.3, shade=0.18),
               text(x + w / 2, base - h - 44, shown, _fit(shown, 44, w + gap), 900, "#FFFFFF", opacity=clamp(grow * 2)),
               text(x + w / 2, base + 56, str(b.get("label", "")), _fit(str(b.get("label", "")), 38, w + gap), 800, "#C9C3F0")]
        out.append(g("".join(bar), s=max(k, 1e-3), ox=x + w / 2, oy=base))
    isx, isy = c.impact()
    return g("".join(out), sx=isx, sy=isy, oy=base, ty=wobble(c.t, 0.25, 4))


COMPONENTS = {"InfoCards": info_cards, "StatBars": stat_bars}
