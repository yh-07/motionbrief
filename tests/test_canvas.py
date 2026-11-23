# SPDX-License-Identifier: Apache-2.0
import pytest

from motionbrief.render.svg_canvas.canvas import Canvas, canvas_for


def test_portrait_canvas_keeps_legacy_integers():
    c = canvas_for("9:16")
    assert (c.w, c.h, c.cx, c.cy) == (1080, 1920, 540, 960)
    assert isinstance(c.cx, int) and isinstance(c.cy, int)


def test_landscape_canvas():
    c = canvas_for("16:9")
    assert (c.w, c.h, c.cx, c.cy) == (1920, 1080, 960, 540)


def test_unknown_aspect_rejected():
    with pytest.raises(KeyError):
        canvas_for("1:1")


def test_video_aspect_drives_size():
    from motionbrief.ir.models import Video

    v = Video(id="x", title="t", aspect="16:9", w=1920, h=1080)
    assert (v.w, v.h) == (1920, 1080)
    with pytest.raises(ValueError):
        Video(id="x", title="t", aspect="16:9", w=1080, h=1920)


def test_ctx_carries_canvas():
    from motionbrief.render.svg_canvas.components import Ctx
    from motionbrief.render.svg_canvas.easing import Beats

    c = Ctx(t=0.0, t0=0.0, t1=1.0, frame=0, props={}, beats=Beats([], 0.0), palette={}, tokens={},
            canvas=canvas_for("16:9"))
    assert c.canvas.w == 1920


def test_landscape_frame_has_landscape_viewbox():
    from motionbrief.ir.models import load
    from motionbrief.paths import REPO_ROOT
    from motionbrief.render.backend import plan_scene
    from motionbrief.render.svg_canvas.scene import frame_svg

    ir = load(REPO_ROOT / "fixtures/isp_v02.json")
    ir.video.aspect, ir.video.w, ir.video.h = "16:9", 1920, 1080
    scene = ir.scenes[0]
    svg = frame_svg(ir, scene, scene.tStart + 0.5, 15, plan_scene(scene).choices, [])
    assert 'viewBox="0 0 1920 1080"' in svg


def test_landscape_allows_longform_duration():
    from motionbrief.ir.models import hard_range

    assert hard_range(landscape=True) == (15.0, 900.0)
    assert hard_range() == (15.0, 420.0)


def test_chapter_card_defaults_to_landscape_only():
    from motionbrief.ir.models import load
    from motionbrief.paths import REPO_ROOT
    from motionbrief.render.backend import plan_scene
    from motionbrief.render.svg_canvas.scene import frame_svg

    ir = load(REPO_ROOT / "fixtures/isp_v02.json")
    scene = ir.scenes[0]
    scene.chapter = "一、核心"
    plan = plan_scene(scene).choices
    assert "一、核心" not in frame_svg(ir, scene, scene.tStart + 0.5, 15, plan, [])
    ir.video.aspect, ir.video.w, ir.video.h = "16:9", 1920, 1080
    assert "一、核心" not in frame_svg(ir, scene, scene.tStart + 0.5, 15, plan, [])  # 82 s: too short for cards
    ir.scenes[-1].tEnd = 130.0  # long-form: cards on by default
    assert "一、核心" in frame_svg(ir, scene, scene.tStart + 0.5, 15, plan, [])
    assert "一、冷开场" not in frame_svg(ir, scene, scene.tStart + 3.0, 90, plan, [])


def test_object_slots_none_on_portrait_and_one_column_each_on_landscape():
    from motionbrief.render.svg_canvas.scene import _object_slots

    assert _object_slots(canvas_for("9:16"), 3) is None
    slots = _object_slots(canvas_for("16:9"), 2)
    assert len(slots) == 2
    s, dx_left = slots[0]
    _, dx_right = slots[1]
    assert dx_left < 0 < dx_right and abs(dx_left + dx_right) < 1e-9  # symmetric about the centre
    assert s * 1080 <= 1920 / 2  # a portrait object never overflows its column


def test_landscape_placement_keeps_portrait_band_centred_and_above_subtitles():
    import re

    from motionbrief.render.svg_canvas.scene import LANDSCAPE_AREA, _object_slots, _place_landscape

    canvas = canvas_for("16:9")
    slot = _object_slots(canvas, 1)[0]
    tr = re.search(r'translate\(([-\d.]+),([-\d.]+)\) rotate\([-\d.]+\) scale\(([-\d.]+)',
                   _place_landscape("<rect/>", canvas, slot, LANDSCAPE_AREA, False))
    x0, y0, s = map(float, tr.groups())  # the band centre (540, 910) lands here
    assert abs(x0 - canvas.cx) < 1e-6
    assert y0 + s * (1400 - 910) <= 800 + 0.5  # band bottom stays clear of the subtitle box (~916)
    assert y0 - s * (910 - 420) >= 100 - 0.5


def test_compile_landscape_plan_sets_canvas_and_chapter():
    import json

    from motionbrief.content.shots import compile_plan
    from motionbrief.paths import REPO_ROOT

    plan = json.loads((REPO_ROOT / "examples/isp_v3/plan_full.json").read_text(encoding="utf-8"))
    plan["video"]["aspect"] = "16:9"
    plan["shots"][0]["chapter"] = "一、冷开场"
    dur = json.loads((REPO_ROOT / "examples/isp_v3/voice_durations_full.json").read_text(encoding="utf-8"))["dur"]
    ir = compile_plan(plan, dur)
    assert (ir["video"]["aspect"], ir["video"]["w"], ir["video"]["h"]) == ("16:9", 1920, 1080)
    assert ir["video"]["durationTier"] != "longform"  # longform tier starts at 480 s; this plan is shorter
    assert ir["scenes"][0]["chapter"] == "一、冷开场"
    assert "chapter" not in ir["scenes"][1]


def test_landscape_system_prompt_is_long_form():
    from motionbrief.content.storyboard import SYSTEM, SYSTEM_LANDSCAPE

    assert "16:9 long-form" in SYSTEM_LANDSCAPE and "design space" in SYSTEM_LANDSCAPE
    assert "9:16 technical explainer shorts" in SYSTEM


def test_landscape_frame_gives_portrait_components_the_portrait_canvas(monkeypatch):
    import json

    from motionbrief.content.shots import compile_plan
    from motionbrief.ir.models import SceneIR
    from motionbrief.paths import REPO_ROOT
    from motionbrief.render.svg_canvas import scene as sc_mod

    plan = json.loads((REPO_ROOT / "examples/isp_v3/plan_full.json").read_text(encoding="utf-8"))
    plan["video"]["aspect"] = "16:9"
    plan["shots"] = plan["shots"][:1]
    plan["shots"][0]["objects"] = [{"id": "a", "component": "InfoCards", "depth": 1, "props": {"items": []}},
                                   {"id": "b", "component": "BusCongestion", "depth": 1, "props": {}}]
    dur = json.loads((REPO_ROOT / "examples/isp_v3/voice_durations_full.json").read_text(encoding="utf-8"))["dur"]
    ir = SceneIR.model_validate(compile_plan(plan, dur))
    seen = {}

    def probe(name):
        def fn(c):
            seen[name] = (c.canvas.w, c.canvas.h)
            return "<g/>"
        fn.native_landscape = name == "BusCongestion"
        return fn

    monkeypatch.setitem(sc_mod.COMPONENTS, "InfoCards", probe("InfoCards"))
    monkeypatch.setitem(sc_mod.COMPONENTS, "BusCongestion", probe("BusCongestion"))
    sc = ir.scenes[0]
    sc_mod.frame_svg(ir, sc, sc.tStart + 0.5, 15, {}, [])
    assert seen == {"InfoCards": (1080, 1920), "BusCongestion": (1920, 1080)}
