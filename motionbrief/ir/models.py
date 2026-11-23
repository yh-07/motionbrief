# SPDX-License-Identifier: Apache-2.0
"""Scene IR v1.2 — pydantic models, semantic validation and migration.

Single source of truth: these models. `schemas/scene_ir.schema.json` is
*generated* from them (`motionbrief export-schema`) and a test asserts the
committed file is up to date.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from motionbrief.paths import REPO_ROOT, load_registry, load_tokens
from motionbrief.render.svg_canvas.canvas import canvas_for

IR_VERSION = "1.2.0"
SUPPORTED_INPUT_VERSIONS = {"1.1.0", "1.2.0"}

DurationTier = Literal["micro", "core", "deep", "extended", "longform"]
def tier_ranges() -> dict[str, tuple[float, float]]:
    return {k: (float(a), float(b)) for k, (a, b) in load_tokens()["duration"]["tiers"].items()}


def hard_range(landscape: bool = False) -> tuple[float, float]:
    d = load_tokens()["duration"]
    hi = d["hardMaxSecLandscape"] if landscape else d["hardMaxSec"]
    return float(d["hardMinSec"]), float(hi)

Renderer = Literal["remotion", "three", "svg", "canvas", "blender"]
CameraMove = Literal["push_in", "pull_out", "pan", "static", "orbit"]
Grammar = Literal["entrance", "reveal", "impact", "exit"]
Transition = Literal["cut", "zoom_through", "mask_reveal", "whip", "match_cut", "morph_fuse"]
AssetStyle = Literal["flat_vector", "toon_2_5d", "toon_3d", "blender_cel"]
RenderQuality = Literal["fast", "standard", "hero"]
Projection = Literal["orthographic", "perspective"]
SceneRole = Literal["hook", "context", "reveal", "mechanism", "payoff", "callback"]
Sfx = Literal["bass_hit", "whoosh", "ui_tick", "riser", "shutter", "digital_blip"]
Anchor = Literal["top", "center", "lower"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Palette(_M):
    primary: list[str] = Field(min_length=1, max_length=2)
    accent: str


class Video(_M):
    id: str = Field(pattern=r"^[a-z0-9_\-]+$")
    title: str
    aspect: Literal["9:16", "16:9"] = "9:16"
    w: int = 1080
    h: int = 1920
    fps: Literal[30] = 30
    visualIP: Literal["cartoon-tech-v1", "cartoon-tech-v2"] = "cartoon-tech-v2"
    durationTier: DurationTier = "core"
    productionLevel: Literal["hero", "standard", "fast"] = "standard"
    chapterCards: Optional[bool] = None  # None = on for 16:9, off for 9:16
    visualStyle: Literal["neon", "cartoon", "ink", "graphite"] = "neon"  # landscape look, see tokens.visualStyles

    @model_validator(mode="after")
    def _size_matches_aspect(self):
        size = canvas_for(self.aspect)
        if (self.w, self.h) != (size.w, size.h):
            raise ValueError(f"{self.aspect} needs {size.w}x{size.h}, got {self.w}x{self.h}")
        return self


class Camera(_M):
    move: CameraMove = "static"
    from_: float = Field(1.0, alias="from", ge=0.5, le=2.0)
    to: float = Field(1.0, ge=0.5, le=2.0)
    easing: str = "easeOutExpo"


class Typography(_M):
    text: str = Field(min_length=1, max_length=24)
    style: str = "headline"
    safeArea: Anchor = "center"
    at: Optional[float] = None      # absolute seconds; default = scene start
    until: Optional[float] = None   # absolute seconds; default = scene end


class MaterialStyle(_M):
    type: Literal["toon", "flat"] = "toon"
    bands: int = Field(3)
    gradientRamp: list[str] = Field(default_factory=list)


class Outline(_M):
    method: Literal["inverted_hull", "depth_normal", "svg_stroke"] = "svg_stroke"
    width: float = Field(0.05, gt=0)
    color: str = "#000"


class VisualObject(_M):
    id: str
    component: str
    renderer: Renderer = "svg"
    props: dict[str, Any] = Field(default_factory=dict)
    depth: int = Field(1, ge=0, le=2)  # 0=back, 1=mid, 2=front (depthLayers=3)
    materialStyle: Optional[MaterialStyle] = None
    outline: Optional[Outline] = None
    lightingPreset: Optional[Literal["single_key_soft", "single_key_hard", "flat"]] = None


class MotionBeat(_M):
    target: str
    grammar: Grammar
    at: float  # absolute seconds


class SoundCue(_M):
    sfx: Sfx
    at: float  # absolute seconds
    gainDb: float = Field(0.0, ge=-24, le=6)


class TransitionIn(_M):
    type: Transition = "cut"


class RendererHints(_M):
    webglFallback: Literal["canvas2d", "svg", "static"] = "svg"
    frameCritical: bool = False


class Scene(_M):
    id: str = Field(pattern=r"^s\d{2,3}$")
    tStart: float = Field(ge=0)
    tEnd: float = Field(gt=0)
    role: SceneRole
    durationTier: Optional[DurationTier] = None  # legacy (v1.1); video-level is authoritative
    chapter: Optional[str] = None  # chapter title; shown as a card for the first 2.5 s when cards are on
    note: Optional[str] = None  # corner footnote (disclaimer, <= 40 chars), drawn on every frame of the scene
    narration: str = ""
    isFactual: bool = True
    citations: list[str] = Field(default_factory=list)
    styleProfile: Literal["cartoon-tech-v1", "cartoon-tech-v2"] = "cartoon-tech-v2"
    assetStyle: AssetStyle = "flat_vector"
    renderQuality: RenderQuality = "standard"
    cameraProjection: Projection = "orthographic"
    depthLayers: int = Field(3, ge=1, le=3)
    camera: Camera = Field(default_factory=Camera)
    typography: list[Typography] = Field(default_factory=list)
    visualObjects: list[VisualObject] = Field(min_length=1)
    motionGrammar: list[MotionBeat] = Field(default_factory=list)
    soundCues: list[SoundCue] = Field(default_factory=list)
    transitionIn: TransitionIn = Field(default_factory=TransitionIn)
    fallback2D: bool = True
    rendererHints: RendererHints = Field(default_factory=RendererHints)

    @field_validator("citations")
    @classmethod
    def _urls(cls, v: list[str]) -> list[str]:
        for c in v:
            if not c.startswith("https://"):
                raise ValueError(f"citation must be a public https URL: {c!r}")
        return v

    @property
    def duration(self) -> float:
        return self.tEnd - self.tStart


class SceneIR(_M):
    irVersion: Literal["1.2.0"]
    video: Video
    palette: Palette
    scenes: list[Scene] = Field(min_length=1)

    @property
    def duration(self) -> float:
        return self.scenes[-1].tEnd

    def scene(self, sid: str) -> Scene:
        for s in self.scenes:
            if s.id == sid:
                return s
        raise KeyError(sid)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
class IRInvalid(ValueError):
    """Scene IR failed validation -> local agent must ESCALATE to the strong model."""


@dataclass
class Issue:
    code: str
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.code} @ {self.path}: {self.message}"


def migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade an IR dict to the current irVersion. Pure function."""
    ir = copy.deepcopy(raw)
    ver = ir.get("irVersion")
    if ver not in SUPPORTED_INPUT_VERSIONS:
        raise ValueError(f"unsupported irVersion {ver!r}; supported: {sorted(SUPPORTED_INPUT_VERSIONS)}")
    if ver == "1.1.0":
        # 1.1 -> 1.2: palette becomes required; durationTier moves to video level;
        # isFactual is explicit; title required.
        tokens = load_tokens()
        ir.setdefault("palette", {
            "primary": tokens["palette"]["default"]["primary"],
            "accent": tokens["palette"]["default"]["accent"],
        })
        video = ir.setdefault("video", {})
        tiers = [s.get("durationTier") for s in ir.get("scenes", []) if s.get("durationTier")]
        video.setdefault("durationTier", tiers[0] if tiers else "core")
        video.setdefault("title", video.get("id", "untitled"))
        for s in ir.get("scenes", []):
            s.setdefault("isFactual", bool(s.get("narration")))
        ir["irVersion"] = "1.2.0"
    return ir


def parse(raw: dict[str, Any]) -> SceneIR:
    return SceneIR.model_validate(migrate(raw))


def _structural_issues(err: ValidationError) -> list[Issue]:
    out = []
    for e in err.errors():
        path = ".".join(str(p) for p in e["loc"])
        out.append(Issue("SCHEMA", path, e["msg"]))
    return out


def semantic_issues(ir: SceneIR) -> list[Issue]:
    tokens = load_tokens()
    registry = load_registry()["components"]
    issues: list[Issue] = []
    add = lambda *a, **k: issues.append(Issue(*a, **k))  # noqa: E731

    # duration / tier
    total = ir.duration
    # Duration is NOT hard-locked (REVIEW R-18): only absurd lengths are errors; tiers are advisory.
    lo, hi = hard_range(landscape=ir.video.aspect == "16:9")
    if not (lo <= total <= hi):
        add("DURATION_RANGE", "scenes", f"total {total:.1f}s outside hard bounds {lo}-{hi}s")
    tlo, thi = tier_ranges()[ir.video.durationTier]
    if not (tlo <= total <= thi):
        add("DURATION_TIER", "video.durationTier",
            f"total {total:.1f}s outside advisory {ir.video.durationTier} range {tlo}-{thi}s", severity="warning")

    # timeline continuity
    prev_end = 0.0
    ids = set()
    for i, s in enumerate(ir.scenes):
        p = f"scenes[{i}]({s.id})"
        if s.id in ids:
            add("DUP_SCENE", p, "duplicate scene id")
        ids.add(s.id)
        if abs(s.tStart - prev_end) > 1e-6:
            add("TIMELINE_GAP", p, f"tStart {s.tStart} != previous tEnd {prev_end}")
        if s.tEnd <= s.tStart:
            add("TIMELINE_ORDER", p, "tEnd must be > tStart")
        prev_end = s.tEnd
        if s.durationTier and s.durationTier != ir.video.durationTier:
            add("TIER_MISMATCH", p, "scene durationTier differs from video tier", severity="warning")

        # facts need citations
        if s.isFactual and s.narration and not s.citations:
            add("CITATION_MISSING", p, "factual scene has narration but no public citation")

        # registry
        obj_ids = set()
        for j, vo in enumerate(s.visualObjects):
            vp = f"{p}.visualObjects[{j}]"
            obj_ids.add(vo.id)
            reg = registry.get(vo.component)
            if reg is None:
                add("COMPONENT_UNKNOWN", vp, f"component {vo.component!r} not in registry")
                continue
            if vo.renderer not in reg["renderers"]:
                add("RENDERER_UNSUPPORTED", vp, f"{vo.component} does not support renderer {vo.renderer}")
            if vo.materialStyle:
                b = vo.materialStyle.bands
                if not (tokens["toon"]["bandsMin"] <= b <= tokens["toon"]["bandsMax"]):
                    add("TOON_BANDS", vp, f"bands {b} outside [2,5]")
            if vo.renderer in ("three", "blender") and not s.fallback2D:
                add("NO_FALLBACK", vp, "3D renderer requires fallback2D=true (graceful degradation)")

        # blender only for hero
        if s.assetStyle == "blender_cel" and s.renderQuality != "hero":
            add("BLENDER_NON_HERO", p, "assetStyle=blender_cel requires renderQuality=hero")
        if any(vo.renderer == "blender" for vo in s.visualObjects) and s.renderQuality != "hero":
            add("BLENDER_NON_HERO", p, "blender renderer requires renderQuality=hero")

        # beats/cues/typography inside the scene, targets exist
        for k, mb in enumerate(s.motionGrammar):
            if not (s.tStart <= mb.at <= s.tEnd):
                add("BEAT_OUT_OF_SCENE", f"{p}.motionGrammar[{k}]", f"at={mb.at} outside scene")
            if mb.target not in obj_ids and mb.target not in {t.text for t in s.typography}:
                add("BEAT_TARGET", f"{p}.motionGrammar[{k}]", f"unknown target {mb.target!r}")
        for k, sc in enumerate(s.soundCues):
            if not (s.tStart <= sc.at <= s.tEnd):
                add("CUE_OUT_OF_SCENE", f"{p}.soundCues[{k}]", f"at={sc.at} outside scene")
        for k, ty in enumerate(s.typography):
            if ty.style not in tokens["typography"]["styles"]:
                add("TYPO_STYLE", f"{p}.typography[{k}]", f"style {ty.style!r} not in tokens")

    # palette
    if len(ir.palette.primary) > tokens["palette"]["maxPrimary"]:
        add("PALETTE", "palette.primary", "more than 2 primary colours")
    return issues


def validate(raw: dict[str, Any]) -> tuple[Optional[SceneIR], list[Issue]]:
    try:
        ir = parse(raw)
    except ValidationError as e:
        return None, _structural_issues(e)
    except ValueError as e:
        return None, [Issue("VERSION", "irVersion", str(e))]
    return ir, semantic_issues(ir)


def load(path: str | Path) -> SceneIR:
    ir, issues = validate(json.loads(Path(path).read_text(encoding="utf-8")))
    errs = [i for i in issues if i.severity == "error"]
    if ir is None or errs:
        raise IRInvalid("invalid Scene IR:\n" + "\n".join(map(str, issues)))
    return ir


def export_json_schema() -> dict[str, Any]:
    schema = SceneIR.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://motionbrief.invalid/schemas/scene_ir.schema.json"
    schema["title"] = f"MotionBrief Scene IR v{IR_VERSION}"
    return schema


SCHEMA_PATH = REPO_ROOT / "schemas" / "scene_ir.schema.json"
