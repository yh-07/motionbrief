# SPDX-License-Identifier: Apache-2.0
"""Remote Layer-A render worker over SSH (a LAN PC as extra render cores).

The remote host runs the *same* SvgBackend (same cairo build, same font file, libx264 intermediates), so its
scene mp4s match local renders; only where the CPU time is spent changes. Host config (local `.env`):

  MOTIONBRIEF_RENDER_HOST     user@host (key auth; BatchMode, never a password). Empty = disabled.
  MOTIONBRIEF_RENDER_ROOT     remote dir holding venv/, cairo/, host.env, engine/<hash>/, jobs/
  MOTIONBRIEF_RENDER_PYTHON   remote python (default <root>/venv/Scripts/python.exe)
  MOTIONBRIEF_RENDER_JOBS     concurrent remote scenes (default 6)

The remote `<root>/host.env` is that machine's own `.env` (PATH for cairo/ffmpeg, font file).
Engine code is shipped as a tarball keyed by its content hash, so a stale remote copy is impossible.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
import uuid
from pathlib import Path

from motionbrief.paths import REPO_ROOT

# keepalives: a dropped LAN link fails within ~60 s instead of hanging until the job timeout;
# 30 s connect: a fully loaded PC answers the SSH banner slowly
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4"]
_lock = threading.Lock()
_engine: dict[str, str] = {}


class RemoteUnavailable(RuntimeError):
    """Host unreachable / remote setup broken: caller falls back to local rendering."""


def host() -> str:
    return os.environ.get("MOTIONBRIEF_RENDER_HOST", "").strip()


def jobs() -> int:
    return int(os.environ.get("MOTIONBRIEF_RENDER_JOBS", "6")) if host() else 0


def _root() -> str:
    return os.environ.get("MOTIONBRIEF_RENDER_ROOT", "").rstrip("/")


def _python() -> str:
    return os.environ.get("MOTIONBRIEF_RENDER_PYTHON") or f"{_root()}/venv/Scripts/python.exe"


def _run(cmd: list[str], timeout: float) -> str:
    """Run ssh/scp with output to temp FILES, not pipes: on Windows a pipe handle inherited by a concurrently
    spawned process (render pool workers, other ssh calls) keeps the pipe open after ssh exits, and reading it
    then never sees EOF, which hung a full run for an hour (even the timeout's cleanup blocks on it)."""
    import tempfile
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=timeout).returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RemoteUnavailable(f"{cmd[0]}: {e}") from e
        out.seek(0)
        err.seek(0)
        if rc != 0:
            raise RemoteUnavailable(f"{cmd[0]} exit {rc}: {err.read().decode('utf-8', 'replace')[-1500:]}")
        return out.read().decode("utf-8", "replace")


def _ssh(command: str, timeout: float = 60) -> str:
    for attempt in range(2):  # connection-level failures (exit 255) get one retry; command failures do not
        try:
            return _run(["ssh", *SSH_OPTS, host(), command], timeout)
        except RemoteUnavailable as e:
            if attempt or "exit 255" not in str(e):
                raise
            time.sleep(3)
    raise AssertionError("unreachable")


def _win(p: str) -> str:
    return p.replace("/", "\\")


def _engine_files() -> list[Path]:
    files = [p for p in sorted((REPO_ROOT / "motionbrief").rglob("*")) if p.is_file()
             and "__pycache__" not in p.parts and p.suffix in (".py", ".yaml", ".mjs", ".html", ".js", ".txt", ".json")]  # .json: component pack catalogs
    return files + [REPO_ROOT / "motion/tokens.json", REPO_ROOT / "motion/registry.json",
                    *sorted((REPO_ROOT / "schemas").glob("*.json"))]


def ensure_engine() -> str:
    """Upload this checkout's engine to the remote once per content hash; return the remote engine dir."""
    with _lock:
        if host() in _engine:
            return _engine[host()]
        files = _engine_files()
        h = hashlib.sha256()
        for p in files:
            h.update(str(p.relative_to(REPO_ROOT)).encode() + p.read_bytes())
        d = f"{_root()}/engine/{h.hexdigest()[:16]}"
        if "READY" not in _ssh(f'if exist "{_win(d)}\\READY" echo READY'):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tf:
                for p in files:
                    tf.add(p, arcname=str(p.relative_to(REPO_ROOT)).replace("\\", "/"))
            tmp = REPO_ROOT / "work" / f"_engine_{uuid.uuid4().hex[:8]}.tgz"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(buf.getvalue())
            try:
                _ssh(f'mkdir "{_win(d)}"')
                _run(["scp", *SSH_OPTS, "-q", str(tmp), f"{host()}:{d}/engine.tgz"], 120)
                _ssh(f'cd /d "{_win(d)}" && tar -xzf engine.tgz && del engine.tgz && echo ok> READY')
            finally:
                tmp.unlink(missing_ok=True)
        _engine[host()] = d
        return d


def _frames(ir, scene, segment, max_frames) -> int:
    n = round(scene.tEnd * ir.video.fps) - round(scene.tStart * ir.video.fps)
    n = min(n, max_frames) if max_frames else n
    return n // segment[1] + 1 if segment else n


def render_frames(ir, scene, out_dir: Path, *, plan, subtitles, png_every: int, max_frames,
                  segment: tuple[int, int] | None = None) -> dict:
    """Same contract as SvgBackend.render_frames, executed on the remote host."""
    engine = ensure_engine()
    job = f"{scene.id}_{uuid.uuid4().hex[:10]}"
    rjob = f"{_root()}/jobs/{job}"
    local = out_dir / "_remote" / job
    local.mkdir(parents=True, exist_ok=True)
    (local / "ir.json").write_text(json.dumps(ir.model_dump(by_alias=True), ensure_ascii=False), encoding="utf-8")
    (local / "job.json").write_text(json.dumps({"sceneId": scene.id, "choices": plan.choices,
                                                "subtitles": subtitles, "pngEvery": png_every,
                                                "maxFrames": max_frames, "segment": segment},
                                               ensure_ascii=False), encoding="utf-8")
    try:
        _ssh(f'mkdir "{_win(rjob)}"')
        _run(["scp", *SSH_OPTS, "-q", str(local / "ir.json"), str(local / "job.json"), f"{host()}:{rjob}/"], 120)
        out = _ssh(f'set "MOTIONBRIEF_ENV_FILE={_win(_root())}\\host.env" && set "PYTHONUTF8=1" && '
                   f'cd /d "{_win(engine)}" && "{_win(_python())}" -m motionbrief.render.remote_worker "{_win(rjob)}"',
                   timeout=120 + 2.0 * _frames(ir, scene, segment, max_frames))  # ≈2 s/frame worst case
        res = json.loads(out.strip().splitlines()[-1])
        _ssh(f'cd /d "{_win(rjob)}" && tar -cf out.tar -C out .')
        _run(["scp", *SSH_OPTS, "-q", f"{host()}:{rjob}/out.tar", str(local / "out.tar")], 600)
        with tarfile.open(local / "out.tar") as tf:
            tf.extractall(out_dir, filter="data")
    finally:
        subprocess.run(["ssh", *SSH_OPTS, host(), f'rmdir /s /q "{_win(rjob)}"'], capture_output=True, timeout=60)
        shutil.rmtree(local, ignore_errors=True)
    return {"video": str(out_dir / res["video"]), "frames": res["frames"], "expectedFrames": res["expectedFrames"],
            "pngs": [str(out_dir / scene.id / Path(p).name) for p in res["pngs"]], "host": host(),
            **({"gpu": res["gpu"]} if res.get("gpu") else {})}
