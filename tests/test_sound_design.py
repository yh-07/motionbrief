# SPDX-License-Identifier: Apache-2.0
"""Sound direction rules: in-key transitions, ~half the cuts silent, no repeats, few full impacts."""
import numpy as np

from motionbrief.audio import sfx, sound_design as sd
from motionbrief.ir.models import load
from motionbrief.paths import REPO_ROOT
from motionbrief.quality.deterministic import _sound_variety


def _v02():
    return load(REPO_ROOT / "fixtures/isp_v02.json")


def test_v02_cues_follow_the_rules():
    ir = _v02()
    sm = sd.summary(sd.resolve(ir), ir.duration, [s.id for s in ir.scenes])
    assert sm["noiseWhooshesPerMin"] == 0
    assert sm["fullImpacts"] <= sd.MAX_IMPACTS
    assert sm["repeatedTransitionCues"] == 0
    assert 0.3 <= sm["silentTransitions"] / sm["transitions"] <= 0.7
    assert _sound_variety(ir) == []


def test_structural_impacts_are_the_hero_and_hook():
    ir = _v02()
    full = {c.scene for c in sd.resolve(ir) if c.sfx == "bass_hit"}
    hero = {s.id for s in ir.scenes if s.renderQuality == "hero"}
    hook = {s.id for s in ir.scenes if s.role == "hook"}
    assert hero | hook <= full


def test_swell_ends_on_the_cut():
    ir = _v02()
    for c in sd.resolve(ir):
        if c.sfx == "swell":
            assert abs(c.at + sd.SWELL_SEC - ir.scene(c.scene).tStart) < 1e-6


def test_tonal_generators_are_finite_and_in_key():
    for name, gen in sfx.TONAL.items():
        x = gen(sfx.chord_at(3.0))
        assert np.isfinite(x).all() and 0.05 < np.max(np.abs(x)) < 1.0, name
    assert sfx.chord_at(0.0) == sfx.BED_CHORDS[0]
    assert sfx.chord_at(4 * 60 / sfx.BED_BPM + 0.01) == sfx.BED_CHORDS[1]


def test_reviewer_json_tolerates_fences():
    from motionbrief.quality.multimodal_review import _json
    assert _json('```json\n{"winner": "A"}\n```') == {"winner": "A"}
    assert _json("no json here") == {}
