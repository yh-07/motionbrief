# SPDX-License-Identifier: Apache-2.0
"""Local-agent executor: runs ONE validated task manifest, deterministically.

Guarantees: schema-validated input, idempotency (key + artifacts exist -> skip),
checkpoint/resume (scene-level hash stamps), bounded retries, explicit degradation,
classified failures, schema-validated result.json. It never makes creative decisions.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from pathlib import Path
from typing import Any

import jsonschema

from motionbrief.agent.actions import ACTIONS
from motionbrief.agent.taxonomy import InvalidTask, Status, classify
from motionbrief.paths import REPO_ROOT

TASK_SCHEMA = json.loads((REPO_ROOT / "schemas" / "task.schema.json").read_text())
RESULT_SCHEMA = json.loads((REPO_ROOT / "schemas" / "result.schema.json").read_text())


def _out_dir(task: dict) -> Path:
    p = Path(task["outDir"])
    return p if p.is_absolute() else REPO_ROOT / p


def _logger(task: dict) -> tuple[logging.Logger, Path]:
    logs = _out_dir(task) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"{task['taskId']}.log"
    lg = logging.getLogger(f"mb.task.{task['taskId']}")
    lg.handlers.clear()
    lg.setLevel(logging.INFO)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    lg.addHandler(fh)
    lg.propagate = False
    return lg, path


def _result_path(task: dict) -> Path:
    return _out_dir(task) / "logs" / "tasks" / f"{task['idempotencyKey']}.result.json"


def _finish(task: dict, res: dict) -> dict:
    jsonschema.validate(res, RESULT_SCHEMA)
    rp = _result_path(task)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def execute(task: dict[str, Any] | str | Path) -> dict:
    if not isinstance(task, dict):
        task = json.loads(Path(task).read_text(encoding="utf-8"))
    try:
        jsonschema.validate(task, TASK_SCHEMA)
        if task["type"] == "render_scene" and not task.get("sceneId"):
            raise InvalidTask("render_scene requires sceneId")
    except (jsonschema.ValidationError, InvalidTask) as e:
        msg = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
        return {"taskId": str(task.get("taskId", "?")), "status": Status.ESCALATE.value, "artifacts": [],
                "metrics": {}, "logsRef": "", "error": {"kind": "InvalidTask", "message": msg, "attempts": 0}}

    # idempotency: same key + all artifacts present -> skip
    rp = _result_path(task)
    if rp.exists():
        prev = json.loads(rp.read_text(encoding="utf-8"))
        if prev["status"] in ("ok", "degraded") and all(Path(a).exists() for a in prev["artifacts"]):
            prev["skipped"] = True
            return prev

    lg, log_path = _logger(task)
    retries = int(task.get("retries", 2))
    attempt, degradations = 0, []
    t0 = time.time()
    while True:
        attempt += 1
        try:
            lg.info("attempt %d %s", attempt, json.dumps(task, ensure_ascii=False))
            artifacts, metrics, degr = ACTIONS[task["type"]](task)
            degradations += degr
            metrics["attempts"] = attempt
            metrics["wallSec"] = round(time.time() - t0, 2)
            status = Status.DEGRADED if degradations else Status.OK
            lg.info("done status=%s degradations=%s", status.value, degradations)
            return _finish(task, {"taskId": task["taskId"], "status": status.value, "artifacts": artifacts,
                                  "metrics": metrics, "logsRef": str(log_path), "error": None,
                                  "degradations": degradations})
        except Exception as e:  # classified below — never swallowed silently
            kind = classify(e)
            lg.error("attempt %d failed (%s): %s\n%s", attempt, kind.value, e, traceback.format_exc())
            if kind == Status.RETRYABLE and attempt <= retries:
                time.sleep(min(2 ** (attempt - 1), 8) * 0.25)
                continue
            if kind == Status.DEGRADED and task.get("degrade", True) and task.get("renderer") not in ("svg",):
                degradations.append({"from": task.get("renderer", "auto"), "to": "svg", "reason": str(e)})
                task = {**task, "renderer": "svg"}
                continue
            final = Status.FATAL if kind == Status.DEGRADED else kind
            return _finish(task, {"taskId": task["taskId"], "status": final.value, "artifacts": [],
                                  "metrics": {"attempts": attempt}, "logsRef": str(log_path),
                                  "error": {"kind": type(e).__name__, "message": str(e)[:4000],
                                            "attempts": attempt},
                                  "degradations": degradations})
