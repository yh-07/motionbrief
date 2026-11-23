# SPDX-License-Identifier: Apache-2.0
"""Research & fact grounding -> stores/fact_db (append-only JSONL). Phase 1: storage + contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from motionbrief.paths import REPO_ROOT

FACT_DB = REPO_ROOT / "stores" / "fact_db" / "facts.jsonl"


def record_fact(claim: str, sources: list[str], topic: str, db: Path = FACT_DB) -> str:
    if not sources or not all(s.startswith("https://") for s in sources):
        raise ValueError("every fact needs >=1 public https source")
    fid = hashlib.sha256(claim.encode()).hexdigest()[:12]
    db.parent.mkdir(parents=True, exist_ok=True)
    with db.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": fid, "topic": topic, "claim": claim, "sources": sources}, ensure_ascii=False) + "\n")
    return fid
