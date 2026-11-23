# SPDX-License-Identifier: Apache-2.0
"""Author the ISP v3 60-second trailer Scene IR from the v3 storyboard + MEASURED voice durations.

Source: 《四个摄像头？讲清 ISP》分镜剧本 v3 (48 shots). Trailer cut per the script's publishing notes:
s01–s02 + s11–s12 + s43–s48, plus s13 (the ISP reveal) so "这台流水线" in s43 has a referent,
and a trailer-only end card "完整版 4 分钟". Narration is verbatim from the script.
Usage: python examples/isp_v3/build_trailer.py  (writes fixtures/isp_v3_trailer.json)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

W = "https://en.wikipedia.org/wiki/"

# (id, role, narration, citations, isFactual) — ids keep the full-cut shot numbers
SCRIPT = [
    ("s01", "hook", "你手机背后有四个摄像头。可没有一个，拍得出照片。", ["Image_processor", "Camera_phone"], True),
    ("s02", "hook", "你相册里每一张照片，都不是拍下来的，是算出来的。", ["Computational_photography"], True),
    ("s11", "reveal", "这就意味着：每个像素都只知道一种颜色，另外两种，它根本没见过。", ["Bayer_filter", "Demosaicing"], True),
    ("s12", "reveal", "你照片里三分之二的颜色，是算出来的。", ["Demosaicing"], True),
    ("s13", "reveal", "负责算的，是手机芯片里一块专用电路，叫ISP，图像信号处理器。", ["Image_processor"], True),
    ("s43", "payoff", "还有时间。拍四K视频，每秒三十帧，这台流水线每秒要处理两亿多个像素。",
     ["4K_resolution", "Frame_rate"], True),
    ("s44", "payoff", "每一帧，只有三十三毫秒，比你眨一次眼还快好几倍。", ["Frame_rate", "Blinking"], True),
    ("s45", "callback", "所以，下次按下快门，你可以想一想：那一刻，照片还不存在。", [], False),
    ("s46", "callback", "四个摄像头拍下的，只是一堆会骗人的格子。", [], False),
    ("s47", "callback", "是ISP在几十毫秒里，替你猜出了颜色，擦掉了噪点，认出了光，保住了天空。", ["Image_processor"], True),
    ("s48", "callback", "照片，是算出来的。", [], False),
    ("s49", "callback", "", [], False),  # trailer-only end card (outside the 48 shots)
]
# the script asks for ~0.3 s of silence before the reversal lines (s12, s39, s48): lengthen the previous shot
PRE_PAUSE = {"s12": 0.3, "s48": 0.3}
END_CARD_SEC = 2.4
LEAD, TAIL, MIN_DUR = 0.15, 0.5, 2.8
CACHE = ROOT / "examples" / "isp_v3" / "voice_durations_trailer.json"


def measure_voice() -> dict[str, float]:
    """Synthesize every line once (sentence-level, same path as production) and return seconds."""
    script = [n for _, _, n, _, _ in SCRIPT]
    if CACHE.exists() and "--remeasure" not in sys.argv:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if cached.get("script") == script:
            return cached["dur"]
    from motionbrief.audio.mix import PAUSE, SENT, SR, _trim, read_audio
    from motionbrief.tts.provider import get_provider
    tts = get_provider()
    tmp = Path(tempfile.mkdtemp())
    items, owner = [], []
    for sid, _, narr, _, _ in SCRIPT:
        for k, m in enumerate(SENT.finditer(narr)):
            if m.group(0).strip():
                items.append((m.group(0).strip(), tmp / f"{sid}_{k}.wav"))
                owner.append(sid)
    tts.synthesize_batch(items, "zh")
    dur: dict[str, float] = {}
    for (sent, p), sid in zip(items, owner):
        d = len(_trim(read_audio(p))) / SR
        dur[sid] = dur.get(sid, 0.0) + d + (PAUSE.get(sent[-1], 0.25) if sid in dur else 0.0)
    print(f"tts={tts.name}", {k: round(v, 2) for k, v in dur.items()}, file=sys.stderr)
    CACHE.write_text(json.dumps({"tts": tts.name, "script": script, "dur": dur}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return dur


def build(dur: dict[str, float]) -> dict:
    ids = [sid for sid, *_ in SCRIPT]
    t, starts = 0.0, {}
    for i, sid in enumerate(ids):
        if sid == "s49":
            d = END_CARD_SEC
        else:
            nxt = ids[i + 1] if i + 1 < len(ids) else None
            d = max(MIN_DUR, LEAD + dur.get(sid, 2.0) + TAIL + PRE_PAUSE.get(nxt, 0.0))
        d = round(d * 30) / 30
        starts[sid] = (round(t, 3), round(t + d, 3))
        t += d
    S = {k: v[0] for k, v in starts.items()}
    E = {k: v[1] for k, v in starts.items()}

    def at(sid: str, frac: float) -> float:
        return min(E[sid], max(S[sid], round(S[sid] + (E[sid] - S[sid]) * frac, 3)))

    def vo(id_, comp, depth=1, renderer="svg", **props):
        return {"id": id_, "component": comp, "renderer": renderer, "depth": depth, "props": props}

    def scene(sid, objs, typo=(), beats=(), cues=(), trans="cut", cam=("push_in", 1.0, 1.04), **kw):
        role, narr, cites, fact = next((r, n, c, f) for i, r, n, c, f in SCRIPT if i == sid)
        return {
            "id": sid, "tStart": S[sid], "tEnd": E[sid], "role": role, "narration": narr, "isFactual": fact,
            "citations": [W + c for c in cites], "styleProfile": "cartoon-tech-v2",
            "assetStyle": kw.get("assetStyle", "toon_2_5d"), "renderQuality": kw.get("rq", "standard"),
            "cameraProjection": kw.get("proj", "orthographic"), "depthLayers": 3,
            "camera": {"move": cam[0], "from": cam[1], "to": cam[2], "easing": "easeOutExpo"},
            "typography": [{"text": a, "style": b, "safeArea": c, "at": d, **({"until": e} if e else {})}
                           for a, b, c, d, *rest in typo for e in [rest[0] if rest else None]],
            "visualObjects": objs,
            "motionGrammar": [{"target": a, "grammar": b, "at": c} for a, b, c in beats],
            "soundCues": [{"sfx": a, "at": b} for a, b in cues],
            "transitionIn": {"type": trans}, "fallback2D": True,
            "rendererHints": kw.get("hints", {"webglFallback": "svg", "frameCritical": False}),
        }

    def rain(seed):
        return vo("rain", "ParticleStream", 0, mode="photons", count=40, seed=seed)

    sc = []
    # s01 HOOK: four lenses light up, then all go dark and get crossed out on "没有一个"
    sc.append(scene("s01", [rain(1), vo("lens", "LensArray", 1, count=4, y=1040)],
                    typo=[("拍不出照片？", "headline", "top", at("s01", 0.6))],
                    beats=[("lens", "entrance", at("s01", 0.0)), ("lens", "reveal", at("s01", 0.18)),
                           ("lens", "exit", at("s01", 0.5)), ("拍不出照片？", "impact", at("s01", 0.6)),
                           ("lens", "impact", at("s01", 0.6))],
                    cues=[("whoosh", S["s01"]), ("digital_blip", at("s01", 0.18)), ("bass_hit", at("s01", 0.6))],
                    cam=("push_in", 1.0, 1.05)))
    # s02 the sunset photo flips into one-colour tiles with "?"
    sc.append(scene("s02", [vo("plate", "RawFramePlate", 1, mode="guess", cells=8, y=1000)],
                    typo=[("是算出来的", "headline", "top", at("s02", 0.64))],
                    beats=[("plate", "entrance", at("s02", 0.0)), ("plate", "reveal", at("s02", 0.2)),
                           ("是算出来的", "impact", at("s02", 0.64)), ("plate", "impact", at("s02", 0.64))],
                    cues=[("whoosh", S["s02"]), ("digital_blip", at("s02", 0.2)), ("bass_hit", at("s02", 0.64))],
                    trans="zoom_through"))
    # s11 each pixel knows only one colour (Bayer tiles; s02 already showed the flip)
    sc.append(scene("s11", [vo("plate", "RawFramePlate", 1, mode="bayer", cells=8, y=1000)],
                    typo=[("只知道 1 种颜色", "label", "top", at("s11", 0.42))],
                    beats=[("plate", "entrance", at("s11", 0.0)), ("plate", "reveal", at("s11", 0.12)),
                           ("只知道 1 种颜色", "impact", at("s11", 0.42))],
                    cues=[("whoosh", S["s11"]), ("ui_tick", at("s11", 0.12)), ("digital_blip", at("s11", 0.42))]))
    # s12 second hook: a huge 2/3; 小光 looks up, surprised, from the corner
    sc.append(scene("s12", [vo("big", "TitleCard", 1, text="2/3", style="impact_reveal", anchor="center",
                               sub="的颜色 · 是算出来的"),
                            vo("guide", "PhotonGuide", 2,
                               keys=[[at("s12", 0.0), 260, 1500, 0.9], [at("s12", 1.0), 280, 1480, 0.9]],
                               moods=[[at("s12", 0.0), "surprised"]], look=[1, -1])],
                    beats=[("big", "entrance", at("s12", 0.0)), ("big", "impact", at("s12", 0.12)),
                           ("guide", "entrance", at("s12", 0.25)), ("guide", "reveal", at("s12", 0.5))],
                    cues=[("whoosh", S["s12"]), ("bass_hit", at("s12", 0.12))],
                    trans="zoom_through"))
    # s13 HERO: the ISP chip slams down (Layer B three.js on the GPU host, 2.5D fallback)
    chip = vo("chip", "ChipReveal", 1, "three", label="")
    chip.update({"materialStyle": {"type": "toon", "bands": 3, "gradientRamp": ["#EFE6FF", "#7C5CFF", "#2A2350"]},
                 "outline": {"method": "inverted_hull", "width": 0.03, "color": "#1A1452"},
                 "lightingPreset": "single_key_soft"})
    sc.append(scene("s13", [vo("stream", "ParticleStream", 0, mode="converge", count=70, seed=13), chip],
                    typo=[("ISP", "impact_reveal", "center", at("s13", 0.55))],
                    beats=[("chip", "entrance", at("s13", 0.05)), ("stream", "reveal", at("s13", 0.3)),
                           ("chip", "impact", at("s13", 0.55)), ("ISP", "impact", at("s13", 0.55))],
                    cues=[("riser", at("s13", 0.08)), ("bass_hit", at("s13", 0.55))],
                    trans="mask_reveal", cam=("push_in", 1.0, 1.07), assetStyle="toon_3d", rq="hero",
                    proj="perspective", hints={"webglFallback": "svg", "frameCritical": True}))
    stages = ["去马赛克", "降噪", "白平衡", "色调映射"]
    # s43 time pressure: the four stages fire in quick succession
    sc.append(scene("s43", [vo("pipe", "PipelineFlythrough", 1, stages=stages, focus=-1, top=380, budget=True,
                               perStage=round((E["s43"] - S["s43"]) * 0.09, 3))],
                    typo=[("2 亿+ 像素/秒", "headline", "lower", at("s43", 0.74))],
                    beats=[("pipe", "entrance", at("s43", 0.0)), ("pipe", "reveal", at("s43", 0.3)),
                           ("2 亿+ 像素/秒", "impact", at("s43", 0.74))],
                    cues=[("whoosh", S["s43"]), ("digital_blip", at("s43", 0.3)), ("bass_hit", at("s43", 0.74))],
                    trans="zoom_through", cam=("pan", 1.0, 1.0)))
    # s44 33 ms vs one blink
    sc.append(scene("s44", [vo("eye", "EyeBlinkFrames", 1, frames=12)],
                    typo=[("33 ms", "headline", "top", at("s44", 0.25))],
                    beats=[("eye", "entrance", at("s44", 0.0)), ("33 ms", "impact", at("s44", 0.25)),
                           ("eye", "reveal", at("s44", 0.55))],
                    cues=[("whoosh", S["s44"]), ("bass_hit", at("s44", 0.25)), ("digital_blip", at("s44", 0.55))]))
    # s45 back to the RAW grid, slow push: the photo doesn't exist yet
    sc.append(scene("s45", [vo("plate", "RawFramePlate", 1, mode="bayer", cells=8, y=1000)],
                    typo=[("照片还不存在", "headline", "top", at("s45", 0.7))],
                    beats=[("plate", "entrance", at("s45", 0.0)), ("plate", "reveal", at("s45", 0.1)),
                           ("照片还不存在", "impact", at("s45", 0.7))],
                    cues=[("whoosh", S["s45"]), ("ui_tick", at("s45", 0.1)), ("digital_blip", at("s45", 0.7))],
                    trans="mask_reveal", cam=("push_in", 1.0, 1.09)))
    # s46 one-colour tiles and "?" again (echo of the hook)
    sc.append(scene("s46", [vo("plate", "RawFramePlate", 1, mode="guess", cells=8, y=1000)],
                    typo=[("会骗人的格子", "headline", "top", at("s46", 0.55))],
                    beats=[("plate", "entrance", at("s46", 0.0)), ("plate", "reveal", at("s46", 0.15)),
                           ("会骗人的格子", "impact", at("s46", 0.55))],
                    cues=[("whoosh", S["s46"]), ("ui_tick", at("s46", 0.15)), ("digital_blip", at("s46", 0.55))]))
    # s47 four capsules light with the four verbs, impact when all are lit
    caps = ["猜出颜色", "擦掉噪点", "认出光", "保住天空"]
    span = E["s47"] - S["s47"]
    first_lit = 0.33 * span  # "是ISP在几十毫秒里，" comes first (character share of the line)
    sc.append(scene("s47", [vo("caps", "PipelineFlythrough", 1, stages=caps, focus=-1, top=420, budget=False,
                               perStage=round(0.15 * span, 3), runDelay=round(first_lit - 0.5, 3))],
                    beats=[("caps", "entrance", at("s47", 0.0)),
                           ("caps", "reveal", at("s47", 0.33)), ("caps", "impact", at("s47", 0.94))],
                    cues=[("whoosh", S["s47"]), ("digital_blip", at("s47", 0.33)), ("bass_hit", at("s47", 0.94))],
                    trans="match_cut"))
    # s48 loop: the four lenses again (same as the hook, all lit), slow pull-out, photon rain
    sc.append(scene("s48", [rain(48), vo("lens", "LensArray", 1, count=4, y=1040)],
                    typo=[("是算出来的", "headline", "top", at("s48", 0.4))],
                    beats=[("lens", "entrance", at("s48", 0.0)), ("lens", "reveal", at("s48", 0.15)),
                           ("是算出来的", "impact", at("s48", 0.4)), ("lens", "impact", at("s48", 0.4))],
                    cues=[("whoosh", S["s48"]), ("digital_blip", at("s48", 0.15)), ("bass_hit", at("s48", 0.4))],
                    trans="match_cut", cam=("pull_out", 1.06, 1.0)))
    # trailer-only end card (no narration; not a follow/like CTA)
    sc.append(scene("s49", [vo("card", "TitleCard", 1, text="完整版 4 分钟", style="headline", anchor="center",
                               sub="四个摄像头？讲清 ISP")],
                    beats=[("card", "entrance", at("s49", 0.0)), ("card", "reveal", at("s49", 0.2))],
                    cues=[("ui_tick", at("s49", 0.2))], trans="mask_reveal", cam=("static", 1.0, 1.0)))
    total = E["s49"]
    tier = "micro" if total <= 40 else "core" if total <= 75 else "deep" if total <= 120 else "extended"
    return {"irVersion": "1.2.0",
            "video": {"id": "isp_v3_trailer", "title": "你手机的四个摄像头，没有一个会拍照（预告）", "aspect": "9:16",
                      "w": 1080, "h": 1920, "fps": 30, "visualIP": "cartoon-tech-v2", "durationTier": tier,
                      "productionLevel": "hero"},
            "palette": {"primary": ["#7C5CFF", "#22D3B6"], "accent": "#FFB547"},
            "scenes": sc}


if __name__ == "__main__":
    ir = build(measure_voice())
    out = ROOT / "fixtures" / "isp_v3_trailer.json"
    out.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}  duration={ir['scenes'][-1]['tEnd']:.2f}s tier={ir['video']['durationTier']}")
