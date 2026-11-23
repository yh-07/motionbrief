# SPDX-License-Identifier: Apache-2.0
"""Sound direction: turn authored sound cues into the cues actually mixed (deterministic, recorded).

Rules (docs/BENCHMARK.md, round 4):
- Transitions are pitched and in key, chosen by the scene's transition type; never a noise whoosh.
- About half the cuts stay silent: match cuts / hard cuts are carried by the downbeat and the next
  shot's own entrance sounds, and a transition sound never repeats the previous one (it is dropped instead).
- Full impacts (with the noise click) only on a few structural moments; other slams become soft impacts.
The authored Scene IR is not modified; every decision lands in audio/sound_design.json.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from motionbrief.ir.models import SceneIR

MAX_IMPACTS = 5
TRANSITION_WINDOW = 0.35  # a whoosh this close to a scene start is that scene's transition sound
# only short, struck sounds on cuts: the pitch glides and swells (glide, swell, riser) read as a "woo" on every cut
BY_TRANSITION = {"zoom_through": "harp", "mask_reveal": "bloom", "morph_fuse": "bloom", "whip": "harp",
                 "match_cut": None, "cut": None}
SWEEPS = {"riser"}  # authored rising sweeps are dropped for the same reason
SWELL_SEC = 0.9
NOISE_TRANSITIONS = {"whoosh"}
ROLE_WEIGHT = {"hook": 2.0, "reveal": 2.0, "callback": 1.5, "payoff": 1.0}


@dataclass
class Cue:
    sfx: str
    at: float
    gainDb: float
    scene: str
    authored: str
    why: str


def _impact_rank(ir: SceneIR) -> set[tuple[str, float]]:
    """(scene, at) of the bass hits that stay full impacts: hero > hook/reveal > first payoff > callback."""
    seen_payoff = False
    scored = []
    for i, s in enumerate(ir.scenes):
        w = ROLE_WEIGHT.get(s.role, 0.0) + (3.0 if s.renderQuality == "hero" else 0.0)
        if s.role == "payoff" and not seen_payoff:
            w, seen_payoff = w + 1.0, True
        for c in s.soundCues:
            if c.sfx == "bass_hit":
                scored.append((-w, c.at, s.id))
    return {(sid, at) for _, at, sid in sorted(scored)[:MAX_IMPACTS]}


def resolve(ir: SceneIR) -> list[Cue]:
    keep_impact = _impact_rank(ir)
    out: list[Cue] = []
    prev_cut = None  # what the *previous* cut sounded like ("never the same cue twice in a row")
    prev_silent = False
    for s in ir.scenes:
        this_cut, had_cut = None, False
        for c in sorted(s.soundCues, key=lambda c: c.at):
            if c.sfx in NOISE_TRANSITIONS and abs(c.at - s.tStart) <= TRANSITION_WINDOW:
                had_cut = True
                want = BY_TRANSITION.get(s.transitionIn.type)
                if want is None and s.transitionIn.type == "match_cut" and prev_silent:
                    want = "harp"  # never two silent cuts in a row: a quiet in-key pluck carries the match
                if want is None:
                    out.append(Cue("", c.at, c.gainDb, s.id, c.sfx,
                                   f"silent: {s.transitionIn.type} rides the downbeat"))
                    continue
                if want == prev_cut:
                    out.append(Cue("", c.at, c.gainDb, s.id, c.sfx, f"silent: {want} would repeat the previous cut"))
                    continue
                at = max(0.0, s.tStart - SWELL_SEC) if want == "swell" else s.tStart
                gain = c.gainDb - (6 if want == "harp" else 2)
                out.append(Cue(want, at, gain, s.id, c.sfx, f"{s.transitionIn.type} -> in-key {want}"))
                this_cut = want
            elif c.sfx in NOISE_TRANSITIONS:
                out.append(Cue("", c.at, c.gainDb, s.id, c.sfx, "silent: mid-scene whoosh dropped"))
            elif c.sfx in SWEEPS:
                out.append(Cue("", c.at, c.gainDb, s.id, c.sfx, "silent: rising sweep dropped"))
            elif c.sfx == "bass_hit" and (s.id, c.at) not in keep_impact:
                out.append(Cue("soft_impact", c.at, c.gainDb - 3, s.id, c.sfx, "non-structural slam"))
            else:
                out.append(Cue(c.sfx, c.at, c.gainDb, s.id, c.sfx,
                               "structural impact" if c.sfx == "bass_hit" else "as authored"))
        prev_cut = this_cut  # a silent cut, or one carried by the scene's own entrance sound, resets it
        prev_silent = had_cut and this_cut is None
    return out


def summary(cues: list[Cue], duration: float, scenes: list[str] | None = None) -> dict:
    """Counts for the gates. `scenes` (ids in order) makes "repeat" mean *adjacent* cuts, as `resolve` does."""
    trans = [c for c in cues if c.authored in NOISE_TRANSITIONS and c.why != "silent: mid-scene whoosh dropped"]
    sounding = [c.sfx for c in trans if c.sfx]
    if scenes:
        by_scene = {c.scene: c.sfx for c in trans}
        seq = [by_scene.get(sid, "") for sid in scenes]
        repeats = sum(bool(a) and a == b for a, b in zip(seq, seq[1:]))
    else:
        repeats = sum(a == b for a, b in zip(sounding, sounding[1:]))
    return {"transitions": len(trans), "silentTransitions": len(trans) - len(sounding),
            "noiseWhooshesPerMin": round(60 * sum(c.sfx in NOISE_TRANSITIONS for c in cues) / max(duration, 1), 2),
            "fullImpacts": sum(c.sfx == "bass_hit" for c in cues),
            "repeatedTransitionCues": repeats,
            "cues": [asdict(c) for c in cues]}
