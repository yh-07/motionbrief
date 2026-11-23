# SPDX-License-Identifier: Apache-2.0
"""G2 — multimodal review (Phase 1 = stub wiring; real prompts land in Phase 2).

Samples key frames, sends them to router.chat("vision_review", exclude_family=<author family>)
so the reviewer is always a different model family than the one that wrote the IR (four-eye).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from motionbrief.ir.models import SceneIR
from motionbrief.llm.router import CapabilityRouter
from motionbrief.quality.deterministic import GateReport

RUBRIC = ["composition", "typography", "visual_hierarchy", "motion_continuity", "pacing", "fact_consistency",
          "small_screen_legibility"]
TRANSITION_RUBRIC = ["starts_on_something", "lands_cleanly", "no_empty_or_black_frame", "no_collision_mid_move",
                     "matches_declared_type"]

GRID = 6  # visual-anchor prompt: 6x6 labelled grid (Code2Video critic, REVIEW R-21)


def anchor_overlay(png: bytes) -> bytes:
    """Overlay a labelled GRIDxGRID anchor grid so the reviewer can name precise cells (e.g. C4)."""
    import io

    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(png)).convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    for i in range(1, GRID):
        d.line([(w * i / GRID, 0), (w * i / GRID, h)], fill=(255, 0, 255), width=2)
        d.line([(0, h * i / GRID), (w, h * i / GRID)], fill=(255, 0, 255), width=2)
    for r in range(GRID):
        for c in range(GRID):
            d.text((w * c / GRID + 6, h * r / GRID + 4), f"{chr(65 + c)}{r + 1}", fill=(255, 0, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


PROMPT = """You are a strict reviewer for 9:16 technical explainer shorts (Cartoon Tech v2).
Frames carry a magenta {grid}x{grid} anchor grid (columns A-F, rows 1-6); cite cells for every layout defect.
The LAST image is the first frame at feed-thumbnail size (no grid): judge small_screen_legibility on it.
Score each criterion 1-5 and list concrete defects with timestamps: {rubric}.
Narration and citations for this scene: {facts}
Return JSON: {{"scores": {{...}}, "defects": [{{"t": sec, "cell": "C4", "criterion": "...", "issue": "...", "fix": "..."}}]}}"""


TRANSITION_PROMPT = """You review the cuts of a 9:16 technical explainer short. Each image is one transition:
{n} frames at 10 fps spanning 0.3 s before to 0.3 s after the cut, left to right, cut from the final encode.
Transitions in order: {items}
Score each transition 1-5 on: {rubric}. A transition should start on something and land cleanly.
Return JSON: {{"transitions": [{{"scene": "s02", "scores": {{...}}, "issue": "", "fix": ""}}]}}"""


def _json(text: str) -> dict:
    """Reviewer JSON, tolerating code fences / prose around it."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        return json.loads(text[a:b + 1]) if 0 <= a < b else {}


def thumbnail(png: bytes, width: int = 360) -> bytes:
    """The frame as it reads in a feed (≈ a third of a phone screen wide)."""
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def transition_strip(video: Path, t: float, frames: int = 6, width: int = 216) -> bytes:
    """frames x 1 strip around a cut at t, taken from the *encoded* video (also catches encode defects)."""
    import subprocess
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t - 0.3):.3f}", "-t", "0.6", "-i", str(video),
                        "-vf", f"fps=10,scale={width}:-1,tile={frames}x1", "-frames:v", "1", "-f", "image2pipe",
                        "-vcodec", "png", "-"], capture_output=True, check=True)
    return r.stdout


def review_transitions(ir: SceneIR, bundle: Path, author_family: str, router: Optional[CapabilityRouter] = None,
                       min_score: int = 4, batch: int = 7) -> GateReport:
    router = router or CapabilityRouter.from_file()
    rep = GateReport("G2", "transitions")
    final = bundle / "final.mp4"
    if not final.exists():
        rep.add("transitions", ["missing final.mp4"])
        return rep
    cuts = ir.scenes[1:]
    for i in range(0, len(cuts), batch):
        part = cuts[i:i + batch]
        items = ", ".join(f"{s.id} ({s.transitionIn.type} at {s.tStart:.2f}s)" for s in part)
        res = router.chat("vision_review", [{"role": "user", "content": TRANSITION_PROMPT.format(
            n=6, items=items, rubric=", ".join(TRANSITION_RUBRIC))}],
            images=[transition_strip(final, s.tStart) for s in part], exclude_family=author_family)
        data = _json(res.text)
        if data.get("stub"):
            rep.add(f"transitions:stub_review({res.family})", [])
            continue
        problems = [] if data else ["reviewer returned non-JSON"]
        for tr in data.get("transitions", []):
            low = {k: v for k, v in (tr.get("scores") or {}).items() if isinstance(v, (int, float)) and v < min_score}
            if low:
                problems.append(f"{tr.get('scene')}: {low} {tr.get('issue', '')} -> {tr.get('fix', '')}")
        rep.add(f"transitions[{part[0].id}..{part[-1].id}]({res.family})", problems)
    return rep


def review(ir: SceneIR, bundle: Path, author_family: str, router: Optional[CapabilityRouter] = None,
           scene_ids: Optional[list[str]] = None, min_score: int = 4) -> GateReport:
    router = router or CapabilityRouter.from_file()
    rep = GateReport("G2", "multimodal" if not scene_ids else f"multimodal:{','.join(scene_ids)}")
    for s in ir.scenes:
        if scene_ids and s.id not in scene_ids:
            continue
        pngs = sorted((bundle / "frames" / s.id).glob("f*.png"))[:4]
        facts = json.dumps({"narration": s.narration, "citations": s.citations}, ensure_ascii=False)
        res = router.chat("vision_review",
                          [{"role": "user", "content": PROMPT.format(grid=GRID, rubric=", ".join(RUBRIC), facts=facts)}],
                          images=[anchor_overlay(p.read_bytes()) for p in pngs]
                          + ([thumbnail(pngs[0].read_bytes())] if pngs else []), exclude_family=author_family)
        problems: list[str] = []
        data = _json(res.text)
        if not data:
            problems.append(f"{s.id}: reviewer returned non-JSON")
        if data.get("stub"):
            rep.add(f"{s.id}:stub_review({res.family})", [])  # wiring verified, no real judgement
            continue
        for k, v in (data.get("scores") or {}).items():
            if isinstance(v, (int, float)) and v < min_score:
                problems.append(f"{s.id}: {k}={v}")
        problems += [f"{s.id}@{d.get('t')}[{d.get('cell', '?')}]: {d.get('criterion')}: {d.get('issue')}"
                     for d in data.get("defects", [])]
        rep.add(f"{s.id}:review({res.family})", problems)
    return rep
