# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible Chat Completions adapter (works with many hosted and local servers)."""
from __future__ import annotations

import base64
import json
import urllib.request
from typing import Optional

from motionbrief.llm.clients.base import Adapter, ProviderError


class OpenAICompatAdapter(Adapter):
    name = "openai_compat"

    def chat(self, model, messages, *, images: Optional[list[bytes]] = None, timeout: float = 60) -> str:
        base = self._require(self.cfg.get("base_url"), "base_url").rstrip("/")
        key = self.cfg.get("api_key") or ""
        if self.name != "local":
            self._require(key, "api_key")
        self._require(model, "model")
        msgs = [dict(m) for m in messages]
        if images:
            parts = [{"type": "text", "text": msgs[-1]["content"]}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}}
                for b in images]
            msgs[-1]["content"] = parts
        req = urllib.request.Request(base + "/chat/completions", method="POST",
                                     data=json.dumps({"model": model, "messages": msgs,
                                                      # reasoning models spend tokens before the answer
                                                      **({"max_tokens": int(self.cfg["max_tokens"])}
                                                         if self.cfg.get("max_tokens") else {})}).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {key}"} if key else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (configured URL)
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # network/HTTP/shape errors
            raise ProviderError(f"{self.name}: {e}") from e


class LocalAdapter(OpenAICompatAdapter):
    name = "local"
