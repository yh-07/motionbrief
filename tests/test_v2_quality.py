# SPDX-License-Identifier: Apache-2.0
"""Guards for the round-3 quality work (voice, visuals, script, subtitles)."""
import json
from pathlib import Path

import numpy as np
import pytest

from motionbrief.audio.mix import SR, align_chunks
from motionbrief.ir.models import load
from motionbrief.quality.deterministic import check_ir
from motionbrief.render.backend import plan_scene
from motionbrief.render.svg_canvas.scene import frame_svg

ROOT = Path(__file__).resolve().parent.parent


def test_v02_fixture_passes_g1():
    ir, rep = check_ir(json.loads((ROOT / "fixtures/isp_v02.json").read_text(encoding="utf-8")))
    assert rep.passed, rep.summary()
    assert ir.video.visualIP == "cartoon-tech-v2" and ir.scenes[-1].role == "callback"


def test_v2_has_no_ink_outline_and_has_gradients():
    ir = load(ROOT / "fixtures/isp_v02.json")
    s = ir.scene("s06")
    svg = frame_svg(ir, s, s.tStart + 2.6, 0, plan_scene(s).choices, [])
    assert "radialGradient" in svg and "linearGradient" in svg
    assert 'stroke="#0E0B1F"' not in svg  # v1 ink colour must not appear


def test_mascot_is_deterministic_and_blinks():
    ir = load(ROOT / "fixtures/isp_v02.json")
    s = ir.scene("s02")
    p = plan_scene(s).choices
    a = frame_svg(ir, s, s.tStart + 2.0, 1, p, [])
    assert a == frame_svg(ir, s, s.tStart + 2.0, 1, p, [])
    eyes = {frame_svg(ir, s, s.tStart + 2.0 + k / 30, 1, p, []).count('fill="#2A1B5C"') for k in range(0, 100)}
    assert len(eyes) > 1  # pupils disappear at some frame -> blink happens


def test_short_cue_never_flashes():
    x = np.concatenate([np.random.rand(int(0.35 * SR)) * 0.3, np.zeros(int(0.12 * SR)),
                        np.random.rand(int(2.0 * SR)) * 0.3])
    cues = align_chunks("结果，每个像素只记住了一种颜色。", x, 14)
    assert all(b - a >= 0.6 - 1e-6 for a, b, _ in cues) and all(len(c) <= 14 for *_, c in cues)


def test_g2p_handles_mixed_text():
    pytest.importorskip("misaki")
    from motionbrief.tts.g2p_zh import phonemize
    ph = phonemize("是一颗叫ISP的芯片")
    assert "ˈaɪ ˈɛs pʰˈi" in ph and "ISP" not in ph  # aspirated p, else heard as "ISB"


def test_g2p_tone_sandhi_and_ascii_punctuation():
    pytest.importorskip("misaki")
    from pypinyin import Style, lazy_pinyin

    from motionbrief.tts.g2p_zh import phonemize, sandhi

    def tones(w):
        return " ".join(sandhi(w, lazy_pinyin(w, style=Style.TONE3, neutral_tone_with_five=True)))
    assert tones("你好") == "ni2 hao3"
    assert tones("一堆") == "yi4 dui1" and tones("一个") == "yi2 ge4" and tones("第一关") == "di4 yi1 guan1"
    assert tones("不对") == "bu2 dui4" and tones("好不好") == "hao3 bu5 hao3"
    ph = phonemize("比你眨一次眼，还快。")
    assert "，" not in ph and "。" not in ph and "," in ph and ph.endswith(".")  # Kokoro vocab is ASCII-only
