# SPDX-License-Identifier: Apache-2.0
import re
from pathlib import Path

import pytest

from motionbrief.llm.clients.base import Adapter, ProviderError
from motionbrief.llm.router import AllProvidersFailed, CapabilityRouter

ROOT = Path(__file__).resolve().parent.parent


def test_code_generation_routes_without_real_model_ids():
    r = CapabilityRouter.from_file()
    res = r.chat("code_generation", [{"role": "user", "content": "hello"}])
    assert res.provider == "stub"
    # every real candidate failed because it is a REPLACE_ME placeholder, and that was recorded
    assert all(a["error"] == "not_configured" for a in res.attempts)


def test_no_model_ids_in_business_code():
    pat = re.compile(r"\b(gpt-\d|claude-\d|claude-(?:opus|sonnet|haiku)|gemini-\d|llama-?\d|qwen\d)", re.I)
    hits = [p for p in (ROOT / "motionbrief").rglob("*.py") if pat.search(p.read_text(encoding="utf-8"))]
    hits += [p for p in [ROOT / "motionbrief/llm/capabilities.example.yaml"] if pat.search(p.read_text())]
    assert not hits, hits


class Boom(Adapter):
    name = "boom"

    def chat(self, model, messages, *, images=None, timeout=60):
        raise ProviderError("down")


class Ok(Adapter):
    name = "ok"

    def chat(self, model, messages, *, images=None, timeout=60):
        return f"ok:{model}"


CAPS = {"capabilities": {c: {"candidates": ["a:m1", "b:m2"], "cross_family": c == "vision_review"}
                         for c in ("fast_text", "deep_reasoning", "code_generation", "vision_review")}}


def test_fallback_order_and_cross_family():
    r = CapabilityRouter(CAPS, {"a": Boom({"family": "fa"}), "b": Ok({"family": "fb"})})
    res = r.chat("fast_text", [{"role": "user", "content": "x"}])
    assert res.text == "ok:m2" and res.attempts[0]["ref"] == "a:m1"
    with pytest.raises(ValueError):
        r.chat("vision_review", [{"role": "user", "content": "x"}])  # four-eye requires exclude_family
    with pytest.raises(AllProvidersFailed):
        r.chat("vision_review", [{"role": "user", "content": "x"}], exclude_family="fb")


def test_unknown_capability():
    with pytest.raises(KeyError):
        CapabilityRouter(CAPS, {}).chat("poetry", [])
