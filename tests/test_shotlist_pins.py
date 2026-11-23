# SPDX-License-Identifier: Apache-2.0
"""Shot-list pins (**组件**), footnotes (**注释**), continuous-motion cadence and the 16:9 catalog flag.
Only pure helpers are exercised; no LLM is called."""
import pytest

from motionbrief.content import storyboard as sb
from motionbrief.content.shots import compile_plan
from motionbrief.ir.models import SceneIR

SHOT_LIST = """## 一、开场
### s01
**旁白**：一秒钟。
**组件**：BusCongestion {"mode": "congestion", "flow": 0.2, "queue": 8, "label": "LPDDR"}
**注释**：简化理论上限模型，并非真实 Benchmark
### s02
**旁白**：二。
**组件**：MatrixArray
"""


def test_parse_pins_with_and_without_props():
    pins = sb.parse_pins(SHOT_LIST)
    assert pins == {"s01": ("BusCongestion", {"mode": "congestion", "flow": 0.2, "queue": 8, "label": "LPDDR"}),
                    "s02": ("MatrixArray", {})}


def test_unknown_pinned_component_raises():
    with pytest.raises(ValueError, match="Hologram"):
        sb.parse_pins("## 一\n### s01\n**旁白**：x\n**组件**：Hologram {\"mode\": \"x\"}\n")


def test_pin_replaces_objects_and_keeps_texts_beats_cues():
    shots = [{"id": "s01", "role": "hook", "narration": "一秒钟。", "texts": [{"text": "100", "style": "impact_reveal"}],
              "beats": {"rev": 0.3, "imp": 0.6}, "cues": ["bass"],
              "objects": [{"id": "bus", "component": "NpuArray", "props": {"mode": "array", "load": 1.0}},
                          {"id": "x", "component": "InfoCards", "props": {}}]}]
    sb._apply_shot_list(shots, 1, {"s01": ("BusCongestion", {"mode": "congestion", "flow": 0.2, "queue": 8})}, None)
    sh = shots[0]
    assert sh["objects"] == [{"id": "bus", "component": "BusCongestion", "depth": 1, "renderer": "svg",
                              "props": {"mode": "congestion", "flow": 0.2, "queue": 8}}]
    assert sh["texts"] == [{"text": "100", "style": "impact_reveal"}]
    assert sh["beats"] == {"rev": 0.3, "imp": 0.6} and sh["cues"] == ["bass"]


def test_shot_list_note_reaches_compiled_scene():
    assert sb.parse_notes(SHOT_LIST) == {"s01": "简化理论上限模型，并非真实 Benchmark"}
    shots = [{"id": "s01", "role": "hook", "narration": "一秒钟。", "note": "简化理论上限模型",
              "objects": [{"id": "a", "component": "TitleCard", "props": {}}]}]
    ir = compile_plan({"video": {"id": "t"}, "shots": shots}, {"s01": 3.0})
    assert ir["scenes"][0]["note"] == "简化理论上限模型"
    SceneIR.model_validate(ir)  # the IR model accepts the field


def test_continuous_component_is_not_a_visual_gap():
    def shot(comp, props):
        return {"id": "s01", "role": "hook", "narration": "一秒钟。", "duration": 12.0, "beats": {"rev": 0.9},
                "objects": [{"id": "o", "component": comp, "props": props}]}

    cont = sb.validate_section([shot("BusCongestion", {"mode": "congestion", "flow": 0.2, "queue": 8})],
                               sb.Section("hook", "", "一秒钟。"), 1)
    assert not any("without a visual event" in e for e in cont)
    still = sb.validate_section([shot("TitleCard", {})], sb.Section("hook", "", "一秒钟。"), 1)
    assert any("without a visual event" in e for e in still)  # control: a still component does leave a gap


def test_landscape_catalog_flags():
    land = sb.catalog(None, landscape=True)
    assert land["BusCongestion"]["landscape"] is True
    assert land["TitleCard"]["landscape"] is False
    assert "landscape" not in sb.catalog()["BusCongestion"]  # 9:16 catalog unchanged


def test_shot_list_fixes_the_cut_even_when_the_llm_merges_and_drops_shots():
    body = ("### s05\n**旁白**：第一句话。\n**组件**：BusCongestion {\"mode\": \"congestion\", \"label\": \"LPDDR\"}\n"
            "### s06\n**旁白**：第二句话。\n**组件**：NpuArray {\"mode\": \"array\", \"label\": \"NPU\"}\n"
            "### s07\n**画面**：无旁白的过渡镜头\n")
    sec = sb.Section("一、开场", body, "第一句话。第二句话。")
    llm = [{"id": "s05", "narration": "第一句话。第二句话。", "texts": [{"text": "合并", "style": "label"}],
            "objects": [{"id": "a", "component": "TitleCard", "props": {}}], "beats": {"rev": 0.4}}]
    shots = sb._align_to_shot_list(llm, sec, 5)
    sb._apply_shot_list(shots, 5, sb.parse_pins(body), {})
    assert [s["id"] for s in shots] == ["s05", "s06", "s07"]
    assert [s["narration"] for s in shots] == ["第一句话。", "第二句话。", ""]
    assert [s["objects"][0]["component"] for s in shots[:2]] == ["BusCongestion", "NpuArray"]
    assert shots[0]["texts"] == shots[1]["texts"] and shots[0]["texts"] is not shots[1]["texts"]
    assert shots[2]["duration"] == 3.0


def test_synthesized_silent_shot_borrows_the_previous_visual():
    body = ("### s01\n**旁白**：一句话。\n**组件**：NpuArray {\"mode\": \"array\", \"label\": \"NPU\"}\n"
            "### s02\n**画面**：结尾卡片\n")
    sec = sb.Section("九、结尾", body, "一句话。")
    shots = sb._align_to_shot_list([{"narration": "一句话。", "objects": []}], sec, 1)
    sb._apply_shot_list(shots, 1, sb.parse_pins(body), {})
    sb._fill_empty_visuals(shots)  # after pins: the silent shot continues the pinned visual
    assert shots[1]["objects"] and shots[1]["objects"][0]["component"] == "NpuArray"


def test_shot_list_beats_line_is_used_and_missing_beats_get_a_default_cut():
    body = ("### s01\n**旁白**：第一句。\n**节拍**：rev 0.2，imp 0.5\n"
            "### s02\n**旁白**：第二句。\n")
    sec = sb.Section("开场", body, "第一句。第二句。")
    llm = [{"narration": "第一句。", "beats": {"rev": 0.9}}, {"narration": "第二句。"}]
    shots = sb._align_to_shot_list(llm, sec, 1)
    assert shots[0]["beats"] == {"rev": 0.2, "imp": 0.5}  # the shot list's line overrides the LLM
    assert shots[1]["beats"] == {"rev": 0.3, "imp": 0.7}  # no beats anywhere: a default cut


def test_single_document_with_inline_shots_is_read_without_a_shotlist_file():
    # one file: chapters are '## 章节' headings with '### sNN' shot blocks, facts at the end
    body = ("## 一、开场\n### s01\n**旁白**：第一句。\n**组件**：InfoCards {\"items\": []}\n"
            "**注释**：简化示意，并非真实 Benchmark\n**节拍**：rev 0.3，imp 0.7\n\n"
            "## 二、正文\n### s02\n**旁白**：第二句。\n**节拍**：rev 0.3，imp 0.7\n\n"
            "## 事实核对\n| 说法 | 依据 | 处理 |\n|---|---|---|\n"
            "| 说法 | [来源](https://en.wikipedia.org/wiki/X) | 事实 |\n")
    secs, context = sb._parse_sections(body)
    assert [s.title for s in secs] == ["一、开场", "二、正文"]
    assert [s.narration for s in secs] == ["第一句。", "第二句。"]
    assert sb.parse_pins(body)["s01"][0] == "InfoCards"
    assert sb.parse_notes(body) == {"s01": "简化示意，并非真实 Benchmark"}
    assert "事实核对" in context


def test_shot_ids_past_99_are_read_whole():
    body = ("## 一、开场\n### s99\n**旁白**：第九十九句。\n**节拍**：rev 0.3，imp 0.7\n"
            "### s100\n**旁白**：第一百句。\n**组件**：TitleCard {\"text\": \"百\"}\n**节拍**：rev 0.3，imp 0.7\n")
    assert [sid for sid, _ in sb._shot_blocks(body)] == ["s99", "s100"]
    assert sb.parse_pins(body)["s100"][0] == "TitleCard"
    assert sb.parse_beat_line(dict(sb._shot_blocks(body))["s100"]) == {"rev": 0.3, "imp": 0.7}


def test_pins_with_invented_or_missing_props_are_rejected_with_every_problem_listed():
    body = ("### s01\n**旁白**：一。\n**组件**：TitleCard {\"title\": \"x\"}\n"
            "### s02\n**旁白**：二。\n**组件**：Equation {\"mode\": \"fraction\", \"num\": \"60\"}\n")
    with pytest.raises(ValueError) as e:
        sb.parse_pins(body)
    msg = str(e.value)
    assert "s01: TitleCard does not take title" in msg and "s01: TitleCard needs text" in msg
    assert "s02: Equation needs den, result" in msg


def test_inbox_ignores_templates_readmes_and_shot_files(tmp_path, monkeypatch):
    from motionbrief.apps import inbox

    for name in ("TEMPLATE_rich.md", "TEMPLATE_minimal.md", "template.md", "README.md", "x.shots.md", "_draft.md",
                 "real_video.md", "plan_only.plan.json"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(inbox, "INBOX", tmp_path)
    assert [p.name for p in inbox.pending_inputs()] == ["plan_only.plan.json", "real_video.md"]
