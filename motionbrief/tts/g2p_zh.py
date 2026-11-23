# SPDX-License-Identifier: Apache-2.0
"""Mandarin + embedded-English G2P for Kokoro v1.0 (REVIEW R-26).

Kokoro's Chinese voices were trained on phonemes from `misaki[zh]`. Feeding raw Chinese text
through an English phonemizer (what generic wrappers do) yields slow, robotic speech. We
split mixed text into Han / Latin runs: Han -> misaki ZHG2P, Latin -> a small IPA lexicon
(acronyms are spelled letter by letter, known words use their English pronunciation).
"""
from __future__ import annotations

import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path

LETTER = {"A": "ˈeɪ", "B": "bˈi", "C": "sˈi", "D": "dˈi", "E": "ˈi", "F": "ˈɛf", "G": "ʤˈi", "H": "ˈeɪʧ",
          "I": "ˈaɪ", "J": "ʤˈeɪ", "K": "kˈeɪ", "L": "ˈɛl", "M": "ˈɛm", "N": "ˈɛn", "O": "ˈO", "P": "pˈi",
          "Q": "kjˈu", "R": "ˈɑɹ", "S": "ˈɛs", "T": "tˈi", "U": "jˈu", "V": "vˈi", "W": "dˈʌbəlju",
          "X": "ˈɛks", "Y": "wˈaɪ", "Z": "zˈi"}
# aspirated pʰ: an unaspirated English p reads as "b" to Mandarin ears ("ISP" was heard as "ISB")
# RAW is said "ròu" in Chinese tech speech; the English ɹˈɔ was heard as "做"
WORDS = {"JPEG": "ʤˈeɪpɛɡ", "RAW": "ɻou̯↘", "HDR": "ˈeɪʧ dˈi ˈɑɹ", "ISP": "ˈaɪ ˈɛs pʰˈi"}
# product / model names read as English words (otherwise unknown Latin runs are spelled letter by letter)
WORDS.update({"SAYCAN": "sˈeɪkæn", "OPENAI": "ˈOpən ˈeɪ ˈaɪ", "LLAMA": "lˈɑmə", "GOOGLE": "ɡˈuɡəl",
              "ZERO": "zˈɪɹO", "ONE": "wˈʌn", "TWO": "tʰˈu", "THREE": "θɹˈi", "FOUR": "fˈɔɹ", "FIVE": "fˈaɪv",
              "SIX": "sˈɪks", "SEVEN": "sˈɛvən", "EIGHT": "ˈeɪt", "NINE": "nˈaɪn"})
# everyday technical words: read as English words, never spelled out
WORDS.update({"TOPS": "tˈɑps"})
# kept only where the lexicon lacks the word (TOKENS) or where the acronym rule (2-5 caps letters) would spell
# it out (RAM, SLAM, INT); everything else comes from the misaki lexicon in en_ipa()
WORDS.update({"TOKENS": "tˈOkᵊnz", "INT": "ˈɪnt", "RAM": "ɹˈæm", "SLAM": "slˈæm"})
_EN_DIGIT = "ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE".split()
_ZH_DIGIT = "零一二三四五六七八九"
_RUN = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


def normalize(text: str) -> str:
    """Spoken form of numbers and symbols before G2P (the narration/subtitles keep the written form):
    π0 -> 派零; model names with digits (RT-1) -> English digits; years (1988年) digit by digit;
    other numbers, decimals and percentages -> Chinese numerals (cn2an)."""
    text = text.replace("π", "派")
    text = re.sub(r"派(\d)", lambda m: "派" + _ZH_DIGIT[int(m.group(1))], text)
    text = re.sub(r"([A-Za-z]+)-?(\d)\b", lambda m: f"{m.group(1)} {_EN_DIGIT[int(m.group(2))]}", text)
    text = re.sub(r"(\d{4})\s*年", lambda m: "".join(_ZH_DIGIT[int(d)] for d in m.group(1)) + "年", text)
    if re.search(r"\d", text):
        import cn2an
        text = re.sub(r"(\d)\s+(?=[万亿千百])", r"\1", text)  # '15 万亿' -> '15万亿'
        text = cn2an.transform(text, "an2cn")
    return text


@lru_cache(maxsize=1)
def _lexicon() -> tuple[dict, ...]:
    """misaki's English lexicons (gold first, then silver), the phoneme style Kokoro's English voices use."""
    spec = importlib.util.find_spec("misaki")
    if spec is None or spec.origin is None:
        return ({}, {})
    data = Path(spec.origin).parent / "data"
    return tuple(json.loads((data / name).read_text(encoding="utf-8")) for name in ("us_gold.json", "us_silver.json"))


def _lookup(key: str) -> str | None:
    """Lower-case key -> phonemes. Entries keyed by part of speech use DEFAULT (else the first value); nulls skip."""
    for table in _lexicon():
        value = table.get(key)
        if isinstance(value, dict):
            value = value.get("DEFAULT") or next((v for v in value.values() if v), None)
        if value:
            return value
    return None


_VOICELESS = "ptkfθ"
_SIBILANT = "szʃʒʧʤ"
_EN_SUFFIXES = ("ing", "ed", "es", "s", "er")
_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")


def _spell(word: str) -> str:
    return " ".join(LETTER.get(c.upper(), "") for c in word)


def _stem_ph(base: str) -> str | None:
    """Stem pronunciation for a bare, e-restored (encod -> encode) or undoubled (mapp -> map) stem."""
    candidates = [base, base + "e"]
    if len(base) > 2 and base[-1] == base[-2]:
        candidates.append(base[:-1])
    return next((ph for ph in map(_lookup, candidates) if ph), None)


def _affix(suffix: str, stem: str) -> str:
    """Phonemes of an inflection, chosen by the stem's final sound."""
    last = stem[-1]
    if suffix == "ing":
        return "ɪŋ"
    if suffix == "er":
        return "əɹ"
    if suffix == "ed":
        return "ɪd" if last in "td" else "t" if last in _VOICELESS else "d"
    return "ɪz" if last in _SIBILANT else "s" if last in _VOICELESS else "z"


def _inflect(word: str) -> str | None:
    """Plural / 3rd person / -ed / -ing / -er of a known stem (word is lower-case)."""
    for suffix in _EN_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = _stem_ph(word[:-len(suffix)])
            if stem:
                return stem + _affix(suffix, stem)
    return None


def _word_ph(word: str) -> str | None:
    """Lexicon entry, else an inflected stem; no letter spelling."""
    return _lookup(word.lower()) or _inflect(word.lower())


def _compound(word: str) -> str | None:
    """Two-word compound (keyframe -> key + frame): the longest lexicon prefix of 3+ letters whose remainder
    (3+ letters) is also a word. Both halves are joined with a space."""
    for i in range(len(word) - 3, 2, -1):
        head, tail = _word_ph(word[:i]), _word_ph(word[i:])
        if head and tail:
            return f"{head} {tail}"
    return None


def _part_ph(part: str) -> str | None:
    """A word or CamelCase part: lexicon, morphology, then a compound split (no letter spelling)."""
    return _word_ph(part) or _compound(part.lower())


def en_ipa(word: str) -> str:
    """One English Latin-run token -> misaki-style phonemes (Kokoro's English phoneme set)."""
    w = word.strip()
    if w.upper() in WORDS:  # 1. curated readings (TOPS, JPEG, RAM, RAW, digit words, ...)
        return WORDS[w.upper()]
    if w.isupper():  # 2. all caps: 1-3 letters spelled (NPU, LLM, KV); longer ones are read if the lexicon has them
        if len(w) <= 3:
            return _spell(w)
        ph = _word_ph(w)  # TOKEN, CLIP read as words; LPDDR, NVME spelled
        if ph is None and len(w) > 5:
            ph = _compound(w.lower())
        return ph or _spell(w)
    ph = _word_ph(w)  # 3.-4. lexicon, then simple morphology
    if ph:
        return ph
    parts = _CAMEL.findall(w)  # 5. VisionTransformer, QFormer: each part (caps parts spelled)
    if len(parts) > 1:
        phones = [_spell(p) if p.isupper() else _part_ph(p) for p in parts]
        if all(phones):
            return " ".join(phones)
    ph = _compound(w.lower())  # keyframe -> key + frame
    if ph:
        return ph
    return _spell(w)  # 6. last resort


@lru_cache(maxsize=1)
def _jieba():
    import logging

    import jieba
    jieba.setLogLevel(logging.WARNING)
    return jieba


# Kokoro's vocabulary has only ASCII punctuation: full-width marks were silently dropped before, so the model
# never saw a comma and placed its own breaths (heard as "比，你眨" in an ASR round-trip).
PUNCT = {"，": ",", "、": ",", "。": ".", "．": ".", "！": "!", "？": "?", "：": ":", "；": ";",
         "（": "(", "）": ")", "“": '"', "”": '"', "《": '"', "》": '"', "—": "—", "…": "…"}
_HAN = re.compile("[一-鿿]+|[^一-鿿]+")


NUMERAL = set("零一二三四五六七八九十百千万亿两第")


def sandhi(chars: str, syl: list[str]) -> list[str]:
    """Mandarin tone sandhi on TONE3 syllables of one phrase (standard rules, applied across word boundaries):
    third-tone runs -> all but the last become 2nd; 一 -> 2nd before a 4th tone, 4th before 1st/2nd/3rd,
    unchanged in numbers/ordinals or phrase-final, neutral in reduplication (看一看); 不 -> 2nd before a 4th
    tone, neutral in X不X (好不好)."""
    tone = [int(x[-1]) if x[-1].isdigit() else 5 for x in syl]
    base = [x[:-1] if x[-1].isdigit() else x for x in syl]
    n = len(syl)
    for i, ch in enumerate(chars):
        nxt = tone[i + 1] if i + 1 < n else None
        redup = 0 < i < n - 1 and chars[i - 1] == chars[i + 1]
        if ch == "一":
            if redup:
                tone[i] = 5
            elif (nxt is None or (i and chars[i - 1] in NUMERAL) or (i + 1 < n and chars[i + 1] in NUMERAL)
                  or (i + 2 < n and chars[i + 1] == "点" and chars[i + 2] in NUMERAL)):  # 一点五 (decimal)
                tone[i] = 1
            else:
                tone[i] = 2 if nxt == 4 else 4
        elif ch == "不":
            tone[i] = 5 if redup else 2 if nxt == 4 else tone[i]
    i = 0
    while i < n:  # third-tone runs
        j = i
        while j < n and tone[j] == 3:
            j += 1
        for k in range(i, j - 1):
            tone[k] = 2
        i = max(j, i + 1)
    return [f"{b}{t}" for b, t in zip(base, tone)]


def _han_ipa(run: str) -> str:
    """Han run (one phrase: punctuation splits runs) -> Kokoro v1.0 IPA with tone sandhi across the WHOLE run,
    so it also applies between words (你|眨, 一|堆); words stay space-separated as in misaki's legacy path."""
    from misaki.zh import ZHG2P
    from pypinyin import Style, lazy_pinyin
    syl = lazy_pinyin(run, style=Style.TONE3, neutral_tone_with_five=True)
    if len(syl) != len(run):  # defensive: fall back to per-word conversion
        return " ".join(ZHG2P.word2ipa(w) for w in _jieba().lcut(run))
    syl = sandhi(run, syl)
    out, i = [], 0
    for w in _jieba().lcut(run, cut_all=False):
        out.append("".join(ZHG2P.py2ipa(py) for py in syl[i:i + len(w)]))
        i += len(w)
    return " ".join(out)


def phonemize(text: str) -> str:
    """Return a Kokoro (v1.0) phoneme string for mixed zh/en text."""
    text = normalize(text)
    out = []
    for run in _RUN.findall(text):
        if run[0].isascii() and run[0].isalpha():
            out.append(" " + en_ipa(run) + " ")
            continue
        for part in _HAN.findall(run):
            if "一" <= part[0] <= "鿿":
                out.append(_han_ipa(part))
            else:
                out.append("".join(PUNCT.get(ch, ch) for ch in part) + " ")
    return re.sub(r"\s+", " ", "".join(out)).strip()
