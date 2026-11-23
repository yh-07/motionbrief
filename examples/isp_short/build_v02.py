# SPDX-License-Identifier: Apache-2.0
"""Author the ISP v02 Scene IR from a script + MEASURED voice durations (voice-first).

This is the reference for what the Phase-2 LLM storyboard stage must emit:
  * Story: curiosity-gap hook -> personified guide -> And/But/Therefore turns -> concrete
    comparison payoff -> callback ending that loops into the hook.
  * Every factual line carries public citations.
Usage: python examples/isp_short/build_v02.py  (writes fixtures/isp_v02.json)
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

W = "https://en.wikipedia.org/wiki/"

# (id, role, narration, citations, isFactual)
SCRIPT = [
    ("s01", "hook", "你拍的每一张照片里，有三分之二的颜色，是手机猜出来的。", ["Bayer_filter", "Demosaicing"], True),
    ("s02", "context", "不信？我们跟着一粒光子走一趟。它叫小光，刚从夕阳出发。", [], False),
    ("s03", "context", "穿过镜头，小光撞上了传感器。可传感器是个色盲：它只会数光子有多少，分不清颜色。",
     ["Image_sensor", "Bayer_filter"], True),
    ("s04", "mechanism", "于是工程师给每个像素戴上一片彩色滤镜。红、绿、蓝里，绿色占了一半，因为人眼对绿光最敏感。",
     ["Bayer_filter"], True),
    ("s05", "context", "结果，每个像素只记住了一种颜色。另外两种，全靠算。", ["Bayer_filter", "Raw_image_format"], True),
    ("s06", "reveal", "负责算的，是一颗专门的芯片：ISP，图像信号处理器。", ["Image_processor"], True),
    ("s07", "mechanism", "第一步，去马赛克。看看邻居是什么颜色，把缺的两种补上。", ["Demosaicing"], True),
    ("s08", "mechanism", "第二步，降噪。夜里光子太少，信号一放大，噪点也跟着放大，ISP要把它们擦掉。",
     ["Image_noise", "Noise_reduction"], True),
    ("s09", "mechanism", "第三步，白平衡。烛光偏橙，阴天偏蓝，ISP得判断：这张纸，本来应该是白色的。",
     ["Color_balance", "Color_temperature"], True),
    ("s10", "mechanism", "第四步，色调映射。天空太亮，房子太暗，ISP把它们一起压进屏幕能显示的范围。",
     ["Tone_mapping", "High-dynamic-range_imaging"], True),
    ("s11", "payoff", "最后压缩成JPEG，小光终于住进了你的相册。", ["JPEG"], True),
    ("s12", "payoff", "拍视频的时候，这一整套流程，每一帧只有大约三十三毫秒。", ["Frame_rate"], True),
    ("s13", "payoff", "你眨一次眼，大约零点一到零点四秒。这段时间里，它已经处理了三到十几帧。",
     ["Blinking", "Frame_rate"], True),
    ("s14", "callback", "所以，那三分之二的颜色，确实是猜的。只不过，猜得刚刚好。", ["Demosaicing"], True),
]

LEAD, TAIL, MIN_DUR = 0.15, 0.55, 3.4


CACHE = ROOT / "examples" / "isp_short" / "voice_durations.json"


def measure_voice() -> dict[str, float]:
    if CACHE.exists() and "--remeasure" not in sys.argv:
        cached = json.loads(CACHE.read_text())
        if cached.get("script") == [n for _, _, n, _, _ in SCRIPT]:
            return cached["dur"]
    """Synthesize every line once (sentence-level, same path as production) and return seconds."""
    from motionbrief.audio.mix import PAUSE, SENT, SR, _trim, read_audio
    from motionbrief.tts.provider import get_provider
    tts = get_provider()
    tmp = Path(tempfile.mkdtemp())
    items, owner = [], []
    for sid, _, narr, _, _ in SCRIPT:
        for k, m in enumerate(SENT.finditer(narr)):
            sent = m.group(0).strip()
            if sent:
                items.append((sent, tmp / f"{sid}_{k}.wav"))
                owner.append(sid)
    tts.synthesize_batch(items, "zh")
    dur: dict[str, float] = {}
    for (sent, p), sid in zip(items, owner):
        d = len(_trim(read_audio(p))) / SR
        dur[sid] = dur.get(sid, 0.0) + d + (PAUSE.get(sent[-1], 0.25) if sid in dur else 0.0)
    print(f"tts={tts.name}", {k: round(v, 2) for k, v in dur.items()}, file=sys.stderr)
    CACHE.write_text(json.dumps({"tts": tts.name, "script": [n for _, _, n, _, _ in SCRIPT], "dur": dur},
                                ensure_ascii=False, indent=1))
    return dur


def build(dur: dict[str, float]) -> dict:
    t = 0.0
    starts: dict[str, tuple[float, float]] = {}
    for sid, *_ in SCRIPT:
        d = max(MIN_DUR, round((LEAD + dur.get(sid, 2.0) + TAIL) * 30) / 30)
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

    def photon(sid, keys, moods=(("0", "happy"),), depth=2, look=None):
        p = {"keys": [[round(S[sid] + a * (E[sid] - S[sid]), 3), x, y, s] for a, x, y, s in keys],
             "moods": [[round(S[sid] + float(a) * (E[sid] - S[sid]), 3), m] for a, m in moods]}
        if look:
            p["look"] = look
        return vo("guide", "PhotonGuide", depth, **p)

    sc = []
    # s01 HOOK: the photo flips into one-colour tiles with question marks; "2/3 靠猜"
    sc.append(scene("s01", [vo("plate", "RawFramePlate", 1, mode="guess", cells=8, y=1000)],
                    typo=[("2/3 是猜的", "headline", "top", at("s01", 0.42))],
                    beats=[("plate", "entrance", at("s01", 0.0)), ("plate", "reveal", at("s01", 0.16)),
                           ("2/3 是猜的", "impact", at("s01", 0.42)), ("plate", "impact", at("s01", 0.42))],
                    cues=[("whoosh", S["s01"]), ("digital_blip", at("s01", 0.16)), ("bass_hit", at("s01", 0.42))],
                    cam=("push_in", 1.0, 1.06)))
    # s02 meet 小光 (personification)
    sc.append(scene("s02", [vo("rain", "ParticleStream", 0, mode="photons", count=46, seed=2),
                            photon("s02", [(0.0, 1240, 160, 1.0), (0.32, 540, 900, 1.6), (1.0, 540, 930, 1.7)],
                                   moods=(("0", "happy"),))],
                    typo=[("小光", "label", "top", at("s02", 0.55))],
                    beats=[("guide", "entrance", at("s02", 0.0)), ("guide", "impact", at("s02", 0.33)),
                           ("rain", "reveal", at("s02", 0.55)), ("小光", "reveal", at("s02", 0.55))],
                    cues=[("whoosh", at("s02", 0.02)), ("bass_hit", at("s02", 0.33)), ("ui_tick", at("s02", 0.55))],
                    trans="zoom_through"))
    # s03 lens -> sensor is colour-blind
    sc.append(scene("s03", [vo("plate", "RawFramePlate", 1, mode="mono", cells=8, y=1080),
                            photon("s03", [(0.0, 540, 160, 1.0), (0.22, 540, 1000, 0.9), (0.5, 540, 600, 1.2),
                                           (1.0, 540, 560, 1.2)],
                                   moods=(("0", "happy"), ("0.5", "worried")))],
                    typo=[("色盲", "headline", "top", at("s03", 0.55))],
                    beats=[("plate", "entrance", at("s03", 0.0)), ("plate", "reveal", at("s03", 0.22)),
                           ("guide", "impact", at("s03", 0.22)), ("色盲", "impact", at("s03", 0.55))],
                    cues=[("whoosh", S["s03"]), ("bass_hit", at("s03", 0.22)), ("ui_tick", at("s03", 0.55))],
                    trans="mask_reveal"))
    # s04 Bayer filters, green = half
    sc.append(scene("s04", [vo("plate", "RawFramePlate", 1, mode="bayer", cells=8, y=880)],
                    typo=[("绿色占一半", "headline", "top", at("s04", 0.62))],
                    beats=[("plate", "entrance", at("s04", 0.0)), ("plate", "reveal", at("s04", 0.35)),
                           ("绿色占一半", "impact", at("s04", 0.62))],
                    cues=[("whoosh", S["s04"]), ("digital_blip", at("s04", 0.35)), ("bass_hit", at("s04", 0.62))],
                    trans="match_cut", cam=("push_in", 1.0, 1.05)))
    # s05 RAW: one colour per pixel
    sc.append(scene("s05", [vo("raw", "TitleCard", 1, text="RAW", style="impact_reveal", anchor="center",
                               sub="每个像素 · 只有 1 种颜色"),
                            photon("s05", [(0.0, 300, 1450, 1.0), (1.0, 330, 1430, 1.0)],
                                   moods=(("0", "surprised"),), look=[1, -1])],
                    beats=[("raw", "entrance", at("s05", 0.0)), ("raw", "impact", at("s05", 0.12)),
                           ("guide", "entrance", at("s05", 0.3)), ("guide", "reveal", at("s05", 0.55))],
                    cues=[("whoosh", S["s05"]), ("bass_hit", at("s05", 0.12)), ("digital_blip", at("s05", 0.55))],
                    trans="zoom_through"))
    # s06 HERO REVEAL: ISP chip (Layer B with 2.5D fallback)
    chip = vo("chip", "ChipReveal", 1, "three", label="")
    chip.update({"materialStyle": {"type": "toon", "bands": 3, "gradientRamp": ["#EFE6FF", "#7C5CFF", "#2A2350"]},
                 "outline": {"method": "inverted_hull", "width": 0.03, "color": "#1A1452"},
                 "lightingPreset": "single_key_soft"})
    sc.append(scene("s06", [vo("stream", "ParticleStream", 0, mode="converge", count=70, seed=6), chip],
                    typo=[("ISP", "impact_reveal", "center", at("s06", 0.55))],
                    beats=[("chip", "entrance", at("s06", 0.05)), ("stream", "reveal", at("s06", 0.3)),
                           ("chip", "impact", at("s06", 0.55)), ("ISP", "impact", at("s06", 0.55))],
                    cues=[("riser", at("s06", 0.08)), ("bass_hit", at("s06", 0.55))],
                    trans="zoom_through", cam=("push_in", 1.0, 1.07), assetStyle="toon_3d", rq="hero",
                    proj="perspective", hints={"webglFallback": "svg", "frameCritical": True}))
    # s07 demosaic
    sc.append(scene("s07", [vo("plate", "RawFramePlate", 1, mode="demosaic", cells=8, y=1020)],
                    typo=[("1 · 去马赛克", "label", "top", at("s07", 0.05))],
                    beats=[("plate", "entrance", at("s07", 0.0)), ("plate", "reveal", at("s07", 0.4)),
                           ("plate", "impact", at("s07", 0.8))],
                    cues=[("whoosh", S["s07"]), ("ui_tick", at("s07", 0.05)), ("digital_blip", at("s07", 0.4)),
                          ("bass_hit", at("s07", 0.8))],
                    trans="mask_reveal"))
    # s08 denoise
    sc.append(scene("s08", [vo("night", "ParticleStream", 1, mode="denoise", count=170, seed=8)],
                    typo=[("2 · 降噪", "label", "top", at("s08", 0.04))],
                    beats=[("night", "entrance", at("s08", 0.0)), ("night", "reveal", at("s08", 0.45)),
                           ("night", "impact", at("s08", 0.82))],
                    cues=[("whoosh", S["s08"]), ("ui_tick", at("s08", 0.04)), ("riser", at("s08", 0.45)),
                          ("bass_hit", at("s08", 0.82))],
                    trans="match_cut", cam=("push_in", 1.0, 1.04)))
    # s09 white balance
    sc.append(scene("s09", [vo("wb", "ColorSweep", 1, mode="white_balance", **{"from": "#FF9A3C", "to": "#FFFFFF"})],
                    typo=[("3 · 白平衡", "label", "top", at("s09", 0.04))],
                    beats=[("wb", "entrance", at("s09", 0.0)), ("wb", "reveal", at("s09", 0.5)),
                           ("wb", "impact", at("s09", 0.85))],
                    cues=[("whoosh", S["s09"]), ("ui_tick", at("s09", 0.04)), ("digital_blip", at("s09", 0.5)),
                          ("bass_hit", at("s09", 0.85))],
                    trans="mask_reveal"))
    # s10 tone mapping
    sc.append(scene("s10", [vo("hdr", "ExposureMerge", 1)],
                    typo=[("4 · 色调映射", "label", "top", at("s10", 0.04))],
                    beats=[("hdr", "entrance", at("s10", 0.0)), ("hdr", "reveal", at("s10", 0.5)),
                           ("hdr", "impact", at("s10", 0.85))],
                    cues=[("whoosh", S["s10"]), ("ui_tick", at("s10", 0.04)), ("riser", at("s10", 0.3)),
                          ("bass_hit", at("s10", 0.85))],
                    trans="morph_fuse", cam=("push_in", 1.0, 1.05)))
    stages = ["去马赛克", "降噪", "白平衡", "色调映射", "JPEG"]
    # s11 JPEG: 小光 arrives in the album
    sc.append(scene("s11", [vo("pipe", "PipelineFlythrough", 1, stages=stages, focus=4, top=330),
                            photon("s11", [(0.0, 900, 420, 0.7), (0.5, 900, 1180, 0.7), (1.0, 540, 1460, 0.9)])],
                    typo=[("JPEG", "impact_reveal", "lower", at("s11", 0.5), round(E["s11"] - 0.6, 3))],
                    beats=[("pipe", "entrance", at("s11", 0.0)), ("pipe", "impact", at("s11", 0.5)),
                           ("JPEG", "impact", at("s11", 0.5)), ("guide", "reveal", at("s11", 0.75))],
                    cues=[("whoosh", S["s11"]), ("shutter", at("s11", 0.5)), ("bass_hit", at("s11", 0.5))],
                    trans="zoom_through"))
    # s12 33 ms
    sc.append(scene("s12", [vo("pipe", "PipelineFlythrough", 1, stages=stages, focus=-1, top=330, budget=False,
                               perStage=round((E["s12"] - S["s12"]) * 0.11, 3))],
                    typo=[("33 ms", "impact_reveal", "lower", at("s12", 0.62))],
                    beats=[("pipe", "entrance", at("s12", 0.0)), ("pipe", "reveal", at("s12", 0.3)),
                           ("33 ms", "impact", at("s12", 0.62))],
                    cues=[("whoosh", S["s12"]), ("riser", at("s12", 0.3)), ("bass_hit", at("s12", 0.62))],
                    trans="match_cut", cam=("pan", 1.0, 1.0)))
    # s13 blink vs frames
    sc.append(scene("s13", [vo("eye", "EyeBlinkFrames", 1, frames=12)],
                    typo=[("1 次眨眼 ≈ 3–12 帧", "label", "top", at("s13", 0.72))],
                    beats=[("eye", "entrance", at("s13", 0.0)), ("eye", "reveal", at("s13", 0.42)),
                           ("eye", "impact", at("s13", 0.72))],
                    cues=[("whoosh", S["s13"]), ("ui_tick", at("s13", 0.42)), ("bass_hit", at("s13", 0.72))],
                    trans="mask_reveal"))
    # s14 callback: the photo is whole again (loops to the hook visual)
    sc.append(scene("s14", [vo("plate", "RawFramePlate", 1, mode="photo", cells=8, y=1000),
                            photon("s14", [(0.0, 540, 2050, 1.0), (0.35, 760, 600, 1.1), (1.0, 760, 580, 1.1)],
                                   moods=(("0", "happy"),))],
                    typo=[("猜得刚刚好", "headline", "top", at("s14", 0.62))],
                    beats=[("plate", "entrance", at("s14", 0.0)), ("guide", "entrance", at("s14", 0.15)),
                           ("plate", "reveal", at("s14", 0.35)), ("猜得刚刚好", "impact", at("s14", 0.62)),
                           ("plate", "impact", at("s14", 0.62))],
                    cues=[("whoosh", S["s14"]), ("digital_blip", at("s14", 0.35)), ("bass_hit", at("s14", 0.62))],
                    trans="match_cut", cam=("pull_out", 1.05, 1.0)))
    total = E["s14"]
    tier = "micro" if total <= 40 else "core" if total <= 75 else "deep" if total <= 120 else "extended"
    return {"irVersion": "1.2.0",
            "video": {"id": "isp_v02", "title": "你的照片有三分之二是猜的：讲清 ISP", "aspect": "9:16", "w": 1080,
                      "h": 1920, "fps": 30, "visualIP": "cartoon-tech-v2", "durationTier": tier,
                      "productionLevel": "hero"},
            "palette": {"primary": ["#7C5CFF", "#22D3B6"], "accent": "#FFB547"},
            "scenes": sc}


if __name__ == "__main__":
    ir = build(measure_voice())
    out = ROOT / "fixtures" / "isp_v02.json"
    out.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}  duration={ir['scenes'][-1]['tEnd']:.2f}s tier={ir['video']['durationTier']}")
