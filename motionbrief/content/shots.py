# SPDX-License-Identifier: Apache-2.0
"""Shot plan -> Scene IR (deterministic). The storyboard LLM only writes the shot plan; timing, beats, sound cues
and IR structure are produced here, so every IR follows the same voice-first policy.

Shot plan (JSON):
  {"video": {"id", "title"}, "palette"?: {...},
   "shots": [{"id": "s01", "role": hook|context|reveal|mechanism|payoff|callback,
              "narration": verbatim line, "citations": [url | Wikipedia title], "transition": cut|zoom_through|...,
              "texts": [{"text", "style": headline|label|impact_reveal, "anchor": top|center|lower}],
              "objects": [{"id", "component", "depth"?: 0|1|2, "renderer"?: "svg"|"three", "props": {...}}],
              "beats": {"ent"?: 0, "rev"?: f|null, "imp"?: f|null, "exit"?: f, "text_at"?: f},   # fractions of the shot
              "cues": ["tick"|"blip"|"bass"|"riser", ...], "camera"?: [move, from, to], "hero"?: bool,
              "target"?: object id driven by the beats, "prePause"?: seconds of silence before this line}]}
Prop values {"spanFrac": f, "offset": o} become seconds relative to the shot length; PhotonGuide keys/moods use
shot fractions as their first element.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from motionbrief.render.svg_canvas.canvas import canvas_for

WIKI = "https://en.wikipedia.org/wiki/"
LEAD, TAIL, MIN_DUR = 0.15, 0.5, 2.8
CUE = {"tick": "ui_tick", "blip": "digital_blip", "bass": "bass_hit", "riser": "riser"}
CHIP_STYLE = {"materialStyle": {"type": "toon", "bands": 3, "gradientRamp": ["#EFE6FF", "#7C5CFF", "#2A2350"]},
              "outline": {"method": "inverted_hull", "width": 0.03, "color": "#1A1452"},
              "lightingPreset": "single_key_soft"}
PALETTE = {"primary": ["#7C5CFF", "#22D3B6"], "accent": "#FFB547"}
BACKGROUND = ("rain", "stream")  # background objects never carry the shot's beats


class PlanError(ValueError):
    pass


def measure_voice(lines: dict[str, str], cache: Path | None = None) -> dict[str, float]:
    """Synthesize every line once (sentence-level, the production path) and return spoken seconds per shot."""
    if cache and cache.exists():
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("lines") == lines:
            return c["dur"]
    from motionbrief.audio.mix import PAUSE, SENT, SR, _trim, read_audio
    from motionbrief.tts.provider import get_provider
    tts = get_provider()
    tmp = Path(tempfile.mkdtemp())
    items, owner = [], []
    for sid, narr in lines.items():
        for k, m in enumerate(SENT.finditer(narr)):
            if m.group(0).strip():
                items.append((m.group(0).strip(), tmp / f"{sid}_{k}.wav"))
                owner.append(sid)
    tts.synthesize_batch(items, "zh")
    dur: dict[str, float] = {}
    for (sent, p), sid in zip(items, owner):
        d = len(_trim(read_audio(p))) / SR
        dur[sid] = dur.get(sid, 0.0) + d + (PAUSE.get(sent[-1], 0.25) if sid in dur else 0.0)
    if cache:
        cache.write_text(json.dumps({"tts": tts.name, "lines": lines, "dur": dur}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return dur


def estimate_voice(lines: dict[str, str], cps: float = 5.0) -> dict[str, float]:
    """Fast stand-in for the repair loop (measured Kokoro 云希 ≈ 5 chars/s)."""
    return {sid: max(0.8, len([ch for ch in n if not ch.isspace()]) / cps) for sid, n in lines.items()}


def _cite(c: str) -> str:
    return c if c.startswith("http") else WIKI + c.replace(" ", "_")


def compile_plan(plan: dict, dur: dict[str, float]) -> dict:
    shots = plan["shots"]
    t, S, E = 0.0, {}, {}
    for i, sh in enumerate(shots):
        nxt = shots[i + 1] if i + 1 < len(shots) else {}
        d = sh.get("duration") or (LEAD + dur.get(sh["id"], 2.0) + TAIL + float(nxt.get("prePause", 0.0)))
        d = round(max(MIN_DUR, d) * 30) / 30
        S[sh["id"]], E[sh["id"]] = round(t, 3), round(t + d, 3)
        t += d
    scenes = [_scene(sh, S[sh["id"]], E[sh["id"]]) for sh in shots]
    total = E[shots[-1]["id"]]
    if plan.get("video", {}).get("aspect") == "16:9" and total >= 480:
        tier = "longform"
    else:
        tier = "micro" if total <= 40 else "core" if total <= 75 else "deep" if total <= 120 else "extended"
    v = plan.get("video", {})
    aspect = v.get("aspect", "9:16")
    size = canvas_for(aspect)
    return {"irVersion": "1.2.0",
            "video": {"id": v.get("id", "video"), "title": v.get("title", ""), "aspect": aspect, "w": size.w, "h": size.h,
                      "fps": 30, "visualIP": "cartoon-tech-v2", "durationTier": tier,
                      "visualStyle": v.get("visualStyle", "neon"),
                      # "hero" promises a Layer B (3D) object; only claim it when a shot carries one
                      "productionLevel": v.get("productionLevel") or
                      ("hero" if any(s.get("hero") for s in shots) else "standard")},
            "palette": plan.get("palette", PALETTE), "scenes": scenes}


def _scene(sh: dict, s0: float, s1: float) -> dict:
    sid, span = sh["id"], s1 - s0
    b = sh.get("beats", {})
    rev, imp = b.get("rev"), b.get("imp")

    def at(f: float) -> float:
        return min(s1, max(s0, round(s0 + span * float(f), 3)))

    vos = []
    for ob in sh["objects"]:
        props = {}
        for k, v in (ob.get("props") or {}).items():
            if isinstance(v, dict) and "spanFrac" in v:
                v = round(span * float(v["spanFrac"]) + float(v.get("offset", 0.0)), 3)
            props[k] = v
        if ob["component"] == "PhotonGuide":
            props["keys"] = [[at(k[0]), *k[1:]] for k in props.get("keys", [[0, 540, 960, 1.0]])]
            props["moods"] = [[at(m[0]), m[1]] for m in props.get("moods", [[0, "happy"]])]
        vo = {"id": ob["id"], "component": ob["component"], "renderer": ob.get("renderer", "svg"),
              "depth": int(ob.get("depth", 1)), "props": props}
        if ob["component"] == "ChipReveal":
            vo.update(CHIP_STYLE)
        vos.append(vo)
    target = sh.get("target") or next((v["id"] for v in vos if v["id"] not in BACKGROUND), vos[0]["id"])
    beats = [(target, "entrance", at(b.get("ent", 0.0)))]
    if rev is not None:
        beats.append((target, "reveal", at(rev)))
    if b.get("exit") is not None:
        beats.append((target, "exit", at(b["exit"])))
    if imp is not None:
        beats.append((target, "impact", at(imp)))
    typo = []
    for k, tx in enumerate(sh.get("texts", [])):
        # the headline lands on the impact; shots without one show it mid-shot (a fresh visual event)
        ta = at(b["text_at"] if b.get("text_at") is not None else imp if imp is not None and k == 0 else 0.55)
        if k == 0 and imp is not None:
            beats.append((tx["text"], "impact", at(imp)))
        typo.append({"text": tx["text"], "style": tx.get("style", "headline"), "safeArea": tx.get("anchor", "top"),
                     "at": ta})
    cues = sh.get("cues", [])
    if "bass" in cues and imp is None:
        raise PlanError(f"{sid}: cue 'bass' needs beats.imp")
    snd = [("whoosh", s0)]
    for name in cues:
        when = {"tick": 0.06, "blip": rev if rev is not None else 0.3, "bass": imp, "riser": 0.08}.get(name)
        if when is None:
            raise PlanError(f"{sid}: unknown cue {name!r} (tick|blip|bass|riser)")
        snd.append((CUE[name], at(when)))
    hero = bool(sh.get("hero"))
    cam = sh.get("camera") or ["push_in", 1.0, 1.07 if hero else 1.04]
    cites = [_cite(c) for c in sh.get("citations", [])]
    chapter = {"chapter": sh["chapter"]} if sh.get("chapter") else {}
    note = {"note": sh["note"]} if sh.get("note") else {}
    return {
        "id": sid, "tStart": s0, "tEnd": s1, "role": sh["role"], "narration": sh["narration"], **chapter, **note,
        "isFactual": bool(cites), "citations": cites, "styleProfile": "cartoon-tech-v2",
        "assetStyle": "toon_3d" if hero else "toon_2_5d", "renderQuality": "hero" if hero else "standard",
        "cameraProjection": "perspective" if hero else "orthographic", "depthLayers": 3,
        "camera": {"move": cam[0], "from": cam[1], "to": cam[2], "easing": "easeOutExpo"},
        "typography": typo, "visualObjects": vos,
        "motionGrammar": [{"target": a, "grammar": g, "at": c} for a, g, c in beats],
        "soundCues": [{"sfx": a, "at": c} for a, c in sorted(snd, key=lambda x: x[1])],
        "transitionIn": {"type": sh.get("transition", "cut")}, "fallback2D": True,
        "rendererHints": {"webglFallback": "svg", "frameCritical": hero},
    }


if __name__ == "__main__":  # python -m motionbrief.content.shots plan.json out.json [--measure]
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    lines = {s["id"]: s["narration"] for s in plan["shots"]}
    d = measure_voice(lines) if "--measure" in sys.argv else estimate_voice(lines)
    Path(sys.argv[2]).write_text(json.dumps(compile_plan(plan, d), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
