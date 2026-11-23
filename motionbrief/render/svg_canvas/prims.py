# SPDX-License-Identifier: Apache-2.0
"""Cartoon Tech v2 drawing primitives (REVIEW R-27).

Look: flat vector shapes with soft gradients for volume, highlight + shade bands from a single
upper-left key light, colored glows, soft contact shadows. NO heavy black outlines (v1's ink
outline read as crude). Everything is pure SVG that CairoSVG rasterises deterministically
(no filters: glows/shadows are radial gradients).
"""
from __future__ import annotations

import hashlib
import math
import os
import subprocess
from functools import lru_cache

import motionbrief.paths  # noqa: F401  (loads host .env before reading font settings)
from motionbrief.render.svg_canvas.easing import clamp, lerp

CX, CY = 540, 960
FONT = os.environ.get("MOTIONBRIEF_FONT_FAMILY", "Noto Sans CJK SC")


# ------------------------------------------------------------------ colour
def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgb(r: float, g: float, b: float) -> str:
    return "#%02X%02X%02X" % tuple(int(clamp(v, 0, 255)) for v in (r, g, b))


def mix(a: str, b: str, t: float) -> str:
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    t = clamp(t)
    return _rgb(lerp(ra, rb, t), lerp(ga, gb, t), lerp(ba, bb, t))


def lighten(c: str, k: float) -> str:
    return mix(c, "#FFFFFF", k)


def darken(c: str, k: float, toward: str = "#0B1033") -> str:
    """Shade toward deep navy (never pure black: keeps shadows saturated)."""
    return mix(c, toward, k)


def _id(*parts) -> str:
    return "g" + hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:10]


# ------------------------------------------------------------------ gradients
def lin(stops: list[tuple[float, str, float]], x1=0.0, y1=0.0, x2=0.0, y2=1.0) -> tuple[str, str]:
    """Return (defs, url) for a linear gradient in objectBoundingBox units."""
    gid = _id("l", stops, x1, y1, x2, y2)
    st = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a:.3f}"/>' for o, c, a in stops)
    return (f'<defs><linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{st}</linearGradient></defs>',
            f"url(#{gid})")


def rad(stops: list[tuple[float, str, float]], cx=0.5, cy=0.5, r=0.5, fx=None, fy=None) -> tuple[str, str]:
    gid = _id("r", stops, cx, cy, r, fx, fy)
    st = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a:.3f}"/>' for o, c, a in stops)
    f = f' fx="{fx}" fy="{fy}"' if fx is not None else ""
    return (f'<defs><radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}"{f}>{st}</radialGradient></defs>',
            f"url(#{gid})")


# ------------------------------------------------------------------ shapes
def glow(cx: float, cy: float, r: float, color: str, a: float = 0.55) -> str:
    if a <= 0.003 or r <= 0:
        return ""
    d, u = rad([(0, color, a), (0.35, color, a * 0.45), (1, color, 0)])
    return f'{d}<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{u}"/>'


def contact_shadow(cx: float, cy: float, rx: float, ry: float, a: float = 0.45) -> str:
    if a <= 0.003:
        return ""
    d, u = rad([(0, "#05071A", a), (1, "#05071A", 0)])
    return f'{d}<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{u}"/>'


def body(x: float, y: float, w: float, h: float, r: float, base: str, *, shine: float = 0.22,
         shade: float = 0.28, rim: bool = True) -> str:
    """Rounded volume: vertical gradient + upper highlight band + lower shade + thin same-hue rim."""
    d, u = lin([(0, lighten(base, 0.18), 1), (0.55, base, 1), (1, darken(base, 0.32), 1)], 0, 0, 0.4, 1)
    out = [d, f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" fill="{u}"/>']
    if shine > 0:
        hd, hu = lin([(0, "#FFFFFF", shine), (1, "#FFFFFF", 0)])
        out.append(f'{hd}<rect x="{x + r * 0.35:.1f}" y="{y + h * 0.04:.1f}" width="{w - r * 0.7:.1f}" '
                   f'height="{h * 0.36:.1f}" rx="{r * 0.8:.1f}" fill="{hu}"/>')
    if shade > 0:
        sd, su = lin([(0, darken(base, 0.6), 0), (1, darken(base, 0.6), shade)])
        out.append(f'{sd}<rect x="{x:.1f}" y="{y + h * 0.55:.1f}" width="{w:.1f}" height="{h * 0.45:.1f}" '
                   f'rx="{r:.1f}" fill="{su}"/>')
    if rim:
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" fill="none" '
                   f'stroke="{lighten(base, 0.45)}" stroke-opacity="0.35" stroke-width="2"/>')
    return "".join(out)


def ball(cx: float, cy: float, r: float, base: str, light: str | None = None) -> str:
    """Sphere-ish disc lit from upper-left."""
    d, u = rad([(0, light or lighten(base, 0.55), 1), (0.55, base, 1), (1, darken(base, 0.35), 1)],
               cx=0.5, cy=0.5, r=0.6, fx=0.35, fy=0.3)
    return f'{d}<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{u}"/>'


def g(inner: str, tx: float = 0, ty: float = 0, s: float = 1.0, ox: float = CX, oy: float = CY,
      opacity: float = 1.0, rot: float = 0.0, sx: float | None = None, sy: float | None = None) -> str:
    if not inner:
        return ""
    sx = s if sx is None else sx * s
    sy = s if sy is None else sy * s
    tr = (f"translate({tx + ox:.2f},{ty + oy:.2f}) rotate({rot:.2f}) scale({max(sx, 1e-4):.4f},{max(sy, 1e-4):.4f}) "
          f"translate({-ox:.2f},{-oy:.2f})")
    op = f' opacity="{clamp(opacity):.3f}"' if opacity < 0.999 else ""
    return f'<g transform="{tr}"{op}>{inner}</g>'


# ------------------------------------------------------------------ text
@lru_cache(maxsize=1)
def font_file() -> str:
    """Font file matching FONT: MOTIONBRIEF_FONT_FILE, else fontconfig (Linux/macOS)."""
    if os.environ.get("MOTIONBRIEF_FONT_FILE"):
        return os.environ["MOTIONBRIEF_FONT_FILE"]
    try:
        return subprocess.run(["fc-match", "-f", "%{file}", f"{FONT}:bold"], capture_output=True, text=True).stdout
    except OSError:
        return ""


@lru_cache(maxsize=None)
def _font(size: int, weight: str):
    from PIL import ImageFont
    path = font_file()
    for idx in range(8):
        try:
            f = ImageFont.truetype(path, size, index=idx)
        except OSError:
            break
        if "SC" in f.getname()[0]:
            try:
                f.set_variation_by_name(weight)
            except Exception:
                pass
            return f
    return ImageFont.truetype(path, size)


def _wname(weight: int) -> str:
    return "Black" if weight >= 850 else "Bold" if weight >= 650 else "Medium" if weight >= 450 else "Regular"


SAFE_TEXT_W = 760   # centred text must fit 540 ± 380 (safe area: left 72, right 160)
MIN_FIT = 0.7       # big text may shrink to 70 % of its style size to fit; below that the text is too long


def fit_size(s: str, size: float, weight: int = 900, max_w: float = SAFE_TEXT_W) -> float:
    """Largest size ≤ `size` (and ≥ MIN_FIT·size) at which `s` fits `max_w`: '具身智能' at 210 px -> ~190 px."""
    w = measure(s, size, weight)
    return size if w <= max_w else max(size * MIN_FIT, size * max_w / w)


def measure(s: str, size: float, weight: int = 700) -> float:
    try:
        return float(_font(int(round(size)), _wname(weight)).getlength(s))
    except Exception:
        return sum(size * (1.0 if ord(ch) > 0x2E80 else 0.6) for ch in s)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x: float, y: float, s: str, size: float, weight: int = 800, fill: str = "#FFFFFF",
         anchor: str = "middle", opacity: float = 1.0, ls: float = 0.0) -> str:
    yb = y + size * 0.36  # visual centre (cairosvg lacks dominant-baseline)
    lsp = f' letter-spacing="{ls:.1f}"' if ls else ""
    return (f'<text x="{x:.1f}" y="{yb:.1f}" font-family="{FONT}" font-size="{size:.1f}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" opacity="{clamp(opacity):.3f}"{lsp}>{esc(s)}</text>')


def shadow_text(x: float, y: float, s: str, size: float, weight: int = 900, fill: str = "#FFFFFF",
                anchor: str = "middle", opacity: float = 1.0) -> str:
    """Text with a soft offset shadow (two translucent layers) instead of a hard stroke."""
    sh = "#060818"
    return (text(x + size * 0.03, y + size * 0.06, s, size, weight, sh, anchor, opacity * 0.35)
            + text(x + size * 0.015, y + size * 0.03, s, size, weight, sh, anchor, opacity * 0.35)
            + text(x, y, s, size, weight, fill, anchor, opacity))


def rich_line(cx: float, y: float, parts: list[tuple[str, str]], size: float, weight: int = 800,
              opacity: float = 1.0) -> str:
    """Centered line made of differently coloured runs (keyword highlighting), measured exactly."""
    widths = [measure(t, size, weight) for t, _ in parts]
    x = cx - sum(widths) / 2
    out = []
    for (t, col), w in zip(parts, widths):
        out.append(text(x, y, t, size, weight, col, "start", opacity))
        x += w
    return "".join(out)


def pill(cx: float, cy: float, label: str, size: float, base: str, opacity: float = 1.0,
         text_col: str = "#FFFFFF") -> str:
    w = measure(label, size, 800) + size * 1.4
    h = size * 1.75
    x, y = cx - w / 2, cy - h / 2
    return g(contact_shadow(cx, cy + h * 0.55, w * 0.55, h * 0.35, 0.35)
             + body(x, y, w, h, h / 2, base, shine=0.25, shade=0.2)
             + text(cx, cy, label, size, 800, text_col), opacity=opacity)


def ease_io(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def back_out(t: float, k: float = 1.70158) -> float:
    """Overshoot ease (anticipation/follow-through feel)."""
    t = clamp(t) - 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


def wobble(t: float, freq: float = 1.0, amp: float = 1.0, phase: float = 0.0) -> float:
    return amp * math.sin(2 * math.pi * freq * t + phase)
