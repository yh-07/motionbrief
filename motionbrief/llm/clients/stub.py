# SPDX-License-Identifier: Apache-2.0
"""Deterministic offline stub — lets the whole pipeline/tests run with zero credentials."""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from motionbrief.llm.clients.base import Adapter


class StubAdapter(Adapter):
    name = "stub"

    def chat(self, model, messages, *, images: Optional[list[bytes]] = None, timeout: float = 60) -> str:
        last = messages[-1]["content"] if messages else ""
        digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:8]
        return json.dumps({"stub": True, "model": model, "echo": str(last)[:200], "digest": digest,
                           "images": len(images or [])}, ensure_ascii=False)
