# SPDX-License-Identifier: Apache-2.0
"""English tokens inside Chinese narration: misaki lexicon first, letter spelling only as last resort."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from motionbrief.tts.g2p_zh import LETTER, WORDS, en_ipa, phonemize


def _lexicon_entry(word: str) -> str:
    """Independent read of misaki's gold/silver lexicons (the source of truth the G2P must use)."""
    data = Path(importlib.util.find_spec("misaki").origin).parent / "data"
    for name in ("us_gold.json", "us_silver.json"):
        table = json.loads((data / name).read_text(encoding="utf-8"))
        value = table.get(word.lower())
        if isinstance(value, dict):
            value = value.get("DEFAULT") or next((v for v in value.values() if v), None)
        if value:
            return value
    raise AssertionError(f"{word!r} missing from misaki lexicons")


def _spelled(word: str) -> str:
    return " ".join(LETTER[c] for c in word.upper())


def test_lexicon_words_use_misaki_phonemes():
    for word in ["Patch", "patch", "Token", "Embedding", "Projector", "Transformer", "Encoder", "Vision",
                 "Attention", "Pixel"]:
        assert en_ipa(word) == _lexicon_entry(word), word
    assert en_ipa("Patch") == "pˈæʧ"
    assert en_ipa("Token") == "tˈOkᵊn"


def test_patches_is_lexicon_or_stem_plus_suffix():
    got = en_ipa("patches")
    assert got in {_lexicon_entry("patches"), _lexicon_entry("patch") + "ɪz"}
    assert got != _spelled("patches")


def test_inflected_word_from_stem_plus_suffix():
    # "encoded" is not in the lexicon: stem "encode" (e-restored) + -ed after a d sound -> ɪd
    assert en_ipa("encoded") == _lexicon_entry("encode") + "ɪd"


def test_tokens_curated_plural():
    assert en_ipa("Tokens") == WORDS["TOKENS"] == "tˈOkᵊnz"


def test_acronyms_are_spelled():
    for word in ["NPU", "LLM", "RGB", "OCR", "KV", "AI", "GPU", "LPDDR"]:
        assert en_ipa(word) == _spelled(word), word


def test_all_caps_words_read_when_in_lexicon():
    assert en_ipa("TOKEN") == _lexicon_entry("token")
    assert en_ipa("CLIP") == _lexicon_entry("clip")


def test_compound_split_into_two_words():
    expected = _lexicon_entry("key") + " " + _lexicon_entry("frame")
    assert en_ipa("keyframe") == expected
    assert en_ipa("Keyframe") == expected
    assert en_ipa("keyframes") == _lexicon_entry("key") + " " + _lexicon_entry("frames")  # keyframe + s
    # "dataset" is in misaki's lexicon, so the lexicon reading wins over the data + set split
    assert en_ipa("dataset") == _lexicon_entry("dataset")


def test_prefill_from_lexicon():
    assert en_ipa("prefill") == _lexicon_entry("prefill")
    assert en_ipa("Prefill") == _lexicon_entry("prefill")


def test_curated_custom_readings():
    assert en_ipa("RAW") == "ɻou̯↘"
    assert en_ipa("TOPS") == "tˈɑps"


def test_camel_case_joins_lexicon_parts():
    assert en_ipa("VisionTransformer") == "vˈɪʒən tɹænsfˈɔɹməɹ"


def test_unknown_word_is_spelled():
    assert en_ipa("Zqxv") == _spelled("Zqxv")


def test_phonemize_uses_lexicon_for_patch_in_chinese_sentence():
    out = phonemize("每一个这样的小方块，就叫一个 Patch。")
    assert "pˈæʧ" in out
    assert "pˈi ˈeɪ tˈi sˈi ˈeɪʧ" not in out


def test_multi_word_english_is_phonemized_word_by_word():
    out = phonemize("视觉 Vision Encoder")
    assert "vˈɪʒən ɪnkˈOdəɹ" in out
