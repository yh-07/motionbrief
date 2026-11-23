# SPDX-License-Identifier: Apache-2.0
"""Bilingual subtitles: English words are never cut, and no cue is a 1-2 character stub."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from motionbrief.audio.mix import VoiceSeg, build_subtitles, chunk_text, reading_units
from motionbrief.paths import load_tokens

MAX = load_tokens()["typography"]["subtitle"]["maxCharsPerLine"]


def _visible(s: str) -> str:
    return re.sub(r"\s", "", s)


def test_linear_projection_not_cut():
    chunks = chunk_text("这些数值，首先会经过一次 Linear Projection 映射。", MAX)
    assert any("Linear" in c for c in chunks), chunks
    assert any("Projection" in c for c in chunks), chunks
    assert _visible("".join(chunks)) == _visible("这些数值首先会经过一次LinearProjection映射")


def test_compression_intact():
    chunks = chunk_text("Visual Token Compression 越来越重要。", MAX)
    assert any("Compression" in c for c in chunks), chunks
    assert all(len(c) <= MAX or " " not in c for c in chunks), chunks


def test_long_chinese_splits_at_punctuation():
    text = "这是一个很长很长的中文句子，它需要被切分成多个短句，以便观众轻松阅读并且理解每一段的意思。"
    chunks = chunk_text(text, MAX)
    assert len(chunks) >= 3, chunks
    assert all(len(c) <= MAX for c in chunks), chunks
    assert "".join(chunks) == "这是一个很长很长的中文句子它需要被切分成多个短句以便观众轻松阅读并且理解每一段的意思"


def test_decimal_and_dotted_term_not_split():
    chunks = chunk_text("模型参数为 3.5 亿，使用 e.g. GPT-4.5 测试。", MAX)
    assert any("3.5" in c for c in chunks), chunks
    assert any("GPT-4.5" in c for c in chunks), chunks


def test_overlong_english_word_stands_alone():
    word = "Electroencephalographically"
    chunks = chunk_text(f"这是{word}结果。", MAX)
    assert word in chunks, chunks


def test_no_one_or_two_char_fragments():
    samples = [
        "这些数值，首先会经过一次 Linear Projection 映射。",
        "AI 技术，正在改变 Visual Token Compression 的方式。",
        "我们用 CLIP 编码图像，然后把 Patch 本身还不是最终表示。",
        "Visual Token Compression 越来越重要。",
    ]
    for text in samples:
        chunks = chunk_text(text, MAX)
        for c in chunks:
            v = _visible(c)
            assert len(v) >= 2, (text, chunks)
            assert not (v.isascii() and v.isalpha() and len(v) < 3), (text, chunks)


def _seg(text: str, dur: float) -> VoiceSeg:
    return VoiceSeg("s1", 0.0, dur, text, Path("unused.wav"), None)


def test_build_subtitles_no_short_cue_when_neighbours_can_absorb():
    min_d = load_tokens()["typography"]["subtitle"]["minDisplaySec"]
    cues = build_subtitles([_seg("这些数值，首先会经过一次 Linear Projection 映射。", 6.0)])
    assert cues, "no cues produced"
    for a, b, _ in cues:
        assert b - a >= min_d - 1e-3, cues


def test_reading_units_counts_latin_as_half():
    assert reading_units("Embedding") == 4.5
    assert reading_units("Patch 本身还不是") == 2.5 + 5  # five CJK characters after "Patch "
    assert reading_units("3.5 GB") == 3.0  # digits 3 and 5 at 1.0, GB at 0.5 each


def _srt_probs(tmp_path, aspect: str, cues: list[tuple[float, float, str]], dur: float) -> list[str]:
    from motionbrief.quality.deterministic import _srt_checks

    lines = []
    for i, (a, b, s) in enumerate(cues, 1):
        lines += [str(i), f"00:00:{a:06.3f} --> 00:00:{b:06.3f}".replace(".", ","), s, ""]
    srt = tmp_path / "t.srt"
    srt.write_text("\n".join(lines), encoding="utf-8")
    ir = SimpleNamespace(video=SimpleNamespace(aspect=aspect), duration=dur)
    scenes = [SimpleNamespace(id="s1", tStart=0.0, tEnd=dur, narration="")]
    return _srt_checks(ir, srt, scenes, load_tokens())


def test_line_length_is_aspect_aware(tmp_path):
    text = "一二三四五六七八九十一二三四五六"  # 16 characters
    landscape = _srt_probs(tmp_path, "16:9", [(0.0, 2.0, text)], 2.0)
    portrait = _srt_probs(tmp_path, "9:16", [(0.0, 2.0, text)], 2.0)
    assert not any("longer than" in p for p in landscape), landscape
    assert any("longer than" in p for p in portrait), portrait


def test_latin_word_reading_speed_uses_units(tmp_path):
    probs = _srt_probs(tmp_path, "16:9", [(0.0, 0.7, "Embedding")], 0.7)
    assert not any("reading speed" in p for p in probs), probs
