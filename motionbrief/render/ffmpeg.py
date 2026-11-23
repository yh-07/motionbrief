# SPDX-License-Identifier: Apache-2.0
"""FFmpeg helpers: encode, concat, mux, probe, black-frame detection."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from motionbrief.render.probe import probe


class FFmpegError(RuntimeError):
    pass


def video_encoder() -> list[str]:
    hw = probe()["hwEncoders"]
    if hw:
        return ["-c:v", hw[0], "-b:v", "12M"]
    # explicit software fallback (deterministic)
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-maxrate", "16M", "-bufsize", "32M",
            "-pix_fmt", "yuv420p", "-profile:v", "high"]


# Per-scene intermediates are re-encoded at assemble, so a HW encoder at high bitrate is fine here and frees
# the CPU for rasterising other scenes in parallel. Pick with MOTIONBRIEF_INTERMEDIATE_ENCODER.
INTERMEDIATE = {
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"],
    "h264_mf": ["-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "20M", "-pix_fmt", "nv12"],      # Windows MF
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "constqp", "-qp", "16", "-pix_fmt", "yuv420p"],
}


def raw_encoder_proc(out: Path, fps: int, w: int, h: int, intermediate: bool = True) -> subprocess.Popen:
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = (INTERMEDIATE[os.environ.get("MOTIONBRIEF_INTERMEDIATE_ENCODER") or "libx264"]
           if intermediate else video_encoder())
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           *enc, "-r", str(fps), str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise FFmpegError(f"{' '.join(cmd[:6])}...: {r.stderr[-800:]}")
    return r.stderr + r.stdout


def concat(parts: list[Path], out: Path, grain: int = 0) -> None:
    lst = out.parent / (out.stem + "_concat.txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    # static (non-temporal) grain: film texture without destroying compression efficiency
    vf = ["-vf", f"noise=alls={grain}:allf=u"] if grain else []
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         *vf, *video_encoder(), str(out)])
    lst.unlink(missing_ok=True)


def concat_copy(parts: list[Path], out: Path) -> None:
    """Join same-encoder slices without re-encoding (each slice starts on a keyframe)."""
    lst = out.parent / (out.stem + "_parts.txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(out)])
    lst.unlink(missing_ok=True)


def mux(video: Path, audio: Path, out: Path) -> None:
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(audio),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
         "-map_metadata", "-1", str(out)])


def ffprobe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-count_frames",
                        "-of", "json", str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise FFmpegError(r.stderr)
    return json.loads(r.stdout)


def black_segments(path: Path, min_dur: float = 0.1, pix_th: float = 0.06) -> list[tuple[float, float]]:
    txt = run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
               f"blackdetect=d={min_dur}:pix_th={pix_th}", "-an", "-f", "null", "-"])
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", txt)]


def loudness(path: Path) -> dict:
    """Integrated loudness (LUFS) and true peak via ebur128."""
    txt = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-filter_complex",
               "ebur128=peak=true", "-f", "null", "-"])
    tail = txt[txt.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", tail)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", tail)
    to_f = lambda m: float(m.group(1)) if m and m.group(1) != "-inf" else float("-inf")  # noqa: E731
    return {"integratedLUFS": to_f(i), "truePeakDBFS": to_f(tp)}


def extract_frame(video: Path, t: float, out: Path) -> None:
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", str(out)])
