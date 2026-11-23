# SPDX-License-Identifier: Apache-2.0
"""TTS provider interface: synthesize(text, voice) -> wav (pluggable adapters)."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path


class TTSUnavailable(RuntimeError):
    """FATAL for the local agent: dependency missing."""


class TTSProvider(ABC):
    name = "abstract"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def synthesize(self, text: str, voice: str, out_wav: Path) -> Path: ...

    def synthesize_batch(self, items: list[tuple[str, Path]], voice: str, speed: float = 1.0) -> list[Path]:
        return [self.synthesize(t, voice, p) for t, p in items]


def get_provider(name: str | None = None) -> TTSProvider:
    from motionbrief.tts.adapters.espeak import EspeakNgAdapter
    from motionbrief.tts.adapters.kokoro import KokoroAdapter
    from motionbrief.tts.adapters.sapi import SapiAdapter
    from motionbrief.tts.adapters.stubs import CloudTTSAdapter, PiperAdapter

    providers: dict[str, TTSProvider] = {p.name: p for p in (KokoroAdapter(), SapiAdapter(), EspeakNgAdapter(),
                                                             PiperAdapter(), CloudTTSAdapter())}
    name = name or os.environ.get("MOTIONBRIEF_TTS")
    if not name:  # best available: neural first, robotic espeak only as CI fallback
        name = next((n for n in ("kokoro", "sapi") if providers[n].available()), "espeak-ng")
    if name not in providers:
        raise TTSUnavailable(f"unknown TTS provider {name!r}")
    p = providers[name]
    if not p.available():
        raise TTSUnavailable(f"TTS provider {name!r} not available on this host")
    return p
