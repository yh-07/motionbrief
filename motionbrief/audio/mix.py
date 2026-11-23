# SPDX-License-Identifier: Apache-2.0
"""Narration timing, subtitles (SRT) and multitrack mix -> loudness-normalised master."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from motionbrief.audio.sfx import SFX, SR, STEM_OF, music_bed
from motionbrief.ir.models import SceneIR
from motionbrief.paths import load_tokens, source_hash
from motionbrief.tts.provider import TTSProvider

VOICE_OFFSET = 0.15
STEMS = ["voice", "music", "impact", "transition", "fx"]


from motionbrief.timing import NarrationTooLong  # noqa: E402  (re-export for the taxonomy)


@dataclass
class VoiceSeg:
    scene_id: str
    start: float
    dur: float
    text: str
    wav: Path
    cues: list = None  # [(rel_start, rel_end, text)] aligned to real pauses in the audio


def read_audio(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def write_wav(path: Path, x: np.ndarray, channels: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(x, -1, 1).astype(np.float32).tobytes()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", str(channels), "-i", "-",
                    "-c:a", "pcm_s16le", str(path)], input=data, check=True)


SENT = re.compile(r"[^。！？!?]+[。！？!?]?")
PAUSE = {"。": 0.30, "！": 0.30, "？": 0.34, "!": 0.30, "?": 0.34}


def _trim(x: np.ndarray, th: float = 0.008) -> np.ndarray:
    nz = np.where(np.abs(x) > th)[0]
    if len(nz) == 0:
        return x[:0]
    return x[max(0, nz[0] - int(0.01 * SR)): nz[-1] + int(0.06 * SR)]


def _gaps(x: np.ndarray, min_gap: float = 0.07) -> list[tuple[float, float]]:
    """Silent gaps (start, end) in seconds, from a 10 ms RMS envelope."""
    hop = int(0.01 * SR)
    n = len(x) // hop
    if n == 0:
        return []
    env = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    quiet = env < max(0.012, 0.06 * np.percentile(env, 95))
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.01 >= min_gap and i > 0 and j < n:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out


def align_chunks(text: str, x: np.ndarray, max_chars: int) -> list[tuple[float, float, str]]:
    """Split one sentence into subtitle chunks and time each chunk at the REAL pauses in its audio.
    Falls back to character-proportional timing inside a chunk only when no pause exists."""
    chunks = chunk_text(text, max_chars)
    dur = len(x) / SR
    if len(chunks) <= 1:
        return [(0.0, dur, chunks[0] if chunks else text)]
    gaps = _gaps(x)
    total = sum(len(c) for c in chunks)
    bounds, acc = [], 0
    for c in chunks[:-1]:
        acc += len(c)
        guess = dur * acc / total
        best = min(gaps, key=lambda g: abs((g[0] + g[1]) / 2 - guess), default=None)
        if best and abs((best[0] + best[1]) / 2 - guess) < 0.6:
            bounds.append((best[0] + best[1]) / 2)
            gaps = [g for g in gaps if g[0] > best[1]]
        else:
            bounds.append(guess)
    edges = [0.0] + bounds + [dur]
    cues = [(edges[i], edges[i + 1], c) for i, c in enumerate(chunks)]
    # readability: a cue shorter than minDisplaySec is merged into a neighbour when the merged line still
    # fits; otherwise it borrows time from the longer neighbour (shift <= 0.3 s, stays near its audio).
    min_d = load_tokens()["typography"]["subtitle"]["minDisplaySec"]
    i = 0
    while i < len(cues) and len(cues) > 1:
        a, b, c = cues[i]
        if b - a >= min_d - 1e-6:
            i += 1
            continue
        nbrs = [j for j in (i + 1, i - 1) if 0 <= j < len(cues)]
        fit = [j for j in nbrs if len(cues[min(i, j)][2]) + 1 + len(cues[max(i, j)][2]) <= max_chars]
        if fit:
            j = fit[0]
            lo, hi = sorted((i, j))
            cues[lo:hi + 1] = [(cues[lo][0], cues[hi][1], cues[lo][2] + " " + cues[hi][2])]
            i = lo
            continue
        need = min(min_d - (b - a), 0.3)
        j = max(nbrs, key=lambda k: cues[k][1] - cues[k][0])
        if j == i + 1:
            cues[i] = (a, b + need, c)
            cues[j] = (cues[j][0] + need, cues[j][1], cues[j][2])
        else:
            cues[i] = (a - need, b, c)
            cues[j] = (cues[j][0], cues[j][1] - need, cues[j][2])
        i += 1
    return cues


def synthesize_narration(ir: SceneIR, work: Path, tts: TTSProvider, voice: str = "zh") -> list[VoiceSeg]:
    """Sentence-level synthesis (keeps natural intonation), batched (model loads once),
    joined with punctuation-dependent pauses; subtitles aligned to detected pauses."""
    st = load_tokens()["typography"]["subtitle"]
    adir = work / "audio" / "voice"
    adir.mkdir(parents=True, exist_ok=True)
    plan: list[tuple[str, str, Path]] = []
    for s in ir.scenes:
        for k, sent in enumerate(m.group(0).strip() for m in SENT.finditer(s.narration) if m.group(0).strip()):
            # the TTS frontend (G2P, sandhi, punctuation) is part of the key: fixing it must re-synthesize
            key = hashlib.sha256(f"{tts.name}|{voice}|{sent}|{source_hash('tts')}".encode()).hexdigest()[:12]
            plan.append((s.id, sent, adir / f"{s.id}_{k:02d}_{key}.wav"))
    todo = [(t, p) for _, t, p in plan if not p.exists()]
    if todo:
        tts.synthesize_batch(todo, voice)
    segs = []
    for s in ir.scenes:
        sents = [(t, p) for sid, t, p in plan if sid == s.id]
        if not sents:
            continue
        parts, cues, t = [], [], 0.0
        for i, (sent, p) in enumerate(sents):
            x = _trim(read_audio(p))
            if len(x) == 0:
                raise NarrationTooLong(f"{s.id}: TTS produced silence for {sent!r}")
            for a, b, c in align_chunks(sent, x, st["maxCharsPerLine"]):
                cues.append((t + a, t + b, c))
            parts.append(x)
            t += len(x) / SR
            if i < len(sents) - 1:
                gap = PAUSE.get(sent[-1], 0.25)
                parts.append(np.zeros(int(gap * SR)))
                t += gap
        x = np.concatenate(parts)
        out = adir / f"{s.id}_scene.wav"
        write_wav(out, x)
        segs.append(VoiceSeg(s.id, s.tStart + load_tokens()["duration"]["voiceLeadSec"], len(x) / SR,
                             s.narration, out, cues))
    return segs


_SPLIT = re.compile(r"(?<=[，。：；！？、:;!?])|(?<=[,.])(?![A-Za-z0-9])")  # "3.5" and "e.g" are not sentence breaks
_LATIN_RUN = re.compile(r"[A-Za-z0-9]+(?:[-.'][A-Za-z0-9]+)*")  # an English word, number or term: never cut


_BREAK_AFTER = set("的了着过和与及或")
_BREAK_BEFORE = set("每只都把让才再就在被将从")


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _cut_points(p: str) -> list[int]:
    """Legal break positions k (break before p[k]): never inside an English word, term or number."""
    inside: set[int] = set()
    for m in _LATIN_RUN.finditer(p):
        inside.update(range(m.start() + 1, m.end()))
    return [k for k in range(1, len(p)) if k not in inside]


def _best_break(p: str, max_chars: int) -> int:
    """Pick a line break near the middle, preferring spaces and CJK/Latin boundaries. An English word is never
    cut; a word longer than the line is cut off whole and stands alone. Returns len(p) if p is one such word."""
    n = len(p)
    valid = _cut_points(p)
    if not valid:
        return n
    cands = [k for k in valid if max(1, n - max_chars) <= k <= max_chars]  # both halves fit the line
    if not cands:
        cands = [k for k in valid if k <= max_chars] or valid[:1]
    best, best_score = cands[0], 1e9
    for k in cands:
        a, b = p[k - 1], p[k]
        score = abs(k - n / 2)
        if a in _BREAK_AFTER:
            score -= 2.5
        if b in _BREAK_BEFORE:
            score -= 2.5
        if a == " " or b == " " or _is_latin(a) != _is_latin(b):
            score -= 1.5
        if score < best_score:
            best, best_score = k, score
    return best


def _join(a: str, b: str) -> str:
    """Re-join two pieces; a space only where English meets other text."""
    return a + (" " if _is_latin(a[-1]) or _is_latin(b[0]) else "") + b


def _is_fragment(s: str) -> bool:
    """A chunk too small to read on its own: under 2 visible characters, or a pure-Latin stub under 3 letters."""
    v = re.sub(r"\s", "", s)
    return len(v) < 2 or (v.isascii() and v.isalpha() and len(v) < 3)


def chunk_text(text: str, max_chars: int) -> list[str]:
    parts = [p.strip() for p in _SPLIT.split(text) if p.strip()]
    out: list[str] = []
    for p in parts:
        p = p.rstrip("，。：；、,.:;")  # subtitle convention: drop trailing punctuation
        while len(p) > max_chars:
            k = _best_break(p, max_chars)
            head = p[:k].strip()
            if head:
                out.append(head)
            p = p[k:].strip()
        if p:
            if out and len(out[-1]) + len(p) + 1 <= max_chars // 2 + 3 and len(out[-1]) <= 4:
                out[-1] = _join(out[-1], p)
            else:
                out.append(p)
    # a fragment too small to read is folded into a neighbour
    merged = True
    while merged and len(out) > 1:
        merged = False
        for i, c in enumerate(out):
            if _is_fragment(c):
                j = i + 1 if i + 1 < len(out) else i - 1
                a, b = sorted((i, j))
                out[a:b + 1] = [_join(out[a], out[b])]
                merged = True
                break
    return out


def place_segments(segs: list[VoiceSeg], ir: SceneIR) -> list[VoiceSeg]:
    """Re-anchor voice segments to the (possibly retimed) scene starts."""
    lead = load_tokens()["duration"]["voiceLeadSec"]
    return [VoiceSeg(v.scene_id, ir.scene(v.scene_id).tStart + lead, v.dur, v.text, v.wav, v.cues) for v in segs]


def build_subtitles(segs: list[VoiceSeg], landscape: bool = False) -> list[tuple[float, float, str]]:
    st = load_tokens()["typography"]["subtitleLandscape" if landscape else "subtitle"]
    cues = []
    for seg in segs:
        if seg.cues:
            for a, b, c in seg.cues:
                cues.append((round(seg.start + a, 3), round(seg.start + max(b, a + st["minDisplaySec"]), 3), c))
            continue
        chunks = chunk_text(seg.text, st["maxCharsPerLine"])
        total = sum(len(c) for c in chunks)
        # merge any chunk that would flash by faster than minDisplaySec into its neighbour
        merged = True
        while merged and len(chunks) > 1:
            merged = False
            for i, c in enumerate(chunks):
                if seg.dur * len(c) / total >= st["minDisplaySec"]:
                    continue
                j = i + 1 if i + 1 < len(chunks) else i - 1
                a, b = sorted((i, j))
                joined = chunks[a] + " " + chunks[b]
                if len(joined) <= st["maxCharsPerLine"]:
                    chunks[a:b + 1] = [joined]
                    total = sum(len(x) for x in chunks)
                    merged = True
                    break
        t = seg.start
        for c in chunks:
            d = seg.dur * len(c) / total
            cues.append((round(t, 3), round(t + max(d, st["minDisplaySec"]), 3), c))
            t += d
    # make strictly non-overlapping
    for i in range(len(cues) - 1):
        a, b, s = cues[i]
        if b > cues[i + 1][0]:
            cues[i] = (a, cues[i + 1][0], s)
    return _relieve_fast_cues(cues, st)


SUB_HOLD_MAX = 0.6   # a line may stay up this long after its words end (standard subtitling practice)
SUB_LEAD_MAX = 0.2   # ...and appear this much before they start
SUB_GAP = 0.08       # keep the screen clear briefly between consecutive lines
SUB_SHIFT_MAX = 0.3  # max a shared boundary may move into a slower neighbour (stays near its audio)


_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")


def reading_units(s: str) -> float:
    """Reading load in Chinese-character units: CJK characters and digits 1.0, each Latin letter 0.5, spaces and
    punctuation 0. Chars-per-second limits use this; line length still counts len()."""
    n = 0.0
    for ch in s:
        if _CJK.match(ch) or ch.isdecimal():
            n += 1.0
        elif ch.isalpha():
            n += 0.5
    return n


def _split_fast_cues(cues: list[tuple[float, float, str]], cps: float) -> list[tuple[float, float, str]]:
    """A cue faster than cps is cut at the punctuation nearest its middle; the two halves share its time by length."""
    out = []
    for a, b, s in cues:
        idx = [i for i, ch in enumerate(s) if ch in "，。！？；,.!?" and 3 <= i < len(s) - 3]
        if reading_units(s) / (b - a) > cps and idx:
            m = min(idx, key=lambda i: abs(i - len(s) / 2))
            cut = round(a + (b - a) * (m + 1) / len(s), 3)
            out += [(a, cut, s[:m + 1]), (cut, b, s[m + 1:])]
        else:
            out.append((a, b, s))
    return out


def _relieve_fast_cues(cues: list[tuple[float, float, str]], st: dict) -> list[tuple[float, float, str]]:
    """Lines the eye can't read in time (> maxCharsPerSec) borrow display time from the silence around them:
    first hold into the following gap, then lead into the preceding one. If the phrases run back to back (no
    silence to borrow), merge with the neighbour when both fit on one line. Speech timing is unchanged."""
    cps, width = st["maxCharsPerSec"], st["maxCharsPerLine"]
    out = _split_fast_cues(list(cues), cps)
    i = 0
    while i < len(out):
        a, b, s = out[i]
        need = max(reading_units(s) / cps, st["minDisplaySec"]) - (b - a) + 2e-3  # readable AND long enough
        if need > 0:
            nxt = out[i + 1][0] - SUB_GAP if i + 1 < len(out) else b  # never hold past the last words / video end
            hold = max(0.0, min(need, SUB_HOLD_MAX, nxt - b))
            prv = out[i - 1][1] + SUB_GAP if i else 0.0
            lead = max(0.0, min(need - hold, SUB_LEAD_MAX, a - prv))
            a, b = round(a - lead, 3), round(b + hold, 3)
            out[i] = (a, b, s)
            # back-to-back phrases: move the boundary into a neighbour that reads with room to spare
            for j in (i + 1, i - 1):
                need = max(reading_units(s) / cps, st["minDisplaySec"]) - (b - a) + 2e-3  # readable AND long enough
                if need <= 0 or not 0 <= j < len(out):
                    continue
                ja, jb, js = out[j]
                slack = (jb - ja) - max(reading_units(js) / cps, st["minDisplaySec"]) - 1e-3
                move = max(0.0, min(need, SUB_SHIFT_MAX, slack))
                if move and j > i and abs(ja - b) < 1e-6:
                    b = round(b + move, 3)
                    out[j] = (b, jb, js)
                elif move and j < i and abs(jb - a) < 1e-6:
                    a = round(a - move, 3)
                    out[j] = (ja, a, js)
                out[i] = (a, b, s)
            if reading_units(s) / (b - a) > cps or b - a < st["minDisplaySec"]:
                for j in (i + 1, i - 1):  # prefer reading forward
                    if 0 <= j < len(out) and len(out[min(i, j)][2]) + 1 + len(out[max(i, j)][2]) <= width:
                        lo, hi = sorted((i, j))
                        out[lo:hi + 1] = [(out[lo][0], out[hi][1], out[lo][2] + " " + out[hi][2])]
                        i = lo - 1  # re-check the merged line
                        break
        i += 1
    for k in range(len(out) - 1):  # rounding may leave a sub-ms overlap: the next line starts when this one ends
        if out[k][1] > out[k + 1][0]:
            out[k + 1] = (out[k][1], max(out[k + 1][1], out[k][1]), out[k + 1][2])
    return out


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues: list[tuple[float, float, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{s}\n\n" for i, (a, b, s) in enumerate(cues, 1)),
                    encoding="utf-8")


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    def sec(x: str) -> float:
        h, m, rest = x.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    cues = []
    for block in path.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = block.strip().splitlines()
        if len(lines) >= 3:
            a, b = [p.strip() for p in lines[1].split("-->")]
            cues.append((sec(a), sec(b), "\n".join(lines[2:])))
    return cues


def _moving_avg_same(x: np.ndarray, win: int) -> np.ndarray:
    """== np.convolve(x, ones(win)/win, "same") in O(n) via prefix sums (direct conv is O(n*win))."""
    if len(x) < win:  # "same" then returns len(win); not worth special-casing
        return np.convolve(x, np.ones(win) / win, mode="same")
    c = np.concatenate(([0.0], np.cumsum(x)))
    k = np.arange(len(x)) + (win - 1) // 2  # index into the full convolution
    return (c[np.minimum(k, len(x) - 1) + 1] - c[np.maximum(k - win + 1, 0)]) / win


def analyze(ir: SceneIR, work: Path) -> dict:
    """We cannot listen, so measure: per-scene RMS of master and each stem + a spectrogram picture
    (logs/spectrum.png) to look at. Written to audio/analysis.json."""
    def db(x: np.ndarray) -> float:
        return round(float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)), 1) if len(x) else -180.0

    tracks = {"master": work / "audio" / "narration_mix.wav",
              **{k: work / "audio" / "stems" / f"{k}.wav" for k in STEMS}}
    data = {k: read_audio(p) for k, p in tracks.items() if p.exists()}
    scenes = [{"scene": s.id, "role": s.role,
               **{k: db(x[int(s.tStart * SR): int(s.tEnd * SR)]) for k, x in data.items()}} for s in ir.scenes]
    m = [s["master"] for s in scenes]
    out = {"perSceneRmsDb": scenes, "masterSpreadDb": round(max(m) - min(m), 1) if m else 0.0}
    (work / "audio" / "analysis.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (work / "logs").mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tracks["master"]), "-lavfi",
                    "showspectrumpic=s=1600x600:legend=1:scale=log", str(work / "logs" / "spectrum.png")], check=True)
    return out


def mix(ir: SceneIR, segs: list[VoiceSeg], work: Path) -> dict:
    """Lay stems, duck music under voice, two-pass loudnorm to target LUFS."""
    total = ir.duration
    n = int(total * SR) + 1
    stems = {k: np.zeros(n) for k in STEMS}
    for seg in segs:
        x = read_audio(seg.wav)
        i0 = int(seg.start * SR)
        stems["voice"][i0:i0 + len(x)] += x[: n - i0] * 0.9
    landscape = ir.video.aspect == "16:9"  # landscape bed has a rhythm section and sits a little louder
    bed = music_bed(total, groove=landscape)[:n]
    stems["music"][:len(bed)] = bed * (0.35 if landscape else 0.25)  # -6 dB: the bed stays well under the voice
    from motionbrief.audio import sound_design
    from motionbrief.audio.sfx import TONAL, chord_at, reverb
    cache = {k: reverb(f(), 1.0, 0.18, seed=3) for k, f in SFX.items()}
    cues = sound_design.resolve(ir)
    (work / "audio" / "sound_design.json").write_text(
        json.dumps(sound_design.summary(cues, total, [s.id for s in ir.scenes]), ensure_ascii=False, indent=2),
        encoding="utf-8")
    for cue in cues:
        if not cue.sfx:  # deliberately silent cut
            continue
        # tonal cues take the notes of the chord sounding at the cut (swells *end* on it)
        src = reverb(TONAL[cue.sfx](chord_at(cue.at + (sound_design.SWELL_SEC if cue.sfx == "swell" else 0))),
                     1.0, 0.18, seed=3) if cue.sfx in TONAL else cache[cue.sfx]
        x = src * (10 ** (cue.gainDb / 20)) * 0.6
        i0 = int(cue.at * SR)
        seg = x[: max(0, n - i0)]
        stems[STEM_OF[cue.sfx]][i0:i0 + len(seg)] += seg
    # broadcast voice chain: rumble cut, gentle compression, presence lift, tiny room
    raw_v = work / "audio" / "voice_raw_stem.wav"
    write_wav(raw_v, stems["voice"])
    proc_v = work / "audio" / "voice_proc_stem.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_v), "-af",
                    "highpass=f=75,acompressor=threshold=-20dB:ratio=3:attack=6:release=90:makeup=2,"
                    "equalizer=f=3200:t=q:w=1.2:g=2.5,equalizer=f=250:t=q:w=1:g=-1.5",
                    "-ar", str(SR), "-ac", "1", str(proc_v)], check=True)
    pv = read_audio(proc_v)
    stems["voice"][:] = 0
    stems["voice"][: min(n, len(pv))] = pv[:n]
    stems["voice"] = reverb(stems["voice"], 0.5, 0.06, seed=5)
    # sidechain-ish ducking: music -8 dB while voice is active (smoothed)
    env = np.abs(stems["voice"])
    win = int(SR * 0.25)
    env = _moving_avg_same(env, win)
    duck = 1 - 0.6 * np.clip(env / 0.02, 0, 1)
    stems["music"] *= duck
    bad = [k for k, x in stems.items() if not np.isfinite(x).all()]
    if bad:  # one NaN would turn the whole master silent after normalisation
        raise ValueError(f"non-finite samples in stems {bad}")
    sdir = work / "audio" / "stems"
    for k, x in stems.items():
        write_wav(sdir / f"{k}.wav", x)
    master = sum(stems.values())
    pre = work / "audio" / "premaster.wav"
    write_wav(pre, master / max(1.0, np.max(np.abs(master)) / 0.95))
    tok = load_tokens()["audio"]
    target = tok["targetLUFS"]
    # pass 1: measure
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(pre), "-af",
                        f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    m = json.loads(r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1])
    out = work / "audio" / "narration_mix.wav"
    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(pre), "-af", af, "-ar", str(SR), "-ac", "2", str(out)],
                   check=True)
    # deliverable: narration-only audio
    narr = work / "audio" / "narration.wav"
    write_wav(narr, stems["voice"])
    return {"master": str(out), "narration": str(narr), "stems": {k: str(sdir / f"{k}.wav") for k in STEMS},
            "loudnormPass1": m}
