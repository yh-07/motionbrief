# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class ProviderError(RuntimeError):
    """Provider-level failure; the router falls through to the next candidate."""


class NotConfigured(ProviderError):
    """Candidate has placeholder credentials/model (REPLACE_ME)."""


class Adapter(ABC):
    name = "abstract"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.family = cfg.get("family", self.name)

    @abstractmethod
    def chat(self, model: str, messages: list[dict], *, images: Optional[list[bytes]] = None,
             timeout: float = 60) -> str: ...

    @staticmethod
    def _require(value: Optional[str], what: str) -> str:
        if not value or "REPLACE_ME" in value:
            raise NotConfigured(f"{what} not configured")
        return value
