# SPDX-License-Identifier: Apache-2.0
"""Remote side of render.remote: `python -m motionbrief.render.remote_worker <jobdir>`.

<jobdir>/ir.json + job.json in; <jobdir>/out/<sceneId>.mp4 (+ sampled PNGs) out; last stdout line = JSON result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from motionbrief.ir.models import load
from motionbrief.render.backend import BACKENDS, RenderPlan


def main(jobdir: str) -> int:
    d = Path(jobdir)
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    ir = load(d / "ir.json")
    scene = ir.scene(job["sceneId"])
    plan = RenderPlan(scene.id, choices=job["choices"])
    cues = [tuple(c) for c in job["subtitles"]]
    res = BACKENDS["svg"].render_frames(ir, scene, d / "out", plan=plan, subtitles=cues,
                                        png_every=job["pngEvery"], max_frames=job["maxFrames"],
                                        segment=tuple(job["segment"]) if job.get("segment") else None)
    print(json.dumps({**{k: res[k] for k in ("frames", "expectedFrames", "pngs")}, "video": Path(res["video"]).name,
                      "gpu": res.get("gpu")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
