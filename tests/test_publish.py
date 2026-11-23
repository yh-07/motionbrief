# SPDX-License-Identifier: Apache-2.0
"""Publish package: copy (LLM or deterministic fallback), chapter lines, designed cover sizes."""
import json
from pathlib import Path

import pytest
from PIL import Image

from motionbrief.apps import publish


class _Result:
    def __init__(self, text):
        self.text = text


class BadRouter:
    def chat(self, capability, messages, **kw):
        assert capability == "fast_text"
        return _Result("sorry, I cannot produce JSON right now")


class GoodRouter:
    def chat(self, capability, messages, **kw):
        return _Result("```json\n" + json.dumps({
            "bilibili": {"title": "手机为什么跑不动大模型", "desc": "讲清内存墙\n简化模型，并非真实 Benchmark",
                         "tags": ["AI", "端侧大模型", "#科普"]},
            "douyin": {"title": "手机跑大模型为啥慢", "desc": "一条视频看懂内存墙", "hashtags": ["科普", "#AI"]},
            "cover": {"main": "跑不动的大模型", "sub": "真正的墙是内存", "tag": "科普"},
        }, ensure_ascii=False) + "\n```")


@pytest.fixture
def outbox(tmp_path):
    d = tmp_path / "outbox" / "demo_vid"
    d.mkdir(parents=True)
    Image.new("RGB", (640, 360), (30, 60, 120)).save(d / "cover.png")
    (d / "input.md").write_text(
        "---\nid: demo_vid\ntitle: 手机都 100 TOPS 了，为什么还是跑不动大模型？\n---\n\n"
        "## 3. 完整旁白\n\n现在手机芯片的算力已经很高了。但内存才是真正的墙。\n", encoding="utf-8")
    (d / "sources.md").write_text(
        "# Sources\n\n- **s01** 旁白\n  - https://example.org\n\n简化模型，并非真实 Benchmark。\n\n"
        "Contains AI-generated narration (label required at publish).\n", encoding="utf-8")
    ir = {"video": {"id": "demo_vid"}, "scenes": [
        {"id": "s01", "tStart": 0.0, "tEnd": 30.0, "narration": "a", "chapter": "一、开场：错觉"},
        {"id": "s02", "tStart": 30.0, "tEnd": 61.5, "narration": "b"},
        {"id": "s03", "tStart": 61.5, "tEnd": 90.0, "narration": "c", "chapter": "二、内存墙"},
    ]}
    ir_path = d.parent / "ir.json"
    ir_path.write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    (d / "status.json").write_text(json.dumps({"id": "demo_vid", "state": "done", "ir": str(ir_path)}),
                                   encoding="utf-8")
    return d.parent


def _assert_package(paths, d):
    assert {Path(p).name for p in paths} == {"publish.md", "cover_16x9.png", "cover_3x4.png", "cover_9x16.png"}
    md = (d / "publish.md").read_text(encoding="utf-8")
    assert "## B站" in md and "## 抖音" in md and "## 封面文字" in md
    assert "00:00 " in md and "01:01 内存墙" in md
    for name, size in publish.COVER_SIZES.items():
        with Image.open(d / name) as im:
            assert im.size == size
    return md


def test_fallback_when_llm_returns_garbage(outbox):
    d = outbox / "demo_vid"
    paths = publish.write_publish("demo_vid", router=BadRouter(), outbox=outbox)
    md = _assert_package(paths, d)
    assert "00:00 开场" in md
    assert "标题：手机都 100 TOPS 了，为什么还是跑不动大模型？" in md
    assert "简化模型，并非真实 Benchmark" in md  # disclaimer from the fact table survives
    assert "AI 生成内容" in md  # AI label survives


def test_valid_llm_copy_is_used_and_overrides_win(outbox):
    d = outbox / "demo_vid"
    md = _assert_package(publish.write_publish("demo_vid", router=GoodRouter(), outbox=outbox), d)
    assert "标题：手机为什么跑不动大模型" in md
    assert "#AI" in md and "#科普" in md  # hashtags are normalised, not doubled
    assert "主标题：跑不动的大模型" in md

    (d / "input.md").write_text(
        "---\nid: demo_vid\ntitle: 长标题\npublish_title: 覆盖标题\ncover_main: 覆盖\n---\n\n旁白。\n", encoding="utf-8")
    publish.write_publish("demo_vid", router=GoodRouter(), outbox=outbox)
    md = (d / "publish.md").read_text(encoding="utf-8")
    assert "标题：覆盖标题" in md and "主标题：覆盖" in md
