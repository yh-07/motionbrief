# SPDX-License-Identifier: Apache-2.0
"""System TTS adapter (espeak-ng). Robotic but deterministic and offline: the
reference adapter for CI and weak hardware. Swap for a neural local TTS in prod (D3)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from motionbrief.tts.provider import TTSProvider


class EspeakNgAdapter(TTSProvider):
    name = "espeak-ng"

    def available(self) -> bool:
        return shutil.which("espeak-ng") is not None

    def synthesize(self, text: str, voice: str, out_wav: Path) -> Path:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        v = {"zh": "cmn", "en": "en-us"}.get(voice, voice)
        subprocess.run(["espeak-ng", "-v", v, "-s", "235", "-p", "45", "-w", str(out_wav), text],
                       check=True, capture_output=True)
        return out_wav
