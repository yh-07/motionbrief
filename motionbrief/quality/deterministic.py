# SPDX-License-Identifier: Apache-2.0
"""G1 — deterministic quality gate (pure code, runs first, no model calls).

Two layers:
  * check_ir(raw_ir)                     — pre-render: schema, registry, style profile, safe area,
                                           cadence, citations, ending, sound/beat alignment
  * check_artifacts(ir, bundle, scope)   — post-render: frame completeness, black frames,
                                           render integrity, subtitles, audio presence/LUFS, sources
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from motionbrief.ir.models import SceneIR, validate
from motionbrief.paths import load_tokens
from motionbrief.render.svg_canvas.components import text_width
from motionbrief.render.svg_canvas.prims import fit_size

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
CTA_ENDING = re.compile(r"(关注|点赞|订阅|三连|下期|评论区|收藏一下|like and subscribe|follow for more)", re.I)
W, H = 1080, 1920


@dataclass
class Check:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)
    advisory: bool = False  # advisory checks report but never block (craft heuristics, not hard rules)


@dataclass
class GateReport:
    gate: str
    scope: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed or c.advisory for c in self.checks)

    def add(self, name: str, problems: list[str], advisory: bool = False) -> None:
        self.checks.append(Check(name, not problems, problems, advisory))

    def to_dict(self) -> dict:
        return {"gate": self.gate, "scope": self.scope, "passed": self.passed,
                "checks": [asdict(c) for c in self.checks]}

    def summary(self) -> str:
        lines = [f"{self.gate} [{self.scope}] {'PASS' if self.passed else 'FAIL'}"]
        for c in self.checks:
            mark = "✔" if c.passed else ("△" if c.advisory else "✘")
            lines.append(f"  {mark} {c.name}" + ("" if c.passed else f": {c.details[:3]}"))
        return "\n".join(lines)


# --------------------------------------------------------------------------- IR level
def _safe_area(ir: SceneIR, tok: dict, scenes) -> list[str]:
    sa = tok["safeArea"]
    x_lo, x_hi = sa["left"], W - sa["right"]
    y_lo, y_hi = sa["top"], H - sa["bottom"]
    probs = []
    for s in scenes:
        for ty in s.typography:
            st = tok["typography"]["styles"][ty.style]
            pad = 0 if ty.style == "impact_reveal" else 36
            # impact text is drawn auto-fitted (prims.fit_size); others at their style size
            size = fit_size(ty.text, st["size"], 900, 2 * min(540 - x_lo, x_hi - 540))                 if ty.style == "impact_reveal" else st["size"]
            w = text_width(ty.text, size) + 2 * pad
            cy = tok["typography"]["anchors"][ty.safeArea]
            box = (540 - w / 2, cy - 0.7 * size, 540 + w / 2, cy + 0.7 * size)
            # horizontal: centred text must fit the narrower side
            half = min(540 - x_lo, x_hi - 540)
            if w / 2 > half or box[1] < y_lo or box[3] > y_hi:
                probs.append(f"{s.id}: '{ty.text}' box {tuple(round(v) for v in box)} outside safe area")
        for vo in s.visualObjects:
            if vo.component == "TitleCard":
                st = tok["typography"]["styles"][vo.props.get("style", "headline")]
                w = text_width(vo.props.get("text", ""), fit_size(vo.props.get("text", ""), st["size"]))
                # 16:9: the drawn card is fitted into the landscape frame, it only has to fit the portrait canvas
                half = 520 if ir.video.aspect == "16:9" else min(540 - x_lo, x_hi - 540)
                if w / 2 > half:
                    probs.append(f"{s.id}: TitleCard text too wide ({w:.0f}px)")
    landscape = ir.video.aspect == "16:9"
    st = tok["typography"]["subtitleLandscape" if landscape else "subtitle"]
    max_w = st["maxCharsPerLine"] * st["size"] + 56
    # 16:9 frame is 1920 wide with subtitle safe area x 180..1740, so the half width is measured from x=960
    half = 960 - 180 if landscape else min(540 - x_lo, x_hi - 540)
    if max_w / 2 > half:
        probs.append(f"subtitle max line width {max_w}px exceeds safe width")
    if st["baselineY"] + st["size"] * 0.75 > y_hi:
        probs.append("subtitle box below bottom safe area")
    return probs


def _style_profile(ir: SceneIR, tok: dict, scenes) -> list[str]:
    probs = []
    allowed = set(tok["transitionsAllowed"])
    hexre = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for c in [*ir.palette.primary, ir.palette.accent]:
        if not hexre.match(c):
            probs.append(f"palette colour {c!r} not #RRGGBB")
    if len(ir.palette.primary) > tok["palette"]["maxPrimary"]:
        probs.append("palette: >2 primary colours")
    for s in scenes:
        if s.styleProfile != ir.video.visualIP:
            probs.append(f"{s.id}: styleProfile {s.styleProfile} != video.visualIP")
        if s.transitionIn.type not in allowed:
            probs.append(f"{s.id}: transition {s.transitionIn.type!r} not allowed in {ir.video.visualIP}")
        for ty in s.typography:
            if EMOJI.search(ty.text):
                probs.append(f"{s.id}: emoji in typography {ty.text!r}")
            if ty.style in tok["forbidden"]["typographyStyles"]:
                probs.append(f"{s.id}: forbidden typography style {ty.style}")
        if s.camera.easing not in ("easeOutExpo", "easeInCubic", "spring", "linear"):
            probs.append(f"{s.id}: easing {s.camera.easing!r} not in motion grammar")
    renderers = {vo.renderer for s in ir.scenes for vo in s.visualObjects}
    if ir.video.productionLevel == "hero" and "three" not in renderers:
        probs.append("hero video must contain at least one Layer B (three) object")
    if ir.video.productionLevel == "fast" and renderers & {"three", "blender"}:
        probs.append("fast video must be pure Layer A")
    return probs


def _continuous_events(scenes) -> set[float]:
    """Scenes holding a continuously moving component (`continuous_motion`) are never a visual gap: they count as
    an event every 2 s across their span."""
    from motionbrief.render.svg_canvas.components import COMPONENTS
    out: set[float] = set()
    for s in scenes:
        if any(getattr(COMPONENTS.get(v.component), "continuous_motion", False) for v in s.visualObjects):
            t = s.tStart
            while t < s.tEnd:
                out.add(round(t, 3))
                t += 2.0
    return out


def _cadence(ir: SceneIR, tok: dict) -> list[str]:
    cad = dict(tok["cadence"])
    if ir.video.aspect == "16:9":  # landscape pace target is 3-5 s per shot; Shorts-style 2-4 s would reject it
        cad["avgCutMinSec"], cad["avgCutMaxSec"] = 1.5, 5.0
    probs = []
    events = sorted({s.tStart for s in ir.scenes}
                    | {m.at for s in ir.scenes for m in s.motionGrammar}
                    | {t.at for s in ir.scenes for t in s.typography if t.at is not None}
                    | _continuous_events(ir.scenes))
    first = ir.scenes[0]
    hook_beats = [m.at for m in first.motionGrammar if m.grammar in ("impact", "reveal")]
    if first.role != "hook":
        probs.append("first scene role must be 'hook'")
    if not hook_beats or min(hook_beats) > cad["hookWithinSec"]:
        probs.append(f"no impact/reveal beat within first {cad['hookWithinSec']}s")
    events.append(ir.duration)
    gaps = [b - a for a, b in zip(events, events[1:])]
    worst = max(gaps) if gaps else ir.duration
    if worst > cad["maxVisualGapSec"]:
        i = gaps.index(worst)
        probs.append(f"visual gap {worst:.1f}s at t={events[i]:.1f}s > {cad['maxVisualGapSec']}s")
    cuts = sorted({s.tStart for s in ir.scenes} | {m.at for s in ir.scenes for m in s.motionGrammar
                                                   if m.grammar == "reveal"})
    avg = ir.duration / max(1, len(cuts))
    if not (cad["avgCutMinSec"] <= avg <= cad["avgCutMaxSec"]):
        probs.append(f"average cut interval {avg:.2f}s outside {cad['avgCutMinSec']}-{cad['avgCutMaxSec']}s")
    return probs


def _sound_alignment(scenes) -> list[str]:
    probs = []
    for s in scenes:
        beats = [m.at for m in s.motionGrammar if m.grammar in ("impact", "reveal")]
        for c in s.soundCues:
            if c.sfx == "bass_hit" and not any(abs(c.at - b) <= 0.05 for b in beats):
                probs.append(f"{s.id}: bass_hit@{c.at} not aligned to an impact/reveal beat")
    return probs


def _citations(scenes) -> list[str]:
    return [f"{s.id}: factual narration without citation" for s in scenes
            if s.isFactual and s.narration and not s.citations]


def _ending(ir: SceneIR) -> list[str]:
    tail = " ".join(s.narration for s in ir.scenes[-2:])
    return [f"CTA-style spoken ending: {m.group(0)!r}" for m in [CTA_ENDING.search(tail)] if m]


def _sound_variety(ir: SceneIR) -> list[str]:
    """Advisory: the *mixed* cues (after sound direction) avoid fatiguing patterns."""
    from motionbrief.audio import sound_design as sd
    sm = sd.summary(sd.resolve(ir), ir.duration, [s.id for s in ir.scenes])
    probs = []
    if sm["noiseWhooshesPerMin"] > 4:
        probs.append(f"{sm['noiseWhooshesPerMin']} noise whooshes/min (> 4): use in-key transition cues")
    if sm["fullImpacts"] > sd.MAX_IMPACTS:
        probs.append(f"{sm['fullImpacts']} full impacts (> {sd.MAX_IMPACTS} structural moments)")
    if sm["repeatedTransitionCues"]:
        probs.append(f"{sm['repeatedTransitionCues']} transition cue(s) repeat the previous one")
    if sm["transitions"] >= 4 and not 0.3 <= sm["silentTransitions"] / sm["transitions"] <= 0.7:
        probs.append(f"{sm['silentTransitions']}/{sm['transitions']} silent cuts (aim for about half)")
    return probs


def _craft_advisories(ir: SceneIR) -> tuple[list[str], list[str]]:
    """Heuristics from mature short-form practice (REVIEW R-23); advisory only."""
    loop = []
    first = {vo.component for vo in ir.scenes[0].visualObjects}
    last = {vo.component for vo in ir.scenes[-1].visualObjects} | {vo.component for vo in ir.scenes[-2].visualObjects}
    if not first & last:
        loop.append("ending shares no visual with the hook: consider a callback/loop ending (replays count on Shorts)")
    if ir.scenes[-1].role != "callback" and ir.scenes[-1].role != "payoff":
        loop.append("last scene should be payoff/callback, not new information")
    dense = []
    for s in ir.scenes:
        n_obj = len([v for v in s.visualObjects if v.depth >= 1])
        if n_obj > 2 or len(s.typography) > 2:
            dense.append(f"{s.id}: {n_obj} foreground objects / {len(s.typography)} labels: one idea per board")
        if s.narration and len(s.narration) / max(s.duration, 0.1) > 6.5:
            dense.append(f"{s.id}: {len(s.narration) / s.duration:.1f} chars/s narration is dense for 9:16")
    return loop, dense


def check_ir(raw: dict[str, Any], scene_ids: Optional[list[str]] = None) -> tuple[Optional[SceneIR], GateReport]:
    rep = GateReport("G1", "ir" if not scene_ids else f"ir:{','.join(scene_ids)}")
    ir, issues = validate(raw)
    rep.add("schema", [str(i) for i in issues if i.code in ("SCHEMA", "VERSION")])
    if ir is None:
        return None, rep
    sem = [i for i in issues if i.code not in ("SCHEMA", "VERSION") and i.severity == "error"]
    rep.add("registry", [str(i) for i in sem if i.code.startswith(("COMPONENT", "RENDERER"))])
    rep.add("ir_semantics", [str(i) for i in sem if not i.code.startswith(("COMPONENT", "RENDERER", "CITATION"))])
    tok = load_tokens()
    scenes = [s for s in ir.scenes if not scene_ids or s.id in scene_ids]
    rep.add("citation", _citations(scenes))
    rep.add("safe_area", _safe_area(ir, tok, scenes))
    rep.add("style_profile", _style_profile(ir, tok, scenes))
    rep.add("sound_beat_alignment", _sound_alignment(scenes))
    if not scene_ids:
        rep.add("cadence_hook", _cadence(ir, tok))
        rep.add("no_cta_ending", _ending(ir))
        loop, dense = _craft_advisories(ir)
        rep.add("loop_callback_ending", loop, advisory=True)
        rep.add("one_idea_per_board", dense, advisory=True)
        rep.add("transition_sound_variety", _sound_variety(ir), advisory=True)
    return ir, rep


# --------------------------------------------------------------------------- artifact level
def _srt_checks(ir: SceneIR, srt: Path, scenes, tok) -> list[str]:
    from motionbrief.audio.mix import parse_srt, reading_units

    if not srt.exists():
        return [f"missing {srt.name}"]
    st = tok["typography"]["subtitleLandscape" if ir.video.aspect == "16:9" else "subtitle"]
    cues = parse_srt(srt)
    probs = []
    t_lo = min(s.tStart for s in scenes)
    t_hi = max(s.tEnd for s in scenes)
    scoped = [c for c in cues if t_lo <= c[0] < t_hi]
    for (a, b, s), nxt in zip(cues, cues[1:] + [None]):
        if b <= a:
            probs.append(f"cue {s!r} non-positive duration")
        if nxt and b > nxt[0] + 1e-3:
            probs.append(f"overlap at {a:.2f}s")
        if b > ir.duration + 1e-3:
            probs.append(f"cue {s!r} beyond video end")
    for a, b, s in scoped:
        if len(s) > st["maxCharsPerLine"]:
            probs.append(f"cue {s!r} longer than {st['maxCharsPerLine']} chars")
        if b - a < st["minDisplaySec"] - 1e-3:
            probs.append(f"cue {s!r} shown {b - a:.2f}s < {st['minDisplaySec']}s")
        if reading_units(s) / max(b - a, 1e-3) > st["maxCharsPerSec"]:
            probs.append(f"cue {s!r} reading speed {reading_units(s) / (b - a):.1f} cps > {st['maxCharsPerSec']}")
    for s in scenes:
        if s.narration and not any(s.tStart <= a < s.tEnd for a, _, _ in cues):
            probs.append(f"{s.id}: narration has no subtitle cue")
    return probs


def _audio_checks(ir: SceneIR, bundle: Path, scenes, full: bool, tok) -> list[str]:
    from motionbrief.audio.mix import SR, read_audio
    from motionbrief.render.ffmpeg import loudness

    probs = []
    master = bundle / "audio" / "narration_mix.wav"
    if not master.exists():
        return ["missing audio/narration_mix.wav"]
    stems = bundle / "audio" / "stems"
    for k in ("voice", "music", "impact", "transition", "fx"):
        if not (stems / f"{k}.wav").exists():
            probs.append(f"missing stem {k}")
    x = read_audio(master)
    for s in scenes:
        seg = x[int(s.tStart * SR): int(s.tEnd * SR)]
        rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
        if rms < 1e-3:
            probs.append(f"{s.id}: audio silent (rms={rms:.5f})")
    if (stems / "voice.wav").exists():
        v = read_audio(stems / "voice.wav")
        for s in scenes:
            if s.narration:
                seg = v[int(s.tStart * SR): int(s.tEnd * SR)]
                if len(seg) == 0 or np.max(np.abs(seg)) < 0.02:
                    probs.append(f"{s.id}: narration track empty")
    if (stems / "impact.wav").exists():
        imp = read_audio(stems / "impact.wav")
        for s in scenes:
            for c in s.soundCues:
                if c.sfx == "bass_hit":
                    i0 = int(c.at * SR)
                    w = imp[max(0, i0 - int(0.05 * SR)): i0 + int(0.1 * SR)]
                    if len(w) == 0 or np.max(np.abs(w)) < 0.05:
                        probs.append(f"{s.id}: no impact energy at {c.at}s")
    # every cue the sound director decided to play must actually be audible in its stem
    plan = bundle / "audio" / "sound_design.json"
    if plan.exists():
        from motionbrief.audio.sfx import STEM_OF
        lo, hi = min(s.tStart for s in scenes), max(s.tEnd for s in scenes)
        loaded: dict[str, np.ndarray] = {}
        for c in json.loads(plan.read_text(encoding="utf-8"))["cues"]:
            if not c["sfx"] or not lo <= c["at"] < hi or not (stems / f"{STEM_OF[c['sfx']]}.wav").exists():
                continue
            st = loaded.setdefault(STEM_OF[c["sfx"]], read_audio(stems / f"{STEM_OF[c['sfx']]}.wav"))
            w = st[int(c["at"] * SR): int((c["at"] + 1.0) * SR)]
            if len(w) == 0 or np.max(np.abs(w)) < 0.01:
                probs.append(f"{c['scene']}: {c['sfx']}@{c['at']:.2f}s inaudible in {STEM_OF[c['sfx']]} stem")
    if full:
        a = tok["audio"]
        ld = loudness(master)
        if abs(ld["integratedLUFS"] - a["targetLUFS"]) > a["toleranceLU"]:
            probs.append(f"integrated loudness {ld['integratedLUFS']} LUFS outside {a['targetLUFS']}±{a['toleranceLU']}")
        if ld["truePeakDBFS"] > -1.0:
            probs.append(f"true peak {ld['truePeakDBFS']} dBFS > -1.0")
    return probs


def _video_checks(ir: SceneIR, bundle: Path, scenes, full: bool) -> list[str]:
    from motionbrief.render.ffmpeg import black_segments, ffprobe

    probs = []
    fps = ir.video.fps
    for s in scenes:
        mp4 = bundle / "frames" / f"{s.id}.mp4"
        if not mp4.exists():
            probs.append(f"{s.id}: missing scene render")
            continue
        info = ffprobe(mp4)
        vs = [x for x in info["streams"] if x["codec_type"] == "video"][0]
        n = int(vs.get("nb_read_frames", 0))
        exp = round(s.tEnd * fps) - round(s.tStart * fps)
        if n != exp:
            probs.append(f"{s.id}: {n} frames, expected {exp}")
        if (vs["width"], vs["height"]) != (ir.video.w, ir.video.h):
            probs.append(f"{s.id}: resolution {vs['width']}x{vs['height']}")
        for a, b in black_segments(mp4):
            probs.append(f"{s.id}: black frames {a:.2f}-{b:.2f}s")
    if full:
        final = bundle / "final.mp4"
        if not final.exists():
            return probs + ["missing final.mp4"]
        info = ffprobe(final)
        vs = [x for x in info["streams"] if x["codec_type"] == "video"]
        aus = [x for x in info["streams"] if x["codec_type"] == "audio"]
        if not vs or not aus:
            probs.append("final.mp4 must have 1 video + 1 audio stream")
        else:
            v = vs[0]
            num, den = map(int, v["r_frame_rate"].split("/"))
            if (v["width"], v["height"]) != (ir.video.w, ir.video.h) or abs(num / den - fps) > 0.01:
                probs.append(f"final: {v['width']}x{v['height']}@{num / den:.2f}")
            n = int(v.get("nb_read_frames", 0))
            exp = round(ir.duration * fps)
            if abs(n - exp) > 1:
                probs.append(f"final: {n} frames, expected {exp}")
            if v.get("codec_name") != "h264" or aus[0].get("codec_name") != "aac":
                probs.append("final: codecs must be h264/aac")
        for a, b in black_segments(final):
            probs.append(f"final: black frames {a:.2f}-{b:.2f}s")
    return probs


def _bundle_checks(ir: SceneIR, bundle: Path, scenes, full: bool) -> list[str]:
    probs = []
    need = ["scene_ir.json", "sources.md", "subs/subtitles.srt", "audio/narration_mix.wav"]
    if full:
        need += ["final.mp4", "cover.png", "audio/narration.wav", "metrics.json"]
    for rel in need:
        if not (bundle / rel).exists():
            probs.append(f"missing {rel}")
    src = bundle / "sources.md"
    if src.exists():
        txt = src.read_text(encoding="utf-8")
        for s in scenes:
            for c in s.citations:
                if c not in txt:
                    probs.append(f"{s.id}: citation {c} not listed in sources.md")
    return probs


def check_artifacts(ir: SceneIR, bundle: Path, scene_ids: Optional[list[str]] = None) -> GateReport:
    full = not scene_ids
    rep = GateReport("G1", "artifacts" if full else f"artifacts:{','.join(scene_ids)}")
    tok = load_tokens()
    scenes = [s for s in ir.scenes if full or s.id in scene_ids]
    rep.add("bundle_complete", _bundle_checks(ir, bundle, scenes, full))
    rep.add("frames_render_integrity", _video_checks(ir, bundle, scenes, full))
    rep.add("subtitle_timing", _srt_checks(ir, bundle / "subs" / "subtitles.srt", scenes, tok))
    rep.add("audio_presence_loudness", _audio_checks(ir, bundle, scenes, full, tok))
    return rep


def run_g1(ir_path: Path, bundle: Optional[Path] = None, scene_ids: Optional[list[str]] = None) -> list[GateReport]:
    raw = json.loads(Path(ir_path).read_text(encoding="utf-8"))
    ir, rep = check_ir(raw, scene_ids)
    reps = [rep]
    if ir is not None and bundle is not None:
        reps.append(check_artifacts(ir, bundle, scene_ids))
    return reps
