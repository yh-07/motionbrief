# SPDX-License-Identifier: Apache-2.0
"""Provider-neutral capability router.

    router.chat("deep_reasoning", messages)
    router.chat("vision_review", messages, images=[png], exclude_family="family_b")

Business code never contains model IDs — only capability names. Candidates are
tried in order; every failure is recorded (not silently swallowed) and returned
in the final error if all candidates fail.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from motionbrief.llm.clients.anthropic import AnthropicAdapter
from motionbrief.llm.clients.base import Adapter, NotConfigured, ProviderError
from motionbrief.llm.clients.openai_compat import LocalAdapter, OpenAICompatAdapter
from motionbrief.llm.clients.stub import StubAdapter
from motionbrief.paths import REPO_ROOT

CAPABILITIES = ("fast_text", "deep_reasoning", "code_generation", "vision_review")
ADAPTERS: dict[str, type[Adapter]] = {
    "openai_compat": OpenAICompatAdapter,
    "anthropic": AnthropicAdapter,
    "local": LocalAdapter,
    "stub": StubAdapter,
}
_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def expand_env(obj: Any) -> Any:
    if isinstance(obj, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), obj)
    if isinstance(obj, list):
        return [expand_env(x) for x in obj]
    if isinstance(obj, dict):
        return {k: expand_env(v) for k, v in obj.items()}
    return obj


class AllProvidersFailed(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    family: str
    attempts: list[dict] = field(default_factory=list)


class CapabilityRouter:
    def __init__(self, caps: dict[str, Any], providers: Optional[dict[str, Adapter]] = None,
                 allow_stub: Optional[bool] = None):
        self.caps = expand_env(caps)
        if providers is None:
            # `type:` lets several named providers share one adapter (e.g. one gateway, many model families)
            providers = {name: ADAPTERS[(cfg or {}).get("type", name)](cfg or {})
                         for name, cfg in self.caps.get("providers", {}).items()
                         if (cfg or {}).get("type", name) in ADAPTERS}
        self.providers = providers
        self.ban = set(self.caps.get("ban", []))
        if allow_stub is None:
            allow_stub = os.environ.get("MOTIONBRIEF_ALLOW_STUB", "1") == "1"
        self.allow_stub = allow_stub

    @classmethod
    def from_file(cls, path: Optional[str | Path] = None, **kw) -> "CapabilityRouter":
        path = Path(path or os.environ.get("MOTIONBRIEF_CAPABILITIES",
                                           REPO_ROOT / "motionbrief/llm/capabilities.example.yaml"))
        path = path if path.is_absolute() else REPO_ROOT / path
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")), **kw)

    def _chain(self, capability: str, exclude_family: Optional[str]) -> list[str]:
        if capability not in CAPABILITIES:
            raise KeyError(f"unknown capability {capability!r}; expected one of {CAPABILITIES}")
        out = []
        for ref in self.caps["capabilities"][capability]["candidates"]:
            if ref in self.ban:
                continue
            prov = ref.split(":", 1)[0]
            if prov not in self.providers:
                continue
            if prov == "stub" and not self.allow_stub:
                continue
            if exclude_family and self.providers[prov].family == exclude_family:
                continue
            out.append(ref)
        return out

    def chat(self, capability: str, messages: list[dict], *, images: Optional[list[bytes]] = None,
             exclude_family: Optional[str] = None) -> ChatResult:
        cfg = self.caps["capabilities"][capability] if capability in self.caps.get("capabilities", {}) else {}
        if capability == "vision_review" and cfg.get("cross_family") and not exclude_family:
            raise ValueError("vision_review requires exclude_family (cross-family four-eye review)")
        timeout = float(cfg.get("timeout_s", 60))
        attempts: list[dict] = []
        for ref in self._chain(capability, exclude_family):
            prov, model = ref.split(":", 1)
            adapter = self.providers[prov]
            try:
                text = adapter.chat(model, messages, images=images, timeout=timeout)
                return ChatResult(text, prov, model, adapter.family, attempts)
            except NotConfigured as e:
                attempts.append({"ref": ref, "error": "not_configured", "detail": str(e)})
            except ProviderError as e:
                attempts.append({"ref": ref, "error": "provider_error", "detail": str(e)[:300]})
        raise AllProvidersFailed(f"[{capability}] all providers failed: {attempts}")
