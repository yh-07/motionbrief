# SPDX-License-Identifier: Apache-2.0
"""Allow-listed deterministic actions the local agent may execute.

No creative decisions happen here: every action is a pure function of a
validated Scene IR + tokens/registry. Each returns (artifacts, metrics, degradations).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

from motionbrief.audio.mix import (build_subtitles, mix, parse_srt, synthesize_narration, write_srt)
from motionbrief.ir.models import SceneIR, load
from motionbrief.paths import REPO_ROOT
from motionbrief.render.backend import BACKENDS, BackendUnavailable, plan_scene, scene_hash, segment_name
from motionbrief.render.probe import probe
from motionbrief.tts.provider import get_provider

ActionResult = tuple[list[str], dict, list[dict]]


def _ir(task: dict) -> tuple[SceneIR, Path]:
    """Effective IR: the voice-retimed IR once TTS has run, else the authored IR."""
    out = Path(task["outDir"])
    out = out if out.is_absolute() else REPO_ROOT / out
    timed = out / "scene_ir.timed.json"
    if task["type"] != "tts_narration" and timed.exists():
        return load(timed), timed
    p = (REPO_ROOT / task["irRef"]).resolve()
    return load(p), p


def _bundle(task: dict, ir: SceneIR) -> Path:
    out = Path(task["outDir"])
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    for d in ("frames", "audio", "subs", "logs"):
        (out / d).mkdir(exist_ok=True)
    return out


def write_sources(ir: SceneIR, b: Path) -> Path:
    lines = [f"# Sources — {ir.video.title} ({ir.video.id})", "",
             "Public references backing every factual scene (auto-generated from Scene IR).", ""]
    for s in ir.scenes:
        if s.citations:
            lines.append(f"- **{s.id}** ({s.tStart:g}–{s.tEnd:g}s) {s.narration}")
            lines += [f"  - {c}" for c in s.citations]
    lines += ["", "Generated with MotionBrief. Contains AI-generated narration (label required at publish)."]
    p = b / "sources.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def tts_narration(task: dict) -> ActionResult:
    ir, ir_path = _ir(task)
    b = _bundle(task, ir)
    voice = task.get("cmd", {}).get("voice", "zh")
    from motionbrief.audio.mix import place_segments
    from motionbrief.timing import retime
    tts = get_provider()
    segs = synthesize_narration(ir, b, tts, voice)
    timed, changes = retime(ir, {v.scene_id: v.dur for v in segs})
    timed_path = b / "scene_ir.timed.json"
    timed_path.write_text(json.dumps(timed.model_dump(by_alias=True), ensure_ascii=False, indent=2), encoding="utf-8")
    segs = place_segments(segs, timed)
    ir, ir_path = timed, timed_path
    cues = build_subtitles(segs, landscape=ir.video.aspect == "16:9")
    srt = b / "subs" / "subtitles.srt"
    write_srt(cues, srt)
    (b / "audio" / "voice_segments.json").write_text(json.dumps(
        [{"sceneId": s.scene_id, "start": s.start, "dur": s.dur, "wav": str(s.wav.relative_to(b)), "cues": s.cues}
         for s in segs],
        indent=2), encoding="utf-8")
    shutil.copyfile(ir_path, b / "scene_ir.json")
    src = write_sources(ir, b)
    retimed = [{"scene": c.scene_id, "from": c.old_dur, "to": c.new_dur} for c in changes]
    return [str(srt), str(src), str(timed_path)], {"voiceSegments": len(segs), "subtitleCues": len(cues),
                                                   "durationSec": timed.duration, "retimed": retimed,
                                                   "tts": tts.name}, []


def _load_cues(b: Path) -> list[tuple[float, float, str]]:
    srt = b / "subs" / "subtitles.srt"
    return parse_srt(srt) if srt.exists() else []


def render_scene(task: dict) -> ActionResult:
    ir, _ = _ir(task)
    b = _bundle(task, ir)
    scene = ir.scene(task["sceneId"])
    cmd = task.get("cmd", {}) or {}
    forced = task.get("renderer", "auto")
    plan = plan_scene(scene)
    if forced not in ("auto", None):
        for vo in scene.visualObjects:
            if forced != plan.choices[vo.id]:
                if not BACKENDS[forced].can_render(vo):
                    if not task.get("degrade", True):
                        raise BackendUnavailable(f"{forced} cannot render {vo.id} and degrade=false")
                    continue
                plan.choices[vo.id] = forced
    cues = [c for c in _load_cues(b) if c[1] > scene.tStart and c[0] < scene.tEnd]
    local = _local_plan(plan)  # what this host can draw itself (GPU objects -> 2.5D when no local WebGL)
    h, h_local = scene_hash(ir, scene, cues, plan), scene_hash(ir, scene, cues, local)
    frames = b / "frames"
    seg = tuple(cmd["segment"]) if cmd.get("segment") else None
    mp4 = frames / (segment_name(scene.id, *seg) if seg else f"{scene.id}.mp4")
    stamp = mp4.with_suffix(".hash")
    max_frames = cmd.get("maxFrames")
    # a 2.5D fallback is only a valid result while no GPU host is configured; otherwise retry for the 3D body
    valid = {h} if local is not plan and probe()["webglRemote"] else {h, h_local}
    # a slice is also done when its whole scene is already joined and valid (slice files are removed on join)
    whole, whole_stamp = frames / f"{scene.id}.mp4", frames / f"{scene.id}.hash"
    for m, st in ((mp4, stamp), (whole, whole_stamp)) if seg else ((mp4, stamp),):
        if task.get("checkpoint", True) and not max_frames and m.exists() and st.exists() \
                and st.read_text().strip() in valid:
            done = plan if st.read_text().strip() == h else local
            return [str(m)], {"checkpointHit": True, "sceneHash": st.read_text().strip()}, done.degradations
    t0 = time.time()
    if not seg and cmd.get("segments") and not max_frames:
        # join slices rendered by parallel workers; all slices must come from the same plan (never mix 3D and
        # 2.5D bodies inside one scene); anything missing/stale -> plain full render below
        n = cmd["segments"]
        parts = [frames / segment_name(scene.id, k, n) for k in range(n)]
        marks = {p.with_suffix(".hash").read_text().strip() if p.exists() and p.with_suffix(".hash").exists()
                 else None for p in parts}
        if len(marks) == 1 and marks <= {h, h_local}:
            mark = marks.pop()
            done = plan if mark == h else local
            from motionbrief.render.ffmpeg import concat_copy
            concat_copy(parts, mp4)
            stamp.write_text(mark)
            for p in parts:
                p.unlink()
                p.with_suffix(".hash").unlink()
            fps = ir.video.fps
            metrics = {"frames": round(scene.tEnd * fps) - round(scene.tStart * fps), "sceneHash": mark,
                       "joinedSegments": n, "renderSec": round(time.time() - t0, 2), "plan": done.choices}
            return [str(mp4), *map(str, sorted((frames / scene.id).glob("f*.png")))], metrics, done.degradations
    kw = dict(subtitles=cues, png_every=cmd.get("pngEvery", 15), max_frames=max_frames, segment=seg)
    res, done, fallback = None, local, []
    if cmd.get("worker") == "remote":
        from motionbrief.render import remote
        # GPU scenes get one more remote attempt: falling back locally would lose their 3D bodies
        for attempt in range(2 if plan is not local else 1):
            try:
                res, done = remote.render_frames(ir, scene, b / "frames", plan=plan, **kw), plan
                break
            except remote.RemoteUnavailable as e:  # LAN host down / broken: render here (GPU objects as 2.5D)
                fallback = [{"object": scene.id, "from": "remote", "to": "local", "reason": str(e)[-500:]}]
        if res is not None:
            fallback = []
    if res is None:
        res = BACKENDS["svg"].render_frames(ir, scene, b / "frames", plan=local, **kw)
    if not max_frames:
        stamp.write_text(h if done is plan else h_local)
    metrics = {"frames": res["frames"], "expectedFrames": res["expectedFrames"],
               "sceneHash": h if done is plan else h_local, "renderSec": round(time.time() - t0, 2),
               "plan": done.choices, "host": res.get("host", "local"), **({"gpu": res["gpu"]} if "gpu" in res else {})}
    return [res["video"], *res["pngs"]], metrics, done.degradations + fallback


def _local_plan(plan):
    """Plan as executable on this host: objects planned on a GPU backend it lacks fall back to 2.5D SVG."""
    gpu = [o for o, r in plan.choices.items() if r == "three"]
    if not gpu or probe()["webgl"]:
        return plan
    from motionbrief.render.backend import RenderPlan
    return RenderPlan(plan.scene_id, {o: ("svg" if r == "three" else r) for o, r in plan.choices.items()},
                      plan.degradations + [{"object": o, "from": "three", "to": "svg",
                                            "reason": "no local WebGL and scene not rendered on the GPU host"}
                                           for o in gpu])


def mix_audio(task: dict) -> ActionResult:
    ir, _ = _ir(task)
    b = _bundle(task, ir)
    meta = json.loads((b / "audio" / "voice_segments.json").read_text(encoding="utf-8"))
    from motionbrief.audio.mix import VoiceSeg
    segs = [VoiceSeg(m["sceneId"], m["start"], m["dur"], ir.scene(m["sceneId"]).narration, b / m["wav"],
                     m.get("cues")) for m in meta]
    out = mix(ir, segs, b)
    from motionbrief.audio.mix import analyze
    ana = analyze(ir, b)
    sd = json.loads((b / "audio" / "sound_design.json").read_text(encoding="utf-8"))
    metrics = {"loudnormPass1": out["loudnormPass1"], "masterSpreadDb": ana["masterSpreadDb"],
               "soundDesign": {k: v for k, v in sd.items() if k != "cues"}}
    arts = [out["master"], out["narration"], *out["stems"].values(), str(b / "audio" / "sound_design.json"),
            str(b / "audio" / "analysis.json"), str(b / "logs" / "spectrum.png")]
    return arts, metrics, []


def assemble(task: dict) -> ActionResult:
    from motionbrief.render.ffmpeg import concat, extract_frame, loudness
    from motionbrief.paths import load_tokens

    ir, ir_path = _ir(task)
    b = _bundle(task, ir)
    parts = [b / "frames" / f"{s.id}.mp4" for s in ir.scenes]
    missing = [p.name for p in parts if not p.exists()]
    if missing:
        from motionbrief.agent.taxonomy import GateFailed
        raise GateFailed(f"cannot assemble, missing scene renders: {missing}")
    from motionbrief.render.ffmpeg import mux, video_encoder
    # the picture is re-encoded only when a scene (or grain/encoder) changed; audio-only edits just remux
    grain = load_tokens()["background"]["grain"]
    vkey = hashlib.sha256(json.dumps([[(b / "frames" / f"{s.id}.hash").read_text().strip()
                                        if (b / "frames" / f"{s.id}.hash").exists() else f"nohash:{s.id}"
                                        for s in ir.scenes], grain, video_encoder()]).encode()).hexdigest()[:16]
    silent, vstamp = b / "frames" / "_video.mp4", b / "frames" / "_video.hash"
    reused = silent.exists() and vstamp.exists() and vstamp.read_text().strip() == vkey
    if not reused:
        concat(parts, silent, grain=grain)
        vstamp.write_text(vkey)
    final = b / "final.mp4"
    mux(silent, b / "audio" / "narration_mix.wav", final)
    # cover: hero moment = first impact beat in a hero-quality scene (else first impact)
    hero = [m.at for s in ir.scenes if s.renderQuality == "hero" for m in s.motionGrammar if m.grammar == "impact"]
    any_imp = [m.at for s in ir.scenes for m in s.motionGrammar if m.grammar == "impact"]
    t_cover = (hero or any_imp or [1.0])[0] + 0.5
    extract_frame(final, t_cover, b / "cover.png")
    write_sources(ir, b)
    shutil.copyfile(ir_path, b / "scene_ir.json")
    ld = loudness(b / "audio" / "narration_mix.wav")
    metrics = {
        "videoId": ir.video.id, "durationSec": ir.duration, "durationTier": ir.video.durationTier,
        "productionLevel": ir.video.productionLevel, "scenes": len(ir.scenes),
        "audio": ld, "probe": probe(), "coverAtSec": t_cover, "videoReused": reused,
        "platform": {"note": "fill after publish (manual in MVP, see D6)", "retention3s": None,
                     "completionRate": None, "follows": None, "saves": None, "shares": None},
    }
    (b / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    return [str(final), str(b / "cover.png"), str(b / "sources.md"), str(b / "metrics.json")], metrics, []


def qa_g1(task: dict) -> ActionResult:
    from motionbrief.agent.taxonomy import GateFailed
    from motionbrief.quality.deterministic import run_g1

    ir, ir_path = _ir(task)
    b = _bundle(task, ir)
    scope = [task["sceneId"]] if task.get("sceneId") else None
    reps = run_g1(ir_path, b, scope)
    name = f"g1_{task['sceneId']}.json" if scope else "g1.json"
    (b / "logs" / name).write_text(json.dumps([r.to_dict() for r in reps], indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    if not all(r.passed for r in reps):
        raise GateFailed("\n".join(r.summary() for r in reps))
    return [str(b / "logs" / name)], {"g1": "pass", "summary": [r.summary() for r in reps]}, []


ACTIONS: dict[str, Callable[[dict], ActionResult]] = {
    "tts_narration": tts_narration,
    "render_scene": render_scene,
    "mix_audio": mix_audio,
    "assemble": assemble,
    "qa_g1": qa_g1,
}
