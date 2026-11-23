# SPDX-License-Identifier: Apache-2.0
"""Gate orchestration: G1 (deterministic) -> G2 (multimodal, cross-family) -> G3 (human)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from motionbrief.quality.deterministic import GateReport, run_g1


STAGES = ("script_lock", "animatic_lock", "final")


def g3_checklist(bundle: Path) -> GateReport:
    """G3 is a HUMAN gate with staged sign-offs (studio practice, REVIEW R-22):
    script_lock (facts + script) -> animatic_lock (boards/timing) -> final (cut, cover, AI label).
    We only verify signed records exist; we never auto-approve."""
    rep = GateReport("G3", "human")
    f = bundle / "approval.json"
    if not f.exists():
        rep.add("human_approval", [f"missing {f.name}: sign {', '.join(STAGES)} in order"])
        return rep
    data = json.loads(f.read_text(encoding="utf-8"))
    probs = []
    for st in STAGES:
        rec = data.get(st) or {}
        if not rec.get("reviewer") or not rec.get("approvedAt"):
            probs.append(f"{st}: reviewer/approvedAt missing")
    fin = data.get("final") or {}
    for k in ("aiContentLabel", "factsChecked"):
        if not fin.get(k):
            probs.append(f"final.{k} must be true")
    rep.add("human_approval", probs)
    return rep


def run_all(ir_path: Path, bundle: Path, author_family: Optional[str] = None,
            scene_ids: Optional[list[str]] = None) -> list[GateReport]:
    reps = run_g1(ir_path, bundle, scene_ids)
    if not all(r.passed for r in reps):
        return reps  # fail fast: never spend model calls on a G1 failure
    if author_family:
        from motionbrief.ir.models import load
        from motionbrief.quality.multimodal_review import review, review_transitions
        reps.append(review(load(ir_path), bundle, author_family, scene_ids=scene_ids))
        if not scene_ids:  # cuts are judged on strips from the final encode
            reps.append(review_transitions(load(ir_path), bundle, author_family))
    if not scene_ids:
        reps.append(g3_checklist(bundle))
    return reps
