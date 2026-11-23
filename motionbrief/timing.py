# SPDX-License-Identifier: Apache-2.0
"""Voice-first retiming (REVIEW R-19).

Mature practice (studio animatic workflow, Motion Canvas time events): the recorded
voiceover sets the timing and the animation follows it. The voice is never sped up to fit
a pre-authored timeline. After TTS we therefore *extend* any scene whose narration does
not fit, keep every beat at the same offset from its scene start, and shift later scenes.
The result is written as `scene_ir.timed.json`; all downstream steps render from it.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from motionbrief.ir.models import SceneIR, hard_range
from motionbrief.paths import load_tokens


class NarrationTooLong(ValueError):
    """ESCALATE: even after retiming the video breaks the hard duration bounds."""


@dataclass
class Retime:
    scene_id: str
    old_dur: float
    new_dur: float
    voice_dur: float


def _q(x: float, fps: int) -> float:
    """Quantise to whole frames so scene boundaries stay frame-exact."""
    return round(x * fps) / fps


def retime(ir: SceneIR, voice_durs: dict[str, float]) -> tuple[SceneIR, list[Retime]]:
    d = load_tokens()["duration"]
    lead, tail = d["voiceLeadSec"], d["voiceTailSec"]
    fps = ir.video.fps
    raw = copy.deepcopy(ir.model_dump(by_alias=True))
    shift, prev_end = 0.0, None
    changes: list[Retime] = []
    for s in raw["scenes"]:
        old_start, old_end = s["tStart"], s["tEnd"]
        dur = old_end - old_start
        need = lead + voice_durs.get(s["id"], 0.0) + tail
        new_dur = _q(max(dur, need), fps)
        if new_dur > dur + 0.5 / fps:  # ignore sub-frame rounding
            changes.append(Retime(s["id"], dur, new_dur, voice_durs.get(s["id"], 0.0)))
        # chained: a scene starts exactly where the previous one ends, so frame rounding cannot open a gap
        s["tStart"] = prev_end if prev_end is not None else _q(old_start + shift, fps)
        shift = s["tStart"] - old_start
        s["tEnd"] = _q(s["tStart"] + max(dur, new_dur), fps)
        # bounds are frame-quantised but times keep 4 decimals: clamp so a beat authored exactly on the scene
        # start (e.g. 4.533 vs a frame-exact 4.5333...) cannot fall a few microseconds outside its scene
        def place(t: float) -> float:
            return min(s["tEnd"], max(s["tStart"], round(t + shift, 4)))
        for key in ("motionGrammar", "soundCues"):
            for b in s[key]:
                b["at"] = place(b["at"])
        for ty in s["typography"]:
            for k in ("at", "until"):
                if ty.get(k) is not None:
                    ty[k] = place(ty[k])
        prev_end = s["tEnd"]
    timed = SceneIR.model_validate(raw)
    lo, hi = hard_range(landscape=timed.video.aspect == "16:9")  # 16:9 long-form runs to 900 s
    if timed.duration > hi:
        raise NarrationTooLong(f"narration needs {timed.duration:.1f}s > hard max {hi}s; shorten the script")
    return timed, changes
