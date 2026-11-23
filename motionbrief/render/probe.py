# SPDX-License-Identifier: Apache-2.0
"""Probe the host for render capabilities BEFORE rendering (weak-hardware-first)."""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
from pathlib import Path

from motionbrief.paths import REPO_ROOT

HW_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_videotoolbox", "h264_vaapi", "h264_amf"]


def _run(cmd: list[str], timeout: float = 20) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _encoder_works(ff: str, enc: str) -> bool:
    r = _run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
              "-frames:v", "1", "-c:v", enc, "-f", "null", "-"], timeout=30)
    return bool(r and r.returncode == 0)


@functools.lru_cache(maxsize=1)
def probe() -> dict:
    forced = os.environ.get("MOTIONBRIEF_FORCE_NO_WEBGL") == "1"
    node = shutil.which("node")
    remotion = bool(node) and (REPO_ROOT / "node_modules" / "@remotion" / "renderer").exists()
    three = bool(node) and (REPO_ROOT / "node_modules" / "three").exists()
    webgl = False
    if remotion and three and not forced:
        r = _run([node, str(REPO_ROOT / "motionbrief/render/three/probe_webgl.mjs")], timeout=60)
        webgl = bool(r and r.returncode == 0 and "webgl:ok" in r.stdout)
    ff = shutil.which("ffmpeg")
    encoders: list[str] = []
    if ff:
        r = _run([ff, "-hide_banner", "-encoders"])
        txt = r.stdout if r else ""
        # compiled-in != usable (e.g. an ARM64 build lists nvenc with no NVIDIA GPU): test-encode one frame
        encoders = [e for e in HW_ENCODERS if f" {e} " in txt and _encoder_works(ff, e)]
    try:
        import cairosvg  # noqa: F401
        svg = True
    except Exception:  # pragma: no cover
        svg = False
    return {
        "svg": svg,
        "canvas": svg,  # canvas2d path shares the cairo rasteriser in the reference impl
        "remotion": remotion,
        "three": three and webgl,
        "webgl": webgl,
        # a LAN render host with a GPU browser (see render/remote.py); GPU scenes are then routed to it
        "webglRemote": bool(os.environ.get("MOTIONBRIEF_RENDER_HOST"))
        and os.environ.get("MOTIONBRIEF_RENDER_WEBGL") == "1",
        "blender": bool(shutil.which("blender")),
        "ffmpeg": bool(ff),
        "ffprobe": bool(shutil.which("ffprobe")),
        "hwEncoders": encoders,
        "tts": {"espeak-ng": bool(shutil.which("espeak-ng"))},
    }


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(probe(), indent=2))
