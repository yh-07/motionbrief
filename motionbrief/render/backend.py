# SPDX-License-Identifier: Apache-2.0
"""Renderer abstraction + degradation planner.

Degradation ladder (per visual object):
    blender -> three -> remotion -> svg (2.5D)  -> canvas -> static
The renderer NEVER imports `motionbrief.content` (one-way dependency rule).
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from motionbrief import __version__
from motionbrief.ir.models import Scene, SceneIR, VisualObject
from motionbrief.paths import load_registry, load_tokens, source_hash
from motionbrief.render.probe import probe

LADDER = ["blender", "three", "remotion", "svg", "canvas"]


class BackendUnavailable(RuntimeError):
    """DEGRADABLE: the requested backend cannot run on this host."""


class RenderFailure(RuntimeError):
    """RETRYABLE (I/O, encoder crash)."""


@dataclass
class RenderPlan:
    scene_id: str
    choices: dict[str, str] = field(default_factory=dict)          # obj id -> renderer
    degradations: list[dict] = field(default_factory=list)


class RendererBackend(ABC):
    name: str = "abstract"

    def probe(self) -> dict:
        p = probe()
        return {"webgl": p["webgl"], "gpu": bool(p["hwEncoders"]), "available": self.available()}

    @abstractmethod
    def available(self) -> bool: ...

    def can_render(self, obj: VisualObject) -> bool:
        reg = load_registry()["components"].get(obj.component)
        return bool(reg) and self.name in reg["renderers"] and self.available()

    @abstractmethod
    def render_frames(self, ir: SceneIR, scene: Scene, out_dir: Path, **kw) -> dict: ...


def _open_layer_b(ir: SceneIR, scene: Scene, plan: RenderPlan) -> dict:
    """One GPU toon page per object planned on `three` (body swapped into the SVG frame)."""
    objs = [vo for vo in scene.visualObjects if plan.choices.get(vo.id) == "three"]
    if not objs:
        return {}
    from motionbrief.render.three.toon import ToonRenderer
    pal = ir.palette.model_dump()
    out = {}
    for vo in objs:
        ms = vo.materialStyle
        spec = {"ramp": ms.gradientRamp if ms and ms.gradientRamp else ["#EFE6FF", pal["primary"][0], "#2A2350"],
                "bands": ms.bands if ms and ms.bands else 3,
                "outlineWidth": vo.outline.width if vo.outline else 0.03,
                "outlineColor": vo.outline.color if vo.outline else "#1A1452",
                "traceColor": pal["primary"][1] if len(pal["primary"]) > 1 else pal["primary"][0]}
        out[vo.id] = ToonRenderer(spec)
    return out


def segment_name(scene_id: str, k: int, n: int) -> str:
    return f"{scene_id}.seg{k:03d}of{n:03d}.mp4"


class SvgBackend(RendererBackend):
    """Layer A reference backend: SVG per frame -> cairo raster -> ffmpeg (no WebGL needed)."""
    name = "svg"

    def available(self) -> bool:
        return probe()["svg"] and probe()["ffmpeg"]

    def can_render(self, obj: VisualObject) -> bool:
        reg = load_registry()["components"].get(obj.component)
        if not reg or not self.available():
            return False
        # svg can always draw the 2D fallback of any registered component
        return reg["status"] == "implemented" or reg["fallback2D"] in load_registry()["components"]

    def render_frames(self, ir: SceneIR, scene: Scene, out_dir: Path, *, plan: RenderPlan,
                      subtitles: list[tuple[float, float, str]], png_every: int = 15,
                      max_frames: Optional[int] = None, segment: Optional[tuple[int, int]] = None,
                      **kw) -> dict:
        """Render the scene (or, with segment=(k, n), only its k-th of n equal frame slices) to an mp4.
        Every frame is a pure function of (IR, t), so slices concatenated in order equal the whole scene."""
        from cairosvg.parser import Tree
        from cairosvg.surface import PNGSurface
        from PIL import Image

        from motionbrief.render.ffmpeg import raw_encoder_proc
        from motionbrief.render.svg_canvas.scene import frame_svg

        fps = ir.video.fps
        f0 = round(scene.tStart * fps)
        f1 = round(scene.tEnd * fps)
        if max_frames:
            f1 = min(f1, f0 + max_frames)
        a, b = f0, f1
        if segment:
            k, n = segment
            a, b = f0 + (f1 - f0) * k // n, f0 + (f1 - f0) * (k + 1) // n
        out_dir.mkdir(parents=True, exist_ok=True)
        png_dir = out_dir / scene.id
        png_dir.mkdir(exist_ok=True)
        mp4 = out_dir / (segment_name(scene.id, *segment) if segment else f"{scene.id}.mp4")
        from motionbrief.render.svg_canvas.components import LAYER_B_STATE
        toons = _open_layer_b(ir, scene, plan)
        layer_b = (lambda vo, ctx: toons[vo.id].frame_uri(LAYER_B_STATE[vo.component](ctx))) if toons else None
        proc = raw_encoder_proc(mp4, fps, ir.video.w, ir.video.h)
        written, pngs = 0, []
        try:
            for f in range(a, b):
                t = f / fps
                svg = frame_svg(ir, scene, t, f, plan.choices, subtitles, layer_b)
                surf = PNGSurface(Tree(bytestring=svg.encode("utf-8")), None, 96)
                surf.cairo.flush()
                buf = bytes(surf.cairo.get_data())
                if len(buf) != ir.video.w * ir.video.h * 4:
                    raise RenderFailure(f"frame {f}: bad buffer size {len(buf)}")
                proc.stdin.write(buf)
                written += 1
                if png_every and (f - f0) % png_every == 0:
                    p = png_dir / f"f{f:05d}.png"
                    Image.frombuffer("RGBA", (ir.video.w, ir.video.h), buf, "raw", "BGRA", 0, 1).convert("RGB").save(p)
                    pngs.append(str(p))
        except BrokenPipeError as e:  # encoder died
            raise RenderFailure(str(e)) from e
        finally:
            for tr in toons.values():
                tr.close()
            if proc.stdin:
                proc.stdin.close()
            rc = proc.wait()
        if rc != 0:
            raise RenderFailure(f"ffmpeg exited {rc}")
        out = {"video": str(mp4), "frames": written, "expectedFrames": b - a, "pngs": pngs}
        if toons:
            out["gpu"] = next(iter(toons.values())).gpu
        return out


class _SkeletonBackend(RendererBackend):
    def render_frames(self, *a, **kw) -> dict:
        raise BackendUnavailable(f"{self.name} backend not available on this host")


class RemotionBackend(_SkeletonBackend):
    name = "remotion"

    def available(self) -> bool:
        return probe()["remotion"]


class ThreeBackend(_SkeletonBackend):
    name = "three"

    def available(self) -> bool:
        # local WebGL, or a remote render host declared WebGL-capable (scenes then run there only)
        return (probe()["three"] and probe()["webgl"]) or probe()["webglRemote"]


class BlenderBackend(_SkeletonBackend):
    name = "blender"

    def available(self) -> bool:
        return probe()["blender"]


BACKENDS: dict[str, RendererBackend] = {
    b.name: b for b in (SvgBackend(), RemotionBackend(), ThreeBackend(), BlenderBackend())
}
BACKENDS["canvas"] = BACKENDS["svg"]


def plan_scene(scene: Scene) -> RenderPlan:
    plan = RenderPlan(scene.id)
    for vo in scene.visualObjects:
        want = vo.renderer
        start = LADDER.index(want) if want in LADDER else LADDER.index("svg")
        chosen = None
        for r in LADDER[start:]:
            if BACKENDS[r].can_render(vo):
                chosen = r
                break
            if r != want and r in ("remotion",):
                continue
        if chosen is None:
            raise BackendUnavailable(f"no backend can render {vo.id}:{vo.component}")
        if chosen != want:
            if not scene.fallback2D:
                raise BackendUnavailable(f"{vo.id}: {want} unavailable and fallback2D=false")
            plan.degradations.append({"object": vo.id, "component": vo.component, "from": want, "to": chosen,
                                      "reason": f"{want} unavailable (webgl={probe()['webgl']})"})
        plan.choices[vo.id] = chosen
    return plan


def scene_hash(ir: SceneIR, scene: Scene, subtitles: list, plan: RenderPlan) -> str:
    h = hashlib.sha256()
    for part in (scene.model_dump(by_alias=True), ir.palette.model_dump(), ir.video.model_dump(),
                 load_tokens(), load_registry(), subtitles, plan.choices, __version__,
                 # only code that changes pixels: transport (remote.py, remote_worker.py) and probing don't
                 source_hash("render/svg_canvas", "render/three", "render/backend.py", "render/ffmpeg.py", "ir")):
        h.update(json.dumps(part, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:16]
