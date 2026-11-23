# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MOTIONBRIEF_ROOT", Path(__file__).resolve().parent.parent))
from motionbrief import hostenv  # noqa: E402

hostenv.load(REPO_ROOT)
WORK_DIR = Path(os.environ.get("MOTIONBRIEF_WORK", REPO_ROOT / "work"))


@lru_cache(maxsize=1)
def load_tokens() -> dict:
    return json.loads((REPO_ROOT / "motion" / "tokens.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_registry() -> dict:
    """motion/registry.json + component packs: every `render/svg_canvas/*.catalog.json` sidecar registers its
    components (Layer A, svg) and their LLM catalog entries, so a pack is self-contained."""
    reg = json.loads((REPO_ROOT / "motion" / "registry.json").read_text(encoding="utf-8"))
    for side in sorted((REPO_ROOT / "motionbrief" / "render" / "svg_canvas").glob("*.catalog.json")):
        for name, entry in json.loads(side.read_text(encoding="utf-8")).items():
            reg["components"].setdefault(name, {"status": "implemented", "layer": "A", "renderers": ["svg"],
                                                "fallback2D": name, "pack": side.name.split(".")[0]})
            reg["components"][name].setdefault("llm", entry)
    return reg


@lru_cache(maxsize=None)
def source_hash(*subpackages: str) -> str:
    """Hash of engine source files (whole package, or selected subpackages).
    Used in idempotency/checkpoint keys so behaviour changes invalidate caches."""
    import hashlib

    pkg = Path(__file__).resolve().parent
    roots = [pkg / s for s in subpackages] if subpackages else [pkg]
    h = hashlib.sha256()
    for r in roots:
        for p in ([r] if r.is_file() else sorted(r.rglob("*.py"))):
            h.update(str(p.relative_to(pkg)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]
