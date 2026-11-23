# SPDX-License-Identifier: Apache-2.0
import pytest

from motionbrief.ir.models import load
from motionbrief.timing import NarrationTooLong, retime


@pytest.fixture
def ir():
    return load("fixtures/isp_v01.json")


def test_fitting_voice_keeps_timeline(ir):
    timed, changes = retime(ir, {s.id: 1.0 for s in ir.scenes if s.narration})
    assert not changes and timed.duration == ir.duration


def test_long_voice_extends_scene_and_shifts_later_beats(ir):
    s03 = ir.scene("s03")
    timed, changes = retime(ir, {"s03": s03.duration + 2.0})
    assert [c.scene_id for c in changes] == ["s03"]
    delta = timed.duration - ir.duration
    assert delta > 2.0
    # beats inside s03 keep their offsets; s04 beats move by delta
    assert timed.scene("s03").motionGrammar[0].at == s03.motionGrammar[0].at
    assert timed.scene("s04").motionGrammar[0].at == pytest.approx(ir.scene("s04").motionGrammar[0].at + delta)
    assert timed.scene("s04").tStart == pytest.approx(timed.scene("s03").tEnd)


def test_absurd_narration_escalates(ir):
    with pytest.raises(NarrationTooLong):
        retime(ir, {"s01": 500.0})


def test_landscape_narration_may_run_past_the_shorts_limit(ir):
    wide = ir.model_copy(update={"video": ir.video.model_copy(update={"aspect": "16:9", "w": 1920, "h": 1080})})
    timed, _ = retime(wide, {"s01": 480.0})  # past the 420 s portrait limit, inside the 900 s landscape one
    assert timed.duration > 480
    with pytest.raises(NarrationTooLong):
        retime(wide, {"s01": 950.0})


def test_retimed_scenes_stay_contiguous_with_off_frame_voice_durations(ir):
    timed, _ = retime(ir, {s.id: s.duration + 0.0137 * (k + 1) for k, s in enumerate(ir.scenes)})
    for a, b in zip(timed.scenes, timed.scenes[1:]):
        assert b.tStart == a.tEnd
