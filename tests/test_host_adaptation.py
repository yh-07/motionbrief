# SPDX-License-Identifier: Apache-2.0
"""Host-adaptation pieces: O(n) ducking envelope, scene slicing + lossless join, GPU-object fallback plan."""
import json

import numpy as np
import pytest

from motionbrief.audio.mix import _moving_avg_same, reading_units
from motionbrief.render.backend import RenderPlan


@pytest.mark.parametrize("n,win", [(1000, 12), (999, 13), (5000, 1200), (50, 120)])
def test_moving_avg_matches_convolve(n, win):
    x = np.abs(np.random.default_rng(0).normal(size=n))
    np.testing.assert_allclose(_moving_avg_same(x, win), np.convolve(x, np.ones(win) / win, mode="same"),
                               atol=1e-12)


def test_local_plan_degrades_gpu_objects_without_webgl(monkeypatch):
    from motionbrief.agent import actions
    monkeypatch.setattr(actions, "probe", lambda: {"webgl": False, "webglRemote": False})
    plan = RenderPlan("s06", {"chip": "three", "stream": "svg"})
    local = actions._local_plan(plan)
    assert local.choices == {"chip": "svg", "stream": "svg"}
    assert [(d["object"], d["from"], d["to"]) for d in local.degradations] == [("chip", "three", "svg")]
    assert actions._local_plan(RenderPlan("s01", {"a": "svg"})).choices == {"a": "svg"}


@pytest.mark.render
def test_slices_join_to_the_whole_scene(tmp_path):
    from motionbrief.ir.models import load
    from motionbrief.paths import REPO_ROOT
    from motionbrief.render.backend import BACKENDS, plan_scene, segment_name
    from motionbrief.render.ffmpeg import concat_copy, ffprobe

    ir = load(REPO_ROOT / "fixtures/isp_v02.json")
    scene = ir.scene("s03")
    plan = plan_scene(scene)
    kw = dict(plan=plan, subtitles=[], png_every=0, max_frames=21)
    parts = []
    for k in range(3):
        res = BACKENDS["svg"].render_frames(ir, scene, tmp_path, segment=(k, 3), **kw)
        assert res["frames"] == 7
        parts.append(tmp_path / segment_name(scene.id, k, 3))
    joined = tmp_path / "joined.mp4"
    concat_copy(parts, joined)
    v = next(s for s in ffprobe(joined)["streams"] if s["codec_type"] == "video")
    assert int(v["nb_read_frames"]) == 21
    assert json.loads(json.dumps(plan.choices))  # plan stays JSON-serialisable for the remote job


def test_retime_keeps_boundary_beats_inside_frame_quantised_scenes():
    from motionbrief.ir.models import load
    from motionbrief.paths import REPO_ROOT
    from motionbrief.timing import retime
    ir = load(REPO_ROOT / "fixtures/isp_v3_trailer.json")
    timed, _ = retime(ir, {})
    for s in timed.scenes:
        for m in s.motionGrammar:
            assert s.tStart <= m.at <= s.tEnd, (s.id, m.at)


def test_fast_subtitles_borrow_silence_or_merge_without_overlap():
    from motionbrief.audio.mix import _relieve_fast_cues
    st = {"maxCharsPerSec": 9.0, "maxCharsPerLine": 14, "minDisplaySec": 0.6}
    for cues in ([(0.15, 1.10, "你拍的每一张照片里"), (1.10, 2.79, "有三分之二的颜色")],
                 [(10.0, 10.6, "替你猜出了颜色"), (10.6, 11.2, "擦掉了噪点"), (11.2, 12.0, "认出了光")]):
        out = _relieve_fast_cues(cues, st)
        assert all(reading_units(s) / (b - a) <= 9.0 + 1e-6 for a, b, s in out), out
        assert all(b <= nxt[0] + 1e-9 for (_, b, _), nxt in zip(out, out[1:])), out


def test_fast_subtitle_takes_boundary_from_slower_neighbour():
    from motionbrief.audio.mix import _relieve_fast_cues
    st = {"maxCharsPerSec": 9.0, "maxCharsPerLine": 14, "minDisplaySec": 0.6}
    cues = [(41.917, 43.997, "是ISP在几十毫秒里"), (43.997, 45.317, "替你猜出了颜色 擦掉了噪点"),
            (45.317, 47.172, "认出了光 保住了天空")]
    out = _relieve_fast_cues(cues, st)
    assert [s for *_, s in out] == [s for *_, s in cues]  # no merge needed: the boundary moved instead
    assert all(reading_units(s) / (b - a) <= 9.0 + 1e-6 for a, b, s in out), out
    assert abs(out[1][1] - 45.317) <= 0.3 + 1e-6 and out[1][1] == out[2][0]


def test_short_subtitle_reaches_min_display_without_overlap():
    from motionbrief.audio.mix import _relieve_fast_cues
    st = {"maxCharsPerSec": 9.0, "maxCharsPerLine": 14, "minDisplaySec": 0.6}
    out = _relieve_fast_cues([(10.0, 11.0, "需要大量数据"), (11.0, 11.5995, "去录"), (11.5995, 13.0, "一条一条地教")], st)
    assert all(b - a >= 0.6 - 1e-3 for a, b, _ in out), out
    assert all(b <= nxt[0] for (_, b, _), nxt in zip(out, out[1:])), out
