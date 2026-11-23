# SPDX-License-Identifier: Apache-2.0
"""Kokoro v1.0 neural TTS adapter (offline, Apache-2.0 weights).

Configuration (env):
  MOTIONBRIEF_KOKORO_PYTHON  python of a venv with `kokoro_onnx` + `soundfile`
  MOTIONBRIEF_KOKORO_MODEL   path to kokoro-v1.0.onnx
  MOTIONBRIEF_KOKORO_VOICES  path to voices-v1.0.bin
Voices: zm_yunxi (default), zm_yunjian, zm_yunyang, zm_yunxia, zf_xiaoxiao, zf_xiaoyi, ...
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from motionbrief.tts.provider import TTSProvider, TTSUnavailable

DEFAULTS = {
    "MOTIONBRIEF_KOKORO_PYTHON": "/opt/lumina-tts/tools/lumina-tts/bin/python",
    "MOTIONBRIEF_KOKORO_MODEL": "/opt/lumina-tts/models/kokoro-v1.0.onnx",
    "MOTIONBRIEF_KOKORO_VOICES": "/opt/lumina-tts/models/voices-v1.0.bin",
}
WORKER = Path(__file__).with_name("kokoro_worker.py")


def _cfg(k: str) -> str:
    return os.environ.get(k, DEFAULTS[k])


class KokoroAdapter(TTSProvider):
    name = "kokoro"
    default_voice = "zm_yunxi"

    def available(self) -> bool:
        try:
            import misaki  # noqa: F401
        except ImportError:
            return False
        py = _cfg("MOTIONBRIEF_KOKORO_PYTHON")
        return (Path(py).exists() or bool(shutil.which(py))) and Path(_cfg("MOTIONBRIEF_KOKORO_MODEL")).exists()

    def synthesize(self, text: str, voice: str, out_wav: Path) -> Path:
        self.synthesize_batch([(text, out_wav)], voice)
        return out_wav

    def synthesize_batch(self, items: list[tuple[str, Path]], voice: str, speed: float = 1.0) -> list[Path]:
        from motionbrief.tts.g2p_zh import phonemize
        voice = self.default_voice if voice in ("zh", "", None) else voice
        jobs = []
        for text, out in items:
            out.parent.mkdir(parents=True, exist_ok=True)
            jobs.append({"phonemes": phonemize(text), "voice": voice, "speed": speed, "out": str(out)})
        req = {"model": _cfg("MOTIONBRIEF_KOKORO_MODEL"), "voices": _cfg("MOTIONBRIEF_KOKORO_VOICES"), "jobs": jobs}
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        r = subprocess.run([_cfg("MOTIONBRIEF_KOKORO_PYTHON"), str(WORKER)], input=json.dumps(req),
                           text=True, encoding="utf-8",
                           capture_output=True, env=env, timeout=1800)
        if r.returncode != 0:
            raise TTSUnavailable(f"kokoro worker failed: {r.stderr[-800:]}")
        return [Path(j["out"]) for j in jobs]
