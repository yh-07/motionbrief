# SPDX-License-Identifier: Apache-2.0
"""Runs INSIDE an isolated Kokoro-onnx environment (stdin JSON jobs -> wav files).
Kept dependency-free from the main package so it can live in any venv that has kokoro_onnx."""
import json
import sys

import soundfile as sf
from kokoro_onnx import Kokoro

req = json.loads(sys.stdin.buffer.read().decode("utf-8"))  # utf-8 regardless of OS locale
m = Kokoro(req["model"], req["voices"])
for job in req["jobs"]:
    s, sr = m.create(job["phonemes"], voice=job["voice"], speed=job.get("speed", 1.0), is_phonemes=True)
    sf.write(job["out"], s, sr)
    print(json.dumps({"out": job["out"], "sec": len(s) / sr}), flush=True)
