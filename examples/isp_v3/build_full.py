# SPDX-License-Identifier: Apache-2.0
"""Author the ISP v3 FULL cut (48 shots, ~4 min) Scene IR from the v3 storyboard + MEASURED voice durations.

Source: 《四个摄像头？讲清 ISP》分镜剧本 v3. One narration line per shot, verbatim. Each shot is
(problem -> method -> failure -> fix) carried by one main object whose entrance / reveal / impact beats
drive the picture; sound cues follow the storyboard order (tick -> blip -> bass_hit) on those beats and the
sound director (audio/sound_design.py) turns transitions into in-key cues.
Usage: python examples/isp_v3/build_full.py [--remeasure]  (writes fixtures/isp_v3_full.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_trailer import LEAD, MIN_DUR, TAIL, W  # noqa: E402  (same timing policy as the trailer)

CUT, ZOOM, MASK, MATCH, MORPH = "cut", "zoom_through", "mask_reveal", "match_cut", "morph_fuse"
RAIN = ("rain", "ParticleStream", 0, "svg", {"mode": "photons", "count": 40, "seed": 1})
CHIP = {"materialStyle": {"type": "toon", "bands": 3, "gradientRamp": ["#EFE6FF", "#7C5CFF", "#2A2350"]},
        "outline": {"method": "inverted_hull", "width": 0.03, "color": "#1A1452"}, "lightingPreset": "single_key_soft"}
STAGES = ["去马赛克", "降噪", "白平衡", "色调映射"]


def o(id_, comp, depth=1, renderer="svg", **props):
    return (id_, comp, depth, renderer, props)


# sid, role, narration, citations, transition, on-screen text [(text, style, anchor)], objects, cues, kw
# cues: storyboard order of tick / blip / bass / riser; beats: rev / imp fractions of the shot; kw extras
SHOTS = [
    # 一、冷开场
    ("s01", "hook", "你手机背后有四个摄像头。可没有一个，拍得出照片。", ["Image_processor", "Camera_phone"], CUT,
     [("拍不出照片？", "headline", "top")], [RAIN, o("lens", "LensArray", 1, count=4, y=1040)], "blip bass",
     dict(rev=0.18, imp=0.6, exit=0.5, cam=("push_in", 1.0, 1.05))),
    ("s02", "hook", "你相册里每一张照片，都不是拍下来的，是算出来的。", ["Computational_photography"], ZOOM,
     [("是算出来的", "headline", "top")], [o("plate", "RawFramePlate", mode="guess", cells=8, y=1000)], "blip bass",
     dict(rev=0.2, imp=0.64)),
    # 二、证据：RAW
    ("s03", "context", "不信？我们把手机的处理全部关掉，直接看传感器交出来的东西。", ["Raw_image_format"], MASK,
     [("不信？", "headline", "top")], [o("plate", "RawFramePlate", mode="raw", cells=8, y=1040)], "blip",
     dict(rev=0.45, imp=None)),
    ("s04", "context", "就是这个：又暗，又灰，还发绿，凑近一看，全是格子。", ["Raw_image_format", "Bayer_filter"], MATCH,
     [("暗 · 灰 · 发绿", "label", "top")], [o("plate", "RawFramePlate", mode="bayer", cells=8, y=1000)], "tick blip",
     dict(rev=0.55, imp=None, cam=("push_in", 1.0, 1.14))),
    ("s05", "context", "这叫RAW，传感器最原始的读数。", ["Raw_image_format"], ZOOM, [],
     [o("raw", "TitleCard", text="RAW", style="impact_reveal", anchor="center", sub="传感器最原始的读数")], "bass",
     dict(rev=None, imp=0.15)),
    # 三、原因：传感器是色盲
    ("s06", "context", "为什么是这样？因为传感器是个色盲。", ["Image_sensor"], MASK, [("色盲", "headline", "top")],
     [RAIN, ("guide", "PhotonGuide", 2, "svg", "GUIDE_DROP")], "blip bass", dict(rev=0.3, imp=0.62, target="guide")),
    ("s07", "mechanism", "每个像素就是一口小井，光子掉进来，变成电荷，它只会数：掉进来多少个。", ["Image_sensor"], MATCH,
     [("只会数光子", "headline", "top")], [o("wells", "PhotonWell", mode="count", y=880)], "tick blip bass",
     dict(rev=0.45, imp=0.82)),
    ("s08", "mechanism", "至于光是什么颜色，它完全不知道。", ["Image_sensor", "Bayer_filter"], CUT,
     [("不知道颜色", "headline", "top")], [o("wells", "PhotonWell", mode="gray", y=880)], "tick blip bass",
     dict(rev=0.35, imp=0.7)),
    ("s09", "mechanism", "工程师的办法是，给每个像素戴上一片彩色眼镜：红、绿、蓝，每个像素只能戴一种。", ["Bayer_filter"], MATCH,
     [("每个像素 只戴一种", "label", "top")], [o("wells", "PhotonWell", mode="filter", y=880)], "tick blip bass",
     dict(rev=0.3, imp=0.8)),
    ("s10", "mechanism", "而且绿色占了一半，因为人眼对绿光最敏感。", ["Bayer_filter"], MATCH, [("绿色占一半", "headline", "top")],
     [o("plate", "RawFramePlate", mode="bayer", cells=8, y=900)], "blip bass", dict(rev=0.2, imp=0.62)),
    # 四、反转
    ("s11", "reveal", "这就意味着：每个像素都只知道一种颜色，另外两种，它根本没见过。", ["Bayer_filter", "Demosaicing"], CUT,
     [("只知道 1 种颜色", "label", "top")], [o("plate", "RawFramePlate", mode="guess", cells=8, y=1000)], "tick blip",
     dict(rev=0.12, imp=None)),
    ("s12", "reveal", "你照片里三分之二的颜色，是算出来的。", ["Demosaicing"], ZOOM, [],
     [o("big", "TitleCard", text="2/3", style="impact_reveal", anchor="center", sub="的颜色 · 是算出来的"),
      ("guide", "PhotonGuide", 2, "svg", "GUIDE_CORNER")], "bass", dict(rev=None, imp=0.12)),
    # 五、主角登场
    ("s13", "reveal", "负责算的，是手机芯片里一块专用电路，叫ISP，图像信号处理器。", ["Image_processor"], ZOOM,
     [("ISP", "impact_reveal", "center")],
     [o("stream", "ParticleStream", 0, mode="converge", count=70, seed=13), ("chip", "ChipReveal", 1, "three", "CHIP")],
     "riser bass", dict(rev=0.3, imp=0.55, ent=0.05, target="chip", hero=True)),
    ("s14", "context", "它要把这堆格子变成照片，得连闯四关。", ["Image_processor"], MATCH, [("连闯四关", "headline", "top")],
     [o("pipe", "PipelineFlythrough", stages=STAGES, focus=-1, top=560, budget=False, perStage=0.5)], "blip bass",
     dict(rev=0.2, imp=0.8)),
    ("s15", "context", "而且顺序不能乱：前一关留下的错，后面会被一路放大。", ["Image_processor"], CUT,
     [("错误会一路放大", "label", "top")],
     [o("pipe", "PipelineFlythrough", stages=STAGES, focus=-1, top=580, budget=False, perStage=0.62, error=True)],
     "tick blip bass", dict(rev=0.25, imp=0.82)),
    # 六、第 1 关：去马赛克
    ("s16", "mechanism", "第一关，去马赛克。一个红色像素缺绿和蓝，怎么办？", ["Demosaicing"], MASK,
     [("① 去马赛克", "headline", "top")], [o("nb", "NeighborGrid", mode="ask", y=1000)], "tick", dict(rev=0.5, imp=None)),
    ("s17", "mechanism", "看邻居。上下左右都是绿的，取个平均，就猜出了绿色。", ["Demosaicing"], CUT,
     [("看邻居 · 取平均", "label", "top")], [o("nb", "NeighborGrid", mode="average", y=920)], "tick blip bass",
     dict(rev=0.3, imp=0.75)),
    ("s18", "mechanism", "平坦的地方，这招很灵。", ["Demosaicing"], MATCH, [("平坦处 · 很灵", "label", "top")],
     [o("plate", "RawFramePlate", mode="demosaic", cells=8, y=1000)], "tick blip", dict(rev=0.15, imp=None)),
    ("s19", "mechanism", "可一遇到栅栏、衬衫格子这种又细又密的纹理，邻居就会骗你，画面上冒出一道道彩虹纹。",
     ["Demosaicing", "Moiré_pattern"], MATCH, [("彩虹纹", "headline", "top")],
     [o("fence", "MoireFence", mode="artifact", y=980)], "blip bass", dict(rev=0.55, imp=0.82)),
    ("s20", "mechanism", "所以好的算法，得先判断边缘朝哪个方向，再顺着边去猜。", ["Demosaicing"], CUT,
     [("顺着边缘猜", "headline", "top")], [o("fence", "MoireFence", mode="fix", y=980)], "tick blip bass",
     dict(rev=0.25, imp=0.85)),
    # 七、第 2 关：降噪
    ("s21", "mechanism", "第二关，降噪。光不是一股水流，而是一粒一粒随机掉下来的。", ["Shot_noise"], MASK,
     [("② 降噪", "headline", "top")], [o("bars", "PhotonBars", mode="stream")], "tick blip", dict(rev=0.5, imp=None)),
    ("s22", "mechanism", "白天光子多，这点随机性看不出来。", ["Shot_noise"], CUT, [("白天：光子多", "label", "top")],
     [o("bars", "PhotonBars", mode="day")], "tick blip", dict(rev=0.5, imp=None)),
    ("s23", "mechanism", "到了夜里，每个像素只接到很少的光子，多一个少一个就是明显的差别，画面上全是彩色噪点。",
     ["Shot_noise", "Image_noise"], MATCH, [("满屏噪点", "headline", "top")], [o("bars", "PhotonBars", mode="night")],
     "blip bass", dict(rev=0.3, imp=0.72)),
    ("s24", "mechanism", "硬抹？细节一起被抹掉。", ["Noise_reduction"], CUT, [("细节没了", "headline", "top")],
     [o("burst", "BurstStack", mode="smear")], "blip bass", dict(rev=0.18, imp=0.8)),
    ("s25", "mechanism", "手机的办法是：连拍一串，逐张对齐，再叠在一起。", ["Computational_photography"], MATCH,
     [("连拍 · 对齐 · 叠加", "label", "top")], [o("burst", "BurstStack", mode="align")], "tick blip",
     dict(rev=0.15, imp=None)),
    ("s26", "mechanism", "随机的噪点会互相抵消，真实的画面会越叠越清楚。", ["Shot_noise"], CUT,
     [("噪点互相抵消", "label", "top")], [o("burst", "BurstStack", mode="stack")], "tick blip bass",
     dict(rev=0.12, imp=0.85)),
    ("s27", "payoff", "叠四张，噪点降一半；叠十六张，降到四分之一。", ["Shot_noise"], MATCH, [("16 张 → 1/4", "label", "top")],
     [o("burst", "BurstStack", mode="milestones")], "blip bass", dict(rev=0.1, imp=0.85)),
    ("s28", "payoff", "你夜里按快门要稳住一两秒，就是在等它拍完这一串。", ["Computational_photography"], CUT,
     [("等它拍完这一串", "label", "top")], [o("burst", "BurstStack", mode="shutter", y=760)], "tick blip bass",
     dict(rev=0.12, imp=0.85)),
    # 八、第 3 关：白平衡
    ("s29", "mechanism", "第三关，白平衡。同一张白纸，在烛光下是橙的，在阴天是蓝的。", ["Color_balance", "Color_temperature"],
     MASK, [("③ 白平衡", "headline", "top")], [o("wb", "WBCompare", mode="temps", y=1000)], "tick blip bass",
     dict(rev=0.6, imp=0.85)),
    ("s30", "mechanism", "你的大脑会自动纠正，你永远觉得它是白的。可传感器不会。", ["Color_constancy"], CUT,
     [("大脑会自动纠正", "label", "top")], [o("wb", "WBCompare", mode="brain", y=1010)], "tick blip bass",
     dict(rev=0.2, imp=0.78)),
    ("s31", "mechanism", "ISP必须从画面里猜：现在是什么光？然后把白纸改回白色。", ["Color_balance"], MATCH,
     [("猜出光源", "headline", "top")],
     [o("wb", "ColorSweep", mode="white_balance", **{"from": "#FF9A3C", "to": "#FFFFFF"})], "blip bass",
     dict(rev=0.45, imp=0.85)),
    ("s32", "mechanism", "猜错了，人脸发黄，雪地发蓝。", ["Color_balance"], CUT, [("黄脸 · 蓝雪", "label", "top")],
     [o("wb", "WBCompare", mode="wrong", y=980)], "tick blip bass", dict(rev=0.15, imp=0.78)),
    ("s33", "mechanism", "夜里最难，因为光源五颜六色，有的手机已经开始用训练过的模型来猜。", ["Color_balance"], MATCH,
     [("AI 来猜光源", "label", "top")], [o("wb", "WBCompare", mode="night", y=1020)], "tick blip bass",
     dict(rev=0.55, imp=0.88)),
    # 九、第 4 关：色调映射
    ("s34", "mechanism", "第四关，色调映射。传感器能分出几千级亮度，可JPEG每个颜色只有二百五十六级。",
     ["Tone_mapping", "Color_depth"], MASK, [("④ 色调映射", "headline", "top")], [o("tl", "ToneLadder", mode="squeeze")],
     "tick blip bass", dict(rev=0.5, imp=0.85)),
    ("s35", "mechanism", "几千级要压进二百五十六级，怎么压？平均压，暗部全黑，天空一片死白。", ["Tone_mapping"], CUT,
     [("天空死白", "headline", "top")], [o("tc", "ToneCard", mode="crush")], "blip bass", dict(rev=0.5, imp=0.8)),
    ("s36", "mechanism", "人眼对暗处更敏感，所以要给暗部多分一点台阶，亮部少分一点。", ["Gamma_correction"], MATCH,
     [("暗部多分台阶", "label", "top")], [o("tl", "ToneLadder", mode="spacing")], "tick blip bass",
     dict(rev=0.4, imp=0.85)),
    ("s37", "mechanism", "有的手机更聪明：拍的时候故意拍暗一点，先保住天空，再把暗处提亮。",
     ["High-dynamic-range_imaging", "Tone_mapping"], CUT, [("先拍暗 · 再提亮", "label", "top")],
     [o("tc", "ToneCard", mode="lift")], "tick blip bass", dict(rev=0.6, imp=0.88)),
    ("s38", "payoff", "这就是你照片里，天空和人脸能同时看清的原因。", ["Tone_mapping"], MORPH, [("亮暗都清楚", "headline", "top")],
     [o("hdr", "ExposureMerge")], "blip bass", dict(rev=0.3, imp=0.75)),
    # 十、Boss：四个摄像头
    ("s39", "reveal", "四关闯完，还没结束。最大的难题是：你有四个摄像头。", ["Camera_phone"], ZOOM,
     [("4 个摄像头", "headline", "top")], [RAIN, o("lens", "LensArray", 1, count=4, y=1040)], "blip bass",
     dict(rev=0.55, imp=0.75, cam=("push_in", 1.0, 1.1))),
    ("s40", "mechanism", "每颗镜头的传感器不一样，镜片不一样，颜色脾气也不一样。", ["Camera_phone"], MATCH,
     [("四颗镜头 · 四种脾气", "label", "top")], [o("zs", "ZoomSwitch", mode="grid")], "tick blip bass",
     dict(rev=0.4, imp=0.82)),
    ("s41", "mechanism", "你从零点六倍拉到五倍，画面在三颗镜头之间切换，颜色要是跳一下，你立刻就会发现。", ["Camera_phone"], CUT,
     [("颜色跳了", "headline", "top")], [o("zs", "ZoomSwitch", mode="zoom")], "blip bass", dict(rev=0.3, imp=0.88)),
    ("s42", "payoff", "所以有的芯片干脆让三套ISP同时开着，三颗摄像头一直在后台待命，你一拉变焦，直接切过去。",
     ["Image_processor"], MATCH, [("三套 ISP", "headline", "top")], [o("tri", "TripleISP")], "bass blip",
     dict(rev=0.4, imp=0.2)),
    # 十一、时间压力
    ("s43", "payoff", "还有时间。拍四K视频，每秒三十帧，这台流水线每秒要处理两亿多个像素。", ["4K_resolution", "Frame_rate"],
     ZOOM, [("2 亿+ 像素/秒", "headline", "lower")],
     [o("pipe", "PipelineFlythrough", stages=STAGES, focus=-1, top=380, budget=True, perStage=lambda span: span * 0.09)], "blip bass",
     dict(rev=0.3, imp=0.74, cam=("pan", 1.0, 1.0))),
    ("s44", "payoff", "每一帧，只有三十三毫秒，比你眨一次眼还快好几倍。", ["Frame_rate", "Blinking"], CUT,
     [("33 ms", "headline", "top"), ("眨眼 ≈ 100–400 ms", "label", "lower")], [o("eye", "EyeBlinkFrames", frames=12)],
     "bass blip", dict(rev=0.55, imp=0.25)),
    # 十二、回扣开头
    ("s45", "callback", "所以，下次按下快门，你可以想一想：那一刻，照片还不存在。", [], MASK, [("照片还不存在", "headline", "top")],
     [o("plate", "RawFramePlate", mode="bayer", cells=8, y=1000)], "tick blip",
     dict(rev=0.1, imp=None, text_at=0.7, cam=("push_in", 1.0, 1.09))),
    ("s46", "callback", "四个摄像头拍下的，只是一堆会骗人的格子。", [], CUT, [("会骗人的格子", "headline", "top")],
     [o("plate", "RawFramePlate", mode="guess", cells=8, y=1000)], "tick blip", dict(rev=0.15, imp=None, text_at=0.55)),
    ("s47", "callback", "是ISP在几十毫秒里，替你猜出了颜色，擦掉了噪点，认出了光，保住了天空。", ["Image_processor"], MATCH, [],
     [o("caps", "PipelineFlythrough", stages=["猜出颜色", "擦掉噪点", "认出光", "保住天空"], focus=-1, top=420,
        budget=False, perStage=lambda span: span * 0.15, runDelay=lambda span: span * 0.33 - 0.5)], "blip bass", dict(rev=0.33, imp=0.94)),
    ("s48", "callback", "照片，是算出来的。", [], MATCH, [("是算出来的", "headline", "top")],
     [RAIN, o("lens", "LensArray", 1, count=4, y=1040)], "blip bass", dict(rev=0.15, imp=0.4, cam=("pull_out", 1.06, 1.0))),
]
PRE_PAUSE = {"s12": 0.3, "s39": 0.3, "s48": 0.3}  # storyboard: ~0.3 s of silence before the reversal lines
CUE = {"tick": "ui_tick", "blip": "digital_blip", "bass": "bass_hit", "riser": "riser"}
CACHE = ROOT / "examples" / "isp_v3" / "voice_durations_full.json"


def measure_voice() -> dict[str, float]:
    import build_trailer
    build_trailer.SCRIPT = [(s[0], s[1], s[2], s[3], True) for s in SHOTS]
    build_trailer.CACHE = CACHE
    return build_trailer.measure_voice()


def build(dur: dict[str, float]) -> dict:
    t, S, E = 0.0, {}, {}
    ids = [s[0] for s in SHOTS]
    for i, sid in enumerate(ids):
        nxt = ids[i + 1] if i + 1 < len(ids) else None
        d = round(max(MIN_DUR, LEAD + dur.get(sid, 2.0) + TAIL + PRE_PAUSE.get(nxt, 0.0)) * 30) / 30
        S[sid], E[sid] = round(t, 3), round(t + d, 3)
        t += d

    def at(sid, f):
        return min(E[sid], max(S[sid], round(S[sid] + (E[sid] - S[sid]) * f, 3)))

    scenes = []
    for sid, role, narr, cites, trans, texts, objs, cues, kw in SHOTS:
        span = E[sid] - S[sid]
        rev, imp = kw.get("rev"), kw.get("imp")
        vos = []
        for id_, comp, depth, renderer, props in objs:
            if props == "CHIP":
                vos.append({"id": id_, "component": comp, "renderer": renderer, "depth": depth, "props": {"label": ""},
                            **CHIP})
                continue
            if props == "GUIDE_DROP":  # 小光 falls in from the sky, lands, turns worried
                props = {"keys": [[at(sid, 0.0), 540, 160, 1.0], [at(sid, 0.3), 540, 1000, 1.5], [at(sid, 1.0), 540, 980, 1.5]],
                         "moods": [[at(sid, 0.0), "happy"], [at(sid, 0.55), "worried"]]}
            elif props == "GUIDE_CORNER":
                props = {"keys": [[at(sid, 0.0), 260, 1500, 0.9], [at(sid, 1.0), 280, 1480, 0.9]],
                         "moods": [[at(sid, 0.0), "surprised"]], "look": [1, -1]}
            props = {k: (round(v(span), 3) if callable(v) else v) for k, v in props.items()}  # span-relative props
            vos.append({"id": id_, "component": comp, "renderer": renderer, "depth": depth, "props": props})
        target = kw.get("target", next(v["id"] for v in vos if v["id"] not in ("rain", "stream")))
        beats = [(target, "entrance", at(sid, kw.get("ent", 0.0)))]
        if rev is not None:
            beats.append((target, "reveal", at(sid, rev)))
        if kw.get("exit") is not None:
            beats.append((target, "exit", at(sid, kw["exit"])))
        if imp is not None:
            beats.append((target, "impact", at(sid, imp)))
        typo = []
        for k, (tx, style, anchor) in enumerate(texts):
            # the headline lands on the impact; shots without one show it mid-shot (a fresh visual event)
            ta = at(sid, kw["text_at"] if "text_at" in kw else imp if imp is not None and k == 0 else 0.55)
            if k == 0 and imp is not None:
                beats.append((tx, "impact", at(sid, imp)))
            typo.append({"text": tx, "style": style, "safeArea": anchor, "at": ta})
        snd = [("whoosh", S[sid])]
        for name in cues.split():
            when = {"tick": at(sid, 0.06), "blip": at(sid, rev if rev is not None else 0.3),
                    "bass": at(sid, imp if imp is not None else 0.6), "riser": at(sid, 0.08)}[name]
            snd.append((CUE[name], when))
        if "bass" in cues and imp is None:
            raise ValueError(f"{sid}: bass_hit needs an impact beat")
        hero = kw.get("hero", False)
        cam = kw.get("cam", ("push_in", 1.0, 1.07 if hero else 1.04))
        scenes.append({
            "id": sid, "tStart": S[sid], "tEnd": E[sid], "role": role, "narration": narr,
            "isFactual": bool(cites), "citations": [W + c for c in cites], "styleProfile": "cartoon-tech-v2",
            "assetStyle": "toon_3d" if hero else "toon_2_5d", "renderQuality": "hero" if hero else "standard",
            "cameraProjection": "perspective" if hero else "orthographic", "depthLayers": 3,
            "camera": {"move": cam[0], "from": cam[1], "to": cam[2], "easing": "easeOutExpo"},
            "typography": typo, "visualObjects": vos,
            "motionGrammar": [{"target": a, "grammar": b, "at": c} for a, b, c in beats],
            "soundCues": [{"sfx": a, "at": b} for a, b in sorted(snd, key=lambda x: x[1])],
            "transitionIn": {"type": trans}, "fallback2D": True,
            "rendererHints": {"webglFallback": "svg", "frameCritical": hero},
        })
    total = E[ids[-1]]
    return {"irVersion": "1.2.0",
            "video": {"id": "isp_v3_full", "title": "你手机的四个摄像头，没有一个会拍照：讲清 ISP", "aspect": "9:16",
                      "w": 1080, "h": 1920, "fps": 30, "visualIP": "cartoon-tech-v2",
                      "durationTier": "extended" if total > 120 else "deep", "productionLevel": "hero"},
            "palette": {"primary": ["#7C5CFF", "#22D3B6"], "accent": "#FFB547"},
            "scenes": scenes}


if __name__ == "__main__":
    ir = build(measure_voice())
    out = ROOT / "fixtures" / "isp_v3_full.json"
    out.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}  scenes={len(ir['scenes'])} duration={ir['scenes'][-1]['tEnd']:.2f}s")
