# SPDX-License-Identifier: Apache-2.0
"""Placeholders for open-source neural local TTS and public cloud TTS (decision D3)."""
from __future__ import annotations

import os
from pathlib import Path

from motionbrief.tts.provider import TTSProvider


class PiperAdapter(TTSProvider):
    name = "local-neural"

    def available(self) -> bool:
        return bool(os.environ.get("MOTIONBRIEF_LOCAL_TTS_MODEL"))

    def synthesize(self, text: str, voice: str, out_wav: Path) -> Path:  # pragma: no cover
        raise NotImplementedError("wire a local neural TTS runtime here (Phase 2+)")


class CloudTTSAdapter(TTSProvider):
    name = "cloud"

    def available(self) -> bool:
        return bool(os.environ.get("MOTIONBRIEF_CLOUD_TTS_ENDPOINT"))

    def synthesize(self, text: str, voice: str, out_wav: Path) -> Path:  # pragma: no cover
        raise NotImplementedError("wire a public cloud TTS API here (Phase 2+)")
