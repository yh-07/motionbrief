# SPDX-License-Identifier: Apache-2.0
"""Anthropic Messages API adapter (stub-grade: text only in Phase 1)."""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

from motionbrief.llm.clients.base import Adapter, ProviderError


class AnthropicAdapter(Adapter):
    name = "anthropic"

    def chat(self, model, messages, *, images: Optional[list[bytes]] = None, timeout: float = 60) -> str:
        key = self._require(self.cfg.get("api_key"), "api_key")
        self._require(model, "model")
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = [m for m in messages if m["role"] != "system"]
        body = {"model": model, "max_tokens": 4096, "messages": msgs, **({"system": system} if system else {})}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
                                     data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "x-api-key": key,
                                              "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                data = json.loads(r.read())
            return "".join(b.get("text", "") for b in data["content"])
        except Exception as e:
            raise ProviderError(f"anthropic: {e}") from e
