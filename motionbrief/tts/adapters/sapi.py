# SPDX-License-Identifier: Apache-2.0
"""Windows SAPI adapter (System.Speech via PowerShell). Offline, zero-install on Windows hosts;
more natural than espeak-ng but still below a neural voice. Voice: MOTIONBRIEF_SAPI_VOICE."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from motionbrief.tts.provider import TTSProvider, TTSUnavailable

# text/paths travel through env vars, so no PowerShell quoting of user text is needed
_SCRIPT = ("Add-Type -AssemblyName System.Speech; "
           "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
           "if ($env:TTS_VOICE) { $s.SelectVoice($env:TTS_VOICE) }; "
           "$s.SetOutputToWaveFile($env:TTS_OUT); "
           "$s.Speak($env:TTS_TEXT); "
           "$s.Dispose()")


class SapiAdapter(TTSProvider):
    name = "sapi"

    def available(self) -> bool:
        return os.name == "nt" and shutil.which("powershell") is not None

    def synthesize(self, text: str, voice: str, out_wav: Path) -> Path:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        v = os.environ.get("MOTIONBRIEF_SAPI_VOICE", "Microsoft Huihui Desktop") if voice in ("zh", "", None) \
            else voice
        env = {**os.environ, "TTS_TEXT": text, "TTS_OUT": str(out_wav.resolve()), "TTS_VOICE": v}
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                           env=env, capture_output=True)
        if r.returncode != 0 or not out_wav.exists():
            raise TTSUnavailable(f"sapi failed: {r.stderr.decode('utf-8', 'replace')[-500:]}")
        return out_wav
