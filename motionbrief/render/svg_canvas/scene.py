# SPDX-License-Identifier: Apache-2.0
"""Compose one frame (Cartoon Tech v2): parallax background, depth layers, typography,
keyword-highlighted subtitles, transitions, camera drift."""
from __future__ import annotations

import math
import random
import re

from motionbrief.ir.models import Scene, SceneIR, VisualObject
from motionbrief.paths import load_registry, load_tokens
from motionbrief.render.svg_canvas.canvas import Canvas, canvas_for
from motionbrief.render.svg_canvas.components import COMPONENTS, Ctx
from motionbrief.render.svg_canvas.easing import EASINGS, Beats, clamp, ease_out_expo, lerp, progress
from motionbrief.render.svg_canvas.prims import (back_out, body, fit_size, g, glow, lin, measure, pill, rich_line,
                                                  shadow_text, text)

DEPTH_GAIN = {0: 0.45, 1: 1.0, 2: 1.4}


def _hx(canvas: Canvas, x: float) -> float:
    """x authored for a 1080-wide design space, scaled to this canvas (identity for 9:16)."""
    return x * canvas.w // 1080


def _vy(canvas: Canvas, y: float) -> float:
    """y authored for a 1920-tall design space, scaled to this canvas (identity for 9:16)."""
    return y * canvas.h // 1920


def component_for(vo: VisualObject, chosen_renderer: str) -> str:
    reg = load_registry()["components"][vo.component]
    if chosen_renderer in ("svg", "canvas") and reg["status"] == "implemented":
        return vo.component
    return reg["fallback2D"]


def _camera(scene: Scene, t: float) -> tuple[float, float, float]:
    """(scale, x, y): authored move + always-on gentle drift so frames are never dead-still."""
    cam = scene.camera
    ease = EASINGS.get(cam.easing, EASINGS["easeOutExpo"])
    u = clamp((t - scene.tStart) / max(0.001, scene.duration))
    u = 0.5 * ease(u) + 0.5 * u
    s, x = 1.0, 0.0
    if cam.move in ("push_in", "pull_out", "orbit"):
        s = lerp(cam.from_, cam.to, u)
    elif cam.move == "pan":
        x = lerp(-40, 40, u)
    x += 8 * math.sin(t * 0.37)
    y = 6 * math.sin(t * 0.29 + 1.3)
    return s, x, y


def _transition_wrap(scene: Scene, t: float, inner: str, bg: str, canvas: Canvas) -> str:
    kind = scene.transitionIn.type
    dur = load_tokens()["durations"]["transition"]
    u = progress(t, scene.tStart, dur)
    if u >= 1 or kind == "cut":
        return inner
    e = ease_out_expo(u)
    if kind == "zoom_through":
        return g(inner, s=lerp(1.5, 1.0, e), opacity=clamp(0.2 + e), ox=canvas.cx, oy=canvas.cy)
    if kind == "match_cut":
        return g(inner, s=lerp(0.95, 1.0, e), ox=canvas.cx, oy=canvas.cy)
    if kind == "morph_fuse":
        return g(inner, sx=lerp(1.12, 1.0, e), sy=lerp(0.75, 1.0, e), ox=canvas.cx, oy=canvas.cy)
    if kind == "mask_reveal":
        r = lerp(0, 1200, e)
        return (f'<rect width="{canvas.w}" height="{canvas.h}" fill="{bg}"/>'
                f'<clipPath id="mr"><circle cx="{canvas.cx}" cy="{canvas.cy}" r="{r:.1f}"/></clipPath>'
                f'<g clip-path="url(#mr)">{inner}</g>')
    return inner


CHAPTER_CARD_SEC = 2.5


PORTRAIT_BAND = (420, 1400)   # portrait content-safe band (y), centre x 540
LANDSCAPE_AREA = (110, 800)   # landscape object area (y): clear of the subtitle box (~916-996)
LANDSCAPE_AREA_TOP = (270, 800)  # ...when a top headline (y ~175-245) is on screen


def _object_area(scene: Scene) -> tuple[int, int]:
    return LANDSCAPE_AREA_TOP if any(ty.safeArea == "top" for ty in scene.typography) else LANDSCAPE_AREA


def _object_slots(canvas: Canvas, count: int, area: tuple[int, int] = LANDSCAPE_AREA) -> list[tuple[float, float]] | None:
    """(scale, dx) per object: each object's centre goes to its own column of a landscape canvas.

    Objects are authored in the portrait design space: their content band (y 420-1400) is mapped onto the
    landscape object area, never wider than its column. Returns None on 9:16 (objects drawn as before).
    """
    if canvas.h >= 1920:
        return None
    col = canvas.w / count
    s = min((area[1] - area[0]) / (PORTRAIT_BAND[1] - PORTRAIT_BAND[0]), 0.92 * col / 1080)
    return [(s, col * (i + 0.5) - canvas.cx) for i in range(count)]


FIT_FILL = 0.88  # a portrait object's drawn content fills this share of its column / of the object area
FIT_MAX = 1.6    # ...but is enlarged at most this much (portrait text is already sized for a phone)
_BBOX: dict[tuple, tuple[float, float, float, float] | None] = {}


def _content_bbox(key: tuple, draws) -> tuple[float, float, float, float] | None:
    """Union of the visible pixels (portrait design units) of an object drawn at a few moments of its shot,
    from a quarter-size raster. Cached per object, so every frame of a scene uses the same placement."""
    if key not in _BBOX:
        import io

        import cairosvg
        from PIL import Image
        box = None
        for inner in draws():
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="270" height="480" viewBox="0 0 1080 1920">{inner}</svg>'
            alpha = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert("RGBA").getchannel("A")
            b = alpha.point(lambda a: 255 if a > 110 else 0).getbbox()  # soft glows and shadows do not count
            if b:
                b = tuple(v * 4 for v in b)
                box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        _BBOX[key] = box
    return _BBOX[key]


def _place_landscape(obj: str, canvas: Canvas, slot: tuple[float, float], area: tuple[int, int], native: bool,
                     count: int = 1, bbox: tuple[float, float, float, float] | None = None, depth: int = 1) -> str:
    """Native 16:9 object (authored for y 120-760): kept, squeezed into the area only when a headline needs the top.
    Depth-0 portrait atmosphere: scaled to cover the frame. Other portrait objects: their drawn content (bbox) is
    fitted to the centre of their column in the object area; without a bbox the content band (y 420-1400) is."""
    cy = (area[0] + area[1]) / 2
    if native:
        if area == LANDSCAPE_AREA:
            return obj
        s = (area[1] - area[0]) / 640
        return g(obj, ty=cy - 440, s=s, ox=canvas.cx, oy=440)
    s, dx = slot
    if depth == 0:
        return g(obj, tx=canvas.cx - 540, ty=canvas.cy - 960, s=canvas.w / 1080, ox=540, oy=960)
    if bbox:
        bw, bh = max(bbox[2] - bbox[0], 1.0), max(bbox[3] - bbox[1], 1.0)
        s = min(FIT_FILL * canvas.w / count / bw, FIT_FILL * (area[1] - area[0]) / bh, FIT_MAX)
        px, py = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        return g(obj, tx=canvas.cx + dx - px, ty=cy - py, s=s, ox=px, oy=py)
    p0y = (PORTRAIT_BAND[0] + PORTRAIT_BAND[1]) / 2
    return g(obj, tx=canvas.cx + dx - 540, ty=cy - p0y, s=s, ox=540, oy=p0y)


def _chapter_card(ir: SceneIR, scene: Scene, t: float, tokens: dict) -> str:
    """Title card for the first scene of a chapter; fades out over its last 0.5 s."""
    cards = ir.video.chapterCards
    default = ir.video.aspect == "16:9" and ir.duration >= 120  # cards are for long-form only by default
    if not scene.chapter or not (cards if cards is not None else default):
        return ""
    since = t - scene.tStart
    if since > CHAPTER_CARD_SEC:
        return ""
    canvas = canvas_for(ir.video.aspect)
    look = _look(canvas, tokens, ir.video.visualStyle)
    st = {**tokens["typography"]["styles"]["headline"], "color": look["headline"]["color"]}
    fade = clamp((CHAPTER_CARD_SEC - since) / 0.5)
    return (f'<g opacity="{fade:.3f}"><rect width="{canvas.w}" height="{canvas.h}" '
            f'fill="{look["background"]["gradient"][1]}" fill-opacity="0.72"/>'
            f'{shadow_text(canvas.cx, canvas.cy, scene.chapter, st["size"], st["weight"], st["color"])}</g>')


NOTE_SIZE, NOTE_MAX_W = 24, 480  # footnote: small, bottom-left, clear of the centred subtitle box (x 560..1360)


def _note(ir: SceneIR, scene: Scene) -> str:
    """Per-scene corner footnote (e.g. a simplification disclaimer), drawn on every frame of the scene."""
    if not scene.note:
        return ""
    size = fit_size(scene.note, NOTE_SIZE, 400, NOTE_MAX_W)
    baseline = ir.video.h - 30 if ir.video.aspect == "16:9" else 1860
    # text() draws its baseline at y + 0.36*size, so pass the centre that puts the baseline on `baseline`
    return text(60, baseline - 0.36 * size, scene.note, size, 400, "#94A3B8", "start", 0.9)


def _look(canvas: Canvas, tokens: dict, style: str) -> dict:
    """Background, band, headline and subtitle look. Landscape reads tokens.visualStyles[style]; portrait keeps
    its original look (no style applies, so portrait output is unchanged)."""
    if canvas.h >= 1920:
        return {"background": tokens["background"], "band": None, "headline": None,
                "subtitle": tokens["typography"]["subtitle"]}
    v = tokens["visualStyles"][style]
    return {**v, "subtitle": {**tokens["typography"]["subtitleLandscape"], **v["subtitle"]}}


def _bands(canvas: Canvas, t: float, color: str, opacity: float) -> str:
    """Slanted translucent bands that drift slowly to the right; the landscape background pattern."""
    shift = (t * 24) % 240
    slant = canvas.h * 0.6
    out = []
    for k in range(-2, canvas.w // 240 + 4):
        x = k * 240 + shift
        out.append(f'<polygon points="{x:.1f},0 {x + 90:.1f},0 {x + 90 - slant:.1f},{canvas.h} {x - slant:.1f},{canvas.h}" '
                   f'fill="{color}" fill-opacity="{opacity}"/>')
    return "".join(out)


def _background(tokens: dict, t: float, cam_x: float, accent_glow: str, canvas: Canvas, style: str) -> str:
    look = _look(canvas, tokens, style)
    a, b = look["background"]["gradient"]
    d, u = lin([(0, a, 1), (1, b, 1)])
    W, H = canvas.w, canvas.h
    out = [d, f'<rect width="{W}" height="{H}" fill="{u}"/>']
    if H < 1920 and look["band"]["opacity"] > 0:  # landscape: style band (neon / cartoon / ink differ here)
        out.append(_bands(canvas, t, look["band"]["color"], look["band"]["opacity"]))
    if style == "graphite":  # technical look: flat graphite, no colour pools, bokeh or stars
        return "".join(out)
    # big soft colour pools (very slow drift)
    out.append(glow(_hx(canvas, 220) + 40 * math.sin(t * 0.11), _vy(canvas, 380), 620, "#5B3FD9", 0.30))
    out.append(glow(_hx(canvas, 900) + 30 * math.cos(t * 0.09), _vy(canvas, 1550), 700, "#1BA5A0", 0.18))
    out.append(glow(canvas.cx, canvas.cy, 760, accent_glow, 0.10))
    # parallax bokeh + twinkling stars (depth 0, moves at 0.3x camera)
    rng = random.Random(42)
    for k in range(18):
        x = (rng.uniform(0, W) + cam_x * 0.3 + t * rng.uniform(-6, 6)) % (W + 200) - 100
        y = (rng.uniform(0, H) - t * rng.uniform(4, 14)) % (H + 200) - 100
        out.append(glow(x, y, rng.uniform(40, 120), rng.choice(["#8E7BFF", "#2EE6C5", "#FFB547"]),
                        rng.uniform(0.06, 0.16)))
    for k in range(70):
        x = (rng.uniform(0, W) + cam_x * 0.15) % W
        y = rng.uniform(0, H)
        tw = 0.25 + 0.6 * abs(math.sin(t * rng.uniform(0.6, 1.8) + k))
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(1.2, 2.8):.1f}" fill="#FFFFFF" '
                   f'opacity="{tw * 0.6:.2f}"/>')
    return "".join(out)


def _typography(ir: SceneIR, scene: Scene, t: float, tokens: dict) -> str:
    canvas = canvas_for(ir.video.aspect)
    out = []
    accent = ir.palette.accent
    for ty in scene.typography:
        at = ty.at if ty.at is not None else scene.tStart
        until = ty.until if ty.until is not None else scene.tEnd
        if t < at or t > until:
            continue
        st = tokens["typography"]["styles"][ty.style]
        if ty.style == "headline" and canvas.h < 1920:  # landscape headline colour comes from the visual style
            st = {**st, "color": _look(canvas, tokens, ir.video.visualStyle)["headline"]["color"]}
        y = _vy(canvas, tokens["typography"]["anchors"][ty.safeArea])
        beats = Beats([(m.grammar, m.at) for m in scene.motionGrammar if m.target == ty.text] + [("entrance", at)],
                      scene.tStart)
        k = back_out(progress(t, at, 0.5))
        since = t - (beats.at("impact") or 1e9)
        sq = 0.10 * math.sin(clamp(since / 0.4) * math.pi * 2) * (1 - clamp(since / 0.4)) if since >= 0 else 0
        exit_k = clamp((until - t) / 0.25) if ty.until is not None else 1.0
        if ty.style == "label":
            body_ = pill(canvas.cx, y, ty.text, st["size"], ir.palette.primary[0])
        elif ty.style == "impact_reveal":
            size = fit_size(ty.text, st["size"], st["weight"])
            w = measure(ty.text, size, st["weight"])
            body_ = glow(canvas.cx, y, w * 0.75, accent, 0.35) + shadow_text(canvas.cx, y, ty.text, size, st["weight"])
        else:
            body_ = shadow_text(canvas.cx, y, ty.text, st["size"], st["weight"], st["color"])
        out.append(g(body_, ty=lerp(40, 0, clamp(k)), s=max(k, 1e-3), sx=1 + sq, sy=1 - sq, oy=y,
                     opacity=clamp(k * 2) * exit_k))
    return "".join(out)


_HL = re.compile(r"([A-Za-z]+|[0-9][0-9./%~\-]*|三分之二|两种|一种|一半|毫秒|色盲|ISP)")


def _subtitle(t: float, cues: list[tuple[float, float, str]], tokens: dict, accent: str, keywords: set[str],
              canvas: Canvas, style: str) -> str:
    st = _look(canvas, tokens, style)["subtitle"]
    for a, b, s in cues:
        if a <= t < b:
            parts, last = [], 0
            for m in _HL.finditer(s):
                if m.start() > last:
                    parts.append((s[last:m.start()], st["color"]))
                parts.append((m.group(0), accent))
                last = m.end()
            if last < len(s):
                parts.append((s[last:], st["color"]))
            for kw in sorted(keywords, key=lambda k: (-len(k), k)):  # longest first; set order varies per process
                parts = [p for chunk in parts for p in _split_kw(chunk, kw, accent)]
            w = measure(s, st["size"], st["weight"])
            y = _vy(canvas, st["baselineY"])
            k = back_out(progress(t, a, 0.22))
            box = (f'<rect x="{canvas.cx - w / 2 - 30:.1f}" y="{y - st["size"] * 0.8:.1f}" width="{w + 60:.1f}" '
                   f'height="{st["size"] * 1.6:.1f}" rx="{st["size"] * 0.45:.1f}" fill="{st["boxColor"]}" '
                   f'opacity="{st["boxOpacity"]}"/>')
            return g(box + rich_line(canvas.cx, y, parts, st["size"], st["weight"]), s=lerp(0.92, 1, clamp(k)), oy=y,
                     opacity=clamp(k * 3))
    return ""


def _split_kw(part: tuple[str, str], kw: str, accent: str) -> list[tuple[str, str]]:
    txt, col = part
    if col == accent or not kw or kw not in txt:
        return [part]
    i = txt.index(kw)
    out = []
    if i:
        out.append((txt[:i], col))
    out.append((kw, accent))
    rest = txt[i + len(kw):]
    if rest:
        out += _split_kw((rest, col), kw, accent)
    return out


def frame_svg(ir: SceneIR, scene: Scene, t: float, frame: int, plan: dict[str, str],
              subtitles: list[tuple[float, float, str]], layer_b=None) -> str:
    """layer_b(vo, ctx) -> PNG data URI for objects planned on a GPU backend (three); None = 2.5D everywhere."""
    tokens = load_tokens()
    palette = ir.palette.model_dump()
    canvas = canvas_for(ir.video.aspect)
    cam_s, cam_x, cam_y = _camera(scene, t)
    layers: dict[int, list[str]] = {0: [], 1: [], 2: []}
    area = _object_area(scene)
    slots = _object_slots(canvas, len(scene.visualObjects), area)
    for i, vo in enumerate(scene.visualObjects):
        comp = component_for(vo, plan.get(vo.id, "svg"))
        beats = Beats([(m.grammar, m.at) for m in scene.motionGrammar if m.target == vo.id], scene.tStart)
        extra = {}
        if vo.materialStyle:
            extra["bands"] = vo.materialStyle.bands
            extra["gradientRamp"] = vo.materialStyle.gradientRamp
        native = getattr(COMPONENTS[comp], "native_landscape", False)
        # a portrait component draws on the portrait design canvas (centre 540, 960) even in 16:9; the whole
        # object is then mapped onto the landscape area, so its x and y stay in one coordinate system
        draw_on = canvas if native or not slots else canvas_for("9:16")
        def make(at: float, fr: int) -> Ctx:
            return Ctx(t=at, t0=scene.tStart, t1=scene.tEnd, frame=fr, props=vo.props, beats=beats,
                       palette=palette, tokens=tokens, canvas=draw_on, obj_id=vo.id, extra=dict(extra))
        ctx = make(t, frame)
        if layer_b and plan.get(vo.id) == "three":
            ctx.extra["layerB"] = layer_b(vo, ctx)
        obj = COMPONENTS[comp](ctx)
        if slots:
            bbox = None
            if not native and vo.depth > 0:
                key = (ir.video.id, scene.id, scene.tStart, scene.tEnd, vo.id, comp, repr(sorted(vo.props.items())))
                moments = [scene.tStart + f * scene.duration for f in (0.35, 0.7, 0.95)]
                bbox = _content_bbox(key, lambda: [COMPONENTS[comp](make(m, int(m * 30))) for m in moments])
            obj = _place_landscape(obj, canvas, slots[i], area, native, len(scene.visualObjects), bbox, vo.depth)
        layers[vo.depth].append(obj)
    look = _look(canvas, tokens, ir.video.visualStyle)
    content = _background(tokens, t, cam_x, palette["primary"][0], canvas, ir.video.visualStyle)
    for d in (0, 1, 2):
        k = DEPTH_GAIN[d]
        content += g("".join(layers[d]), tx=cam_x * k, ty=cam_y * k, s=1 + (cam_s - 1) * k, ox=canvas.cx, oy=canvas.cy)
    content += _typography(ir, scene, t, tokens)
    bg = look["background"]["gradient"][1]
    content = _transition_wrap(scene, t, content, bg, canvas)
    d, vig = lin([(0, "#000000", 0)], 0, 0, 0, 1)
    vign = (f'<defs><radialGradient id="vig" cx="0.5" cy="0.45" r="0.8"><stop offset="0.6" stop-color="#03040F" '
            f'stop-opacity="0"/><stop offset="1" stop-color="#03040F" stop-opacity="{look["background"]["vignette"]}"/>'
            f'</radialGradient></defs><rect width="{canvas.w}" height="{canvas.h}" fill="url(#vig)"/>')
    kws = {ty.text for ty in scene.typography if len(ty.text) <= 6}
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas.w}" height="{canvas.h}" '
            f'viewBox="0 0 {canvas.w} {canvas.h}">'
            f'<rect width="{canvas.w}" height="{canvas.h}" fill="{bg}"/>{content}{vign}'
            f'{_chapter_card(ir, scene, t, tokens)}{_note(ir, scene)}'
            f'{_subtitle(t, subtitles, tokens, palette["accent"], kws, canvas, ir.video.visualStyle)}</svg>')
