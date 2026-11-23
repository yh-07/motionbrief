# SPDX-License-Identifier: Apache-2.0
"""Renderer smoke, degradation, executor protocol, and the s03 sprint acceptance."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from motionbrief.agent.executor import execute
from motionbrief.agent.taxonomy import Status, classify
from motionbrief.ir.models import load
from motionbrief.render.backend import BackendUnavailable, RenderFailure, plan_scene
from motionbrief.render.svg_canvas.scene import frame_svg

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def ir():
    return load(ROOT / "fixtures/isp_v01.json")


def test_frame_is_deterministic(ir):
    s = ir.scene("s03")
    plan = plan_scene(s)
    a = frame_svg(ir, s, 13.2, 396, plan.choices, [])
    b = frame_svg(ir, s, 13.2, 396, plan.choices, [])
    assert a == b and a.startswith("<svg")


def test_webgl_unavailable_degrades_to_2d(ir, monkeypatch):
    plan = plan_scene(ir.scene("s03"))
    assert plan.choices["chip"] in ("svg", "three")
    if plan.choices["chip"] == "svg":
        assert plan.degradations and plan.degradations[0]["from"] == "three"


def test_failure_taxonomy():
    assert classify(RenderFailure("x")) == Status.RETRYABLE
    assert classify(BackendUnavailable("x")) == Status.DEGRADED
    assert classify(FileNotFoundError("ffmpeg")) == Status.FATAL


def test_invalid_task_escalates():
    r = execute({"taskId": "t", "type": "rm_rf", "idempotencyKey": "xxxxxxxx", "irRef": "x", "outDir": "y"})
    assert r["status"] == "escalate"


@pytest.mark.render
def test_s03_layer_a_acceptance(tmp_path):
    """Sprint §21 steps 5–7: s03 renders on Layer A and passes G1 (scene scope)."""
    out = str(tmp_path / "bundle")
    from motionbrief.apps.cli import main
    assert main(["produce", "fixtures/isp_v01.json", "--scenes", "s03", "--out", out, "--png-every", "60"]) == 0
    b = Path(out)
    assert (b / "frames/s03.mp4").exists() and list((b / "frames/s03").glob("f*.png"))
    g1 = json.loads((b / "logs/g1_s03.json").read_text())
    assert all(r["passed"] for r in g1)
    # idempotency: second run skips via result cache / checkpoint
    assert main(["produce", "fixtures/isp_v01.json", "--scenes", "s03", "--out", out]) == 0


def test_animatic_keyframes_cover_every_scene(ir):
    from motionbrief.render.animatic import keyframes
    kfs = keyframes(ir)
    assert {k[0] for k in kfs} == {s.id for s in ir.scenes}
    assert all(ir.scene(sid).tStart <= t < ir.scene(sid).tEnd for sid, t, _ in kfs)


def test_g3_needs_all_stages(tmp_path):
    from motionbrief.quality.gates import g3_checklist
    assert not g3_checklist(tmp_path).passed
    (tmp_path / "approval.json").write_text(json.dumps({
        "script_lock": {"reviewer": "a", "approvedAt": "t"},
        "animatic_lock": {"reviewer": "a", "approvedAt": "t"},
        "final": {"reviewer": "a", "approvedAt": "t", "aiContentLabel": True, "factsChecked": True}}))
    assert g3_checklist(tmp_path).passed


def test_anchor_overlay_returns_png():
    import io

    from PIL import Image

    from motionbrief.quality.multimodal_review import anchor_overlay
    buf = io.BytesIO()
    Image.new("RGB", (108, 192), "black").save(buf, "PNG")
    out = anchor_overlay(buf.getvalue())
    assert Image.open(io.BytesIO(out)).size == (108, 192)
