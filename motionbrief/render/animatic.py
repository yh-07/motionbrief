# SPDX-License-Identifier: Apache-2.0
"""Animatic / storyboard sheet (REVIEW R-20).

Studio practice: lock script -> board/animatic -> only then animate, because a change on the
board costs minutes and a change after animation costs a re-render. This renders one low-res
keyframe per motion beat (plus scene start), labelled with time, role, beat and narration,
into a single contact sheet. It takes seconds instead of the full render's minutes and is the
artifact for the `animatic_lock` approval (G3) and for G2 layout review.
"""
from __future__ import annotations

from pathlib import Path

from motionbrief.ir.models import SceneIR
from motionbrief.render.backend import plan_scene
from motionbrief.render.svg_canvas.scene import frame_svg

TW, TH = 270, 480


def keyframes(ir: SceneIR) -> list[tuple[str, float, str]]:
    out = []
    for s in ir.scenes:
        times = {round(s.tStart + 0.5, 3): "start"}
        for m in s.motionGrammar:
            if m.grammar in ("reveal", "impact"):
                t = min(m.at + 0.45, s.tEnd - 1 / ir.video.fps)
                times.setdefault(round(t, 3), f"{m.grammar}:{m.target}")
        out += [(s.id, t, lab) for t, lab in sorted(times.items())]
    return out


def render_sheet(ir: SceneIR, out: Path, cols: int = 6) -> Path:
    import cairosvg
    from PIL import Image, ImageDraw, ImageFont

    out.parent.mkdir(parents=True, exist_ok=True)
    kfs = keyframes(ir)
    font = small = None
    from motionbrief.render.svg_canvas.prims import font_file
    try:
        fp = font_file()
        font, small = ImageFont.truetype(fp, 15), ImageFont.truetype(fp, 13)
    except (OSError, FileNotFoundError):
        font = small = ImageFont.load_default()
    cap_h = 70
    th = TW * ir.video.h // ir.video.w  # cell height follows the canvas: 480 for 9:16, 151 for 16:9
    rows = (len(kfs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * TW, rows * (th + cap_h)), "#F4F2FA")
    draw = ImageDraw.Draw(sheet)
    plans = {s.id: plan_scene(s) for s in ir.scenes}
    tmp = out.parent / "_kf.png"
    for i, (sid, t, label) in enumerate(kfs):
        s = ir.scene(sid)
        svg = frame_svg(ir, s, t, int(t * ir.video.fps), plans[sid].choices, [])
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(tmp), output_width=TW, output_height=th)
        x, y = (i % cols) * TW, (i // cols) * (th + cap_h)
        sheet.paste(Image.open(tmp).convert("RGB"), (x, y))
        draw.text((x + 6, y + th + 4), f"{sid} {t:5.2f}s {s.role} | {label}", fill="#1A1438", font=font)
        narr = s.narration[:20] + ("…" if len(s.narration) > 20 else "")
        draw.text((x + 6, y + th + 26), narr or "(no narration)", fill="#5A5470", font=small)
        if s.citations:
            draw.text((x + 6, y + th + 46), f"{len(s.citations)} source(s)", fill="#2EC4B6", font=small)
    tmp.unlink(missing_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
