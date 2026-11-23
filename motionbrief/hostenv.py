# SPDX-License-Identifier: Apache-2.0
"""Host configuration: load `<repo>/.env` (gitignored) into os.environ and expose host tools.

Real environment variables always win over `.env`. Recognised host keys:
  MOTIONBRIEF_BIN_DIRS   extra dirs (os.pathsep-separated) prepended to PATH: ffmpeg/ffprobe/espeak-ng, and on
                         Windows the libcairo-2.dll dir (cffi's dlopen searches PATH, not add_dll_directory)
MOTIONBRIEF_ENV_FILE points at another file instead (e.g. a remote render host's host.env);
MOTIONBRIEF_NO_DOTENV=1 skips it (hermetic CI).
"""
from __future__ import annotations

import os
from pathlib import Path


def _parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load(root: Path) -> None:
    env_file = Path(os.environ.get("MOTIONBRIEF_ENV_FILE") or root / ".env")
    if os.environ.get("MOTIONBRIEF_NO_DOTENV") != "1" and env_file.exists():
        for k, v in _parse(env_file.read_text(encoding="utf-8")).items():
            os.environ.setdefault(k, v)
    extra = [d for d in os.environ.get("MOTIONBRIEF_BIN_DIRS", "").split(os.pathsep) if d]
    path = os.environ.get("PATH", "").split(os.pathsep)
    missing = [d for d in extra if d not in path]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing + path)
