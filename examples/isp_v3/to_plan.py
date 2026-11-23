# SPDX-License-Identifier: Apache-2.0
"""Convert the hand-authored v3 shot table (build_full.SHOTS) into the generic shot-plan JSON."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_full as bf  # noqa: E402

GUIDES = {"GUIDE_DROP": {"keys": [[0.0, 540, 160, 1.0], [0.3, 540, 1000, 1.5], [1.0, 540, 980, 1.5]],
                         "moods": [[0.0, "happy"], [0.55, "worried"]]},
          "GUIDE_CORNER": {"keys": [[0.0, 260, 1500, 0.9], [1.0, 280, 1480, 0.9]], "moods": [[0.0, "surprised"]],
                           "look": [1, -1]}}
SPANS = {("s43", "perStage"): (0.09, 0.0), ("s47", "perStage"): (0.15, 0.0), ("s47", "runDelay"): (0.33, -0.5)}


def plan() -> dict:
    shots = []
    for sid, role, narr, cites, trans, texts, objs, cues, kw in bf.SHOTS:
        obs = []
        for id_, comp, depth, renderer, props in objs:
            if props == "CHIP":
                props = {"label": ""}
            elif isinstance(props, str):
                props = GUIDES[props]
            else:
                props = {k: ({"spanFrac": SPANS[(sid, k)][0], "offset": SPANS[(sid, k)][1]} if callable(v) else v)
                         for k, v in props.items()}
            obs.append({"id": id_, "component": comp, "depth": depth, "renderer": renderer, "props": props})
        beats = {k: kw[k] for k in ("ent", "rev", "imp", "exit", "text_at") if k in kw}
        sh = {"id": sid, "role": role, "narration": narr, "citations": cites, "transition": trans,
              "texts": [{"text": a, "style": b, "anchor": c} for a, b, c in texts], "objects": obs, "beats": beats,
              "cues": cues.split()}
        for k in ("cam", "hero", "target"):
            if k in kw:
                sh["camera" if k == "cam" else k] = list(kw[k]) if k == "cam" else kw[k]
        if sid in bf.PRE_PAUSE:
            sh["prePause"] = bf.PRE_PAUSE[sid]
        shots.append(sh)
    return {"video": {"id": "isp_v3_full", "title": "你手机的四个摄像头，没有一个会拍照：讲清 ISP"}, "shots": shots}


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "plan_full.json"
    out.write_text(json.dumps(plan(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", out)
