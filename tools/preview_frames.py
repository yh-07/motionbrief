# SPDX-License-Identifier: Apache-2.0
"""Review real frames (not animatic thumbnails) of a finished or in-progress video.

Renders chosen scenes at a fraction of their duration with the SVG canvas (same path as the
animatic/final render) and tiles them two per row on one sheet of at most 800 px wide.

Usage:
    .venv/Scripts/python.exe tools/preview_frames.py ep01_cinematic_v2 --n 4
    .venv/Scripts/python.exe tools/preview_frames.py ep01_cinematic_v2 --shots s15,s22 --at 0.5
    .venv/Scripts/python.exe tools/preview_frames.py ep01_cinematic_v2 --out work/_preview/check.png
"""
import argparse
import io
import json
import sys
from pathlib import Path

import motionbrief.paths  # noqa: F401  (loads .env and the cairo DLL path)
import cairosvg
from PIL import Image, ImageDraw, ImageFont

from motionbrief.ir.models import load
from motionbrief.render.svg_canvas.scene import frame_svg

ROOT = Path(__file__).resolve().parents[1]


def pick_scenes(ir, shots: str | None, n: int) -> list:
    if shots:
        wanted = [s.strip() for s in shots.split(",") if s.strip()]
        by_id = {s.id: s for s in ir.scenes}
        missing = [s for s in wanted if s not in by_id]
        if missing:
            sys.exit(f"unknown scene id(s): {', '.join(missing)}")
        return [by_id[s] for s in wanted]
    scenes = list(ir.scenes)
    if n <= 1 or len(scenes) <= 1:
        return scenes[:1]
    idx = sorted({round(i * (len(scenes) - 1) / (n - 1)) for i in range(n)})
    return [scenes[i] for i in idx]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_id")
    ap.add_argument("--shots", help="comma list of scene ids, e.g. s02,s05")
    ap.add_argument("--at", type=float, default=0.8, help="fraction of each scene's duration (default 0.8)")
    ap.add_argument("--n", type=int, default=6, help="scenes to spread evenly when --shots is omitted (default 6)")
    ap.add_argument("--out", help="output PNG (default work/_preview/<video_id>_frames.png)")
    args = ap.parse_args()

    status = json.loads((ROOT / "outbox" / args.video_id / "status.json").read_text(encoding="utf-8"))
    ir_path = ROOT / status["ir"].replace("\\", "/")
    ir = load(ir_path)
    scenes = pick_scenes(ir, args.shots, args.n)

    tw, th = ir.video.w // 2, ir.video.h // 2  # 960x540 for 16:9, 540x960 for 9:16
    try:  # Pillow >= 10.1 default font takes a size; labels are drawn before the 800 px shrink
        font = ImageFont.load_default(size=26)
    except TypeError:
        font = ImageFont.load_default()
    tiles = []
    for sc in scenes:
        t = sc.tStart + args.at * (sc.tEnd - sc.tStart)
        cue = sc.narration[:18] if sc.narration else ""
        svg = frame_svg(ir, sc, t, int(t * ir.video.fps), {}, [(sc.tStart, sc.tEnd, cue)])
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=tw, output_height=th)
        tile = Image.open(io.BytesIO(png)).convert("RGB")
        label = sc.id + "  " + ", ".join(vo.component for vo in sc.visualObjects)
        draw = ImageDraw.Draw(tile)
        box = draw.textbbox((8, 8), label, font=font)
        draw.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill=(0, 0, 0))
        draw.text((8, 8), label, fill=(255, 255, 255), font=font)
        tiles.append(tile)

    rows = (len(tiles) + 1) // 2
    sheet = Image.new("RGB", (tw * 2, th * rows), (40, 40, 40))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 2) * tw, (i // 2) * th))
    sheet.thumbnail((800, 4000))

    out = Path(args.out) if args.out else ROOT / "work" / "_preview" / f"{args.video_id}_frames.png"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(out)
    print(f"{len(tiles)} frames, sheet {sheet.size[0]}x{sheet.size[1]}")


if __name__ == "__main__":
    main()
