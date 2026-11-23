# SPDX-License-Identifier: Apache-2.0
"""Script -> shot plan -> IR: the deterministic half (compiler parity, validator, parser, repair loop)."""
import json

from motionbrief.content import storyboard as sb
from motionbrief.content.shots import compile_plan
from motionbrief.paths import REPO_ROOT

PLAN = REPO_ROOT / "examples/isp_v3/plan_full.json"


def _plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def test_compiler_reproduces_the_hand_built_full_cut():
    dur = json.loads((REPO_ROOT / "examples/isp_v3/voice_durations_full.json").read_text(encoding="utf-8"))["dur"]
    ir = compile_plan(_plan(), dur)
    ref = json.loads((REPO_ROOT / "fixtures/isp_v3_full.json").read_text(encoding="utf-8"))
    ir["video"]["title"] = ref["video"]["title"]
    assert ir == ref


def test_catalog_covers_every_implemented_component():
    from motionbrief.paths import load_registry
    impl = {k for k, v in load_registry()["components"].items() if v["status"] == "implemented"}
    assert impl == set(sb.catalog())


def test_validator_catches_typical_llm_mistakes():
    shots = _plan()["shots"][:2]
    sec = sb.Section("hook", "", "".join(s["narration"] for s in shots))
    assert sb.validate_section(shots, sec, 1) == []
    bad = json.loads(json.dumps(shots))
    bad[0]["objects"][1]["component"] = "Hologram"
    bad[1]["objects"][0]["props"]["mode"] = "sparkle"
    bad[1]["texts"][0]["text"] = "这句屏幕文字明显太长了"
    bad[1]["narration"] = bad[1]["narration"][:-3]
    errs = " ".join(sb.validate_section(bad, sec, 1))
    assert "unknown component 'Hologram'" in errs and "mode 'sparkle'" in errs
    assert "too wide" in errs and "verbatim" in errs


def test_parser_reads_prose_scripts_and_shot_lists(tmp_path):
    prose = "## 3. 完整旁白\n\n### 一、开场\n\n第一句。第二句。\n\n### 二、结尾\n\n最后一句。\n\n## 4. 事实核对\n| a | b |\n"
    secs, ctx = sb.parse_script(prose)
    assert [s.narration for s in secs] == ["第一句。第二句。", "最后一句。"] and "事实核对" in ctx
    shots = "## 一、开场\n\n### s01　0:00\n\n- **旁白**：第一句。\n- **画面**：x\n\n### s02\n\n- **旁白**：第二句。\n"
    secs, _ = sb.parse_script(prose, shots)
    assert len(secs) == 1 and secs[0].narration == "第一句。第二句。"


def test_repair_loop_feeds_errors_back():
    good = {"shots": _plan()["shots"][:2]}
    sec = sb.Section("hook", "", "".join(s["narration"] for s in good["shots"]))
    broken = json.loads(json.dumps(good))
    broken["shots"][0]["objects"][1]["component"] = "Hologram"
    replies = iter([json.dumps(broken), "```json\n" + json.dumps(good) + "\n```"])
    seen = []

    class FakeRouter:
        caps = {"capabilities": {"deep_reasoning": {"timeout_s": 1}}}

        class providers:  # noqa: N801
            pass

    def ask(router, ref, messages):
        seen.append(messages[-1]["content"])
        return next(replies), "fake:model"

    orig, sb._ask = sb._ask, ask
    try:
        shots, errs, rounds, used = sb.storyboard_section(sec, 1, "", "", FakeRouter(), repairs=2)
    finally:
        sb._ask = orig
    assert errs == [] and rounds == 1 and "Hologram" in seen[1]
