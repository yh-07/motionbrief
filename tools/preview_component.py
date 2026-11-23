# SPDX-License-Identifier: Apache-2.0
"""Render one component at a few moments of a fake shot into a contact sheet (component development aid).

  python tools/preview_component.py motionbrief.render.svg_canvas.components_robot:robot_arm \
      --props '{"mode": "fail"}' --dur 5 --rev 0.4 --imp 0.75 --times 0.05,0.3,0.55,0.8,0.95 \
      --out work/_preview/robot_fail.png

Beats/times are fractions of the shot. Background, camera and subtitles are omitted; the content-safe band
(y 420-1400) and the headline band (y 330-470) are drawn as faint guides.
"""
from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import motionbrief.paths  # noqa: E402,F401  (loads .env: cairo DLL path, fonts)
from motionbrief.paths import load_tokens  # noqa: E402
from motionbrief.render.svg_canvas.canvas import canvas_for  # noqa: E402
from motionbrief.render.svg_canvas.components import Ctx  # noqa: E402
from motionbrief.render.svg_canvas.easing import Beats  # noqa: E402

PALETTE = {"primary": ["#7C5CFF", "#22D3B6"], "accent": "#FFB547"}


def _bg(w: int, h: int) -> str:
    """Preview background at the canvas size, with the content-safe guides for each aspect."""
    if h >= 1920:
        guides = ('<rect x="0" y="330" width="1080" height="140" fill="#FFFFFF" opacity="0.04"/>'
                  '<rect x="0" y="420" width="1080" height="980" fill="none" stroke="#FFFFFF" stroke-opacity="0.12" '
                  'stroke-dasharray="12 12" stroke-width="3"/>')
    else:
        guides = ('<rect x="80" y="120" width="1760" height="640" fill="none" stroke="#FFFFFF" stroke-opacity="0.12" '
                  'stroke-dasharray="12 12" stroke-width="3"/>')
    return ('<defs><linearGradient id="pbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1C2029"/>'
            f'<stop offset="1" stop-color="#0B0D12"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#pbg)"/>'
            + guides)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="module:function")
    ap.add_argument("--props", default="{}")
    ap.add_argument("--dur", type=float, default=5.0)
    ap.add_argument("--ent", type=float, default=0.0)
    ap.add_argument("--rev", type=float)
    ap.add_argument("--imp", type=float)
    ap.add_argument("--exit", type=float)
    ap.add_argument("--times", default="0.05,0.3,0.55,0.8,0.97")
    ap.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    mod, fn = a.target.split(":")
    comp = getattr(importlib.import_module(mod), fn)
    beats = [("entrance", a.ent * a.dur)] + [(g, f * a.dur) for g, f in
                                              (("reveal", a.rev), ("impact", a.imp), ("exit", a.exit)) if f is not None]
    import cairosvg
    from PIL import Image, ImageDraw
    canvas = canvas_for(a.aspect)
    tw, th = (360, 640) if canvas.h >= 1920 else (640, 360)  # tile size keeps the canvas aspect
    tiles = []
    for f in [float(x) for x in a.times.split(",")]:
        t = f * a.dur
        ctx = Ctx(t=t, t0=0.0, t1=a.dur, frame=int(t * 30), props=json.loads(a.props), beats=Beats(beats, 0.0),
                  palette=PALETTE, tokens=load_tokens(), canvas=canvas, obj_id="obj", extra={})
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas.w}" height="{canvas.h}" '
               f'viewBox="0 0 {canvas.w} {canvas.h}">{_bg(canvas.w, canvas.h)}{comp(ctx)}</svg>')
        im = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=tw, output_height=th)))
        ImageDraw.Draw(im).text((8, 8), f"t={f:.2f} ({t:.2f}s)", fill="white")
        tiles.append(im.convert("RGB"))
    sheet = Image.new("RGB", (tw * len(tiles), th))
    for i, im in enumerate(tiles):
        sheet.paste(im, (i * tw, 0))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
